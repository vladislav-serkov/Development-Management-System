import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.document import Document, Feature, Project
from app.models.registry import DependencyEntry, GapEntry
from app.schemas.extraction import FeatureResponse, ProjectResponse, feature_to_response
from app.schemas.registry import GapResponse, RegistryResponse

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PatchProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.post("/", response_model=ProjectResponse)
async def create_project(
    req: CreateProjectRequest,
    session: AsyncSession = Depends(get_session),
):
    project = Project(name=req.name)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _project_response(project)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Project)
        .options(selectinload(Project.documents))
        .order_by(Project.created_at.desc())
    )
    result = await session.execute(stmt)
    return [_project_response(p) for p in result.scalars().all()]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, session)
    return _project_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def patch_project(
    project_id: int,
    patch: PatchProjectRequest,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, session)
    project.name = patch.name
    await session.commit()
    await session.refresh(project)
    return _project_response(project)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, session)
    await session.delete(project)
    await session.commit()
    return {"ok": True}


async def _get_project(project_id: int, session: AsyncSession) -> Project:
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.documents))
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@router.get("/{project_id}/features", response_model=list[FeatureResponse])
async def get_project_features(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    """All features across all documents in this project."""
    stmt = (
        select(Feature)
        .join(Document)
        .where(Document.project_id == project_id)
        .order_by(Feature.id)
    )
    result = await session.execute(stmt)
    return [feature_to_response(f) for f in result.scalars().all()]


@router.get("/{project_id}/registry", response_model=RegistryResponse)
async def get_project_registry(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Aggregated dependencies across all documents in this project."""
    stmt = (
        select(DependencyEntry)
        .join(Document)
        .where(Document.project_id == project_id)
    )
    result = await session.execute(stmt)
    grouped: dict[str, list] = {"db": [], "external_api": [], "cache": []}
    for entry in result.scalars().all():
        data = json.loads(entry.data_json)
        if entry.registry_type in grouped:
            grouped[entry.registry_type].append({"id": entry.id, "name": entry.name, "data": data})
    return RegistryResponse(**grouped)


@router.get("/{project_id}/gaps", response_model=list[GapResponse])
async def get_project_gaps(
    project_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Aggregated gaps across all documents in this project."""
    stmt = (
        select(GapEntry)
        .join(Document)
        .where(Document.project_id == project_id)
    )
    result = await session.execute(stmt)
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
        for g in result.scalars().all()
    ]


def _project_response(project: Project) -> ProjectResponse:
    total_features = sum(d.feature_count for d in project.documents)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        document_count=len(project.documents),
        feature_count=total_features,
        status=_project_status(project.documents),
    )


def _project_status(documents: list) -> str:
    if not documents:
        return "empty"
    statuses = [d.status for d in documents]
    if any(s in ("processing", "extracting") for s in statuses):
        return "processing"
    if all(s == "done" for s in statuses):
        return "done"
    if any(s == "error" for s in statuses):
        return "partial"
    return "pending"
