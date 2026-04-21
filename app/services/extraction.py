import base64
import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.extraction import (
    DETECT_FEATURE_PROMPT,
    build_mapping_prompt,
    _collect_step_texts,
    _collect_dep_texts,
)
from app.services.claude_client import call_claude, log_cache_stats
from app.services.rules import build_system_prompt
from app.schemas.extraction import (
    DetectedFeature,
    FeatureDetectionResult,
    MappingExtractionBatch,
    MappingExtractionResult,
)

logger = logging.getLogger(__name__)


def _normalize_dep_name(name: str) -> str:
    """Normalize dependency name: trim whitespace, spaces to underscores. Preserves original case."""
    return name.strip().replace(" ", "_")



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
    """Recursively merge MappingExtractionResult.fields into matching LogicStep.message_mapping.

    mappings_by_step maps step_number → list[MappingExtractionResult].
    When multiple mappings exist for one step (e.g. UPDATE table_a + INSERT table_b),
    all fields are concatenated — but duplicates (same message_type) are skipped.
    """
    for step in steps:
        if step.number in mappings_by_step:
            all_fields = []
            seen_types: set[str] = set()
            type_names: list[str] = []
            for mapping in mappings_by_step[step.number]:
                if mapping.message_type in seen_types:
                    continue
                seen_types.add(mapping.message_type)
                type_names.append(mapping.message_type)
                all_fields.extend(mapping.fields)
            step.message_mapping = all_fields
            step.message_type = type_names[0] if len(type_names) == 1 else ", ".join(type_names)
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


async def _detect_features(
    pdf_b64: str,
    model: str,
    system_prompt: str = "",
) -> list[DetectedFeature]:
    """Call 1: detect one or more features via tool_use (PDF cached for subsequent calls).

    Usually returns a single-element list for kafka_consumer/rest_endpoint, but may
    return multiple for scheduled_task documents that describe N independent tasks.
    """
    logger.info("[Call 1] Detecting features (model=%s, pdf_size=%.1fKB)", model, len(pdf_b64) * 3 / 4 / 1024)
    tool = {
        "name": "detect_features",
        "description": "Extract one or more features from the technical specification",
        "input_schema": FeatureDetectionResult.model_json_schema(),
    }

    create_kwargs: dict = dict(
        model=model,
        max_tokens=16384,
        tools=[tool],
        tool_choice={"type": "tool", "name": "detect_features"},
    )
    if system_prompt:
        create_kwargs["system"] = system_prompt

    response = await call_claude(
        label="detect_features",
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
    features_input = (tool_input or {}).get("features") or []
    if not features_input:
        logger.warning("[Call 1] Claude returned empty features list: %s", tool_input)
        raise ValueError(
            "Claude не смог извлечь ни одной feature из документа. "
            "Возможно, PDF нечитаем или не содержит технического задания."
        )

    result = FeatureDetectionResult.model_validate(tool_input)
    logger.info(
        "[Call 1] Detected %d feature(s): %s",
        len(result.features),
        [(f.name, f.type.value) for f in result.features],
    )
    log_cache_stats(response.usage, "detect_features")
    return result.features


MAPPING_BATCH_SIZE = 7
MAPPING_MAX_RETRIES = 2


async def _extract_mapping_batch(
    pdf_b64: str,
    feature: DetectedFeature,
    steps_batch: list[str],
    batch_idx: int,
    model: str,
    system_prompt: str = "",
    step_texts: list[str] | None = None,
    dep_texts: list[str] | None = None,
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
                            "text": build_mapping_prompt(
                                feature.name, feature.type.value, steps_list,
                                step_texts=step_texts, dep_texts=dep_texts,
                            ),
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

    # Collect context from Call 1 to pass into Call 2
    step_texts = _collect_step_texts(feature.structured_logic.logic_steps)
    dep_texts = _collect_dep_texts(feature.structured_logic.used_dependencies)

    import asyncio
    batch_results = await asyncio.gather(*(
        _extract_mapping_batch(
            pdf_b64, feature, batch, idx, model, system_prompt,
            step_texts=step_texts, dep_texts=dep_texts,
        )
        for idx, batch in enumerate(batches, 1)
    ))
    all_mappings: list[MappingExtractionResult] = []
    for results in batch_results:
        all_mappings.extend(results)

    logger.info("[Call 2] Total: %d mapping(s) for '%s'", len(all_mappings), feature.name)
    return all_mappings


async def _process_single_feature(
    detected: DetectedFeature,
    pdf_b64: str,
    filename: str,
    doc_slug: str,
    project_slug: str,
    store,
    model: str,
    system_prompt: str,
    now_iso: str,
) -> None:
    """Save a single feature, upsert its dependency stubs, run Call 2, save again.

    Raises on fatal errors; caller decides per-feature rollback.
    """
    feature_data = {
        "name": detected.name,
        "display_name": detected.display_name,
        "source_document": doc_slug,
        "type": detected.type.value,
        "confidence": detected.confidence,
        "summary": detected.summary,
        "method": detected.method,
        "endpoint": detected.endpoint,
        "schedule": detected.schedule,
        "dependencies_json": detected.dependencies,
        "structured_logic_json": detected.structured_logic.model_dump(),
        "status": "extracting",
        "extracted_at": None,
    }
    await store.save_feature(project_slug, feature_data)

    # Upsert dependency stubs (non-fatal)
    try:
        for dep in detected.structured_logic.used_dependencies:
            # external_doc names are arbitrary document titles (spaces, case preserved)
            # referenced verbatim from logic_steps.external_doc_refs — must not normalize,
            # otherwise the UI link "ref → dep" silently breaks.
            dep_name = dep.name if dep.type == "external_doc" else _normalize_dep_name(dep.name)
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
        logger.warning("Stub upsert failed for '%s' (non-fatal): %s", detected.name, exc)

    # Call 2 (conditional): Message mapping extraction
    steps_with_mapping = _collect_steps_with_mapping(detected.structured_logic.logic_steps)

    if steps_with_mapping:
        mapping_results = await _extract_message_mappings(
            pdf_b64, detected, steps_with_mapping, model, system_prompt
        )
        from collections import defaultdict
        mappings_by_step: dict[str, list] = defaultdict(list)
        for r in mapping_results:
            mappings_by_step[r.step_number].append(r)
        _merge_mappings_into_steps(detected.structured_logic.logic_steps, mappings_by_step)

        def _walk_steps_for_propagation(steps) -> None:
            for step in steps:
                if step.message_mapping:
                    _propagate_is_collection(step.message_mapping)
                _walk_steps_for_propagation(step.children)
        _walk_steps_for_propagation(detected.structured_logic.logic_steps)
        feature_data["structured_logic_json"] = detected.structured_logic.model_dump()
    else:
        logger.info("[Call 2] Skipped for '%s' — no steps with has_detailed_mapping=True", detected.name)

    feature_data["status"] = "done"
    feature_data["extracted_at"] = datetime.now(UTC).isoformat()
    await store.save_feature(project_slug, feature_data)


async def run_extraction_pipeline(
    filename: str,
    pdf_bytes: bytes,
    store,
    project_slug: str,
    doc_slug: str = "",
) -> None:
    """Extraction pipeline for one PDF = one or more features.

    Designed to run as a background task (asyncio.create_task).
    The document record must already exist in storage before calling this.

    Contract:
      - Call 1 detects N features (1 for kafka/rest, N for scheduled_task docs).
      - For each feature: save stub, run Call 2, save with mappings.
      - Per-feature failure is isolated: that feature is deleted, others continue.
      - Document status:
          • All features succeeded → "done".
          • Some succeeded, some failed → "partial" (error_message lists failures).
          • All failed or Call 1 itself failed → "error".
    """
    from datetime import datetime

    logger.info("=== Pipeline started: '%s' (%.1fKB) ===", filename, len(pdf_bytes) / 1024)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    now_iso = datetime.now(UTC).isoformat()

    if not doc_slug:
        doc_slug = store.make_doc_slug(project_slug, filename)
    doc_data = await store.get_document(project_slug, doc_slug)
    if doc_data is None:
        logger.error("Document record not found for %s/%s", project_slug, doc_slug)
        return

    task = await store.create_task(
        project_slug,
        kind="extraction",
        target_type="document",
        target_id=doc_slug,
    )

    model = settings.claude_model
    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    extraction_system_prompt = build_system_prompt(
        base="",
        global_rules=global_rules.get("extraction", ""),
        project_rules=project_rules.get("extraction", ""),
    )

    try:
        detected_features = await _detect_features(pdf_b64, model, extraction_system_prompt)
    except Exception as exc:
        logger.error("Extraction Call 1 failed for %s: %s", filename, exc)
        doc_data["status"] = "error"
        doc_data["error_message"] = str(exc)
        doc_data["feature_count"] = 0
        await store.save_document(project_slug, doc_data)
        await store.finish_task(project_slug, task["id"], status="error", error_message=str(exc))
        return

    doc_data["feature_count"] = len(detected_features)
    doc_data["status"] = "extracting"
    doc_data["error_message"] = None
    await store.save_document(project_slug, doc_data)

    succeeded: list[str] = []
    failures: list[tuple[str, str]] = []

    for detected in detected_features:
        try:
            await _process_single_feature(
                detected=detected,
                pdf_b64=pdf_b64,
                filename=filename,
                doc_slug=doc_slug,
                project_slug=project_slug,
                store=store,
                model=model,
                system_prompt=extraction_system_prompt,
                now_iso=now_iso,
            )
            succeeded.append(detected.name)
        except Exception as exc:
            logger.error("Feature '%s' failed: %s", detected.name, exc)
            failures.append((detected.name, str(exc)))
            try:
                await store.delete_feature(project_slug, detected.name)
            except Exception as del_exc:
                logger.warning("Rollback of feature '%s' failed: %s", detected.name, del_exc)

    # required_sync after at least one success (non-fatal)
    if succeeded:
        try:
            from app.services.required_sync import sync_required_after_enrichment
            by_type = await store.list_dependencies(project_slug)
            for dep_type, deps in by_type.items():
                for dep in deps:
                    enriched = dep.get("enriched_data")
                    if enriched and dep.get("enrichment_status") == "enriched":
                        await sync_required_after_enrichment(
                            project_slug=project_slug,
                            dep_type=dep_type,
                            dep_name=dep["name"],
                            enriched_data=enriched,
                            store=store,
                        )
        except Exception as sync_exc:
            logger.warning("required_sync after extraction failed (non-fatal): %s", sync_exc)

    doc_data["feature_count"] = len(succeeded)
    if not succeeded:
        doc_data["status"] = "error"
        doc_data["error_message"] = "; ".join(f"{n}: {e}" for n, e in failures) or "no features succeeded"
        task_status, task_error = "error", doc_data["error_message"]
    elif failures:
        doc_data["status"] = "partial"
        doc_data["error_message"] = "; ".join(f"{n}: {e}" for n, e in failures)
        task_status, task_error = "done", None
    else:
        doc_data["status"] = "done"
        doc_data["error_message"] = None
        task_status, task_error = "done", None

    await store.save_document(project_slug, doc_data)
    await store.finish_task(project_slug, task["id"], status=task_status, error_message=task_error)
    logger.info(
        "=== Pipeline finished: '%s' → %s (succeeded=%d, failed=%d) ===",
        filename, doc_data["status"], len(succeeded), len(failures),
    )
