import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FeatureType(str, Enum):
    kafka_consumer = "kafka_consumer"
    rest_endpoint = "rest_endpoint"
    unknown = "unknown"


class ParameterField(BaseModel):
    name: str = Field(description="Parameter name in Latin")
    field_type: str = Field(description="Data type: string, integer, boolean, object, array, etc.")
    description: str = Field(description="Description in Russian from the spec")
    required: bool = Field(default=True)
    validation_rules: list[str] = Field(default_factory=list, description="Validation rules in Russian, e.g. 'Не более 50 символов'")
    param_in: str | None = Field(default=None, description="For REST: body, header, query, path. Null for Kafka.")
    children: list["ParameterField"] = Field(default_factory=list, description="Nested fields for object/array types")


class MessageField(BaseModel):
    element: str = Field(description="Field/element name")
    parent: str | None = Field(default=None, description="Parent element name")
    field_type: str | None = Field(default=None, description="Data type")
    required: bool = Field(default=False)
    cardinality: str | None = Field(default=None, description="Verbatim cardinality from spec table: '1', '0-1', '1-N', '0-N'. Null if not present in spec.")
    is_collection: bool = Field(default=False, description="True if this field is a list/array based on direct textual cues in the spec")
    description: str | None = Field(default=None, description="What this field is, in Russian from the spec")
    source: str | None = Field(default=None, description="Where the value comes from, in Russian from the spec")
    children: list["MessageField"] = Field(default_factory=list)


class LogicStep(BaseModel):
    number: str = Field(description="Step number like '1', '1.1', '1.1.2'")
    text: str = Field(description="VERBATIM text from the PDF specification in Russian")
    has_detailed_mapping: bool = Field(default=False, description="True if this step contains XML/JSON message mapping table")
    message_mapping: list[MessageField] | None = Field(default=None, description="Extracted message mapping fields")
    children: list["LogicStep"] = Field(default_factory=list)


class UsedDependency(BaseModel):
    type: str = Field(description="db_table, external_api, cache, or kafka_topic")
    name: str = Field(description="Name: table name, cache structure name, Kafka topic name, or endpoint path for external_api")
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

    name: str
    type: FeatureType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    method: str | None = Field(default=None, description="HTTP method for REST (GET/POST/PUT/DELETE) or CONSUMER for Kafka")
    endpoint: str | None = Field(default=None, description="REST path like /v1/credit-line or Kafka topic like pay-later.flp.rbo-adapter.product.return.queue")
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
    detected = "detected"
    extracting = "extracting"
    done = "done"
    error = "error"


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
    source_document: str  # doc slug
    type: str
    confidence: float
    summary: str | None = None
    status: str
    method: str | None = None
    endpoint: str | None = None
    structured_logic: dict | None = None  # from structured_logic_json field
    gap_count: int = 0
    pending_gap_count: int = 0
    gaps_status: str | None = None
    apply_status: str | None = None
    test_case_count: int = 0
    pending_test_case_count: int = 0
    test_cases_status: str | None = None

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
