"""Gaps analysis pipeline: single Claude call with few-shot examples."""
import json
import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.gaps import (
    ANALYSIS_PROMPT,
    APPLY_SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    SYSTEM_PROMPT,
    build_apply_user_message,
)
from app.schemas.gaps import ApplyResult, GapsAnalysisResult
from app.services.claude_client import call_claude, log_cache_stats
from app.services.context_builder import build_feature_context
from app.services.rules import build_system_prompt

logger = logging.getLogger(__name__)


async def _call_gaps_analysis(
    model: str,
    shared_context: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> list[dict]:
    """Single Claude call to find all gap types with few-shot examples."""
    tool_schema = GapsAnalysisResult.model_json_schema()
    tool = {
        "name": "analyze_gaps",
        "description": "Find specification gaps across all categories",
        "input_schema": tool_schema,
    }

    response = await call_claude(
        label="gaps_analysis",
        model=model,
        max_tokens=8192,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": "analyze_gaps"},
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
                        "text": FEW_SHOT_EXAMPLES,
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                ],
            }
        ],
    )

    log_cache_stats(response.usage, "gaps:analysis")

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        logger.warning("[gaps:analysis] No tool_use block in Claude response")
        return []

    result = GapsAnalysisResult.model_validate(tool_block.input)
    logger.info("[gaps:analysis] Found %d gap(s)", len(result.gaps))

    return [
        {
            "gap_type": g.gap_type,
            "severity": g.severity,
            "actionable": g.actionable,
            "question": g.question,
            "suggestion": g.suggestion,
            "status": "pending",
            "analyst_text": None,
        }
        for g in result.gaps
    ]


def _smart_merge_gaps(existing_gaps: list[dict], new_gaps: list[dict]) -> list[dict]:
    """Merge new gaps with existing, preserving analyst decisions.

    Rules:
    - Approved/clarified gaps matching new results: keep existing (preserve decision).
    - New gaps not matching existing approved/clarified: add as pending.
    - Approved/clarified gaps not in new results: keep (don't delete stale reviewed gaps).
    - Pending gaps not in new results: remove (stale unreviewed).
    """
    merged: list[dict] = []

    # Pass 1: keep existing approved/clarified gaps (whether in new results or not)
    for existing in existing_gaps:
        if existing.get("status") in ("approved", "clarified"):
            merged.append(existing)

    # Pass 2: add new gaps that are NOT already covered by an approved/clarified entry
    approved_clarified_identities = {
        (g["gap_type"], g["question"][:80]) for g in merged
    }
    for new_gap in new_gaps:
        identity = (new_gap["gap_type"], new_gap["question"][:80])
        if identity not in approved_clarified_identities:
            merged.append(new_gap)

    return merged


async def run_gaps_pipeline(
    project_slug: str,
    feature_name: str,
    store,
    *,
    task_id: str | None = None,
) -> list[dict]:
    """Run single-call gap analysis and return merged gaps list.

    On success: gaps.json is saved, task (if any) is finished with status=done.
    On error: task is finished with status=error.
    """
    try:
        result = await _run_gaps_pipeline_inner(project_slug, feature_name, store)
    except Exception as exc:
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error", error_message=str(exc),
            )
        raise
    if task_id:
        await store.finish_task(project_slug, task_id, status="done")
    return result


async def _run_gaps_pipeline_inner(
    project_slug: str,
    feature_name: str,
    store,
) -> list[dict]:
    """Core pipeline without task handling (caller wraps for task lifecycle)."""
    # Load feature
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ValueError(f"Feature '{feature_name}' not found in project '{project_slug}'")

    # Enrichment gate: all dependencies must be enriched
    all_deps_by_type = await store.list_dependencies(project_slug)
    flat_deps: dict[str, dict] = {}
    for dep_list in all_deps_by_type.values():
        for dep in dep_list:
            flat_deps[dep["name"]] = dep

    # Get feature's used dependencies from structured_logic
    sl = feature.get("structured_logic_json") or feature.get("structured_logic") or {}
    used_deps = sl.get("used_dependencies", []) if isinstance(sl, dict) else []

    # Normalize name for matching (lowercase, spaces to underscores)
    def _norm(n: str) -> str:
        return n.lower().replace(" ", "_").replace("-", "_")

    # Build normalized flat_deps lookup
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
            f"Cannot run gaps analysis: the following dependencies are not enriched: "
            f"{', '.join(unenriched)}"
        )

    # Build enriched dependency context (only enriched ones)
    enriched_deps = {name: dep for name, dep in flat_deps.items()
                     if dep.get("enrichment_status") == "enriched"}

    shared_ctx = build_feature_context(feature, enriched_deps)

    model = settings.gaps_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    system_prompt = build_system_prompt(
        base=SYSTEM_PROMPT,
        global_rules=global_rules.get("gaps", ""),
        project_rules=project_rules.get("gaps", ""),
    )

    all_new_gaps = await _call_gaps_analysis(model, shared_ctx, system_prompt)

    # Smart merge with existing gaps
    existing_gaps = await store.get_gaps(project_slug, feature_name)
    merged_gaps = _smart_merge_gaps(existing_gaps, all_new_gaps)

    # Save gaps; timestamp stays on feature.json as a last-run marker
    await store.save_gaps(project_slug, feature_name, merged_gaps)
    await store.update_feature(project_slug, feature_name, {
        "gaps_run_at": datetime.now(UTC).isoformat(),
    })

    return merged_gaps




async def generate_apply_preview(
    project_slug: str,
    feature_name: str,
    store,
) -> dict:
    """Generate proposed structured_logic from approved/clarified gaps via Claude.

    Returns {"original": ..., "proposed": ..., "changes": [...]}.
    Raises ValueError if no approved/clarified gaps exist.
    """
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ValueError(f"Feature '{feature_name}' not found in project '{project_slug}'")

    current_sl = feature.get("structured_logic_json") or {}

    gaps = await store.get_gaps(project_slug, feature_name)
    actionable_gaps = [g for g in gaps if g.get("status") in ("approved", "clarified")]

    if not actionable_gaps:
        raise ValueError("No approved or clarified gaps to apply")

    # Build gap descriptions with indices for change tracking
    gap_lines = []
    for i, gap in enumerate(actionable_gaps):
        lines = [f"Gap #{i} [{gap.get('gap_type')}]: {gap.get('question')}"]
        lines.append(f"  Рекомендация: {gap.get('suggestion')}")
        if gap.get("status") == "clarified" and gap.get("analyst_text"):
            lines.append(f"  Уточнение аналитика: {gap.get('analyst_text')}")
        gap_lines.append("\n".join(lines))

    gaps_text = "\n\n".join(gap_lines)

    sl_json = json.dumps(current_sl, ensure_ascii=False, indent=2)

    user_message = build_apply_user_message(sl_json, current_sl, gaps_text)

    tool_schema = ApplyResult.model_json_schema()
    tool = {
        "name": "apply_gaps",
        "description": "Return the complete updated structured_logic (preserving ALL existing data) plus human-readable change descriptions",
        "input_schema": tool_schema,
    }

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    apply_system_prompt = build_system_prompt(
        base=APPLY_SYSTEM_PROMPT,
        global_rules=global_rules.get("gaps", ""),
        project_rules=project_rules.get("gaps", ""),
    )
    response = await call_claude(
        label="gaps_apply_preview",
        model=settings.gaps_model,
        max_tokens=16384,
        system=apply_system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": "apply_gaps"},
        messages=[{"role": "user", "content": user_message}],
    )

    log_cache_stats(response.usage, "gaps:apply_preview")

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        raise RuntimeError("Claude did not return a tool_use block for apply_preview")

    result = ApplyResult.model_validate(tool_block.input)
    proposed_dict = result.structured_logic.model_dump(mode="json")
    changes_list = [c.model_dump(mode="json") for c in result.changes]

    # Sanity check: proposed should have at least as many items as original
    for key in ("input_parameters", "success_response", "error_responses", "logic_steps", "used_dependencies", "business_rules"):
        orig_count = len(current_sl.get(key, []))
        proposed_count = len(proposed_dict.get(key, []))
        if proposed_count < orig_count:
            logger.warning(
                "[gaps:apply_preview] %s shrunk: %d → %d — Claude may have dropped items",
                key, orig_count, proposed_count,
            )

    logger.info(
        "[gaps:apply_preview] Generated proposed logic with %d changes for feature '%s'",
        len(changes_list), feature_name,
    )

    return {"original": current_sl, "proposed": proposed_dict, "changes": changes_list}


async def run_apply_preview_background(
    project_slug: str,
    feature_name: str,
    store,
    *,
    task_id: str | None = None,
) -> None:
    """Background task: generate apply preview and save to storage."""
    try:
        result = await generate_apply_preview(project_slug, feature_name, store)
        await store.save_apply_preview(project_slug, feature_name, {
            "status": "done",
            **result,
        })
    except Exception as exc:
        logger.error("Apply preview failed for feature '%s': %s", feature_name, exc)
        await store.save_apply_preview(project_slug, feature_name, {
            "status": "error",
            "error": str(exc),
        })
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error", error_message=str(exc),
            )
        return
    if task_id:
        await store.finish_task(project_slug, task_id, status="done")


async def confirm_apply(
    project_slug: str,
    feature_name: str,
    proposed: dict,
    store,
) -> None:
    """Save proposed structured_logic and mark approved/clarified gaps as applied."""
    await store.update_feature(project_slug, feature_name, {"structured_logic_json": proposed})

    gaps = await store.get_gaps(project_slug, feature_name)
    for gap in gaps:
        if gap.get("status") in ("approved", "clarified"):
            gap["status"] = "applied"

    await store.save_gaps(project_slug, feature_name, gaps)
    await store.delete_apply_preview(project_slug, feature_name)
    logger.info(
        "[gaps:confirm_apply] Applied proposed logic to feature '%s'",
        feature_name,
    )
