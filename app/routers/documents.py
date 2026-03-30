import asyncio
import json
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

from app.config import settings
from app.routers.projects import _feature_to_response, store
from app.schemas.export import ExportRequest, ExportResponse
from app.schemas.extraction import DocumentPatchRequest, DocumentResponse, FeaturePatchRequest, FeatureResponse
from app.services.export import export_document_context
from app.services.extraction import run_extraction_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_to_response(doc: dict, features: list[dict]) -> DocumentResponse:
    from datetime import datetime
    uploaded_at = doc.get("uploaded_at")
    if isinstance(uploaded_at, str):
        uploaded_at = datetime.fromisoformat(uploaded_at)
    return DocumentResponse(
        slug=doc["slug"],
        project_slug=doc.get("project_slug", ""),
        filename=doc["filename"],
        status=doc.get("status", "pending"),
        pdf_size_bytes=doc.get("pdf_size_bytes", 0),
        feature_count=doc.get("feature_count", 0),
        features=[_feature_to_response(f) for f in features],
        uploaded_at=uploaded_at,
        error_message=doc.get("error_message"),
    )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    project_slug: str = Query(...),
    file: UploadFile = File(...),
):
    # Verify project exists
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    contents = await file.read()

    logger.info("upload_document: project=%s, file=%s, size=%.1fKB", project_slug, file.filename, len(contents) / 1024)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    if not contents[:5] == b"%PDF-":
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid PDF (missing %PDF- header)",
        )

    if len(contents) > settings.max_pdf_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds {settings.max_pdf_size_mb}MB limit",
        )

    result = await run_extraction_pipeline(
        filename=file.filename or "unnamed.pdf",
        pdf_bytes=contents,
        store=store,
        project_slug=project_slug,
    )
    return result


@router.get("/", response_model=list[DocumentResponse])
async def list_documents():
    """List all documents across all projects."""
    all_docs = []
    projects = await store.list_projects()
    for proj in projects:
        slug = proj["slug"]
        docs = await store.list_documents(slug)
        features = await store.list_features(slug)
        for doc in docs:
            all_docs.append(_doc_to_response(doc, features))
    return all_docs


@router.get("/{doc_slug}/progress")
async def stream_extraction_progress(
    doc_slug: str,
    project_slug: str = Query(...),
):
    """Stream document + feature status updates via SSE until terminal state."""

    async def event_generator():
        while True:
            doc = await store.get_document(project_slug, doc_slug)

            if doc is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'not found'})}\n\n"
                return

            features = await store.list_features(project_slug)
            payload = {
                "type": "progress",
                "status": doc.get("status"),
                "feature_count": doc.get("feature_count", 0),
                "features": [
                    {"name": f["name"], "type": f.get("type", ""), "status": f.get("status", "")}
                    for f in features
                ],
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if doc.get("status") in ("done", "error", "partial"):
                yield f"data: {json.dumps({'type': 'done', 'status': doc.get('status')})}\n\n"
                return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.patch("/{doc_slug}/features/{feature_name}", response_model=FeatureResponse)
async def patch_feature(
    doc_slug: str,
    feature_name: str,
    patch: FeaturePatchRequest,
    project_slug: str = Query(...),
):
    """Update editable fields of a feature."""
    logger.info("patch_feature: project=%s, feature=%s", project_slug, feature_name)
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found in project '{project_slug}'")

    updates = {}
    if patch.structured_logic_json is not None:
        updates["structured_logic_json"] = patch.structured_logic_json

    if updates:
        feature = await store.update_feature(project_slug, feature_name, updates)

    return _feature_to_response(feature)


@router.patch("/{doc_slug}", response_model=DocumentResponse)
async def patch_document(
    doc_slug: str,
    patch: DocumentPatchRequest,
    project_slug: str = Query(...),
):
    """Update document fields."""
    logger.info("patch_document: project=%s, doc=%s, new_filename=%s", project_slug, doc_slug, patch.filename)
    doc = await store.update_document(project_slug, doc_slug, {"filename": patch.filename})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_slug}' not found")
    features = await store.list_features(project_slug)
    return _doc_to_response(doc, features)


@router.get("/{doc_slug}", response_model=DocumentResponse)
async def get_document(
    doc_slug: str,
    project_slug: str = Query(...),
):
    doc = await store.get_document(project_slug, doc_slug)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_slug}' not found")
    features = await store.list_features(project_slug)
    return _doc_to_response(doc, features)


@router.post("/{doc_slug}/export", response_model=ExportResponse)
async def export_document(
    doc_slug: str,
    request: ExportRequest,
    project_slug: str = Query(...),
):
    """Export .context/ for a document's features to filesystem."""
    doc = await store.get_document(project_slug, doc_slug)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_slug}' not found")

    logger.info("export_document: project=%s, doc=%s, feature=%s, target=%s", project_slug, doc_slug, request.feature_name, request.target_path)

    from pathlib import Path
    if request.target_path and not Path(request.target_path).is_absolute():
        raise HTTPException(status_code=400, detail="target_path must be an absolute path")

    response = await export_document_context(
        project_slug=project_slug,
        doc_slug=doc_slug,
        feature_name=request.feature_name,
        store=store,
        target_path=request.target_path,
    )
    return response
