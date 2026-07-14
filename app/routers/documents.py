import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.routers.projects import _feature_to_response, store
from app.schemas.extraction import (
    ConfluenceImportRequest,
    DocumentResponse,
)
from app.services.confluence import ConfluenceError, fetch_page
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
    doc_slug = store.make_doc_slug(project_slug, filename)
    now_iso = datetime.now(UTC).isoformat()
    doc_data = {
        "slug": doc_slug,
        "project_slug": project_slug,
        "filename": filename,
        "source_type": "confluence",
        "confluence_page_id": page["id"],
        "confluence_url": request.url,
        "confluence_version": page["version"],
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

    async def _import_chain():
        await run_extraction_pipeline(
            filename=filename,
            text_content=page["markdown"],
            store=store,
            project_slug=project_slug,
            doc_slug=doc_slug,
            tables=page["tables"],
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
