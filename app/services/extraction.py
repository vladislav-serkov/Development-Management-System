import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.extraction import DETECT_FEATURE_PROMPT
from app.services.claude_client import call_claude, log_cache_stats
from app.services.rules import build_system_prompt
from app.schemas.extraction import (
    DetectedFeature,
    FeatureDetectionResult,
    GenericTable,
)

logger = logging.getLogger(__name__)


def _normalize_dep_name(name: str) -> str:
    """Normalize dependency name: trim whitespace, spaces to underscores. Preserves original case."""
    return name.strip().replace(" ", "_")


def _build_document_block(text: str, cache: bool = False) -> dict:
    """Plain-text document block for Claude (markdown from Confluence)."""
    block = {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": text},
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def _strip_doc_refs(steps, removed: set[str]) -> None:
    for step in steps:
        if step.external_doc_refs:
            step.external_doc_refs = [r for r in step.external_doc_refs if r not in removed]
        _strip_doc_refs(step.children, removed)


def _dedupe_external_docs(structured_logic) -> list[str]:
    """Drop external_doc deps that duplicate an executable dependency.

    Claude sometimes records one linked page twice: as external_api and as
    external_doc (page title "getWallet.do — Получение клиента" vs path
    "/api/{partner}/getWallet.do"). Keep the executable entry, drop the doc
    stub and its external_doc_refs in steps.
    """
    exec_by_key: dict[str, object] = {}
    for dep in structured_logic.used_dependencies:
        if dep.type == "external_doc":
            continue
        for token in (dep.name, dep.path):
            seg = (token or "").rstrip("/").split("/")[-1]
            if len(seg) >= 4:
                exec_by_key[seg.lower()] = dep

    removed = []
    for dep in structured_logic.used_dependencies:
        if dep.type != "external_doc":
            continue
        match = next((d for k, d in exec_by_key.items() if k in dep.name.lower()), None)
        if match is not None:
            removed.append(dep.name)
            # Doc dup carries the link to the page describing the executable dep —
            # keep it for auto-enrichment instead of losing it with the dup.
            if not match.source_doc_title:
                match.source_doc_title = dep.source_doc_title or dep.name
    if removed:
        removed_set = set(removed)
        structured_logic.used_dependencies = [
            dep for dep in structured_logic.used_dependencies if dep.name not in removed_set
        ]
        _strip_doc_refs(structured_logic.logic_steps, removed_set)
    return removed


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


def _apply_table_mappings(steps, tables_by_id: dict[str, dict]) -> list[str]:
    """Fill message_mapping from parsed document tables for steps that reference
    [TABLE:Tn] markers. Returns filled step numbers.

    A referenced table that doesn't parse as a field mapping is preserved
    verbatim in the step's reference_tables — no LLM fallback.
    """
    from app.services.table_mapping import table_to_message_fields

    filled: list[str] = []
    for step in steps:
        if step.mapping_table_ids and not step.message_mapping:
            fields = []
            for tid in step.mapping_table_ids:
                table = tables_by_id.get(tid.strip().upper())
                if table is None:
                    logger.warning("Step %s references unknown table id %s", step.number, tid)
                    continue
                parsed = table_to_message_fields(table)
                if parsed is None:
                    logger.warning("Table %s (step %s) is not a parseable mapping — kept verbatim in reference_tables", tid, step.number)
                    step.reference_tables.append(
                        GenericTable(caption=None, headers=table["headers"], rows=table["rows"])
                    )
                    continue
                fields.extend(parsed)
            if fields:
                _propagate_is_collection(fields)
                step.message_mapping = fields
                step.has_detailed_mapping = True
                filled.append(step.number)
        filled.extend(_apply_table_mappings(step.children, tables_by_id))
    return filled


async def _detect_features(
    doc_content: str,
    model: str,
    system_prompt: str = "",
) -> list[DetectedFeature]:
    """Detect one or more features via tool_use.

    Usually returns a single-element list for kafka_consumer/rest_endpoint, but may
    return multiple for scheduled_task documents that describe N independent tasks.
    """
    logger.info("[Detect] Detecting features (model=%s, doc_size=%.1fKB)", model, len(doc_content) / 1024)
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
                    _build_document_block(doc_content, cache=True),
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
        logger.warning("[Detect] Claude returned empty features list: %s", tool_input)
        raise ValueError(
            "Claude не смог извлечь ни одной feature из документа. "
            "Возможно, документ не содержит технического задания."
        )

    result = FeatureDetectionResult.model_validate(tool_input)
    logger.info(
        "[Detect] Detected %d feature(s): %s",
        len(result.features),
        [(f.name, f.type.value) for f in result.features],
    )
    log_cache_stats(response.usage, "detect_features")
    return result.features


async def _process_single_feature(
    detected: DetectedFeature,
    filename: str,
    doc_slug: str,
    project_slug: str,
    store,
    now_iso: str,
    tables_by_id: dict[str, dict],
) -> None:
    """Fill mappings from document tables, save the feature, upsert dependency stubs.

    Raises on fatal errors; caller decides per-feature rollback.
    """
    removed_docs = _dedupe_external_docs(detected.structured_logic)
    if removed_docs:
        logger.info("Dropped %d duplicate external_doc dep(s) for '%s': %s", len(removed_docs), detected.name, removed_docs)

    if tables_by_id:
        filled = _apply_table_mappings(detected.structured_logic.logic_steps, tables_by_id)
        if filled:
            logger.info("Deterministic mappings for '%s': %d step(s) %s", detected.name, len(filled), filled)

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
        "status": "done",
        "extracted_at": datetime.now(UTC).isoformat(),
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
                    "source_doc_title": dep.source_doc_title,
                },
            )
    except Exception as exc:
        logger.warning("Stub upsert failed for '%s' (non-fatal): %s", detected.name, exc)


async def run_extraction_pipeline(
    filename: str,
    text_content: str,
    store,
    project_slug: str,
    doc_slug: str = "",
    tables: list[dict] | None = None,
) -> None:
    """Extraction pipeline for one document (markdown text) = one or more features.

    `tables` — parsed table grids matching [TABLE:Tn] markers in text_content;
    message mappings are built from them deterministically, without an LLM call.

    Designed to run as a background task (asyncio.create_task).
    The document record must already exist in storage before calling this.

    Contract:
      - Claude detects N features (1 for kafka/rest, N for scheduled_task docs).
      - For each feature: fill mappings from tables, save, upsert dependency stubs.
      - Per-feature failure is isolated: that feature is deleted, others continue.
      - Document status:
          • All features succeeded → "done".
          • Some succeeded, some failed → "partial" (error_message lists failures).
          • All failed or detection itself failed → "error".
    """
    tables_by_id = {t["id"].upper(): t for t in (tables or [])}

    logger.info(
        "=== Pipeline started: '%s' (%.1fKB, tables=%d) ===",
        filename, len(text_content) / 1024, len(tables_by_id),
    )
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
        detected_features = await _detect_features(text_content, model, extraction_system_prompt)
    except Exception as exc:
        logger.error("Feature detection failed for %s: %s", filename, exc)
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
                filename=filename,
                doc_slug=doc_slug,
                project_slug=project_slug,
                store=store,
                now_iso=now_iso,
                tables_by_id=tables_by_id,
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
