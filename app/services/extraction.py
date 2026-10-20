import difflib
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import settings
from app.prompts.extraction import DETECT_FEATURE_PROMPT
from app.schemas.extraction import (
    DetectedFeature,
    FeatureDetectionResult,
    GenericTable,
)
from app.services.claude_client import call_claude, log_cache_stats, parse_tool_input
from app.services.rules import build_system_prompt
from app.services.spec_diff import compute_spec_diff, merge_reextracted_feature

logger = logging.getLogger(__name__)


def _normalize_dep_name(name: str) -> str:
    """Normalize dependency name: trim whitespace, spaces to underscores. Preserves original case."""
    return name.strip().replace(" ", "_")


# Dotted identifiers like Kafka topics: at least three dot-separated segments
_DOTTED_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}\b")
# URL-ish paths like /v1/credit-line or /api/orders/{id}
_PATH_TOKEN_RE = re.compile(r"(?<![\w.])/(?:[\w.-]+|\{[\w.-]+\})(?:/(?:[\w.-]+|\{[\w.-]+\}))+")


def _enforce_spec_identity(
    detected: DetectedFeature,
    *,
    title: str,
    text: str,
    tables: list[dict] | None,
) -> str | None:
    """Feature identity must be verbatim from the spec, never invented by the LLM:
    the Kafka topic / REST path the model claims has to literally occur in the
    document (title, body or tables). If it doesn't, replace it with the closest
    real token from the spec. Returns a warning string when a correction happened.

    scheduled_task names are semantic slugs by design and are not touched
    (their verbatim identity lives in display_name).
    """
    ftype = detected.type.value if hasattr(detected.type, "value") else str(detected.type)
    corpus = "\n".join([title or "", text or "", json.dumps(tables or [], ensure_ascii=False)])

    if ftype == "kafka_consumer":
        claimed = (detected.endpoint or detected.name or "").strip()
        candidates = list(dict.fromkeys(_DOTTED_TOKEN_RE.findall(corpus)))
        if claimed and claimed in candidates:
            detected.name = claimed
            detected.endpoint = claimed
            return None
        best = None
        if claimed and candidates:
            matches = difflib.get_close_matches(claimed, candidates, n=1, cutoff=0.6)
            best = matches[0] if matches else None
        if best is None:
            # A Kafka spec page is conventionally titled with the topic name
            title_tokens = _DOTTED_TOKEN_RE.findall(title or "")
            best = title_tokens[0] if title_tokens else None
        if best is None:
            return f"kafka topic '{claimed}' не найден в тексте ТЗ (оставлен как есть)"
        detected.name = best
        detected.endpoint = best
        return f"kafka topic '{claimed}' не найден в ТЗ — заменён на '{best}'"

    if ftype == "rest_endpoint":
        claimed = (detected.endpoint or "").strip()
        candidates = list(dict.fromkeys(_PATH_TOKEN_RE.findall(corpus)))
        path = claimed if claimed and claimed in candidates else None
        if path is None and claimed and candidates:
            matches = difflib.get_close_matches(claimed, candidates, n=1, cutoff=0.6)
            path = matches[0] if matches else None
        if path is None:
            return f"REST path '{claimed}' не найден в тексте ТЗ (оставлен как есть)" if claimed else None
        canonical = f"{detected.method} {path}".strip() if detected.method else path
        changed = path != claimed or detected.name != canonical
        detected.endpoint = path
        detected.name = canonical
        return f"REST path '{claimed}' не найден в ТЗ — заменён на '{path}'" if changed and path != claimed else None

    return None


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
            if not match.link_ids:
                match.link_ids = dep.link_ids
            if not match.source_doc_title:
                match.source_doc_title = dep.source_doc_title or dep.name
    if removed:
        removed_set = set(removed)
        structured_logic.used_dependencies = [
            dep for dep in structured_logic.used_dependencies if dep.name not in removed_set
        ]
        _strip_doc_refs(structured_logic.logic_steps, removed_set)
    return removed


def _link_stable_key(link: dict) -> str | None:
    """Version-independent identity of a link target.

    [LINK:Ln] ids are numbered per parse and shift when links are added to the
    page; the target page they point at does not. The spec diff matches
    dependencies across versions by these keys."""
    page_id = str(link.get("page_id") or "").strip()
    if page_id:
        return f"page:{page_id}"
    title = " ".join(str(link.get("title") or "").split()).lower()
    if not title:
        return None
    space = str(link.get("space_key") or "").upper()
    anchor = str(link.get("anchor") or "").strip()
    return f"title:{space}/{title}#{anchor}"


def _annotate_dep_link_keys(structured_logic: dict, links_by_id: dict[str, dict]) -> None:
    """Resolve each dependency's [LINK:Ln] ids to stable target keys, stored
    as ``link_keys`` next to ``link_ids`` inside structured_logic_json."""
    for dep in structured_logic.get("used_dependencies") or []:
        keys = []
        for link_id in dep.get("link_ids") or []:
            link = links_by_id.get(str(link_id).strip())
            key = _link_stable_key(link) if link else None
            if key:
                keys.append(key)
        if keys:
            dep["link_keys"] = list(dict.fromkeys(keys))


def _build_link_resolver(used_dependencies) -> Callable[[str], tuple[str, str] | None]:
    """[LINK:Ln] → the dependency Claude attached that link to.

    Both sides key off the same marker ids, so a source cell linking to the
    "[flp-credit-line] DB" page resolves to the exact db_table dependency without
    any name matching.
    """
    by_link: dict[str, tuple[str, str]] = {}
    for dep in used_dependencies:
        dep_name = dep.name if dep.type == "external_doc" else _normalize_dep_name(dep.name)
        for link_id in dep.link_ids:
            by_link.setdefault(link_id, (dep.type, dep_name))
    return by_link.get


def _resolve_spec_tables(structured_logic, tables_by_id: dict[str, dict], resolve_link=None) -> None:
    """Replace LLM table references in input_tables/response_tables with tables
    parsed verbatim from the document grids.

    The LLM only classified the tables (which id belongs to which section, plus
    status codes for responses); the columns and rows come from the parsed grid.
    LLM entries without a table_id are the inline fallback for documents without
    [TABLE:Tn] markers and are kept as-is when they carry fields.
    """
    from app.services.table_mapping import table_to_spec_table

    for attr in ("input_tables", "response_tables"):
        resolved = []
        for entry in getattr(structured_logic, attr):
            tid = (entry.table_id or "").strip().upper()
            if tid and tid in tables_by_id:
                parsed = table_to_spec_table(
                    tables_by_id[tid], resolve_link=resolve_link, require_typed=False,
                )
                if parsed is not None:
                    # Caption-derived status codes win; the LLM's value fills the gap
                    # when the heading above the table names none.
                    if entry.status_codes and not parsed.status_codes:
                        parsed.status_codes = entry.status_codes
                    resolved.append(parsed)
                    continue
                logger.warning("Table %s (%s) did not parse as a field table — dropped", tid, attr)
            elif tid:
                logger.warning("%s references unknown table id %s", attr, tid)
            if entry.fields:
                resolved.append(entry)
        setattr(structured_logic, attr, resolved)


def _apply_table_mappings(steps, tables_by_id: dict[str, dict], resolve_link=None) -> list[str]:
    """Fill mapping_tables from parsed document tables for steps that reference
    [TABLE:Tn] markers. Returns filled step numbers.

    A referenced table that doesn't parse as a field mapping is preserved
    verbatim in the step's reference_tables — no LLM fallback.
    """
    from app.services.table_mapping import table_to_spec_table

    filled: list[str] = []
    for step in steps:
        if step.mapping_table_ids and not step.mapping_tables:
            spec_tables = []
            for tid in step.mapping_table_ids:
                table = tables_by_id.get(tid.strip().upper())
                if table is None:
                    logger.warning("Step %s references unknown table id %s", step.number, tid)
                    continue
                parsed = table_to_spec_table(table, resolve_link=resolve_link)
                if parsed is None:
                    logger.warning("Table %s (step %s) is not a parseable mapping — kept verbatim in reference_tables", tid, step.number)
                    step.reference_tables.append(
                        GenericTable(caption=None, headers=table["headers"], rows=table["rows"])
                    )
                    continue
                spec_tables.append(parsed)
            if spec_tables:
                step.mapping_tables = spec_tables
                step.has_detailed_mapping = True
                filled.append(step.number)
        filled.extend(_apply_table_mappings(step.children, tables_by_id, resolve_link))
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
        max_tokens=settings.extraction_max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": "detect_features"},
        # NOTE: current Claude models (Sonnet 5 / Opus 5+) removed the sampling
        # params (temperature/top_p/top_k return 400), so run-to-run extraction
        # variance cannot be pinned at the API level. The spec diff neutralizes
        # it structurally instead (see app/services/spec_diff.py).
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

    if response.stop_reason == "max_tokens":
        # The tool_use block is cut off mid-JSON: its input is empty or partial, which
        # would otherwise surface as the misleading "Claude извлёк 0 features".
        raise ValueError(
            f"Ответ Claude обрезан лимитом в {settings.extraction_max_tokens} токенов "
            f"(документ слишком большой). Увеличьте EXTRACTION_MAX_TOKENS или разбейте документ."
        )

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        raise ValueError("No tool_use block in Claude response")

    try:
        result = parse_tool_input(FeatureDetectionResult, tool_block.input or {})
    except ValidationError:
        logger.warning("[Detect] Unparseable tool input: %s", str(tool_block.input)[:500])
        result = None
    if result is None or not result.features:
        raise ValueError(
            "Claude не смог извлечь ни одной feature из документа. "
            "Возможно, документ не содержит технического задания."
        )
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
    prior_feature: dict | None = None,
    links_by_id: dict[str, dict] | None = None,
) -> None:
    """Fill mappings from document tables, save the feature, upsert dependency stubs.

    ``prior_feature`` — the stored record from before re-extraction; its
    analysis state (counts, impl/autotest status, stale flags) is carried over
    so a re-import doesn't erase it.

    Raises on fatal errors; caller decides per-feature rollback.
    """
    removed_docs = _dedupe_external_docs(detected.structured_logic)
    if removed_docs:
        logger.info("Dropped %d duplicate external_doc dep(s) for '%s': %s", len(removed_docs), detected.name, removed_docs)

    resolve_link = _build_link_resolver(detected.structured_logic.used_dependencies)
    if tables_by_id:
        filled = _apply_table_mappings(
            detected.structured_logic.logic_steps, tables_by_id, resolve_link
        )
        if filled:
            logger.info("Deterministic mappings for '%s': %d step(s) %s", detected.name, len(filled), filled)

    _resolve_spec_tables(detected.structured_logic, tables_by_id, resolve_link)

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
    if links_by_id:
        _annotate_dep_link_keys(feature_data["structured_logic_json"], links_by_id)
    await store.save_feature(project_slug, merge_reextracted_feature(prior_feature, feature_data))

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
                    "link_ids": dep.link_ids,
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
    prev_confluence_version: int | None = None,
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
        doc_slug = await store.make_doc_slug(project_slug, filename)
    doc_data = await store.get_document(project_slug, doc_slug)
    if doc_data is None:
        logger.error("Document record not found for %s/%s", project_slug, doc_slug)
        return

    # Stable link targets for dependency identity across spec versions
    links_by_id: dict[str, dict] = {}
    try:
        source = await store.get_document_source(project_slug, doc_slug)
        if source:
            links_by_id = {str(l.get("id")): l for l in source.get("links") or [] if l.get("id")}
    except Exception as exc:
        logger.warning("Loading document source links failed (non-fatal): %s", exc)

    # Snapshot this document's features before re-extraction: the source of the
    # spec diff and of the analysis state carried over per feature.
    prior_features = {
        f["name"]: f
        for f in await store.list_features(project_slug)
        if f.get("source_document") == doc_slug
    }

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

    # Identity must come from the spec, not the LLM: same page → same feature name
    for detected in detected_features:
        warning = _enforce_spec_identity(
            detected, title=filename, text=text_content, tables=tables,
        )
        if warning:
            logger.warning("Feature identity corrected for '%s': %s", filename, warning)

    # Single-feature pages (kafka/rest: the page IS the feature): a different
    # detected name is a rename, not remove+add — e.g. the LLM picked the
    # gateway path this run and the controller path last run. Rename the prior
    # row so its gaps/test-cases/bugs follow the feature instead of orphaning.
    active_prior = {n: f for n, f in prior_features.items() if not f.get("orphaned")}
    if len(active_prior) == 1 and len(detected_features) == 1:
        (prior_name, prior_feat), = active_prior.items()
        detected = detected_features[0]
        if prior_name != detected.name and prior_feat.get("type") == detected.type.value:
            try:
                renamed = await store.rename_feature(project_slug, prior_name, detected.name)
                if renamed is not None:
                    prior_features.pop(prior_name, None)
                    prior_features[detected.name] = renamed
                    logger.info(
                        "Single-feature re-extraction: '%s' renamed to '%s' (analysis carried over)",
                        prior_name, detected.name,
                    )
            except ValueError:
                pass  # target name already exists — keep name-based matching

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
                prior_feature=prior_features.get(detected.name),
                links_by_id=links_by_id,
            )
            succeeded.append(detected.name)
        except Exception as exc:
            logger.error("Feature '%s' failed: %s", detected.name, exc)
            failures.append((detected.name, str(exc)))
            # Roll back only brand-new features; a pre-existing record was not
            # overwritten (save is the last step) and must survive the failure.
            if prior_features.get(detected.name) is None:
                try:
                    await store.delete_feature(project_slug, detected.name)
                except Exception as del_exc:
                    logger.warning("Rollback of feature '%s' failed: %s", detected.name, del_exc)

    # Features no longer detected (renamed/removed in the spec) are marked
    # orphaned, not deleted: their gaps/test-cases/bugs may hold exported Jira
    # issues and MRs, so dropping them is the user's call, made in the UI.
    if succeeded:
        try:
            detected_names = {d.name for d in detected_features}
            for name in prior_features.keys() - detected_names:
                await store.update_feature(project_slug, name, {
                    "orphaned": True,
                    "orphaned_at": datetime.now(UTC).isoformat(),
                })
                logger.info("Feature '%s' is gone from document '%s' — marked orphaned", name, doc_slug)
        except Exception as exc:
            logger.warning("Orphan marking failed (non-fatal): %s", exc)

    # Deterministic spec diff (re-import only) + stale cascade: gaps/test-cases
    # of materially changed features were computed against the old spec version.
    if succeeded and prior_features:
        try:
            current_features = {
                f["name"]: f
                for f in await store.list_features(project_slug)
                if f.get("source_document") == doc_slug and not f.get("orphaned")
            }
            # A previously orphaned feature that reappears counts as added
            prior_for_diff = {n: f for n, f in prior_features.items() if not f.get("orphaned")}
            diff = compute_spec_diff(
                prior_for_diff,
                current_features,
                old_version=prev_confluence_version,
                new_version=doc_data.get("confluence_version"),
            )
            doc_data["last_diff"] = diff
            stale_note = None
            if prev_confluence_version and doc_data.get("confluence_version"):
                stale_note = f"спека v{prev_confluence_version} → v{doc_data['confluence_version']}"
            for detail in diff["changed"]:
                if not detail["material"]:
                    continue
                prior = prior_features.get(detail["name"]) or {}
                stale_updates = {}
                if prior.get("gap_count"):
                    stale_updates["gaps_stale"] = True
                if prior.get("test_case_count"):
                    stale_updates["test_cases_stale"] = True
                if stale_updates:
                    stale_updates["stale_spec_note"] = stale_note
                    await store.update_feature(project_slug, detail["name"], stale_updates)
            logger.info(
                "Spec diff for '%s': material=%s (+%d / -%d / ~%d)",
                doc_slug, diff["material"], len(diff["added"]), len(diff["removed"]), len(diff["changed"]),
            )
        except Exception as exc:
            logger.warning("Spec diff failed (non-fatal): %s", exc)

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

    # A finished (re-)import means the stored extraction matches the fetched page
    if succeeded and doc_data.get("confluence_version"):
        doc_data["latest_confluence_version"] = doc_data["confluence_version"]
        doc_data["spec_outdated"] = False

    await store.save_document(project_slug, doc_data)
    await store.finish_task(project_slug, task["id"], status=task_status, error_message=task_error)
    logger.info(
        "=== Pipeline finished: '%s' → %s (succeeded=%d, failed=%d) ===",
        filename, doc_data["status"], len(succeeded), len(failures),
    )
