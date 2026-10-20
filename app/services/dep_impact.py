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
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def dep_key(dep_type: str, name: str) -> tuple[str, str]:
    """Dependency lookups are case-insensitive (see ProjectStore), and rows of
    non-document types are stored under ``_normalize_dep_name`` (spaces → "_")
    while features keep the raw LLM name."""
    name = " ".join(str(name or "").split())
    if dep_type != "external_doc":
        name = name.replace(" ", "_")
    return dep_type, name.lower()


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


async def mark_feature_stale(store, project_slug: str, feature_name: str, note: str) -> bool:
    """Flag the feature's existing gaps/test cases as computed before a change.

    ``*_stale_at`` lets a run that was already in flight leave the flag alone
    (``ProjectStore.clear_stale``). Returns whether anything was flagged.
    """
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        return False
    now_iso = datetime.now(UTC).isoformat()
    updates: dict = {}
    if feature.get("gap_count"):
        updates.update(gaps_stale=True, gaps_stale_at=now_iso)
    if feature.get("test_case_count"):
        updates.update(test_cases_stale=True, test_cases_stale_at=now_iso)
    if not updates:
        return False
    updates["stale_spec_note"] = merge_stale_note(feature, note)
    await store.update_feature(project_slug, feature_name, updates)
    return True


async def mark_dependents_stale(store, project_slug: str, dep_type: str, dep_name: str, note: str) -> list[str]:
    """Flag gaps/test cases of every live feature using the dependency as stale.
    Returns the names of the features flagged."""
    key = dep_key(dep_type, dep_name)
    flagged = [
        feature["name"]
        for feature in await store.list_features(project_slug)
        if not feature.get("orphaned") and key in feature_dep_keys(feature)
        and await mark_feature_stale(store, project_slug, feature["name"], note)
    ]
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
