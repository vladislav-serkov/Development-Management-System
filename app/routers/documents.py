from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_session
from app.models.document import Document
from app.schemas.export import ExportRequest, ExportResponse
from app.schemas.extraction import DocumentResponse, feature_to_response
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
