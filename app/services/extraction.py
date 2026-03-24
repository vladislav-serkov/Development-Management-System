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
from app.models.registry import DependencyEntry, GapEntry
from app.schemas.extraction import (
    DetectedFeature,
    DocumentResponse,
    FeatureDetectionResult,
    FeatureResponse,
    feature_to_response,
)
from app.schemas.registry import DeduplicationResult

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
                            "is a separate feature.\n\n"
                            "For each feature extract:\n"
                            "- name, type (kafka_consumer/rest_endpoint/scheduled_task/unknown), confidence (0.0-1.0), one-line summary, dependency names\n"
                            "- structured_logic with: processing_steps (list of {step, action, description}), "
                            "input_schema, output_schema, error_handling, external_api_calls, "
                            "database_operations, cache_operations, business_rules"
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
                            "Use whatever JSON structure you think is most useful for a developer or AI agent "
                            "to understand and implement this feature. Be thorough and precise.\n\n"
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


DEDUP_GAPS_PROMPT = """Analyze the business logic JSON for all features above and return a single JSON object with these three top-level keys:

1. "dependencies": A dict with keys "db", "external_api", and "cache". Each value is a list of deduplicated dependency objects. Merge mentions of the same dependency from different features into one entry.
   - For "db" entries include: name, type ("db_table"), columns (list of {name, type, nullable}), used_by_features (list of feature names), known_operations (list like ["SELECT", "UPDATE"])
   - For "external_api" entries include: name, type ("rest_api"), base_url, endpoints (list of {method, path, description}), used_by_features
   - For "cache" entries include: name, type ("redis_cache"), structure, used_by_features, known_operations

2. "overviews": A dict mapping each feature name to a markdown string overview. Each overview must include: feature type, one-line summary, list of dependencies with their roles, brief business logic description, and references to any relevant gaps.

3. "gaps": A list of gap objects for missing information. Each gap must have: category ("DB", "API", or "Cache"), name (short identifier), affected_features (list of feature names), what_missing (specific description of missing info), priority ("critical", "medium", or "low"), suggestion (nullable dict with proposed schema/structure or null).

Return ONLY the raw JSON object. No markdown fencing, no explanation text."""

KNOWN_REGISTRY_TYPES = frozenset(["db", "external_api", "cache"])


async def _run_dedup_and_gaps(
    features: list[tuple[str, dict]],
    client: anthropic.AsyncAnthropic,
    model: str,
) -> DeduplicationResult:
    """Third Claude call: dependency deduplication + gap detection + overview generation.

    Args:
        features: list of (feature_name, business_logic_dict) tuples for successful extractions
        client: Anthropic async client
        model: Claude model name

    Returns:
        DeduplicationResult with merged dependencies, overviews, and gaps
    """
    context_blob = json.dumps(
        {name: bl for name, bl in features},
        ensure_ascii=False,
        indent=2,
    )

    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context_blob,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": DEDUP_GAPS_PROMPT,
                    },
                ],
            }
        ],
    )

    raw = _extract_json_from_text(response.content[0].text)
    result = DeduplicationResult.model_validate(raw)
    _log_cache_stats(response.usage, "dedup_and_gaps")
    return result


async def _store_dedup_results(
    result: DeduplicationResult,
    doc: Document,
    feature_orm_map: dict[str, Feature],
    session: AsyncSession,
) -> None:
    """Persist deduplication results: dependency entries, gap entries, and feature overviews.

    Args:
        result: parsed DeduplicationResult from 3rd Claude call
        doc: Document ORM object
        feature_orm_map: mapping of feature name -> Feature ORM object
        session: async database session
    """
    # Store dependency entries
    for registry_type, entries in result.dependencies.items():
        if registry_type not in KNOWN_REGISTRY_TYPES:
            logger.warning(
                "Unknown registry_type '%s' from dedup call for document %d, skipping",
                registry_type,
                doc.id,
            )
            continue
        for entry in entries:
            dep = DependencyEntry(
                document_id=doc.id,
                registry_type=registry_type,
                name=entry.get("name", "unknown"),
                data_json=json.dumps(entry, ensure_ascii=False),
            )
            session.add(dep)

    # Store gap entries
    for gap in result.gaps:
        gap_entry = GapEntry(
            document_id=doc.id,
            category=gap.category,
            name=gap.name,
            affected_features=json.dumps(gap.affected_features, ensure_ascii=False),
            what_missing=gap.what_missing,
            priority=gap.priority,
            suggestion_json=json.dumps(gap.suggestion, ensure_ascii=False) if gap.suggestion else None,
        )
        session.add(gap_entry)

    # Set feature overviews (with fallback for missing overviews)
    for feature_name, feature_orm in feature_orm_map.items():
        if feature_name in result.overviews:
            feature_orm.overview_md = result.overviews[feature_name]
        else:
            # Fallback: generate minimal overview from stored summary
            feature_orm.overview_md = (
                f"## {feature_name}\n\n{feature_orm.summary or 'No overview available.'}"
            )


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
                structured_logic_json=detected.structured_logic.model_dump_json(),
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

        # Phase 3: Dependency deduplication + gap detection + overview generation
        successful_features = [
            (f_schema.name, bl_dict)
            for f_schema, bl_dict, err in results
            if bl_dict is not None
        ]

        if successful_features:
            try:
                dedup_result = await _run_dedup_and_gaps(successful_features, client, model)
                await _store_dedup_results(dedup_result, doc, feature_orm_map, session)
            except Exception as dedup_exc:
                logger.error(
                    "Dedup+gaps pipeline failed for %s: %s", filename, dedup_exc
                )
                # Don't fail the whole pipeline for dedup failure
                if doc.error_message:
                    doc.error_message += " (dedup failed)"
                else:
                    doc.error_message = "Dedup+gaps pipeline failed"

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
