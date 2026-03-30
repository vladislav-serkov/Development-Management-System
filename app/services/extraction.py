import base64
import json
import logging
import re
from datetime import UTC, datetime

import anthropic
import httpx

from app.config import settings
from app.prompts.extraction import DETECT_FEATURE_PROMPT, build_mapping_prompt
from app.services.rules import build_system_prompt
from app.schemas.extraction import (
    DetectedFeature,
    DocumentResponse,
    FeatureResponse,
    MappingExtractionBatch,
    MappingExtractionResult,
)

logger = logging.getLogger(__name__)


def _normalize_dep_name(name: str) -> str:
    """Normalize dependency name for cross-feature matching."""
    return name.lower().replace(" ", "_")


def _get_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(timeout=900.0, connect=5.0),
    )


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


def _collect_steps_with_mapping(steps, result=None):
    """Recursively collect step numbers where has_detailed_mapping=True."""
    if result is None:
        result = []
    for step in steps:
        if step.has_detailed_mapping:
            result.append(step.number)
        _collect_steps_with_mapping(step.children, result)
    return result


def _merge_mappings_into_steps(steps, mappings_by_step: dict) -> None:
    """Recursively merge MappingExtractionResult.fields into matching LogicStep.message_mapping."""
    for step in steps:
        if step.number in mappings_by_step:
            step.message_mapping = mappings_by_step[step.number].fields
        _merge_mappings_into_steps(step.children, mappings_by_step)


def _propagate_is_collection(fields: list) -> None:
    """Post-order traversal: set parent.is_collection=True if any child has cardinality ending with '-N'."""
    for field in fields:
        if field.children:
            _propagate_is_collection(field.children)
            # After recursing children, check if any child has -N cardinality
            if not field.is_collection:
                for child in field.children:
                    if child.cardinality and child.cardinality.endswith("-N"):
                        field.is_collection = True
                        break


async def _detect_feature(
    pdf_b64: str,
    client: anthropic.AsyncAnthropic,
    model: str,
    system_prompt: str = "",
) -> DetectedFeature:
    """Call 1: detect feature metadata via tool_use (PDF cached for subsequent calls)."""
    logger.info("[Call 1] Detecting feature (model=%s, pdf_size=%.1fKB)", model, len(pdf_b64) * 3 / 4 / 1024)
    tool = {
        "name": "detect_feature",
        "description": "Extract the single feature from the technical specification",
        "input_schema": DetectedFeature.model_json_schema(),
    }

    create_kwargs: dict = dict(
        model=model,
        max_tokens=16384,
        tools=[tool],
        tool_choice={"type": "tool", "name": "detect_feature"},
    )
    if system_prompt:
        create_kwargs["system"] = system_prompt

    response = await client.messages.create(
        **create_kwargs,
        messages=[
            {
                "role": "user",
                "content": [
                    _build_document_block(pdf_b64, cache=True),
                    {
                        "type": "text",
                        "text": DETECT_FEATURE_PROMPT,
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

    tool_input = tool_block.input
    if not tool_input or not tool_input.get("name"):
        logger.warning("[Call 1] Claude returned empty tool input: %s", tool_input)
        raise ValueError(
            "Claude не смог извлечь feature из документа. "
            "Возможно, PDF нечитаем или не содержит технического задания."
        )

    result = DetectedFeature.model_validate(tool_input)
    logger.info("[Call 1] Detected feature '%s' (type=%s)", result.name, result.type.value)
    _log_cache_stats(response.usage, "detect_feature")
    return result


async def _extract_message_mappings(
    pdf_b64: str,
    feature: DetectedFeature,
    steps_with_mapping: list[str],  # step numbers
    client: anthropic.AsyncAnthropic,
    model: str,
    system_prompt: str = "",
) -> list[MappingExtractionResult]:
    """Call 2 (conditional): extract message field mappings for steps that have mapping tables."""
    logger.info(
        "[Call 2] Extracting message mappings for '%s', steps: %s",
        feature.name,
        steps_with_mapping,
    )
    tool = {
        "name": "extract_message_mappings",
        "description": "Extract structured message field mappings for specified steps",
        "input_schema": MappingExtractionBatch.model_json_schema(),
    }

    steps_list = ", ".join(steps_with_mapping)
    create_kwargs2: dict = dict(
        model=model,
        max_tokens=16384,
        tools=[tool],
        tool_choice={"type": "tool", "name": "extract_message_mappings"},
    )
    if system_prompt:
        create_kwargs2["system"] = system_prompt
    response = await client.messages.create(
        **create_kwargs2,
        messages=[
            {
                "role": "user",
                "content": [
                    _build_document_block(pdf_b64, cache=True),
                    {
                        "type": "text",
                        "text": build_mapping_prompt(feature.name, feature.type.value, steps_list),
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
        logger.warning("[Call 2] No tool_use block in Claude response for '%s'", feature.name)
        return []

    batch = MappingExtractionBatch.model_validate(tool_block.input)
    logger.info("[Call 2] Extracted %d mapping(s) for '%s'", len(batch.mappings), feature.name)
    _log_cache_stats(response.usage, f"message_mappings:{feature.name}")
    return batch.mappings


def _feature_dict_to_response(f: dict) -> FeatureResponse:
    sl = f.get("structured_logic_json")
    if not isinstance(sl, dict):
        sl = None
    else:
        sl = None
    return FeatureResponse(
        name=f["name"],
        source_document=f.get("source_document", ""),
        type=f.get("type", "unknown"),
        confidence=f.get("confidence", 0.0),
        summary=f.get("summary"),
        status=f.get("status", "detected"),
        method=f.get("method"),
        endpoint=f.get("endpoint"),
        structured_logic=sl,
    )


async def run_extraction_pipeline(
    filename: str,
    pdf_bytes: bytes,
    store,
    project_slug: str,
) -> DocumentResponse:
    """1-2 call extraction pipeline: detect feature, conditionally extract message mappings."""
    from datetime import datetime

    logger.info("=== Pipeline started: '%s' (%.1fKB) ===", filename, len(pdf_bytes) / 1024)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    # Generate document slug
    doc_slug = store.make_doc_slug(project_slug, filename)

    now_iso = datetime.now(UTC).isoformat()
    doc_data = {
        "slug": doc_slug,
        "project_slug": project_slug,
        "filename": filename,
        "pdf_size_bytes": len(pdf_bytes),
        "uploaded_at": now_iso,
        "status": "processing",
        "error_message": None,
        "feature_count": 0,
    }
    await store.save_document(project_slug, doc_data)

    client = _get_client()
    model = settings.claude_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    extraction_system_prompt = build_system_prompt(
        base="",
        global_rules=global_rules.get("extraction", ""),
        project_rules=project_rules.get("extraction", ""),
    )

    try:
        # Call 1: Feature detection (structured, via tool_use)
        detected = await _detect_feature(pdf_b64, client, model, extraction_system_prompt)

        feature_data = {
            "name": detected.name,
            "source_document": doc_slug,
            "type": detected.type.value,
            "confidence": detected.confidence,
            "summary": detected.summary,
            "method": detected.method,
            "endpoint": detected.endpoint,
            "dependencies_json": detected.dependencies,
            "structured_logic_json": detected.structured_logic.model_dump(),
            "status": "detected",
            "error_message": None,
            "extracted_at": None,
        }
        await store.save_feature(project_slug, feature_data)

        doc_data["feature_count"] = 1
        doc_data["status"] = "extracting"
        await store.save_document(project_slug, doc_data)

        # Upsert dependency stubs
        try:
            for dep in detected.structured_logic.used_dependencies:
                dep_name = _normalize_dep_name(dep.name)
                await store.upsert_dependency(
                    project_slug=project_slug,
                    dep_type=dep.type,
                    name=dep_name,
                    data={
                        "dep_type": dep.type,
                        "name": dep_name,
                        "description": dep.description,
                        "enrichment_status": "stub",
                        "enriched_data": None,
                        "source_pdf_name": filename,
                        "enriched_at": None,
                        "created_at": now_iso,
                        "method": dep.method,
                        "service_name": dep.service_name,
                        "path": dep.path,
                    },
                )
        except Exception as exc:
            logger.warning("Stub upsert failed (non-fatal): %s", exc)

        # Call 2 (conditional): Message mapping extraction
        steps_with_mapping = _collect_steps_with_mapping(
            detected.structured_logic.logic_steps
        )

        if steps_with_mapping:
            mapping_results = await _extract_message_mappings(
                pdf_b64, detected, steps_with_mapping, client, model, extraction_system_prompt
            )
            mappings_by_step = {r.step_number: r for r in mapping_results}
            _merge_mappings_into_steps(
                detected.structured_logic.logic_steps, mappings_by_step
            )
            # Post-processing: propagate is_collection from child cardinality
            def _walk_steps_for_propagation(steps) -> None:
                for step in steps:
                    if step.message_mapping:
                        _propagate_is_collection(step.message_mapping)
                    _walk_steps_for_propagation(step.children)
            _walk_steps_for_propagation(detected.structured_logic.logic_steps)
            feature_data["structured_logic_json"] = detected.structured_logic.model_dump()
        else:
            logger.info("[Call 2] Skipped — no steps with has_detailed_mapping=True")

        feature_data["status"] = "done"
        feature_data["extracted_at"] = datetime.now(UTC).isoformat()
        await store.save_feature(project_slug, feature_data)

        doc_data["status"] = "done"
        await store.save_document(project_slug, doc_data)
        logger.info("=== Pipeline finished: '%s' → done ===", filename)

    except Exception as exc:
        logger.error("Extraction pipeline failed for %s: %s", filename, exc)
        doc_data["status"] = "error"
        doc_data["error_message"] = str(exc)
        await store.save_document(project_slug, doc_data)
        raise

    features = await store.list_features(project_slug)
    from datetime import datetime as dt
    uploaded_at_val = doc_data.get("uploaded_at")
    if isinstance(uploaded_at_val, str):
        uploaded_at_val = dt.fromisoformat(uploaded_at_val)

    return DocumentResponse(
        slug=doc_data["slug"],
        project_slug=project_slug,
        filename=doc_data["filename"],
        status=doc_data["status"],
        pdf_size_bytes=doc_data["pdf_size_bytes"],
        feature_count=doc_data["feature_count"],
        features=[_feature_dict_to_response(f) for f in features],
        uploaded_at=uploaded_at_val,
        error_message=doc_data.get("error_message"),
    )
