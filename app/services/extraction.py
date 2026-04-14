import base64
import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.extraction import DETECT_FEATURE_PROMPT, build_mapping_prompt
from app.services.claude_client import call_claude, log_cache_stats
from app.services.rules import build_system_prompt
from app.schemas.extraction import (
    DetectedFeature,
    MappingExtractionBatch,
    MappingExtractionResult,
)

logger = logging.getLogger(__name__)


def _normalize_dep_name(name: str) -> str:
    """Normalize dependency name for cross-feature matching."""
    return name.lower().replace(" ", "_")


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

    response = await call_claude(
        label="detect_feature",
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
    log_cache_stats(response.usage, "detect_feature")
    return result


MAPPING_BATCH_SIZE = 7
MAPPING_MAX_RETRIES = 2


async def _extract_mapping_batch(
    pdf_b64: str,
    feature: DetectedFeature,
    steps_batch: list[str],
    batch_idx: int,
    model: str,
    system_prompt: str = "",
) -> list[MappingExtractionResult]:
    """Single Call 2 request for a batch of steps, with one retry on empty response."""
    tool = {
        "name": "extract_message_mappings",
        "description": "Extract structured message field mappings for specified steps",
        "input_schema": MappingExtractionBatch.model_json_schema(),
    }
    steps_list = ", ".join(steps_batch)
    create_kwargs: dict = dict(
        model=model,
        max_tokens=32768,
        tools=[tool],
        tool_choice={"type": "tool", "name": "extract_message_mappings"},
    )
    if system_prompt:
        create_kwargs["system"] = system_prompt

    for attempt in range(1, MAPPING_MAX_RETRIES + 1):
        label = f"[Call 2.{batch_idx} attempt {attempt}/{MAPPING_MAX_RETRIES}]"
        logger.info("%s steps: %s", label, steps_batch)

        response = await call_claude(
            label=f"mapping_batch:{feature.name}:b{batch_idx}",
            **create_kwargs,
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
        log_cache_stats(response.usage, f"message_mappings:{feature.name}:b{batch_idx}")

        tool_block = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                tool_block = block
                break

        if tool_block is None or not tool_block.input or not tool_block.input.get("mappings"):
            logger.warning("%s empty response for '%s': %s", label, feature.name, getattr(tool_block, "input", None))
            if attempt < MAPPING_MAX_RETRIES:
                continue
            return []

        batch = MappingExtractionBatch.model_validate(tool_block.input)
        logger.info("%s extracted %d mapping(s) for '%s'", label, len(batch.mappings), feature.name)
        return batch.mappings

    return []


async def _extract_message_mappings(
    pdf_b64: str,
    feature: DetectedFeature,
    steps_with_mapping: list[str],
    model: str,
    system_prompt: str = "",
) -> list[MappingExtractionResult]:
    """Call 2: extract message field mappings, batched by MAPPING_BATCH_SIZE steps per request."""
    batches = [
        steps_with_mapping[i:i + MAPPING_BATCH_SIZE]
        for i in range(0, len(steps_with_mapping), MAPPING_BATCH_SIZE)
    ]
    logger.info(
        "[Call 2] Extracting mappings for '%s': %d steps → %d batch(es)",
        feature.name, len(steps_with_mapping), len(batches),
    )

    import asyncio
    batch_results = await asyncio.gather(*(
        _extract_mapping_batch(pdf_b64, feature, batch, idx, model, system_prompt)
        for idx, batch in enumerate(batches, 1)
    ))
    all_mappings: list[MappingExtractionResult] = []
    for results in batch_results:
        all_mappings.extend(results)

    logger.info("[Call 2] Total: %d mapping(s) for '%s'", len(all_mappings), feature.name)
    return all_mappings


async def run_extraction_pipeline(
    filename: str,
    pdf_bytes: bytes,
    store,
    project_slug: str,
    doc_slug: str = "",
) -> None:
    """1-2 call extraction pipeline: detect feature, conditionally extract message mappings.

    Designed to run as a background task (asyncio.create_task).
    The document record must already exist in storage before calling this.
    """
    from datetime import datetime

    logger.info("=== Pipeline started: '%s' (%.1fKB) ===", filename, len(pdf_bytes) / 1024)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    now_iso = datetime.now(UTC).isoformat()

    # Load existing document record (created by upload endpoint)
    if not doc_slug:
        doc_slug = store.make_doc_slug(project_slug, filename)
    doc_data = await store.get_document(project_slug, doc_slug)
    if doc_data is None:
        logger.error("Document record not found for %s/%s", project_slug, doc_slug)
        return

    model = settings.claude_model
    feature_data: dict = {}

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    extraction_system_prompt = build_system_prompt(
        base="",
        global_rules=global_rules.get("extraction", ""),
        project_rules=project_rules.get("extraction", ""),
    )

    try:
        # Call 1: Feature detection (structured, via tool_use)
        detected = await _detect_feature(pdf_b64, model, extraction_system_prompt)

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
            "status": "extracting",
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
            try:
                mapping_results = await _extract_message_mappings(
                    pdf_b64, detected, steps_with_mapping, model, extraction_system_prompt
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
            except Exception as exc:
                logger.warning(
                    "[Call 2] Message mapping extraction failed for '%s' (partial success): %s",
                    detected.name, exc,
                )
                feature_data["error_message"] = f"Маппинги не извлечены: {exc}"
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
        # If feature was already created by Call 1, mark it as error too
        if feature_data.get("name"):
            try:
                feature_data["status"] = "error"
                feature_data["error_message"] = str(exc)
                await store.save_feature(project_slug, feature_data)
            except Exception:
                pass
