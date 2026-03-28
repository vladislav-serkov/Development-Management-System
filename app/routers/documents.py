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
from app.schemas.extraction import DocumentPatchRequest, DocumentResponse, FeaturePatchRequest, feature_to_response
from app.schemas.registry import DependencyEntryPatchRequest, GapEntryPatchRequest, GapResponse, RegistryResponse
from app.services.export import export_document_context
from app.services.extraction import run_extraction_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    # Verify project exists
    from app.models.document import Project
    proj = await session.get(Project, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

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
        project_id=project_id,
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
            project_id=doc.project_id,
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

    grouped: dict[str, list] = {"db": [], "external_api": [], "cache": []}
    for entry in entries:
        data = json.loads(entry.data_json)
        if entry.registry_type in grouped:
            grouped[entry.registry_type].append({"id": entry.id, "name": entry.name, "data": data})

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


@router.patch("/{document_id}/features/{feature_id}", response_model=None)
async def patch_feature(
    document_id: int,
    feature_id: int,
    patch: FeaturePatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update editable fields of a feature."""
    from app.models.document import Feature
    stmt = select(Feature).where(Feature.id == feature_id, Feature.document_id == document_id)
    result = await session.execute(stmt)
    feature = result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found in document {document_id}")
    if patch.overview_md is not None:
        feature.overview_md = patch.overview_md
    if patch.business_logic is not None:
        feature.business_logic = json.dumps(patch.business_logic)
    if patch.structured_logic_json is not None:
        feature.structured_logic_json = json.dumps(patch.structured_logic_json)
    await session.commit()
    await session.refresh(feature)
    return feature_to_response(feature)


@router.patch("/{document_id}/registry/entries/{entry_id}")
async def patch_dependency_entry(
    document_id: int,
    entry_id: int,
    patch: DependencyEntryPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Replace the data blob of a dependency registry entry."""
    entry = await session.get(DependencyEntry, entry_id)
    if entry is None or entry.document_id != document_id:
        raise HTTPException(status_code=404, detail=f"Registry entry {entry_id} not found in document {document_id}")
    entry.data_json = json.dumps(patch.data)
    await session.commit()
    return {"ok": True}


@router.patch("/{document_id}/gaps/{entry_id}")
async def patch_gap_entry(
    document_id: int,
    entry_id: int,
    patch: GapEntryPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update editable fields of a gap entry."""
    entry = await session.get(GapEntry, entry_id)
    if entry is None or entry.document_id != document_id:
        raise HTTPException(status_code=404, detail=f"Gap entry {entry_id} not found in document {document_id}")
    if patch.what_missing is not None:
        entry.what_missing = patch.what_missing
    if patch.priority is not None:
        entry.priority = patch.priority
    if patch.affected_features is not None:
        entry.affected_features = json.dumps(patch.affected_features)
    if patch.suggestion is not None:
        entry.suggestion_json = json.dumps(patch.suggestion)
    await session.commit()
    await session.refresh(entry)
    return GapResponse(
        id=entry.id,
        category=entry.category,
        name=entry.name,
        affected_features=json.loads(entry.affected_features),
        what_missing=entry.what_missing,
        priority=entry.priority,
        suggestion=json.loads(entry.suggestion_json) if entry.suggestion_json else None,
    )


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
        project_id=doc.project_id,
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
        project_id=doc.project_id,
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
