import logging

from fastapi import APIRouter, HTTPException, Path

from app.schemas.gaps import ApplyConfirmRequest, GapReviewRequest
from app.services.gaps import confirm_apply, run_apply_preview_background, run_gaps_pipeline
from app.services.task_manager import task_manager
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/gaps",
    tags=["gaps"],
)


@router.post("/run")
async def run_gaps_analysis(
    project_slug: str,
    feature_name: str,
):
    """Run gaps analysis pipeline — returns merged gaps list."""
    logger.info("run_gaps_analysis: project=%s, feature=%s", project_slug, feature_name)
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    if feature.get("gaps_status") == "done":
        raise HTTPException(
            status_code=409,
            detail="Gaps analysis already completed for this feature",
        )
    task_key = f"gaps:{project_slug}/{feature_name}"
    if feature.get("gaps_status") == "running":
        if task_manager.is_running(task_key):
            raise HTTPException(status_code=409, detail="Gaps analysis is already running for this feature")
        # No live task — stuck state, recover
        logger.warning("run_gaps: stuck 'running' state detected for %s/%s, recovering", project_slug, feature_name)
        await store.update_feature(project_slug, feature_name, {"gaps_status": "error"})

    # Mark as running immediately and launch in background
    await store.update_feature(project_slug, feature_name, {"gaps_status": "running"})
    task_manager.launch(task_key, run_gaps_pipeline(project_slug, feature_name, store))

    return {"status": "running"}


@router.get("/")
async def list_gaps(
    project_slug: str,
    feature_name: str,
):
    """Return current gaps list for a feature."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    gaps = await store.get_gaps(project_slug, feature_name)
    return {
        "gaps": gaps,
        "gaps_status": feature.get("gaps_status"),
        "gaps_run_at": feature.get("gaps_run_at"),
    }


@router.patch("/{gap_index}")
async def review_gap(
    project_slug: str,
    feature_name: str,
    gap_index: int = Path(..., description="Zero-based index of gap in the gaps list"),
    body: GapReviewRequest = None,
):
    """Update status and analyst_text for a specific gap."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    gaps = await store.get_gaps(project_slug, feature_name)
    if gap_index < 0 or gap_index >= len(gaps):
        raise HTTPException(
            status_code=404,
            detail=f"Gap index {gap_index} out of range (total: {len(gaps)})",
        )

    logger.info("review_gap: project=%s, feature=%s, index=%d, status=%s", project_slug, feature_name, gap_index, body.status)
    gaps[gap_index]["status"] = body.status
    gaps[gap_index]["analyst_text"] = body.analyst_text

    await store.save_gaps(project_slug, feature_name, gaps)

    return {"gaps": gaps}


@router.delete("/{gap_index}")
async def delete_gap(
    project_slug: str,
    feature_name: str,
    gap_index: int = Path(..., description="Zero-based index of gap to delete"),
):
    """Delete a gap from the list."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    gaps = await store.get_gaps(project_slug, feature_name)
    if gap_index < 0 or gap_index >= len(gaps):
        raise HTTPException(
            status_code=404,
            detail=f"Gap index {gap_index} out of range (total: {len(gaps)})",
        )

    logger.info("delete_gap: project=%s, feature=%s, index=%d", project_slug, feature_name, gap_index)
    gaps.pop(gap_index)
    await store.save_gaps(project_slug, feature_name, gaps)

    return {"gaps": gaps}


@router.post("/apply-preview")
async def apply_preview_run(
    project_slug: str,
    feature_name: str,
):
    """Launch apply preview generation in background."""
    logger.info("apply_preview_run: project=%s, feature=%s", project_slug, feature_name)
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    task_key = f"apply:{project_slug}/{feature_name}"
    if feature.get("apply_status") == "running":
        if task_manager.is_running(task_key):
            raise HTTPException(status_code=409, detail="Apply preview is already running")
        logger.warning("apply_preview: stuck 'running' state detected for %s/%s, recovering", project_slug, feature_name)
        await store.update_feature(project_slug, feature_name, {"apply_status": "error"})

    await store.update_feature(project_slug, feature_name, {"apply_status": "running"})
    task_manager.launch(task_key, run_apply_preview_background(project_slug, feature_name, store))
    return {"status": "running"}


@router.get("/apply-preview")
async def apply_preview_get(
    project_slug: str,
    feature_name: str,
):
    """Get apply preview result (poll while apply_status is running)."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    apply_status = feature.get("apply_status")
    if apply_status == "running":
        return {"status": "running"}

    preview = await store.get_apply_preview(project_slug, feature_name)
    if preview is None:
        return {"status": None}

    return preview


@router.post("/apply-confirm")
async def apply_confirm(
    project_slug: str,
    feature_name: str,
    body: ApplyConfirmRequest,
):
    """Save proposed structured_logic and mark gaps as applied."""
    logger.info("apply_confirm: project=%s, feature=%s", project_slug, feature_name)
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    await confirm_apply(project_slug, feature_name, body.proposed, store)
    return {"status": "applied"}
