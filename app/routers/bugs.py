import logging

from fastapi import APIRouter, HTTPException, Path

from app.schemas.bugs import BugGenerateRequest, BugPatchRequest
from app.services.bugs import generate_bug_report
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/bugs",
    tags=["bugs"],
)


@router.post("/generate")
async def generate_bug(
    project_slug: str,
    feature_name: str,
    body: BugGenerateRequest,
):
    """Generate a bug report from a test case using Claude. Synchronous (fast, single call)."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

    try:
        bug = await generate_bug_report(
            project_slug=project_slug,
            feature_name=feature_name,
            tc_index=body.tc_index,
            analyst_text=body.analyst_text,
            store=store,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    bugs = await store.get_bugs(project_slug, feature_name)
    bugs.append(bug)
    await store.save_bugs(project_slug, feature_name, bugs)

    logger.info("generate_bug: project=%s, feature=%s, tc_index=%d", project_slug, feature_name, body.tc_index)
    return {"bugs": bugs}


@router.get("/")
async def list_bugs(
    project_slug: str,
    feature_name: str,
):
    """Return current bugs list for a feature."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    bugs = await store.get_bugs(project_slug, feature_name)
    return {"bugs": bugs, "bug_count": len(bugs)}


@router.patch("/{bug_index}")
async def patch_bug(
    project_slug: str,
    feature_name: str,
    bug_index: int = Path(..., description="Zero-based index of bug in the list"),
    body: BugPatchRequest = None,
):
    """Update status and analyst_text for a specific bug."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    bugs = await store.get_bugs(project_slug, feature_name)
    if bug_index < 0 or bug_index >= len(bugs):
        raise HTTPException(
            status_code=404,
            detail=f"Bug index {bug_index} out of range (total: {len(bugs)})",
        )

    logger.info("patch_bug: project=%s, feature=%s, index=%d, status=%s", project_slug, feature_name, bug_index, body.status)
    bugs[bug_index]["status"] = body.status
    bugs[bug_index]["analyst_text"] = body.analyst_text

    await store.save_bugs(project_slug, feature_name, bugs)
    return {"bugs": bugs}


@router.delete("/{bug_index}")
async def delete_bug(
    project_slug: str,
    feature_name: str,
    bug_index: int = Path(..., description="Zero-based index of bug to delete"),
):
    """Delete a bug from the list."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )

    bugs = await store.get_bugs(project_slug, feature_name)
    if bug_index < 0 or bug_index >= len(bugs):
        raise HTTPException(
            status_code=404,
            detail=f"Bug index {bug_index} out of range (total: {len(bugs)})",
        )

    bug = bugs[bug_index]
    tc_index = bug.get("tc_index")

    logger.info("delete_bug: project=%s, feature=%s, index=%d", project_slug, feature_name, bug_index)
    bugs.pop(bug_index)
    await store.save_bugs(project_slug, feature_name, bugs)

    # Reset linked test case back to pending
    if tc_index is not None:
        test_cases = await store.get_test_cases(project_slug, feature_name)
        if 0 <= tc_index < len(test_cases):
            test_cases[tc_index]["status"] = "pending"
            test_cases[tc_index]["analyst_text"] = None
            await store.save_test_cases(project_slug, feature_name, test_cases)

    return {"bugs": bugs}
