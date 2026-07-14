"""Enrichment pipeline: Claude tool_use extraction for dependency documents (Confluence markdown)."""
import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.enrichment import ENRICHMENT_SCHEMAS
from app.schemas.enrichment import DependencyResponse
from app.services.claude_client import call_claude, log_cache_stats
from app.services.extraction import (
    _build_document_block,
    _normalize_dep_name,
)
from app.services.rules import build_system_prompt

logger = logging.getLogger(__name__)

# Single source of truth for the "external_doc needs a specific dep_name" error —
# used by both the HTTP guard in the router and the runtime guard in this service.
EXTERNAL_DOC_TARGETED_ONLY_MSG = (
    "external_doc requires dep_name: 1 page enriches exactly one named document"
)


def _dep_to_response(dep: dict, project_slug: str) -> DependencyResponse:
    """Convert dependency dict to DependencyResponse schema."""
    enriched = dep.get("enriched_data")

    created_at = dep.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.now(UTC)

    enriched_at = dep.get("enriched_at")
    if isinstance(enriched_at, str):
        enriched_at = datetime.fromisoformat(enriched_at)

    return DependencyResponse(
        project_slug=project_slug,
        dep_type=dep["dep_type"],
        name=dep["name"],
        description=dep.get("description"),
        enrichment_status=dep.get("enrichment_status", "enriched"),
        enriched_data=enriched,
        source_pdf_name=dep.get("source_pdf_name"),
        enriched_at=enriched_at,
        created_at=created_at,
        method=dep.get("method"),
        service_name=dep.get("service_name"),
        path=dep.get("path"),
    )



def _match_table(tables, dep_name: str):
    """Find an extracted table matching a dependency name (normalized, case-insensitive)."""
    want = _normalize_dep_name(dep_name).lower()
    return next(
        (t for t in tables if _normalize_dep_name(t.table_name).lower() == want),
        None,
    )


async def _extract_enrichment(
    project_slug: str,
    dep_type: str,
    text_content: str,
    source_name: str,
    store,
):
    """Single Claude tool_use call: document markdown → validated batch schema for dep_type."""
    if dep_type not in ENRICHMENT_SCHEMAS:
        raise ValueError(f"Invalid dep_type: {dep_type}. Must be one of: {list(ENRICHMENT_SCHEMAS)}")

    cfg = ENRICHMENT_SCHEMAS[dep_type]
    schema_class = cfg["schema"]
    tool_name = cfg["tool_name"]
    prompt_text = cfg["prompt"]

    logger.info(
        "=== Enrichment pipeline started: dep_type=%s, doc=%s (%.1fKB) ===",
        dep_type,
        source_name,
        len(text_content) / 1024,
    )

    model = settings.claude_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    system_prompt = build_system_prompt(
        base="",
        global_rules=global_rules.get("enrichment", ""),
        project_rules=project_rules.get("enrichment", ""),
    )

    tool = {
        "name": tool_name,
        "description": f"Extract structured {dep_type} data from the document",
        "input_schema": schema_class.model_json_schema(),
    }

    create_kwargs_enr: dict = dict(
        model=model,
        max_tokens=16384,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
    )
    if system_prompt:
        create_kwargs_enr["system"] = system_prompt

    response = await call_claude(
        label=f"enrichment:{dep_type}",
        **create_kwargs_enr,
        messages=[
            {
                "role": "user",
                "content": [
                    _build_document_block(text_content, cache=True),
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    )

    log_cache_stats(response.usage, f"enrichment:{dep_type}")

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        raise ValueError("No tool_use block in Claude response for enrichment")

    if response.stop_reason == "max_tokens":
        raise ValueError(
            f"Claude response truncated by max_tokens for enrichment:{dep_type} — document too large"
        )

    result = schema_class.model_validate(tool_block.input)
    logger.info("Enrichment extraction complete for dep_type=%s", dep_type)
    return result


async def enrich_db_tables_from_page(
    project_slug: str,
    dep_names: list[str],
    text_content: str,
    source_name: str,
    store,
) -> tuple[dict[str, DependencyResponse | None], list[str]]:
    """One Claude call over a page describing many tables → upsert ALL of them.

    Requested stubs (dep_names) are updated in place; every other table extracted
    from the page is upserted as a new enriched dependency (the page describes the
    whole DB, so all its tables belong to the project).

    Returns (outcomes, extracted_table_names): outcomes maps each requested dep name to
    its updated DependencyResponse, or None when no table on the page matched it.
    """
    result = await _extract_enrichment(project_slug, "db_table", text_content, source_name, store)
    extracted_names = [t.table_name for t in result.tables]
    now_iso = datetime.now(UTC).isoformat()

    outcomes: dict[str, DependencyResponse | None] = {}
    matched_tables: set[int] = set()
    for dep_name in dep_names:
        table = _match_table(result.tables, dep_name)
        if table is None and len(result.tables) == 1 and len(dep_names) == 1:
            table = result.tables[0]
        if table is None:
            outcomes[dep_name] = None
            continue
        matched_tables.add(id(table))
        updated_dep = await store.update_dependency(
            project_slug,
            "db_table",
            dep_name,
            {
                "enriched_data": table.model_dump(),
                "enrichment_status": "enriched",
                "source_pdf_name": source_name,
                "enriched_at": now_iso,
            },
        )
        outcomes[dep_name] = _dep_to_response(updated_dep, project_slug) if updated_dep else None

    # The page describes the whole DB — upsert the remaining tables too
    # (enriches same-named stubs from other groups thanks to case-insensitive merge).
    for table in result.tables:
        if id(table) in matched_tables:
            continue
        normalized_name = _normalize_dep_name(table.table_name)
        await store.upsert_dependency(
            project_slug=project_slug,
            dep_type="db_table",
            name=normalized_name,
            data={
                "dep_type": "db_table",
                "name": normalized_name,
                "enriched_data": table.model_dump(),
                "enrichment_status": "enriched",
                "source_pdf_name": source_name,
                "enriched_at": now_iso,
            },
        )

    logger.info(
        "DB group enrichment: page='%s', extracted=%d tables, matched %d/%d deps, upserted %d extra",
        source_name, len(extracted_names),
        sum(1 for v in outcomes.values() if v is not None), len(dep_names),
        len(result.tables) - len(matched_tables),
    )
    return outcomes, extracted_names


async def run_enrichment_pipeline(
    project_slug: str,
    dep_type: str,
    text_content: str,
    source_name: str,
    store,
    target_dep_name: str | None = None,
) -> list[DependencyResponse]:
    """Run Claude tool_use enrichment for a dependency document (markdown text)."""
    result = await _extract_enrichment(project_slug, dep_type, text_content, source_name, store)

    now = datetime.now(UTC)
    now_iso = now.isoformat()

    # Targeted enrichment: update a single named dependency, preserving identity fields
    if target_dep_name is not None:
        logger.info("Targeted enrichment: dep_type=%s, target=%s", dep_type, target_dep_name)
        if dep_type == "db_table":
            table = _match_table(result.tables, target_dep_name)
            if table is None and len(result.tables) == 1:
                table = result.tables[0]
            if table is None:
                raise ValueError(
                    f"Таблица '{target_dep_name}' не найдена в документе; "
                    f"извлечены: {[t.table_name for t in result.tables]}"
                )
            enriched_data = table.model_dump()
        elif dep_type == "external_api":
            enriched_data = result.model_dump()
        elif dep_type == "cache":
            enriched_data = result.caches[0].model_dump() if result.caches else {}
        elif dep_type == "kafka_topic":
            enriched_data = result.topics[0].model_dump() if result.topics else {}
        elif dep_type == "external_doc":
            enriched_data = result.model_dump()
        else:
            enriched_data = {}

        updated_dep = await store.update_dependency(
            project_slug,
            dep_type,
            target_dep_name,
            {
                "enriched_data": enriched_data,
                "enrichment_status": "enriched",
                "source_pdf_name": source_name,
                "enriched_at": now_iso,
            },
        )
        if updated_dep is None:
            raise ValueError(
                f"Dependency '{target_dep_name}' of type '{dep_type}' not found in project '{project_slug}'"
            )
        logger.info("Targeted enrichment complete: dep_type=%s, name=%s", dep_type, target_dep_name)
        return [_dep_to_response(updated_dep, project_slug)]

    upserted_deps: list[dict] = []

    if dep_type == "external_doc":
        # external_doc supports only targeted enrichment (1 PDF = 1 document) —
        # bulk upload can't auto-bind an anonymous markdown dump to an existing stub.
        raise ValueError(EXTERNAL_DOC_TARGETED_ONLY_MSG)

    if dep_type == "db_table":
        for table in result.tables:
            normalized_name = _normalize_dep_name(table.table_name)
            dep = await store.upsert_dependency(
                project_slug=project_slug,
                dep_type=dep_type,
                name=normalized_name,
                data={
                    "dep_type": dep_type,
                    "name": normalized_name,
                    "enriched_data": table.model_dump(),
                    "enrichment_status": "enriched",
                    "source_pdf_name": source_name,
                    "enriched_at": now_iso,
                },
            )
            upserted_deps.append(dep)

    elif dep_type == "external_api":
        api_name = _normalize_dep_name(result.api_name)
        enriched_data = result.model_dump()
        # Find existing stubs by service_name match
        all_deps = await store.list_dependencies(project_slug)
        matching_stubs = [
            d for d in all_deps.get("external_api", [])
            if d.get("service_name") and _normalize_dep_name(d["service_name"]).lower() == api_name.lower()
        ]
        if matching_stubs:
            # Update each stub that belongs to this service
            for stub in matching_stubs:
                dep = await store.upsert_dependency(
                    project_slug=project_slug,
                    dep_type=dep_type,
                    name=stub["name"],
                    data={
                        "dep_type": dep_type,
                        "name": stub["name"],
                        "enriched_data": enriched_data,
                        "enrichment_status": "enriched",
                        "source_pdf_name": source_name,
                        "enriched_at": now_iso,
                        "method": stub.get("method"),
                        "service_name": stub.get("service_name"),
                        "path": stub.get("path"),
                    },
                )
                upserted_deps.append(dep)
        else:
            # No stubs found — create entry keyed by api_name
            dep = await store.upsert_dependency(
                project_slug=project_slug,
                dep_type=dep_type,
                name=api_name,
                data={
                    "dep_type": dep_type,
                    "name": api_name,
                    "enriched_data": enriched_data,
                    "enrichment_status": "enriched",
                    "source_pdf_name": source_name,
                    "enriched_at": now_iso,
                    "method": None,
                    "service_name": api_name,
                    "path": None,
                },
            )
            upserted_deps.append(dep)

    elif dep_type == "cache":
        for cache in result.caches:
            normalized_name = _normalize_dep_name(cache.cache_name)
            dep = await store.upsert_dependency(
                project_slug=project_slug,
                dep_type=dep_type,
                name=normalized_name,
                data={
                    "dep_type": dep_type,
                    "name": normalized_name,
                    "enriched_data": cache.model_dump(),
                    "enrichment_status": "enriched",
                    "source_pdf_name": source_name,
                    "enriched_at": now_iso,
                },
            )
            upserted_deps.append(dep)

    elif dep_type == "kafka_topic":
        for topic in result.topics:
            normalized_name = _normalize_dep_name(topic.topic_name)
            dep = await store.upsert_dependency(
                project_slug=project_slug,
                dep_type=dep_type,
                name=normalized_name,
                data={
                    "dep_type": dep_type,
                    "name": normalized_name,
                    "enriched_data": topic.model_dump(),
                    "enrichment_status": "enriched",
                    "source_pdf_name": source_name,
                    "enriched_at": now_iso,
                },
            )
            upserted_deps.append(dep)

    logger.info(
        "=== Enrichment pipeline finished: dep_type=%s, upserted=%d rows ===",
        dep_type,
        len(upserted_deps),
    )

    return [_dep_to_response(dep, project_slug) for dep in upserted_deps]
