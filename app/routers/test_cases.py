import logging

from fastapi import APIRouter, HTTPException, Path

from app.schemas.test_cases import TestCaseAskRequest, TestCaseReviewRequest
from app.services.task_manager import task_manager
from app.services.test_cases import (
    _check_enrichment_gate,
    run_test_case_ask_pipeline,
    run_test_cases_pipeline,
)
from app.storage import ActiveTaskExistsError, ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/test-cases",
    tags=["test-cases"],
)


async def _create_test_cases_task(project_slug: str, feature_name: str) -> tuple[str, dict | None]:
    """Shared preamble for /run and /ask: validate the feature, recover stuck
    tasks and create a 'test_cases' task (one per feature, shared by both
    endpoints so full runs and asks never write the list concurrently).

    Returns (canonical_feature_name, task) — task is None if one is already running.
    """
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
    feature_name = feature["name"]
    if feature.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail="Feature extraction is not done — cannot generate test cases",
        )

    task_key = f"test_cases:{project_slug}/{feature_name}"
    active = await store.get_active_task(
        project_slug, kind="test_cases", target_id=feature_name,
    )
    if active is not None:
        if task_manager.is_running(task_key):
            return feature_name, None
        logger.warning(
            "test_cases: stuck task %s for %s/%s, recovering",
            active["id"], project_slug, feature_name,
        )
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )

    # Pre-validate enrichment gate
    try:
        await _check_enrichment_gate(feature, project_slug, store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        task = await store.create_task(
            project_slug, kind="test_cases", target_type="feature", target_id=feature_name,
        )
    except ActiveTaskExistsError:
        return feature_name, None
    return feature_name, task


@router.post("/run")
async def run_test_cases(
    project_slug: str,
    feature_name: str,
):
    """Launch test cases generation in background. Poll GET / for status."""
    feature_name, task = await _create_test_cases_task(project_slug, feature_name)
    if task is None:
        return {"status": "already_running"}
    logger.info("run_test_cases: project=%s, feature=%s, task=%s", project_slug, feature_name, task["id"])
    task_manager.launch(
        f"test_cases:{project_slug}/{feature_name}",
        run_test_cases_pipeline(project_slug, feature_name, store, task_id=task["id"]),
    )

    return {"status": "started"}


@router.post("/ask")
async def ask_test_case(
    project_slug: str,
    feature_name: str,
    body: TestCaseAskRequest,
):
    """Launch on-demand generation for a specific spec item. Poll GET / for status;
    the outcome summary lands in last_ask_message."""
    feature_name, task = await _create_test_cases_task(project_slug, feature_name)
    if task is None:
        return {"status": "already_running"}
    logger.info(
        "ask_test_case: project=%s, feature=%s, task=%s, request=%r",
        project_slug, feature_name, task["id"], body.request[:200],
    )
    task_manager.launch(
        f"test_cases:{project_slug}/{feature_name}",
        run_test_case_ask_pipeline(project_slug, feature_name, body.request, store, task_id=task["id"]),
    )

    return {"status": "started"}


@router.get("/")
async def list_test_cases(
    project_slug: str,
    feature_name: str,
):
    """Return current test cases list for a feature."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]
    test_cases = await store.get_test_cases(project_slug, feature_name)
    active = await store.get_active_task(
        project_slug, kind="test_cases", target_id=feature_name,
    )
    # Latest finished ask outcome (full runs leave result_message empty)
    tasks = await store.list_tasks(project_slug, kind="test_cases", target_id=feature_name)
    last_ask = next(
        (t for t in tasks if t["status"] != "running" and t.get("result_message")),
        None,
    )
    return {
        "test_cases": test_cases,
        "test_cases_running": active is not None,
        "test_cases_run_at": feature.get("test_cases_run_at"),
        "last_ask_message": last_ask["result_message"] if last_ask else None,
        "last_ask_at": last_ask["finished_at"] if last_ask else None,
        "last_ask_covered_by": (last_ask.get("result_data") or {}).get("covered_by", []) if last_ask else [],
    }


@router.patch("/{tc_index}")
async def review_test_case(
    project_slug: str,
    feature_name: str,
    tc_index: int = Path(..., description="Zero-based index of test case in the list"),
    body: TestCaseReviewRequest = None,
):
    """Update status and analyst_text for a specific test case."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]

    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index < 0 or tc_index >= len(test_cases):
        raise HTTPException(
            status_code=404,
            detail=f"Test case index {tc_index} out of range (total: {len(test_cases)})",
        )

    logger.info("review_test_case: project=%s, feature=%s, index=%d, status=%s", project_slug, feature_name, tc_index, body.status)
    test_cases[tc_index]["status"] = body.status
    test_cases[tc_index]["analyst_text"] = body.analyst_text

    await store.save_test_cases(project_slug, feature_name, test_cases)

    return {"test_cases": test_cases}


@router.delete("/{tc_index}")
async def delete_test_case(
    project_slug: str,
    feature_name: str,
    tc_index: int = Path(..., description="Zero-based index of test case to delete"),
):
    """Delete a test case from the list."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]

    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index < 0 or tc_index >= len(test_cases):
        raise HTTPException(
            status_code=404,
            detail=f"Test case index {tc_index} out of range (total: {len(test_cases)})",
        )

    logger.info("delete_test_case: project=%s, feature=%s, index=%d", project_slug, feature_name, tc_index)
    test_cases.pop(tc_index)
    await store.save_test_cases(project_slug, feature_name, test_cases)

    return {"test_cases": test_cases}
