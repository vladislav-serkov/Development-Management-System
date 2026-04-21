import logging

from fastapi import APIRouter, HTTPException, Path

from app.schemas.test_cases import TestCaseReviewRequest
from app.services.task_manager import task_manager
from app.services.test_cases import run_test_cases_pipeline, _check_enrichment_gate
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/test-cases",
    tags=["test-cases"],
)


@router.post("/run")
async def run_test_cases(
    project_slug: str,
    feature_name: str,
):
    """Launch test cases generation in background. Poll GET / for status."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
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
            return {"status": "already_running"}
        logger.warning(
            "run_test_cases: stuck task %s for %s/%s, recovering",
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

    task = await store.create_task(
        project_slug, kind="test_cases", target_type="feature", target_id=feature_name,
    )
    logger.info("run_test_cases: project=%s, feature=%s, task=%s", project_slug, feature_name, task["id"])
    task_manager.launch(
        task_key,
        run_test_cases_pipeline(project_slug, feature_name, store, task_id=task["id"]),
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
    test_cases = await store.get_test_cases(project_slug, feature_name)
    active = await store.get_active_task(
        project_slug, kind="test_cases", target_id=feature_name,
    )
    return {
        "test_cases": test_cases,
        "test_cases_running": active is not None,
        "test_cases_run_at": feature.get("test_cases_run_at"),
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
