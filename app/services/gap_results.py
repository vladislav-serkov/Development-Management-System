"""Compact public remarks and compatibility with previously stored reports."""

PRIVATE_SOURCE_IDS = frozenset({"project-notes", "analyst-decisions", "analysis-rules"})

# Decisions belong to the application, not the model's response schema.
REVIEW_FIELDS = {
    "id", "status", "analyst_text", "presence", "needs_review", "history", "archived",
    "first_seen_at", "last_seen_at", "source_hashes", "review_source_hashes",
}


def gap_text(item: dict) -> str:
    if "text" in item:
        return item["text"]
    # Old findings remain readable without keeping their report schema alive.
    parts = [item.get(key, "").strip() for key in (
        "question", "scenario", "business_impact", "suggestion",
    ) if item.get(key)]
    return " ".join(dict.fromkeys(parts))


def public_sources(sources: list[dict]) -> list[dict]:
    fields = {"id", "title", "url", "version", "content_hash", "page_id"}
    return [{k: v for k, v in source.items() if k in fields}
            for source in sources if source.get("id") not in PRIVATE_SOURCE_IDS]


def public_gaps(items: list[dict], sources: list[dict] | None = None) -> list[dict]:
    result = []
    for item in items:
        # Legacy remarks based on private notes are not specification evidence.
        if any(e.get("source_id") in PRIVATE_SOURCE_IDS for e in item.get("evidence", [])):
            continue
        gap = {k: v for k, v in item.items() if k in REVIEW_FIELDS}
        gap["text"] = gap_text(item)
        gap["evidence"] = [{k: e[k] for k in ("source_id", "location", "quote") if k in e}
                           for e in item.get("evidence", [])]
        cited = {e["source_id"] for e in gap["evidence"]}
        gap["source_snapshots"] = public_sources([
            s for s in item.get("source_snapshots", sources or []) if s.get("id") in cited
        ])
        result.append(gap)
    return result


def public_analysis(report: dict | None) -> dict | None:
    if report is None:
        return None
    # Diagnostics and source inventories stay in the backend/run logs.
    return {k: v for k, v in report.items() if k in {"coverage", "finished_at"}}
