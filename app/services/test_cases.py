"""Test cases generation pipeline: plan → coverage critic → batched detail calls."""
import asyncio
import json
import logging
import re
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import settings
from app.prompts.test_cases import (
    ASK_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    DETAIL_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    get_few_shot,
)
from app.schemas.test_cases import TestCaseAskResult, TestCaseGenerationResult, TestCasePlanResult
from app.services.claude_client import call_claude, log_cache_stats, parse_tool_input
from app.services.context_builder import build_feature_context
from app.services.rules import build_system_prompt

logger = logging.getLogger(__name__)


# How many plan items to detail per Claude call — keeps each response short enough
# that late cases stay as thorough as early ones.
DETAIL_BATCH_SIZE = 10

# How many detail batches run concurrently (after batch 1 warms the prompt cache).
# Bounded so a big plan doesn't burst-hit the API rate limit.
DETAIL_CONCURRENCY = 4

_UUID_PATTERN = re.compile(r'[0-9a-zA-Z]{8}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{12}')
_VALID_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


def _validate_test_cases(test_cases: list[dict], plan_count: int) -> list[str]:
    """Post-generation validation — returns list of warning strings.

    Checks: invalid UUID characters, INSERT-before-DELETE in sql_setup, plan count mismatch.
    """
    warnings: list[str] = []

    # Check count matches plan
    if len(test_cases) != plan_count:
        warnings.append(
            f"Count mismatch: plan had {plan_count} items, but generated {len(test_cases)} test cases"
        )

    for i, tc in enumerate(test_cases):
        tc_name = tc.get("name", f"test_case[{i}]")

        # Check UUID validity in all string fields
        for field_name, value in tc.items():
            if not isinstance(value, str):
                continue
            for match in _UUID_PATTERN.findall(value):
                if not _VALID_UUID.match(match):
                    warnings.append(
                        f"[{tc_name}] field '{field_name}': invalid UUID '{match}' contains non-hex characters"
                    )

        # Check sql_setup DELETE-before-INSERT order
        sql = tc.get("sql_setup")
        if sql:
            insert_pos = sql.upper().find("INSERT")
            delete_pos = sql.upper().find("DELETE")
            if insert_pos != -1 and delete_pos == -1:
                warnings.append(
                    f"[{tc_name}] sql_setup: INSERT found but no DELETE — missing cleanup before insert"
                )
            elif insert_pos != -1 and delete_pos != -1 and insert_pos < delete_pos:
                warnings.append(
                    f"[{tc_name}] sql_setup: INSERT appears before DELETE — wrong order (DELETE then INSERT)"
                )

    return warnings


def _get_tables_from_dep(dep_data: dict) -> list[dict]:
    """Extract table info list from a dependency entry.

    Handles both flat format (real data: enriched_data IS the table)
    and batch format (future-proof: enriched_data has tables list).
    Returns empty list for non-db_table deps or unenriched deps.
    """
    if dep_data.get("dep_type") != "db_table":
        return []
    enriched = dep_data.get("enriched_data")
    if not enriched:
        return []
    # Flat format: enriched_data IS the table (DbTableEnrichment.model_dump())
    if "table_name" in enriched:
        return [enriched]
    # Batch format: enriched_data has a tables list
    if "tables" in enriched:
        return enriched["tables"]
    return []


def _expand_fk_parents(enriched_deps: dict, flat_deps: dict) -> dict:
    """Recursively include FK parent tables from flat_deps not already in enriched_deps.

    A feature may only use child tables, but INSERT ordering requires parent tables too.
    This function auto-includes them by scanning FK references and looking up parents
    in the project-wide flat_deps. Iterates until no new parents are added.
    """
    result = dict(enriched_deps)
    norm_result: set[str] = {_norm(n) for n in result}

    while True:
        added: dict[str, dict] = {}
        for dep_data in list(result.values()):
            for table in _get_tables_from_dep(dep_data):
                for col in table.get("columns", []):
                    if not col.get("is_fk") or not col.get("fk_references"):
                        continue
                    parent_table = col["fk_references"].split(".")[0]
                    parent_norm = _norm(parent_table)
                    if parent_norm in norm_result:
                        continue
                    # Find enriched parent in flat_deps
                    for name, dep in flat_deps.items():
                        if _norm(name) == parent_norm and dep.get("enrichment_status") == "enriched":
                            added[name] = dep
                            norm_result.add(parent_norm)
                            break

        if not added:
            break
        result.update(added)
        logger.info("[fk_tree] Auto-included FK parent deps: %s", list(added.keys()))

    return result


def _build_fk_tree(enriched_deps: dict) -> dict:
    """Build FK dependency tree from enriched db_table dependencies.

    Returns {"delete_order": [...], "insert_order": [...]} if FK relationships exist,
    or empty dict if no FK relationships found.

    delete_order: topological order with children first, parents last (for DELETE statements).
    insert_order: reverse of delete_order — parents first, children last (for INSERT statements).
    """
    from collections import deque

    # Collect all tables and edges (child -> parent)
    all_tables: set[str] = set()
    edges: list[tuple[str, str]] = []  # (child, parent)

    for dep_data in enriched_deps.values():
        for table in _get_tables_from_dep(dep_data):
            table_name = table.get("table_name")
            if not table_name:
                continue
            all_tables.add(table_name)
            for col in table.get("columns", []):
                if not col.get("is_fk"):
                    continue
                fk_ref = col.get("fk_references")
                if not fk_ref:
                    continue
                # fk_references format: "target_table.column_name"
                parent_table = fk_ref.split(".")[0]
                if parent_table and parent_table != table_name:
                    edges.append((table_name, parent_table))

    logger.info("[fk_tree] Tables: %s, FK edges: %s", sorted(all_tables), edges)

    # If no FK relationships found, return empty dict
    if not edges:
        return {}

    # Kahn's algorithm on child->parent graph:
    # in_degree[node] = number of children that reference this node as parent.
    # Nodes with in_degree=0 are leaf children (nothing references them), so they go first.
    # Traversal gives: children first = delete_order (DELETE child rows before parent rows).
    # insert_order = reversed delete_order = parents first.

    graph: dict[str, set[str]] = {t: set() for t in all_tables}
    in_degree: dict[str, int] = {t: 0 for t in all_tables}

    for child, parent in edges:
        # Add parent to graph if not seen (may be outside enriched_deps)
        if parent not in graph:
            graph[parent] = set()
            in_degree[parent] = 0
        if parent not in graph[child]:
            graph[child].add(parent)
            in_degree[parent] += 1

    queue: deque[str] = deque(
        sorted(node for node, deg in in_degree.items() if deg == 0)
    )

    delete_order: list[str] = []
    visited: set[str] = set()

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        delete_order.append(node)
        for neighbor in sorted(graph[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Handle cycles: remaining unvisited nodes
    remaining = sorted(t for t in graph if t not in visited)
    if remaining:
        logger.warning(
            "[fk_tree] Cycle detected in FK graph, appending remaining tables: %s", remaining
        )
        delete_order.extend(remaining)

    insert_order = list(reversed(delete_order))

    logger.info("[fk_tree] DELETE order: %s", delete_order)
    logger.info("[fk_tree] INSERT order: %s", insert_order)

    return {"delete_order": delete_order, "insert_order": insert_order}


def _build_shared_context(feature: dict, enriched_deps: dict) -> str:
    """Build a shared text block for all parallel test case calls.

    Reuses the common feature+deps context builder, then appends the FK
    dependency tree (specific to test_cases for sql_setup ordering).
    """
    base = build_feature_context(feature, enriched_deps)

    fk_tree = _build_fk_tree(enriched_deps)
    if not fk_tree:
        return base

    extra = [
        "",
        "## FK Dependency Tree",
        "DELETE order (child -> parent): " + ", ".join(fk_tree["delete_order"]),
        "INSERT order (parent -> child): " + ", ".join(fk_tree["insert_order"]),
        "",
        "sql_setup MUST follow INSERT order for INSERTs and DELETE order for DELETEs.",
    ]
    return base + "\n" + "\n".join(extra)


_PLAN_TOOL = {
    "name": "plan_test_cases",
    "description": "Plan test cases for the feature — coverage plan without details",
    "input_schema": TestCasePlanResult.model_json_schema(),
}


async def _call_plan_tool(label: str, model: str, system_prompt: str, user_blocks: list[dict]) -> list[dict] | None:
    """Shared plumbing for the plan and critic phases: forced plan_test_cases call.

    Returns parsed plan items, or None when the model returned an empty list —
    the caller decides whether empty is an error (plan) or "nothing to add" (critic).
    """
    # Sonnet 5: adaptive thinking is on by default and counts against max_tokens,
    # and the new tokenizer emits ~30% more tokens for the same text — a tight
    # budget truncates the tool_use block, which surfaces as "no tool_use in response".
    # Missing/malformed tool_use is also a transient model failure — re-ask before giving up.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        response = await call_claude(
            label=label,
            model=model,
            max_tokens=16000,
            system=system_prompt,
            tools=[_PLAN_TOOL],
            tool_choice={"type": "tool", "name": _PLAN_TOOL["name"]},
            messages=[{"role": "user", "content": user_blocks}],
        )
        log_cache_stats(response.usage, label)

        tool_block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        try:
            if tool_block is None:
                raise RuntimeError(
                    f"[{label}] Claude did not return tool_use (stop_reason={response.stop_reason})"
                )
            if not tool_block.input or not tool_block.input.get("test_cases"):
                return None
            result = parse_tool_input(TestCasePlanResult, tool_block.input)
        except (RuntimeError, ValidationError) as exc:
            if attempt == max_attempts:
                raise
            logger.warning("[%s] attempt %d/%d failed, retrying: %s", label, attempt, max_attempts, exc)
            continue
        return [item.model_dump() for item in result.test_cases]


async def _call_plan_phase(
    model: str,
    shared_context: str,
    system_prompt: str = PLAN_SYSTEM_PROMPT,
) -> list[dict]:
    """Call 1: generate a test case coverage plan (names, categories, checks, covers, priorities)."""
    plan_items = await _call_plan_tool(
        "test_cases_plan",
        model,
        system_prompt,
        [
            {
                "type": "text",
                "text": shared_context,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": "Составь план тест-кейсов для этой фичи."},
        ],
    )
    if not plan_items:
        raise RuntimeError("[test_cases_plan] Claude returned an empty plan — no test cases planned")

    logger.info("[test_cases:plan] Planned %d test case(s)", len(plan_items))
    return plan_items


async def _call_critic_phase(
    model: str,
    shared_context: str,
    plan_items: list[dict],
    system_prompt: str = CRITIC_SYSTEM_PROMPT,
) -> list[dict]:
    """Call 2: coverage critic — returns plan items MISSING from the plan (may be empty)."""
    additions = await _call_plan_tool(
        "test_cases_critic",
        model,
        system_prompt,
        [
            {
                "type": "text",
                "text": shared_context,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": "## Существующий план тест-кейсов\n"
                + json.dumps(plan_items, ensure_ascii=False, indent=2),
            },
            {
                "type": "text",
                "text": "Найди пробелы покрытия и верни только недостающие тест-кейсы.",
            },
        ],
    )
    if not additions:
        logger.info("[test_cases:critic] Plan is complete — no additions")
        return []

    # Drop additions that duplicate an existing plan item by name
    existing_names = {_norm(item["name"]) for item in plan_items}
    fresh = [item for item in additions if _norm(item.get("name", "")) not in existing_names]
    logger.info("[test_cases:critic] %d addition(s), %d after dedup", len(additions), len(fresh))
    return fresh


async def _call_detail_phase(
    model: str,
    shared_context: str,
    plan_items: list[dict],
    feature_type: str = "",
    system_prompt: str = DETAIL_SYSTEM_PROMPT,
) -> list[dict]:
    """Detail phase: batched calls of DETAIL_BATCH_SIZE plan items each.

    A single call detailing the whole plan degrades on long outputs (later cases
    come out lazier) and risks truncation now that the plan is uncapped. Batches
    run sequentially so every batch after the first reads the shared context
    from the prompt cache.
    """
    tool = {
        "name": "generate_detailed_test_cases",
        "description": "Generate detailed test cases with artifacts based on the plan",
        "input_schema": TestCaseGenerationResult.model_json_schema(),
    }

    covers_by_name = {_norm(item.get("name", "")): item.get("covers") for item in plan_items}
    batches = [plan_items[i:i + DETAIL_BATCH_SIZE] for i in range(0, len(plan_items), DETAIL_BATCH_SIZE)]

    async def detail_batch(batch_no: int, batch: list[dict]) -> list[dict]:
        label = f"test_cases_detail[{batch_no}/{len(batches)}]"
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            response = await call_claude(
                label=label,
                model=model,
                max_tokens=64000,
                system=system_prompt,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": shared_context,
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": get_few_shot(feature_type),
                            },
                            {
                                "type": "text",
                                "text": "## План тест-кейсов (батч "
                                f"{batch_no} из {len(batches)}, {len(batch)} кейсов)\n"
                                + json.dumps(batch, ensure_ascii=False, indent=2),
                            },
                            {
                                "type": "text",
                                "text": "Детализируй каждый тест-кейс из этого батча — ровно "
                                f"{len(batch)} кейсов. Сохраняй category и priority из плана.",
                            },
                        ],
                    }
                ],
            )

            log_cache_stats(response.usage, label)
            logger.info("[%s] stop_reason=%s, content_blocks=%d", label, response.stop_reason, len(response.content))

            tool_block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
            try:
                if tool_block is None or not tool_block.input or not tool_block.input.get("test_cases"):
                    raise RuntimeError(
                        f"[{label}] Claude did not return tool_use — no test cases generated "
                        f"(stop_reason={response.stop_reason})"
                    )
                result = parse_tool_input(TestCaseGenerationResult, tool_block.input)
            except (RuntimeError, ValidationError) as exc:
                if attempt == max_attempts:
                    raise
                logger.warning("[%s] attempt %d/%d failed, retrying: %s", label, attempt, max_attempts, exc)
                continue
            break
        if len(result.test_cases) != len(batch):
            logger.warning(
                "[%s] batch size mismatch: plan had %d, generated %d",
                label, len(batch), len(result.test_cases),
            )

        return [
            {
                "category": tc.category,
                "name": tc.name,
                "preconditions": tc.preconditions,
                "steps": [{"action": s.action, "expected": s.expected} for s in tc.steps],
                "expected_result": tc.expected_result,
                "priority": tc.priority,
                "status": "pending",
                "analyst_text": None,
                "covers": covers_by_name.get(_norm(tc.name)),
                "curl_command": tc.curl_command,
                "kafka_message": tc.kafka_message.model_dump() if tc.kafka_message else None,
                "sql_setup": tc.sql_setup,
                "mock_config": tc.mock_config,
            }
            for tc in result.test_cases
        ]

    detailed: list[dict] = []
    if batches:
        # Batch 1 runs alone: it writes the shared context into the prompt cache.
        # The rest read that cache, so they can run concurrently (bounded — a big
        # plan must not burst-hit the API rate limit).
        detailed.extend(await detail_batch(1, batches[0]))
        if len(batches) > 1:
            semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)

            async def bounded(batch_no: int, batch: list[dict]) -> list[dict]:
                async with semaphore:
                    return await detail_batch(batch_no, batch)

            rest = await asyncio.gather(
                *(bounded(no, batch) for no, batch in enumerate(batches[1:], start=2))
            )
            for part in rest:
                detailed.extend(part)

    logger.info("[test_cases:detail] Generated %d detailed test case(s) in %d batch(es)", len(detailed), len(batches))
    return detailed


def _smart_merge_test_cases(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge new test cases with existing, preserving analyst decisions.

    Rules:
    - Approved/edited test cases: keep existing (preserve decision).
    - New test cases not matching existing approved/edited: add as pending.
    - Approved/edited test cases not in new results: keep (don't delete reviewed).
    - Pending test cases not in new results: remove (stale unreviewed).
    """
    merged: list[dict] = []

    # Pass 1: keep existing approved/edited test cases
    for existing_tc in existing:
        if existing_tc.get("status") in ("approved", "edited"):
            merged.append(existing_tc)

    # Pass 2: add new test cases not already covered by an approved/edited entry
    approved_edited_identities = {
        (tc["category"], tc["name"][:80]) for tc in merged
    }
    for new_tc in new:
        identity = (new_tc["category"], new_tc["name"][:80])
        if identity not in approved_edited_identities:
            merged.append(new_tc)

    return merged


def _norm(n: str) -> str:
    """Normalize dependency name for matching."""
    return n.lower().replace(" ", "_").replace("-", "_")


async def _check_enrichment_gate(feature: dict, project_slug: str, store) -> None:
    """Validate all used dependencies are enriched. Raises ValueError if not."""
    all_deps_by_type = await store.list_dependencies(project_slug)
    flat_deps: dict[str, dict] = {}
    for dep_list in all_deps_by_type.values():
        for dep in dep_list:
            flat_deps[dep["name"]] = dep

    sl = feature.get("structured_logic_json") or feature.get("structured_logic") or {}
    used_deps = sl.get("used_dependencies", []) if isinstance(sl, dict) else []

    norm_flat: dict[str, dict] = {_norm(name): dep for name, dep in flat_deps.items()}

    # Build lookup for external_api by service_name+path
    api_deps = [d for d in flat_deps.values() if d.get("dep_type") == "external_api"]

    unenriched: list[str] = []
    for dep in used_deps:
        if not isinstance(dep, dict):
            continue
        dep_name = dep.get("name", "")
        if not dep_name:
            continue

        # For external_api: match by service_name + path fields
        if dep.get("type") == "external_api" and dep.get("service_name"):
            matched = next(
                (d for d in api_deps
                 if _norm(d.get("service_name") or "") == _norm(dep.get("service_name") or "")
                 and _norm(d.get("path") or "") == _norm(dep.get("path") or "")),
                None,
            )
            display = f"{dep['service_name']}/{(dep.get('path') or '').lstrip('/')}"
            if matched is None or matched.get("enrichment_status") != "enriched":
                unenriched.append(display)
            continue

        norm_name = _norm(dep_name)
        if norm_name in norm_flat:
            if norm_flat[norm_name].get("enrichment_status") != "enriched":
                unenriched.append(dep_name)
        else:
            unenriched.append(dep_name)

    if unenriched:
        raise ValueError(
            f"Cannot run test cases: the following dependencies are not enriched: "
            f"{', '.join(unenriched)}"
        )


async def run_test_cases_pipeline(
    project_slug: str,
    feature_name: str,
    store,
    *,
    task_id: str | None = None,
) -> list[dict]:
    """Run 2 sequential Claude calls (plan + detail with few-shot) and return merged test cases."""
    try:
        result = await _run_test_cases_pipeline_inner(project_slug, feature_name, store)
    except Exception as exc:
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error", error_message=str(exc),
            )
        raise
    if task_id:
        await store.finish_task(project_slug, task_id, status="done")
    return result


async def _prepare_feature_context(
    project_slug: str,
    feature_name: str,
    store,
) -> tuple[dict, str, str]:
    """Load the feature, run the enrichment gate and build the shared prompt context.

    Returns (feature, feature_type, shared_context).
    """
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ValueError(f"Feature '{feature_name}' not found in project '{project_slug}'")

    # Enrichment gate
    await _check_enrichment_gate(feature, project_slug, store)

    # Build enriched dependency context — only deps used by this feature
    all_deps_by_type = await store.list_dependencies(project_slug)
    flat_deps: dict[str, dict] = {}
    for dep_list in all_deps_by_type.values():
        for dep in dep_list:
            flat_deps[dep["name"]] = dep

    # Get feature's used_dependencies list for scoped filtering
    sl = feature.get("structured_logic_json") or feature.get("structured_logic") or {}
    used_deps_list = sl.get("used_dependencies", []) if isinstance(sl, dict) else []

    # Collect names of deps actually used by this feature
    used_dep_names: set[str] = set()
    for dep in used_deps_list:
        if not isinstance(dep, dict):
            continue
        dep_name = dep.get("name", "")
        if dep.get("type") == "external_api" and dep.get("service_name") and dep.get("path"):
            dep_name = f"{dep['service_name']}/{dep['path'].lstrip('/')}"
        if dep_name:
            used_dep_names.add(_norm(dep_name))

    # Filter to only enriched deps that are used by this feature
    enriched_deps: dict[str, dict] = {}
    for name, dep in flat_deps.items():
        if dep.get("enrichment_status") == "enriched" and _norm(name) in used_dep_names:
            enriched_deps[name] = dep

    # Auto-include FK parent tables not in used_dependencies but referenced by FK columns
    enriched_deps = _expand_fk_parents(enriched_deps, flat_deps)

    feature_type = feature.get("type", "")
    shared_ctx = _build_shared_context(feature, enriched_deps)
    return feature, feature_type, shared_ctx


async def _run_test_cases_pipeline_inner(
    project_slug: str,
    feature_name: str,
    store,
) -> list[dict]:
    """Core pipeline without task handling (caller wraps for task lifecycle)."""
    _, feature_type, shared_ctx = await _prepare_feature_context(project_slug, feature_name, store)

    model = settings.test_cases_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    plan_system_prompt = build_system_prompt(
        base=PLAN_SYSTEM_PROMPT,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )
    critic_system_prompt = build_system_prompt(
        base=CRITIC_SYSTEM_PROMPT,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )
    detail_system_prompt = build_system_prompt(
        base=DETAIL_SYSTEM_PROMPT,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )

    # Pipeline: plan → coverage critic (fills gaps) → batched detail
    plan_items = await _call_plan_phase(model, shared_ctx, plan_system_prompt)
    plan_items += await _call_critic_phase(model, shared_ctx, plan_items, critic_system_prompt)
    all_new_test_cases = await _call_detail_phase(model, shared_ctx, plan_items, feature_type, detail_system_prompt)

    # Post-generation validation (observability only — log warnings, do not reject)
    validation_warnings = _validate_test_cases(all_new_test_cases, len(plan_items))
    for warning in validation_warnings:
        logger.warning("[test_cases:validate] %s", warning)

    # Smart merge with existing test cases
    existing_test_cases = await store.get_test_cases(project_slug, feature_name)
    merged_test_cases = _smart_merge_test_cases(existing_test_cases, all_new_test_cases)

    # Save test cases; timestamp stays on feature.json as a last-run marker
    await store.save_test_cases(project_slug, feature_name, merged_test_cases)
    await store.update_feature(project_slug, feature_name, {
        "test_cases_run_at": datetime.now(UTC).isoformat(),
    })

    return merged_test_cases


def _summarize_existing_test_cases(test_cases: list[dict]) -> str:
    """Compact list of existing cases (name/category/covers) for the ask prompt."""
    if not test_cases:
        return "Существующих тест-кейсов нет."
    lines = []
    for tc in test_cases:
        covers = tc.get("covers") or "—"
        lines.append(f"- [{tc.get('category', '?')}] {tc.get('name', '')} (покрывает: {covers})")
    return "\n".join(lines)


async def _call_ask_phase(
    model: str,
    shared_context: str,
    existing_summary: str,
    request_text: str,
    feature_type: str = "",
    system_prompt: str = ASK_SYSTEM_PROMPT,
) -> TestCaseAskResult:
    """Single Claude call: tester's free-text ask → 0..N detailed test cases + comment."""
    tool = {
        "name": "generate_requested_test_cases",
        "description": "Generate detailed test cases for the requested spec item, or explain why none were added",
        "input_schema": TestCaseAskResult.model_json_schema(),
    }
    label = "test_cases_ask"
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        response = await call_claude(
            label=label,
            model=model,
            max_tokens=32000,
            system=system_prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": shared_context,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": get_few_shot(feature_type)},
                        {"type": "text", "text": "## Существующие тест-кейсы\n" + existing_summary},
                        {"type": "text", "text": "## Запрос тестировщика\n" + request_text},
                    ],
                }
            ],
        )
        log_cache_stats(response.usage, label)

        tool_block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        try:
            if tool_block is None or tool_block.input is None:
                raise RuntimeError(
                    f"[{label}] Claude did not return tool_use (stop_reason={response.stop_reason})"
                )
            return parse_tool_input(TestCaseAskResult, tool_block.input)
        except (RuntimeError, ValidationError) as exc:
            if attempt == max_attempts:
                raise
            logger.warning("[%s] attempt %d/%d failed, retrying: %s", label, attempt, max_attempts, exc)


async def run_test_case_ask_pipeline(
    project_slug: str,
    feature_name: str,
    request_text: str,
    store,
    *,
    task_id: str | None = None,
) -> dict:
    """On-demand generation: tester asks for a test case on a specific spec item.

    Appends generated cases to the feature's list as pending; the outcome
    summary is stored on the task as result_message.
    """
    try:
        result = await _run_test_case_ask_pipeline_inner(project_slug, feature_name, request_text, store)
    except Exception as exc:
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error", error_message=str(exc),
            )
        raise
    if task_id:
        await store.finish_task(
            project_slug, task_id, status="done", result_message=result["message"],
        )
    return result


async def _run_test_case_ask_pipeline_inner(
    project_slug: str,
    feature_name: str,
    request_text: str,
    store,
) -> dict:
    """Core ask pipeline without task handling (caller wraps for task lifecycle)."""
    _, feature_type, shared_ctx = await _prepare_feature_context(project_slug, feature_name, store)

    existing_test_cases = await store.get_test_cases(project_slug, feature_name)
    existing_summary = _summarize_existing_test_cases(existing_test_cases)

    system_prompt = ASK_SYSTEM_PROMPT
    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    system_prompt = build_system_prompt(
        base=system_prompt,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )

    result = await _call_ask_phase(
        settings.test_cases_model, shared_ctx, existing_summary, request_text, feature_type, system_prompt,
    )

    new_cases = [
        {
            "category": tc.category,
            "name": tc.name,
            "preconditions": tc.preconditions,
            "steps": [{"action": s.action, "expected": s.expected} for s in tc.steps],
            "expected_result": tc.expected_result,
            "priority": tc.priority,
            "status": "pending",
            "analyst_text": None,
            "covers": tc.covers,
            "curl_command": tc.curl_command,
            "kafka_message": tc.kafka_message.model_dump() if tc.kafka_message else None,
            "sql_setup": tc.sql_setup,
            "mock_config": tc.mock_config,
        }
        for tc in result.test_cases
    ]

    # Drop generated cases that duplicate an existing one (same identity as smart merge)
    existing_identities = {(tc.get("category"), (tc.get("name") or "")[:80]) for tc in existing_test_cases}
    added = [tc for tc in new_cases if (tc["category"], tc["name"][:80]) not in existing_identities]

    if added:
        await store.save_test_cases(project_slug, feature_name, existing_test_cases + added)

    validation_warnings = _validate_test_cases(added, len(added))
    for warning in validation_warnings:
        logger.warning("[test_cases:ask:validate] %s", warning)

    if added:
        message = f"Добавлено кейсов: {len(added)}."
        if result.comment:
            message += f" {result.comment}"
    else:
        message = result.comment or "Кейсы не добавлены: запрошенный пункт уже покрыт или не найден в ТЗ."

    logger.info(
        "[test_cases:ask] project=%s feature=%s added=%d message=%s",
        project_slug, feature_name, len(added), message,
    )
    return {"added": added, "message": message}
