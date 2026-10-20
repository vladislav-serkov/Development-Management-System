"""Feature ⇄ dependency impact: which features rely on a dependency.

A feature lists its dependencies in ``structured_logic_json.used_dependencies``
by (type, name) — the same normalized name the dependency row is stored under.
Two consumers:

- the source cascade: a dependency whose source page changed *materially*
  (``spec_diff.diff_enriched_data`` is non-None) makes the gaps/test cases of
  every feature using it stale, exactly like a material spec change does;
- the spec-update check: a document is worth re-importing when the source page
  of any dependency its features use moved ahead, even if the spec page itself
  did not change.
"""

import logging

logger = logging.getLogger(__name__)


def dep_key(dep_type: str, name: str) -> tuple[str, str]:
    """Dependency lookups are case-insensitive (see ProjectStore)."""
    return dep_type, " ".join(str(name or "").split()).lower()


def feature_dep_keys(feature: dict) -> set[tuple[str, str]]:
    logic = feature.get("structured_logic_json") or {}
    return {
        dep_key(d.get("type") or "", d.get("name") or "")
        for d in logic.get("used_dependencies") or []
        if d.get("type") and d.get("name")
    }


def merge_stale_note(feature: dict, note: str) -> str:
    """Append ``note`` to the reasons the feature's analysis is stale; a fresh
    analysis run clears the flags, so old notes only count while still stale."""
    still_stale = feature.get("gaps_stale") or feature.get("test_cases_stale")
    notes = [n for n in ((feature.get("stale_spec_note") or "") if still_stale else "").split("; ") if n]
    if note not in notes:
        notes.append(note)
    return "; ".join(notes)


async def mark_dependents_stale(store, project_slug: str, dep_type: str, dep_name: str, note: str) -> list[str]:
    """Flag gaps/test cases of every live feature using the dependency as stale.

    Only analysis that exists can go stale; notes accumulate so a feature hit
    by several source changes before its next run lists all of them.
    Returns the names of the features flagged.
    """
    key = dep_key(dep_type, dep_name)
    flagged = []
    for feature in await store.list_features(project_slug):
        if feature.get("orphaned") or key not in feature_dep_keys(feature):
            continue
        updates: dict = {}
        if feature.get("gap_count"):
            updates["gaps_stale"] = True
        if feature.get("test_case_count"):
            updates["test_cases_stale"] = True
        if not updates:
            continue
        updates["stale_spec_note"] = merge_stale_note(feature, note)
        await store.update_feature(project_slug, feature["name"], updates)
        flagged.append(feature["name"])
    if flagged:
        logger.info("Source of %s/%s changed → stale analysis on %s", dep_type, dep_name, flagged)
    return flagged


async def outdated_deps_of_document(store, project_slug: str, doc_slug: str) -> list[str]:
    """Names of the dependencies used by the document's features whose source
    page moved ahead of their enrichment (``source_outdated``)."""
    keys: set[tuple[str, str]] = set()
    for feature in await store.list_features(project_slug):
        if feature.get("source_document") == doc_slug and not feature.get("orphaned"):
            keys |= feature_dep_keys(feature)
    if not keys:
        return []
    deps_by_type = await store.list_dependencies(project_slug)
    return sorted(
        dep["name"]
        for dep_type, deps in deps_by_type.items()
        for dep in deps
        if dep.get("source_outdated") and dep_key(dep_type, dep["name"]) in keys
    )
