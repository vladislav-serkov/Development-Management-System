import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.tasks import TaskKind, TaskListResponse, TaskRecord, TaskStatus
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/tasks",
    tags=["tasks"],
)


@router.get("", response_model=TaskListResponse)
async def list_project_tasks(
    project_slug: str,
    status: TaskStatus | None = Query(default=None),
    kind: TaskKind | None = Query(default=None),
    target_id: str | None = Query(default=None),
):
    """Return the project's background-task log, newest first, with optional filters."""
    if await store.get_project(project_slug) is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    raw = await store.list_tasks(
        project_slug,
        status=status.value if status else None,
        kind=kind.value if kind else None,
        target_id=target_id,
    )
    return TaskListResponse(tasks=[TaskRecord.model_validate(t) for t in raw])
