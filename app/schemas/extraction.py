import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FeatureType(str, Enum):
    kafka_consumer = "kafka_consumer"
    rest_endpoint = "rest_endpoint"
    scheduled_task = "scheduled_task"
    unknown = "unknown"


class DetectedFeature(BaseModel):
    """Feature detected from PDF by the 1st Claude call (tool_use schema)."""

    name: str
    type: FeatureType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    dependencies: list[str] = Field(default_factory=list)


class FeatureDetectionResult(BaseModel):
    """Root model for 1st Claude call structured output."""

    features: list[DetectedFeature]


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


class FeatureResponse(BaseModel):
    """HTTP response model for a single feature."""

    id: int
    name: str
    type: str
    confidence: float
    summary: str | None = None
    status: str
    business_logic: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    """HTTP response model for a document with its features."""

    id: int
    filename: str
    status: str
    pdf_size_bytes: int
    feature_count: int
    features: list[FeatureResponse]
    uploaded_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


def feature_to_response(feature) -> FeatureResponse:
    """Convert Feature ORM to FeatureResponse, parsing business_logic JSON."""
    bl = None
    if feature.business_logic:
        try:
            bl = json.loads(feature.business_logic)
        except json.JSONDecodeError:
            bl = {"_raw": feature.business_logic}
    return FeatureResponse(
        id=feature.id,
        name=feature.name,
        type=feature.type,
        confidence=feature.confidence,
        summary=feature.summary,
        status=feature.status,
        business_logic=bl,
    )
