"""Public gap results: private analysis context never leaves the backend."""

PRIVATE_SOURCE_IDS = frozenset({"project-notes", "analyst-decisions", "analysis-rules"})

_GAP_FIELDS = {
    "id", "kind", "gap_type", "severity", "actionable", "question", "suggestion",
    "status", "analyst_text", "subject", "location", "scenario", "business_impact",
    "presence", "needs_review", "history", "archived", "first_seen_at", "last_seen_at",
    "reconsideration_reason",
}


def public_sources(sources: list[dict]) -> list[dict]:
    fields = {"id", "title", "url", "version", "content_hash", "page_id"}
    return [{k: v for k, v in source.items() if k in fields}
            for source in sources if source.get("id") not in PRIVATE_SOURCE_IDS]


def public_gaps(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        # Older reports could cite analyst notes as if they were requirements.
        # Do not publish these unsupported findings, including their quotations.
        if any(e.get("source_id") in PRIVATE_SOURCE_IDS for e in item.get("evidence", [])):
            continue
        gap = {k: v for k, v in item.items() if k in _GAP_FIELDS}
        if "evidence" in item:
            gap["evidence"] = [{k: e[k] for k in ("source_id", "location", "quote") if k in e}
                               for e in item["evidence"]]
        if "source_snapshots" in item:
            gap["source_snapshots"] = public_sources(item["source_snapshots"])
        for field in ("source_hashes", "review_source_hashes"):
            if field in item:
                gap[field] = {sid: value for sid, value in item[field].items() if sid not in PRIVATE_SOURCE_IDS}
        result.append(gap)
    return result


def public_analysis(report: dict | None) -> dict | None:
    if report is None:
        return None
    return {
        **{k: v for k, v in report.items() if k in {
            "coverage", "started_at", "finished_at", "engine", "limitations",
        }},
        "sources": public_sources(report.get("sources", [])),
    }
