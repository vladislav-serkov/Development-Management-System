import asyncio
import base64
import json
import logging
import re
from datetime import UTC, datetime

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document, Feature
from app.schemas.extraction import (
    DetectedFeature,
    DocumentResponse,
    FeatureDetectionResult,
    FeatureResponse,
    feature_to_response,
)

logger = logging.getLogger(__name__)


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _build_document_block(pdf_b64: str, cache: bool = False) -> dict:
    block = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": pdf_b64,
        },
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def _log_cache_stats(usage, call_name: str) -> None:
    input_tokens = getattr(usage, "input_tokens", 0)
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    logger.info(
        "%s: input_tokens=%d, cache_creation_input_tokens=%d, cache_read_input_tokens=%d",
        call_name,
        input_tokens,
        cache_creation,
        cache_read,
    )


def _extract_json_from_text(text: str) -> dict:
    """Extract JSON from text, handling optional markdown fences."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?([\s\S]+?)\n?\s*```", stripped)
    if match:
        return json.loads(match.group(1).strip())

    raise ValueError(f"Cannot parse JSON from response (first 200 chars): {stripped[:200]}")


async def _detect_features(
    pdf_b64: str,
    client: anthropic.AsyncAnthropic,
    model: str,
) -> FeatureDetectionResult:
    """First Claude call: detect features using tool_use with forced tool choice."""
    tool = {
        "name": "detect_features",
        "description": "Extract all features detected in the technical specification",
        "input_schema": FeatureDetectionResult.model_json_schema(),
    }

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": "detect_features"},
        messages=[
            {
                "role": "user",
                "content": [
                    _build_document_block(pdf_b64, cache=False),
                    {
                        "type": "text",
                        "text": (
                            "This is a technical specification for a microservice. "
                            "Identify every distinct feature defined in this document. "
                            "Each Kafka topic consumer, REST endpoint path, and scheduled task "
                            "is a separate feature. Extract name, type, confidence (0.0-1.0), "
                            "one-line summary, and dependency names for each feature."
                        ),
                    },
                ],
            }
        ],
    )

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        raise ValueError("No tool_use block in Claude response")

    result = FeatureDetectionResult.model_validate(tool_block.input)
    _log_cache_stats(response.usage, "detect_features")
    return result


async def _extract_single_feature_logic(
    pdf_b64: str,
    feature: DetectedFeature,
    client: anthropic.AsyncAnthropic,
    model: str,
) -> dict:
    """Second Claude call: extract business logic for a single feature."""
    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    _build_document_block(pdf_b64, cache=True),
                    {
                        "type": "text",
                        "text": (
                            f"Focus on the feature '{feature.name}' (type: {feature.type.value}).\n\n"
                            "Return a JSON object with the complete business logic for this feature, "
                            "optimized for an LLM coding agent to generate implementation code.\n\n"
                            "Include these aspects where applicable:\n"
                            "- processing_steps: ordered list of what the feature does\n"
                            "- input_schema: message/request format\n"
                            "- output_schema: response format (if any)\n"
                            "- error_handling: rules for different error scenarios\n"
                            "- external_api_calls: any HTTP calls to other services\n"
                            "- database_operations: tables read/written\n"
                            "- cache_operations: Redis/cache interactions\n"
                            "- business_rules: validation, conditions, edge cases\n\n"
                            "Return ONLY the raw JSON object. No markdown fencing, no explanation text."
                        ),
                    },
                ],
            }
        ],
    )

    result = _extract_json_from_text(response.content[0].text)
    _log_cache_stats(response.usage, f"business_logic:{feature.name}")
    return result


async def _extract_all_business_logic(
    pdf_b64: str,
    features: list[DetectedFeature],
    client: anthropic.AsyncAnthropic,
    model: str,
) -> list[tuple[DetectedFeature, dict | None, str | None]]:
    """Extract business logic for all features in parallel."""

    async def _safe_extract(feature: DetectedFeature):
        try:
            result = await _extract_single_feature_logic(pdf_b64, feature, client, model)
            return (feature, result, None)
        except Exception as exc:
            logger.error("Failed to extract business logic for %s: %s", feature.name, exc)
            return (feature, None, str(exc))

    tasks = [_safe_extract(f) for f in features]
    return await asyncio.gather(*tasks)


async def run_extraction_pipeline(
    filename: str,
    pdf_bytes: bytes,
    session: AsyncSession,
) -> DocumentResponse:
    """Full two-call extraction pipeline: detect features, then extract business logic."""
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    doc = Document(filename=filename, pdf_size_bytes=len(pdf_bytes), status="processing")
    session.add(doc)
    await session.flush()

    client = _get_client()
    model = settings.claude_model

    try:
        # Phase 1: Feature detection
        detection_result = await _detect_features(pdf_b64, client, model)

        feature_orm_map: dict[str, Feature] = {}
        for detected in detection_result.features:
            feature_orm = Feature(
                document_id=doc.id,
                name=detected.name,
                type=detected.type.value,
                confidence=detected.confidence,
                summary=detected.summary,
                dependencies_json=json.dumps(detected.dependencies, ensure_ascii=False),
                status="detected",
            )
            session.add(feature_orm)
            feature_orm_map[detected.name] = feature_orm

        doc.feature_count = len(detection_result.features)
        doc.status = "extracting"
        await session.flush()

        # Phase 2: Business logic extraction (parallel)
        results = await _extract_all_business_logic(pdf_b64, detection_result.features, client, model)

        done_count = 0
        error_count = 0

        for feature_schema, bl_dict, error in results:
            orm = feature_orm_map[feature_schema.name]
            if bl_dict is not None:
                orm.business_logic = json.dumps(bl_dict, ensure_ascii=False)
                orm.status = "done"
                orm.extracted_at = datetime.now(UTC)
                done_count += 1
            elif error is not None:
                orm.status = "error"
                orm.error_message = error
                error_count += 1

        # Final status
        total = len(results)
        if error_count == 0:
            doc.status = "done"
        elif done_count == 0:
            doc.status = "error"
            doc.error_message = "All feature extractions failed"
        else:
            doc.status = "partial"
            doc.error_message = f"{error_count} of {total} features failed extraction"

        await session.commit()

    except Exception as exc:
        logger.error("Extraction pipeline failed for %s: %s", filename, exc)
        doc.status = "error"
        doc.error_message = str(exc)
        await session.commit()
        raise

    # Refresh to get all relationships
    await session.refresh(doc)

    features_response = [feature_to_response(f) for f in doc.features]
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        pdf_size_bytes=doc.pdf_size_bytes,
        feature_count=doc.feature_count,
        features=features_response,
        uploaded_at=doc.uploaded_at,
        error_message=doc.error_message,
    )
