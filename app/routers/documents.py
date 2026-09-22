import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.routers.projects import _feature_to_response, store
from app.schemas.extraction import (
    ConfluenceImportRequest,
    DocumentResponse,
)
import asyncio

from app.schemas.extraction import SpecUpdateCheck, SpecUpdatesResponse
from app.services.confluence import ConfluenceError, fetch_page, fetch_page_meta
from app.services.extraction import run_extraction_pipeline
from app.services.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_to_response(
    doc: dict,
    features: list[dict],
    *,
    active_tasks: list[dict] | None = None,
) -> DocumentResponse:
    uploaded_at = doc.get("uploaded_at")
    if isinstance(uploaded_at, str):
        uploaded_at = datetime.fromisoformat(uploaded_at)
    return DocumentResponse(
        slug=doc["slug"],
        project_slug=doc.get("project_slug", ""),
        filename=doc["filename"],
        status=doc.get("status", "pending"),
        source_type=doc.get("source_type", "confluence"),
        pdf_size_bytes=doc.get("pdf_size_bytes", 0),
        feature_count=doc.get("feature_count", 0),
        features=[_feature_to_response(f, active_tasks=active_tasks) for f in features],
        uploaded_at=uploaded_at,
        error_message=doc.get("error_message"),
        confluence_url=doc.get("confluence_url"),
        confluence_version=doc.get("confluence_version"),
        latest_confluence_version=doc.get("latest_confluence_version"),
        spec_checked_at=doc.get("spec_checked_at"),
        spec_outdated=bool(doc.get("spec_outdated")),
        last_diff=doc.get("last_diff"),
    )


@router.post("/import-confluence", response_model=DocumentResponse)
async def import_confluence_page(
    request: ConfluenceImportRequest,
    project_slug: str = Query(...),
):
    """Import a Confluence page as a document: fetch via PAT, convert to markdown, extract."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    try:
        page = await fetch_page(request.url)
    except ConfluenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info(
        "import_confluence: project=%s, page_id=%s, title='%s'",
        project_slug, page["id"], page["title"],
    )

    filename = page["title"]
    # Re-import of the same page must update the existing document, not spawn a copy
    existing = next(
        (d for d in await store.list_documents(project_slug)
         if str(d.get("confluence_page_id")) == str(page["id"])),
        None,
    )
    doc_slug = existing["slug"] if existing else await store.make_doc_slug(project_slug, filename)
    now_iso = datetime.now(UTC).isoformat()
    doc_data = {
        "slug": doc_slug,
        "project_slug": project_slug,
        "filename": filename,
        "source_type": "confluence",
        "confluence_page_id": page["id"],
        "confluence_url": request.url,
        "confluence_version": page["version"],
        "service_name": page.get("service_name"),
        "pdf_size_bytes": len(page["markdown"].encode("utf-8")),
        "uploaded_at": now_iso,
        "status": "processing",
        "error_message": None,
        "feature_count": 0,
    }
    await store.save_document(project_slug, doc_data)
    await store.save_document_source(
        project_slug,
        doc_slug,
        {
            "confluence_page_id": page["id"],
            "confluence_url": request.url,
            "confluence_version": page["version"],
            "title": page["title"],
            "space_key": page["space_key"],
            "fetched_at": now_iso,
            "markdown": page["markdown"],
            "links": page["links"],
            "tables": page["tables"],
        },
    )

    prev_version = existing.get("confluence_version") if existing else None

    async def _import_chain():
        await run_extraction_pipeline(
            filename=filename,
            text_content=page["markdown"],
            store=store,
            project_slug=project_slug,
            doc_slug=doc_slug,
            tables=page["tables"],
            prev_confluence_version=prev_version,
        )
        # Auto-enrich stub deps linked from the imported page (non-fatal)
        try:
            from app.services.auto_enrich import auto_enrich_from_links
            await auto_enrich_from_links(project_slug, page["links"], page["space_key"], store)
        except Exception as exc:
            logger.warning("Auto-enrich after import failed (non-fatal): %s", exc)

    task_key = f"extraction:{project_slug}/{doc_slug}"
    task_manager.launch(task_key, _import_chain())

    return _doc_to_response(doc_data, [], active_tasks=[])


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(project_slug: str = Query(...)):
    """List the project's documents (without per-document feature payloads)."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    docs = await store.list_documents(project_slug)
    return [_doc_to_response(d, []) for d in docs]


@router.post("/check-spec-updates", response_model=SpecUpdatesResponse)
async def check_spec_updates(project_slug: str = Query(...)):
    """Probe Confluence for new versions of every imported page.

    Lightweight (version numbers only, no page bodies); results are persisted on
    the documents so the outdated badge survives reloads.
    """
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    docs = [
        d for d in await store.list_documents(project_slug)
        if d.get("confluence_page_id")
    ]
    if not docs:
        return SpecUpdatesResponse(checked=0, outdated=0, documents=[])

    async def _check(doc: dict) -> SpecUpdateCheck:
        slug = doc["slug"]
        current = doc.get("confluence_version")
        try:
            meta = await fetch_page_meta(str(doc["confluence_page_id"]))
        except ConfluenceError as exc:
            return SpecUpdateCheck(
                slug=slug, filename=doc.get("filename", slug),
                confluence_url=doc.get("confluence_url"),
                current_version=current, latest_version=None,
                outdated=bool(doc.get("spec_outdated")), error=str(exc),
            )
        latest = meta["version"]
        outdated = bool(current) and latest > current
        await store.update_document(project_slug, slug, {
            "latest_confluence_version": latest,
            "spec_checked_at": datetime.now(UTC).isoformat(),
            "spec_outdated": outdated,
        })
        return SpecUpdateCheck(
            slug=slug, filename=doc.get("filename", slug),
            confluence_url=doc.get("confluence_url"),
            current_version=current, latest_version=latest,
            outdated=outdated, error=None,
        )

    results = await asyncio.gather(*(_check(d) for d in docs))
    return SpecUpdatesResponse(
        checked=len(results),
        outdated=sum(1 for r in results if r.outdated),
        documents=list(results),
    )
