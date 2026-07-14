from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class TaskKind(str, Enum):
    extraction = "extraction"
    gaps = "gaps"
    apply_gaps = "apply_gaps"
    test_cases = "test_cases"
    enrichment = "enrichment"


class TaskStatus(str, Enum):
    running = "running"
    done = "done"
    error = "error"


class TaskTargetType(str, Enum):
    document = "document"
    feature = "feature"
    dependency = "dependency"


class TaskRecord(BaseModel):
    id: str
    kind: TaskKind
    target_type: TaskTargetType
    target_id: str
    status: TaskStatus
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None
    duration_ms: int | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    tasks: list[TaskRecord]
