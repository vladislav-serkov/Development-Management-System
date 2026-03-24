from pydantic import BaseModel, Field


class DependencyItem(BaseModel):
    name: str
    type: str  # "db_table", "rest_api", "redis_cache"
    used_by_features: list[str] = Field(default_factory=list)
    # Additional fields are stored as-is in data_json


class GapItem(BaseModel):
    category: str  # "DB", "API", "Cache"
    name: str
    affected_features: list[str]
    what_missing: str
    priority: str = "medium"  # "critical", "medium", "low"
    suggestion: dict | None = None


class DeduplicationResult(BaseModel):
    """Schema for parsing the 3rd Claude call response."""

    dependencies: dict[str, list[dict]]  # {"db": [...], "external_api": [...], "cache": [...]}
    overviews: dict[str, str]  # {"feature-name": "## overview markdown..."}
    gaps: list[GapItem] = Field(default_factory=list)
