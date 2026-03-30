import asyncio
import logging

from fastapi import APIRouter, HTTPException, Path

from app.schemas.test_cases import TestCaseReviewRequest
from app.services.test_cases import run_test_cases_pipeline, _check_enrichment_gate
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

# Track background tasks keyed by "{project_slug}/{feature_name}" to detect stuck "running" states
_running_tasks: dict[str, asyncio.Task] = {}

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
    # Validate feature exists + enrichment gate before launching background task
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

    task_key = f"{project_slug}/{feature_name}"

    if feature.get("test_cases_status") == "running":
        # Check if there is actually a live task running — if not, the previous run crashed
        existing_task = _running_tasks.get(task_key)
        if existing_task is not None and not existing_task.done():
            return {"status": "already_running"}
        # No live task found — stuck state: reset to "error" and allow re-run
        logger.warning(
            "run_test_cases: stuck 'running' state detected for %s/%s, recovering",
            project_slug, feature_name,
        )
        await store.update_feature(project_slug, feature_name, {"test_cases_status": "error"})

    if feature.get("test_cases_status") == "done":
        raise HTTPException(
            status_code=409,
            detail="Test cases already generated for this feature",
        )

    # Pre-validate enrichment gate (raises ValueError if not ready)
    try:
        await _check_enrichment_gate(feature, project_slug, store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Mark running immediately
    await store.update_feature(project_slug, feature_name, {"test_cases_status": "running"})

    logger.info("run_test_cases: project=%s, feature=%s", project_slug, feature_name)

    # Launch in background and track the task reference
    task = asyncio.create_task(run_test_cases_pipeline(project_slug, feature_name, store))
    _running_tasks[task_key] = task

    def _on_task_done(t: asyncio.Task) -> None:
        _running_tasks.pop(task_key, None)
        if not t.cancelled() and t.exception() is not None:
            logger.error(
                "run_test_cases background task failed for %s/%s: %s",
                project_slug, feature_name, t.exception(),
            )

    task.add_done_callback(_on_task_done)

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
    return {
        "test_cases": test_cases,
        "test_cases_status": feature.get("test_cases_status"),
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
