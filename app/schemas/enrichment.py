from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import MessageField


# --- DB table enrichment ---
class DbColumnInfo(BaseModel):
    name: str
    col_type: str = Field(description="SQL data type, e.g. BIGINT, VARCHAR(255)")
    nullable: bool = True
    description: str = ""
    is_pk: bool = False
    is_fk: bool = False
    fk_references: str | None = None


class DbTableEnrichment(BaseModel):
    table_name: str
    description: str = ""
    columns: list[DbColumnInfo] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)
    business_notes: list[str] = Field(default_factory=list)


class DbEnrichmentBatch(BaseModel):
    """1 PDF -> N tables. Used as Claude tool schema for db_table enrichment."""
    tables: list[DbTableEnrichment]


# --- External API enrichment ---
class ApiParamInfo(BaseModel):
    name: str
    param_in: str = Field(description="query | header | path | body")
    param_type: str
    required: bool = True
    description: str = ""


class ApiEndpointInfo(BaseModel):
    method: str = Field(description="GET | POST | PUT | DELETE | PATCH")
    path: str
    description: str = ""
    params: list[ApiParamInfo] = Field(default_factory=list)
    request_body_schema: dict | None = None
    response_schema: dict | None = None
    error_codes: list[str] = Field(default_factory=list)


class ExternalApiEnrichment(BaseModel):
    """1 PDF -> 1 API. Used as Claude tool schema for external_api enrichment."""
    api_name: str
    base_url: str | None = None
    description: str = ""
    endpoints: list[ApiEndpointInfo] = Field(default_factory=list)


# --- Cache enrichment ---
class CacheKeyPattern(BaseModel):
    pattern: str = Field(description="Key pattern, e.g. product:{id}:status")
    description: str = ""
    ttl_seconds: int | None = None
    value_structure: dict | None = None


class CacheEnrichment(BaseModel):
    cache_name: str
    description: str = ""
    key_patterns: list[CacheKeyPattern] = Field(default_factory=list)
    eviction_policy: str | None = None
    notes: list[str] = Field(default_factory=list)


class CacheEnrichmentBatch(BaseModel):
    """1 PDF -> N cache structures. Used as Claude tool schema for cache enrichment."""
    caches: list[CacheEnrichment]


# --- Kafka topic enrichment ---
class KafkaTopicEnrichment(BaseModel):
    topic_name: str
    description: str = ""
    message_fields: list[MessageField] = Field(default_factory=list, description="Hierarchical message field mapping")
    key_fields: list[MessageField] = Field(default_factory=list, description="Hierarchical key field mapping")
    partitions: int | None = None
    retention_ms: int | None = Field(default=None, description="Retention in milliseconds")
    notes: list[str] = Field(default_factory=list)


class KafkaTopicEnrichmentBatch(BaseModel):
    """1 PDF -> N topics. Used as Claude tool schema for kafka_topic enrichment."""
    topics: list[KafkaTopicEnrichment]


# --- Manual dependency creation ---
class CreateDependencyRequest(BaseModel):
    dep_type: str = Field(description="db_table | external_api | cache | kafka_topic")
    name: str = Field(min_length=1)
    description: str = ""
    method: str | None = None       # for external_api
    service_name: str | None = None  # for external_api
    path: str | None = None          # for external_api


# --- API response ---
class DependencyResponse(BaseModel):
    """HTTP response model for a single dependency."""
    project_slug: str
    dep_type: str
    name: str
    description: str | None = None
    enrichment_status: str
    enriched_data: dict | None = None
    source_pdf_name: str | None = None
    enriched_at: datetime | None = None
    created_at: datetime
    method: str | None = None
    service_name: str | None = None
    path: str | None = None

    model_config = ConfigDict(from_attributes=True)
