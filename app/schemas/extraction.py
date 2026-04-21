import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FeatureType(str, Enum):
    kafka_consumer = "kafka_consumer"
    rest_endpoint = "rest_endpoint"
    scheduled_task = "scheduled_task"
    unknown = "unknown"


class ParameterField(BaseModel):
    name: str = Field(description="Parameter name in Latin")
    field_type: str = Field(description="Data type: string, integer, boolean, object, array, etc.")
    description: str = Field(description="Description in Russian from the spec")
    required: bool = Field(default=True)
    validation_rules: list[str] = Field(default_factory=list, description="Validation rules in Russian, e.g. 'Не более 50 символов'")
    param_in: str | None = Field(default=None, description="For REST: body, header, query, path. Null for Kafka.")
    example: str | None = Field(default=None, description="Sample value for this field. Extract from spec if given, otherwise synthesise a realistic one based on type. Null for container fields (object/array) whose value is represented by children.")
    children: list["ParameterField"] = Field(default_factory=list, description="Nested fields for object/array types")


class MessageField(BaseModel):
    element: str = Field(description="Field/element name")
    parent: str | None = Field(default=None, description="Parent element name")
    field_type: str | None = Field(default=None, description="Data type")
    required: bool | None = Field(default=None, description="Verbatim from spec table 'Обяз.' column: true/false. Null if no such column in spec.")
    cardinality: str | None = Field(default=None, description="Verbatim cardinality from spec table: '1', '0-1', '1-N', '0-N'. Null if not present in spec.")
    is_collection: bool = Field(default=False, description="True if this field is a list/array based on direct textual cues in the spec")
    description: str | None = Field(default=None, description="What this field is, in Russian from the spec")
    source: str | None = Field(default=None, description="Where the value comes from, in Russian from the spec")
    example: str | None = Field(default=None, description="Sample value for this field. Extract from spec if given, otherwise synthesise a realistic one based on type. Null for container fields whose value is represented by children.")
    children: list["MessageField"] = Field(default_factory=list)


class GenericTable(BaseModel):
    """Reference / lookup table from the spec that is NOT a field mapping.

    Examples: enum value → action mapping, error code reference, status matrix.
    Stored verbatim as headers + rows so the original table structure is preserved
    without forcing it into the MessageField schema.
    """

    caption: str | None = Field(default=None, description="Optional table title/caption from the spec, in Russian")
    headers: list[str] = Field(description="Column headers verbatim from the spec, in order")
    rows: list[list[str]] = Field(description="Data rows; each row has len(headers) cells as strings")


class LogicStep(BaseModel):
    number: str = Field(description="Step number like '1', '1.1', '1.1.2'")
    text: str = Field(description="VERBATIM text from the PDF specification in Russian")
    has_detailed_mapping: bool = Field(default=False, description="True if this step contains XML/JSON message mapping table")
    message_type: str | None = Field(default=None, description="Target table/message type name from Call 2, e.g. 'outbox_payment'")
    message_mapping: list[MessageField] | None = Field(default=None, description="Extracted message mapping fields")
    reference_tables: list[GenericTable] = Field(
        default_factory=list,
        description="Reference/lookup tables attached to this step (enum value mappings, code reference tables, etc.) — NOT field mappings.",
    )
    external_doc_refs: list[str] = Field(
        default_factory=list,
        description="Names of external documents referenced in this step. Must exactly match names in used_dependencies (type=external_doc).",
    )
    children: list["LogicStep"] = Field(default_factory=list)


class UsedDependency(BaseModel):
    type: str = Field(description="db_table, external_api, cache, kafka_topic, or external_doc")
    name: str = Field(description="Name: table name, cache structure name, Kafka topic name, endpoint path for external_api, or document title for external_doc")
    description: str = Field(description="What it's used for, in Russian")
    method: str | None = Field(default=None, description="HTTP method for external_api: GET/POST/PUT/DELETE/PATCH")
    service_name: str | None = Field(default=None, description="Service name for external_api, e.g. flp-credit-line")
    path: str | None = Field(default=None, description="Endpoint path for external_api, e.g. /v1/credit-line")


ParameterField.model_rebuild()
MessageField.model_rebuild()
LogicStep.model_rebuild()


class MappingExtractionResult(BaseModel):
    step_number: str = Field(description="Step number like '7.b'")
    message_type: str = Field(description="Message type name like 'AgreemtListMod'")
    queue_or_endpoint: str | None = Field(default=None)
    fields: list[MessageField] = Field(default_factory=list)


class MappingExtractionBatch(BaseModel):
    mappings: list[MappingExtractionResult]


class ErrorResponseSchema(BaseModel):
    status_codes: str = Field(description="HTTP status codes, e.g. '400', '404', '500', '4xx'")
    description: str = Field(description="When this error occurs, in Russian")
    parameters: list[ParameterField] = Field(default_factory=list, description="Response body fields for this error")


class StructuredBusinessLogic(BaseModel):
    input_parameters: list[ParameterField] = Field(default_factory=list)
    output_parameters: list[ParameterField] | None = Field(default=None)  # kept for backward compat with old data
    success_response: list[ParameterField] = Field(default_factory=list)
    error_responses: list[ErrorResponseSchema] = Field(default_factory=list)
    logic_steps: list[LogicStep] = Field(default_factory=list)
    used_dependencies: list[UsedDependency] = Field(default_factory=list)
    error_handling: dict | None = None
    business_rules: list[str] = Field(default_factory=list)


class DocumentPatchRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class DetectedFeature(BaseModel):
    """Feature detected from PDF by the 1st Claude call (tool_use schema)."""

    name: str = Field(description="Latin slug identifier: topic name for Kafka, METHOD /path for REST, or a latin snake_case slug derived from the scheduled-task heading")
    display_name: str | None = Field(default=None, description="Human-readable name verbatim from the spec (Russian). Required for scheduled_task (heading of the task section). Null for kafka_consumer/rest_endpoint — UI falls back to name.")
    type: FeatureType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    method: str | None = Field(default=None, description="HTTP method for REST (GET/POST/PUT/DELETE), CONSUMER for Kafka, SCHEDULED for scheduled_task")
    endpoint: str | None = Field(default=None, description="REST path like /v1/credit-line or Kafka topic like pay-later.flp.rbo-adapter.product.return.queue. Null for scheduled_task — use `schedule` instead.")
    schedule: str | None = Field(default=None, description="Trigger schedule verbatim from the spec (Russian). Examples: 'Ежедневно в 19:00 МСК', 'Каждый час'. Required for scheduled_task, null otherwise.")
    dependencies: list[str] = Field(default_factory=list)
    structured_logic: StructuredBusinessLogic = Field(default_factory=StructuredBusinessLogic)


class FeatureDetectionResult(BaseModel):
    """Root model for 1st Claude call structured output."""

    features: list[DetectedFeature]


class SingleFeatureExtraction(BaseModel):
    """Combined schema: feature metadata + structured logic in one call."""

    name: str = Field(description="Feature name in Latin")
    type: FeatureType = Field(description="kafka_consumer or rest_endpoint")
    summary: str = Field(description="Brief description in Russian")
    method: str | None = Field(default=None, description="HTTP method for REST (GET/POST/PUT/DELETE) or CONSUMER for Kafka")
    endpoint: str | None = Field(default=None, description="REST path like /v1/credit-line or Kafka topic like pay-later.flp.rbo-adapter.product.return.queue")
    dependencies: list[str] = Field(default_factory=list)
    structured_logic: StructuredBusinessLogic = Field(default_factory=StructuredBusinessLogic)


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    extracting = "extracting"
    done = "done"
    error = "error"
    partial = "partial"


class FeatureStatus(str, Enum):
    extracting = "extracting"
    done = "done"


class FeaturePatchRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    method: str | None = None
    endpoint: str | None = None
    summary: str | None = None
    structured_logic_json: dict | None = None


class FeatureResponse(BaseModel):
    """HTTP response model for a single feature."""

    name: str
    display_name: str | None = None
    source_document: str  # doc slug
    type: str
    confidence: float
    summary: str | None = None
    status: str
    method: str | None = None
    endpoint: str | None = None
    schedule: str | None = None
    structured_logic: dict | None = None  # from structured_logic_json field
    gap_count: int = 0
    pending_gap_count: int = 0
    gaps_running: bool = False
    apply_running: bool = False
    test_case_count: int = 0
    pending_test_case_count: int = 0
    test_cases_running: bool = False

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    """HTTP response model for a document with its features."""

    slug: str
    project_slug: str
    filename: str
    status: str
    pdf_size_bytes: int
    feature_count: int
    features: list[FeatureResponse]
    uploaded_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    """HTTP response model for a project."""

    slug: str
    name: str
    created_at: datetime
    document_count: int
    feature_count: int = 0
    status: str = "empty"

    model_config = ConfigDict(from_attributes=True)
