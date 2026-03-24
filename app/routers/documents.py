import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse

from app.config import settings
from app.database import get_session
from app.models.document import Document
from app.models.registry import DependencyEntry, GapEntry
from app.schemas.export import ExportRequest, ExportResponse
from app.schemas.extraction import DocumentPatchRequest, DocumentResponse, feature_to_response
from app.schemas.registry import GapResponse, RegistryResponse
from app.services.export import export_document_context
from app.services.extraction import run_extraction_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    contents = await file.read()

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
        session=session,
    )
    return result


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Document)
        .options(selectinload(Document.features))
        .order_by(Document.uploaded_at.desc())
    )
    result = await session.execute(stmt)
    documents = result.scalars().all()

    return [
        DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,
            pdf_size_bytes=doc.pdf_size_bytes,
            feature_count=doc.feature_count,
            features=[feature_to_response(f) for f in doc.features],
            uploaded_at=doc.uploaded_at,
            error_message=doc.error_message,
        )
        for doc in documents
    ]


@router.get("/{document_id}/progress")
async def stream_extraction_progress(
    document_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Stream document + feature status updates via SSE until terminal state."""

    async def event_generator():
        while True:
            stmt = (
                select(Document)
                .where(Document.id == document_id)
                .options(selectinload(Document.features))
            )
            result = await session.execute(stmt)
            doc = result.scalar_one_or_none()

            if doc is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'not found'})}\n\n"
                return

            payload = {
                "type": "progress",
                "status": doc.status,
                "feature_count": doc.feature_count,
                "features": [
                    {"id": f.id, "name": f.name, "type": f.type, "status": f.status}
                    for f in doc.features
                ],
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if doc.status in ("done", "error", "partial"):
                yield f"data: {json.dumps({'type': 'done', 'status': doc.status})}\n\n"
                return

            await session.expire_all()
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/{document_id}/registry", response_model=RegistryResponse)
async def get_document_registry(
    document_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return dependency entries grouped by registry type."""
    stmt = select(DependencyEntry).where(DependencyEntry.document_id == document_id)
    result = await session.execute(stmt)
    entries = result.scalars().all()

    grouped: dict[str, list[dict]] = {"db": [], "external_api": [], "cache": []}
    for entry in entries:
        data = json.loads(entry.data_json)
        if entry.registry_type in grouped:
            grouped[entry.registry_type].append(data)

    return RegistryResponse(**grouped)


@router.get("/{document_id}/gaps", response_model=list[GapResponse])
async def get_document_gaps(
    document_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Return gap entries as structured list."""
    stmt = select(GapEntry).where(GapEntry.document_id == document_id)
    result = await session.execute(stmt)
    entries = result.scalars().all()

    return [
        GapResponse(
            id=g.id,
            category=g.category,
            name=g.name,
            affected_features=json.loads(g.affected_features),
            what_missing=g.what_missing,
            priority=g.priority,
            suggestion=json.loads(g.suggestion_json) if g.suggestion_json else None,
        )
        for g in entries
    ]


@router.patch("/{document_id}", response_model=DocumentResponse)
async def patch_document(
    document_id: int,
    patch: DocumentPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update document fields (currently: filename/project name)."""
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.features))
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    doc.filename = patch.filename
    await session.commit()
    await session.refresh(doc)

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        pdf_size_bytes=doc.pdf_size_bytes,
        feature_count=doc.feature_count,
        features=[feature_to_response(f) for f in doc.features],
        uploaded_at=doc.uploaded_at,
        error_message=doc.error_message,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.features))
    )
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        pdf_size_bytes=doc.pdf_size_bytes,
        feature_count=doc.feature_count,
        features=[feature_to_response(f) for f in doc.features],
        uploaded_at=doc.uploaded_at,
        error_message=doc.error_message,
    )


@router.post("/{document_id}/export", response_model=ExportResponse)
async def export_document(
    document_id: int,
    request: ExportRequest,
    session: AsyncSession = Depends(get_session),
):
    """Export .context/ for a document (all features or one) to filesystem."""
    # Verify document exists
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if doc.status not in ("done", "partial"):
        raise HTTPException(
            status_code=400,
            detail=f"Document status is '{doc.status}', extraction must complete first",
        )

    # Validate target path
    target = Path(request.target_path)
    if not target.is_absolute():
        raise HTTPException(status_code=400, detail="target_path must be an absolute path")
    if not target.parent.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Parent directory does not exist: {target.parent}",
        )

    response = await export_document_context(
        document_id=document_id,
        target_path=request.target_path,
        feature_name=request.feature_name,
        session=session,
    )
    return response
