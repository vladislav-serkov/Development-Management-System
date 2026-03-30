"""Test cases generation pipeline: 2 sequential Claude calls (plan + detail with few-shot)."""
import json
import logging
import re
from datetime import UTC, datetime

from app.config import settings
from app.prompts.test_cases import DETAIL_SYSTEM_PROMPT, PLAN_SYSTEM_PROMPT, get_few_shot
from app.schemas.test_cases import TestCaseGenerationResult, TestCasePlanResult
from app.services.extraction import _get_client, _log_cache_stats
from app.services.rules import build_system_prompt

logger = logging.getLogger(__name__)


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
    """Build a shared text block for all parallel test case calls."""
    lines = []
    lines.append("## Feature")
    lines.append(f"Name: {feature.get('name', '')}")
    lines.append(f"Type: {feature.get('type', '')}")
    lines.append(f"Method: {feature.get('method', '')}")
    lines.append(f"Endpoint: {feature.get('endpoint', '')}")
    lines.append(f"Summary: {feature.get('summary', '')}")
    lines.append("")

    structured_logic = feature.get("structured_logic_json")
    if structured_logic:
        lines.append("### Structured Logic")
        lines.append(json.dumps(structured_logic, ensure_ascii=False, indent=2))
        lines.append("")

    lines.append("## Dependencies")
    if enriched_deps:
        for dep_name, dep_data in enriched_deps.items():
            lines.append(f"### {dep_name} ({dep_data.get('dep_type', '')})")
            enriched = dep_data.get("enriched_data")
            if enriched:
                lines.append(json.dumps(enriched, ensure_ascii=False, indent=2))
            else:
                lines.append(f"Description: {dep_data.get('description', '')}")
                lines.append(f"Status: {dep_data.get('enrichment_status', 'stub')}")
            lines.append("")
    else:
        lines.append("No enriched dependencies available.")

    fk_tree = _build_fk_tree(enriched_deps)
    if fk_tree:
        lines.append("")
        lines.append("## FK Dependency Tree")
        lines.append(
            "DELETE order (child -> parent): " + ", ".join(fk_tree["delete_order"])
        )
        lines.append(
            "INSERT order (parent -> child): " + ", ".join(fk_tree["insert_order"])
        )
        lines.append("")
        lines.append("sql_setup MUST follow INSERT order for INSERTs and DELETE order for DELETEs.")

    return "\n".join(lines)


async def _call_plan_phase(
    client,
    model: str,
    shared_context: str,
    system_prompt: str = PLAN_SYSTEM_PROMPT,
) -> list[dict]:
    """Call 1: generate a test case coverage plan (names, categories, checks, priorities)."""
    tool_schema = TestCasePlanResult.model_json_schema()
    tool_name = "plan_test_cases"
    tool = {
        "name": tool_name,
        "description": "Plan test cases for the feature — coverage plan without details",
        "input_schema": tool_schema,
    }

    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
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
                        "text": "Составь план тест-кейсов для этой фичи.",
                    },
                ],
            }
        ],
    )

    _log_cache_stats(response.usage, "test_cases:plan")

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        logger.error("[test_cases:plan] No tool_use block in Claude response")
        raise RuntimeError("[test_cases:plan] Claude did not return tool_use — no test cases planned")

    if not tool_block.input or not tool_block.input.get("test_cases"):
        logger.error("[test_cases:plan] Empty tool_use input: %s", tool_block.input)
        raise RuntimeError("[test_cases:plan] Claude did not return tool_use — no test cases planned")

    result = TestCasePlanResult.model_validate(tool_block.input)
    logger.info("[test_cases:plan] Planned %d test case(s)", len(result.test_cases))

    return [item.model_dump() for item in result.test_cases]


async def _call_detail_phase(
    client,
    model: str,
    shared_context: str,
    plan_items: list[dict],
    feature_type: str = "",
    system_prompt: str = DETAIL_SYSTEM_PROMPT,
) -> list[dict]:
    """Call 2: generate detailed test cases with artifacts, guided by the plan and few-shot examples."""
    tool_schema = TestCaseGenerationResult.model_json_schema()
    tool_name = "generate_detailed_test_cases"
    tool = {
        "name": tool_name,
        "description": "Generate detailed test cases with artifacts based on the plan",
        "input_schema": tool_schema,
    }

    response = await client.messages.create(
        model=model,
        max_tokens=42768,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
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
                        "text": "## План тест-кейсов\n" + json.dumps(plan_items, ensure_ascii=False, indent=2),
                    },
                    {
                        "type": "text",
                        "text": "Детализируй каждый тест-кейс из плана. Сохраняй category и priority из плана.",
                    },
                ],
            }
        ],
    )

    _log_cache_stats(response.usage, "test_cases:detail")
    logger.info("[test_cases:detail] stop_reason=%s, content_blocks=%d", response.stop_reason, len(response.content))

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        logger.error("[test_cases:detail] No tool_use block. Content: %s", [b.type for b in response.content])
        raise RuntimeError("[test_cases:detail] Claude did not return tool_use — no test cases generated")

    if not tool_block.input or not tool_block.input.get("test_cases"):
        logger.error("[test_cases:detail] Empty tool_use input: %s", tool_block.input)
        raise RuntimeError("[test_cases:detail] Claude did not return tool_use — no test cases generated")

    result = TestCaseGenerationResult.model_validate(tool_block.input)
    logger.info("[test_cases:detail] Generated %d detailed test case(s)", len(result.test_cases))

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
            "curl_command": tc.curl_command,
            "kafka_message": tc.kafka_message,
            "sql_setup": tc.sql_setup,
            "mock_config": tc.mock_config,
        }
        for tc in result.test_cases
    ]


def _smart_merge_test_cases(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge new test cases with existing, preserving analyst decisions.

    Rules:
    - Approved/edited test cases: keep existing (preserve decision).
    - New test cases not matching existing approved/edited: add as pending.
    - Approved/edited test cases not in new results: keep (don't delete reviewed).
    - Pending test cases not in new results: remove (stale unreviewed).
    """
    new_identity_set = {(tc["category"], tc["name"][:80]) for tc in new}

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

    unenriched: list[str] = []
    for dep in used_deps:
        if not isinstance(dep, dict):
            continue
        dep_name = dep.get("name", "")
        if dep.get("type") == "external_api" and dep.get("service_name") and dep.get("path"):
            dep_name = f"{dep['service_name']}/{dep['path'].lstrip('/')}"
        if not dep_name:
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
) -> list[dict]:
    """Run 2 sequential Claude calls (plan + detail with few-shot) and return merged test cases."""
    # Load feature
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

    norm_flat: dict[str, dict] = {_norm(name): dep for name, dep in flat_deps.items()}

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

    client = _get_client()
    model = settings.test_cases_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    plan_system_prompt = build_system_prompt(
        base=PLAN_SYSTEM_PROMPT,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )
    detail_system_prompt = build_system_prompt(
        base=DETAIL_SYSTEM_PROMPT,
        global_rules=global_rules.get("test_cases", ""),
        project_rules=project_rules.get("test_cases", ""),
    )

    # Sequential 2-call pipeline: plan then detail
    try:
        plan_items = await _call_plan_phase(client, model, shared_ctx, plan_system_prompt)
        all_new_test_cases = await _call_detail_phase(client, model, shared_ctx, plan_items, feature_type, detail_system_prompt)

        # Post-generation validation (observability only — log warnings, do not reject)
        validation_warnings = _validate_test_cases(all_new_test_cases, len(plan_items))
        for warning in validation_warnings:
            logger.warning("[test_cases:validate] %s", warning)

        # Smart merge with existing test cases
        existing_test_cases = await store.get_test_cases(project_slug, feature_name)
        merged_test_cases = _smart_merge_test_cases(existing_test_cases, all_new_test_cases)

        # Save results: test_cases go to test-cases.json, status/timestamp go to feature.json
        await store.save_test_cases(project_slug, feature_name, merged_test_cases)
        await store.update_feature(project_slug, feature_name, {
            "test_cases_status": "done",
            "test_cases_run_at": datetime.now(UTC).isoformat(),
        })

        return merged_test_cases

    except Exception as exc:
        logger.error("Test cases pipeline fatal error for feature '%s': %s", feature_name, exc)
        await store.update_feature(project_slug, feature_name, {"test_cases_status": "error"})
        raise
