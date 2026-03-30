from fastapi import APIRouter, HTTPException

from app.schemas.rules import RulesData
from app.storage import ProjectStore

store = ProjectStore()
router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/global", response_model=RulesData)
async def get_global_rules():
    return RulesData(**await store.get_global_rules())


@router.put("/global", response_model=RulesData)
async def save_global_rules(body: RulesData):
    saved = await store.save_global_rules(body.model_dump())
    return RulesData(**saved)


@router.get("/projects/{project_slug}", response_model=RulesData)
async def get_project_rules(project_slug: str):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    return RulesData(**await store.get_project_rules(project_slug))


@router.put("/projects/{project_slug}", response_model=RulesData)
async def save_project_rules(project_slug: str, body: RulesData):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    saved = await store.save_project_rules(project_slug, body.model_dump())
    return RulesData(**saved)
