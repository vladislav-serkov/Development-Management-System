import logging

from fastapi import APIRouter, HTTPException, Path

from app.config import settings
from app.schemas.bugs import BugExportRequest, BugGenerateRequest, BugPatchRequest
from app.services import bug_fixer, jira
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
    feature_name = feature["name"]

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
    feature_name = feature["name"]
    bugs = await store.get_bugs(project_slug, feature_name)
    return {"bugs": bugs, "bug_count": len(bugs), "jira_configured": jira.is_configured()}


async def _source_doc_info(project_slug: str, feature: dict) -> tuple[str | None, str | None]:
    """(confluence_url, service_name) of the feature's source spec document."""
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return None, None
    doc = await store.get_document(project_slug, doc_slug) or {}
    return doc.get("confluence_url"), doc.get("service_name")


@router.post("/{bug_index}/export-jira")
async def export_bug_to_jira(
    project_slug: str,
    feature_name: str,
    bug_index: int = Path(..., description="Zero-based index of bug to export"),
    body: BugExportRequest | None = None,
):
    """Create a Jira issue from a stored bug and remember its key/url on the bug."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]

    if not jira.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Jira не настроена — задайте JIRA_BASE_URL и JIRA_PAT в .env",
        )

    bugs = await store.get_bugs(project_slug, feature_name)
    if bug_index < 0 or bug_index >= len(bugs):
        raise HTTPException(
            status_code=404,
            detail=f"Bug index {bug_index} out of range (total: {len(bugs)})",
        )
    bug = bugs[bug_index]
    if bug.get("jira_key"):
        raise HTTPException(
            status_code=409,
            detail=f"Баг уже создан в Jira: {bug['jira_key']}",
        )

    spec_url, service_name = await _source_doc_info(project_slug, feature)
    feature_ticket = body.feature_ticket if body else None
    try:
        issue = await jira.create_bug_issue(bug, feature, spec_url, service_name, feature_ticket)
    except jira.JiraError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    bug["jira_key"] = issue["key"]
    bug["jira_url"] = issue["url"]
    bug["jira_status"] = None
    await store.save_bugs(project_slug, feature_name, bugs)

    logger.info("export_bug_to_jira: project=%s, feature=%s, index=%d, key=%s",
                project_slug, feature_name, bug_index, issue["key"])

    # An exported bug is a confirmed bug — hand it to the fixer right away
    if settings.bug_fixer_auto and bug_fixer.is_configured():
        try:
            await bug_fixer.request_fix(store, project_slug, feature_name, bug_index)
        except bug_fixer.BugFixerError as exc:
            logger.warning("export_bug_to_jira: auto-fix not queued: %s", exc)
            bugs[bug_index]["fix_status"] = "failed"
            bugs[bug_index]["fix_error"] = str(exc)
            await store.save_bugs(project_slug, feature_name, bugs)

    return {"bugs": await store.get_bugs(project_slug, feature_name)}


@router.post("/{bug_index}/fix")
async def fix_bug(
    project_slug: str,
    feature_name: str,
    bug_index: int = Path(..., description="Zero-based index of bug to fix"),
):
    """Queue a headless Claude Code run that fixes the bug in the service repo."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]

    try:
        await bug_fixer.request_fix(store, project_slug, feature_name, bug_index)
    except bug_fixer.BugFixerError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info("fix_bug: project=%s, feature=%s, index=%d", project_slug, feature_name, bug_index)
    return {"bugs": await store.get_bugs(project_slug, feature_name)}


@router.post("/sync-jira")
async def sync_jira_statuses(
    project_slug: str,
    feature_name: str,
):
    """Refresh jira_status from Jira for every exported bug of the feature."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    feature_name = feature["name"]

    bugs = await store.get_bugs(project_slug, feature_name)
    keys = [b["jira_key"] for b in bugs if b.get("jira_key")]
    if not jira.is_configured() or not keys:
        return {"bugs": bugs, "synced": False}

    try:
        statuses = await jira.fetch_issue_statuses(keys)
    except jira.JiraError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    changed = False
    for bug in bugs:
        key = bug.get("jira_key")
        if key and bug.get("jira_status") != statuses.get(key):
            bug["jira_status"] = statuses.get(key)
            changed = True
    if changed:
        await store.save_bugs(project_slug, feature_name, bugs)
    return {"bugs": bugs, "synced": True}


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
    feature_name = feature["name"]

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
    feature_name = feature["name"]

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
