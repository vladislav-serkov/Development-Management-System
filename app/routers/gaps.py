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
    if feature.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail="Feature extraction is not done — cannot run gaps analysis",
        )

    task_key = f"gaps:{project_slug}/{feature_name}"
    active = await store.get_active_task(project_slug, kind="gaps", target_id=feature_name)
    if active is not None:
        if task_manager.is_running(task_key):
            raise HTTPException(status_code=409, detail="Gaps analysis is already running for this feature")
        logger.warning(
            "run_gaps: stuck task %s for %s/%s, recovering", active["id"], project_slug, feature_name
        )
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )

    task = await store.create_task(
        project_slug, kind="gaps", target_type="feature", target_id=feature_name,
    )
    task_manager.launch(
        task_key,
        run_gaps_pipeline(project_slug, feature_name, store, task_id=task["id"]),
    )

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
    active = await store.get_active_task(project_slug, kind="gaps", target_id=feature_name)
    return {
        "gaps": gaps,
        "gaps_running": active is not None,
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

    all_gaps = await store.get_gaps(project_slug, feature_name, include_archived=True)

    # Find the N-th active (non-archived) gap by index
    active_count = 0
    target_real_index = None
    for i, g in enumerate(all_gaps):
        if not g.get("archived"):
            if active_count == gap_index:
                target_real_index = i
                break
            active_count += 1

    if target_real_index is None:
        raise HTTPException(
            status_code=404,
            detail=f"Gap index {gap_index} out of range",
        )

    logger.info("delete_gap (archive): project=%s, feature=%s, index=%d", project_slug, feature_name, gap_index)
    all_gaps[target_real_index]["archived"] = True
    await store.save_gaps(project_slug, feature_name, all_gaps)

    return {"gaps": [g for g in all_gaps if not g.get("archived")]}


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
    if feature.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail="Feature extraction is not done — cannot apply gaps",
        )

    task_key = f"apply:{project_slug}/{feature_name}"
    active = await store.get_active_task(project_slug, kind="apply_gaps", target_id=feature_name)
    if active is not None:
        if task_manager.is_running(task_key):
            raise HTTPException(status_code=409, detail="Apply preview is already running")
        logger.warning(
            "apply_preview: stuck task %s for %s/%s, recovering",
            active["id"], project_slug, feature_name,
        )
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )

    task = await store.create_task(
        project_slug, kind="apply_gaps", target_type="feature", target_id=feature_name,
    )
    task_manager.launch(
        task_key,
        run_apply_preview_background(project_slug, feature_name, store, task_id=task["id"]),
    )
    return {"status": "running"}


@router.get("/apply-preview")
async def apply_preview_get(
    project_slug: str,
    feature_name: str,
):
    """Get apply preview result (poll while apply task is running)."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    active = await store.get_active_task(project_slug, kind="apply_gaps", target_id=feature_name)
    if active is not None:
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
