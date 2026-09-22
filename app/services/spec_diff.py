"""Deterministic diff of extracted features between two versions of a spec page.

Re-importing a Confluence page replaces the document's features; this module
answers "what actually changed" without any LLM call. The comparison leans on
the deterministic parts of extraction (tables parsed verbatim from grids,
dependency lists, feature identity) so the diff reflects the spec, not LLM
noise: a version bump with identical structures is reported as non-material.

The diff dict is stored on the document (``last_diff``) and rendered by the UI.
"""

from datetime import UTC, datetime

# Keys the extraction pipeline owns: on re-extraction these come from the new
# run, everything else (analysis counts, impl/autotest state, stale flags) is
# carried over from the prior feature record so re-import doesn't erase it.
EXTRACTION_OWNED_KEYS = {
    "name",
    "display_name",
    "source_document",
    "type",
    "confidence",
    "summary",
    "method",
    "endpoint",
    "schedule",
    "dependencies_json",
    "structured_logic_json",
    "status",
    "extracted_at",
}

# Cleared on re-extraction regardless of the prior record: a re-detected
# feature is present in the new spec version by definition.
_CLEARED_ON_REEXTRACT = {"orphaned", "orphaned_at"}


def merge_reextracted_feature(prior: dict | None, extracted: dict) -> dict:
    """Merge a freshly extracted feature payload onto the prior record.

    Extraction-owned keys win from ``extracted``; analysis state (gap/test-case
    counts, run timestamps, impl_* and stale flags) survives from ``prior``.
    """
    if not prior:
        return extracted
    merged = {k: v for k, v in prior.items() if k not in EXTRACTION_OWNED_KEYS and k not in _CLEARED_ON_REEXTRACT}
    merged.update(extracted)
    return merged


# ----------------------------------------------------------------------
# Diff computation
# ----------------------------------------------------------------------


def _norm(text) -> str:
    return " ".join(str(text or "").split())


def _flatten_fields(fields: list[dict], prefix: str = "") -> dict[str, dict]:
    """Flatten a SpecField tree into {dotted_name: field}."""
    out: dict[str, dict] = {}
    for field in fields or []:
        name = _norm(field.get("name"))
        path = f"{prefix}.{name}" if prefix else name
        # Duplicate rows (same field name twice in a table) keep the first one
        out.setdefault(path, field)
        out.update(_flatten_fields(field.get("children") or [], path))
    return out


def _cells_by_header(table: dict, field: dict) -> dict[str, str]:
    headers = [_norm(c.get("header")) for c in table.get("columns") or []]
    cells = field.get("cells") or []
    return {h: _norm(cells[i]) if i < len(cells) else "" for i, h in enumerate(headers) if h}


def _diff_table_pair(old: dict, new: dict) -> dict | None:
    """Diff two matched SpecTables. Returns None when identical."""
    old_fields = _flatten_fields(old.get("fields") or [])
    new_fields = _flatten_fields(new.get("fields") or [])

    added = [n for n in new_fields if n not in old_fields]
    removed = [n for n in old_fields if n not in new_fields]

    changed = []
    for name in old_fields.keys() & new_fields.keys():
        old_cells = _cells_by_header(old, old_fields[name])
        new_cells = _cells_by_header(new, new_fields[name])
        cell_changes = []
        for header in old_cells.keys() | new_cells.keys():
            o, n = old_cells.get(header, ""), new_cells.get(header, "")
            if o != n:
                cell_changes.append({"column": header, "old": o, "new": n})
        if cell_changes:
            cell_changes.sort(key=lambda c: c["column"])
            changed.append({"name": name, "changes": cell_changes})

    if not added and not removed and not changed:
        return None
    added.sort()
    removed.sort()
    changed.sort(key=lambda c: c["name"])
    return {"added_fields": added, "removed_fields": removed, "changed_fields": changed}


def _match_tables(old_tables: list[dict], new_tables: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """Pair tables of one section: by caption first, leftovers by order."""
    old_left = list(old_tables or [])
    new_left = list(new_tables or [])
    pairs: list[tuple[dict | None, dict | None]] = []

    for old in list(old_left):
        cap = _norm(old.get("caption"))
        if not cap:
            continue
        match = next((n for n in new_left if _norm(n.get("caption")) == cap), None)
        if match is not None:
            pairs.append((old, match))
            old_left.remove(old)
            new_left.remove(match)

    while old_left or new_left:
        pairs.append((old_left.pop(0) if old_left else None, new_left.pop(0) if new_left else None))
    return pairs


def _table_label(table: dict | None) -> str | None:
    if table is None:
        return None
    return _norm(table.get("caption")) or None


def _diff_tables_section(section: str, old_tables: list[dict], new_tables: list[dict]) -> list[dict]:
    out = []
    for old, new in _match_tables(old_tables, new_tables):
        if old is None:
            out.append({"section": section, "caption": _table_label(new), "table": "added"})
        elif new is None:
            out.append({"section": section, "caption": _table_label(old), "table": "removed"})
        else:
            diff = _diff_table_pair(old, new)
            if diff is not None:
                out.append({"section": section, "caption": _table_label(new) or _table_label(old), **diff})
    return out


def _flatten_steps(steps: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for step in steps or []:
        number = _norm(step.get("number"))
        out.setdefault(number, step)
        out.update(_flatten_steps(step.get("children") or []))
    return out


def _diff_steps(old_steps: list[dict], new_steps: list[dict]) -> dict | None:
    old_flat = _flatten_steps(old_steps)
    new_flat = _flatten_steps(new_steps)

    added = [{"number": n, "text": _norm(new_flat[n].get("text"))} for n in new_flat if n not in old_flat]
    removed = [{"number": n, "text": _norm(old_flat[n].get("text"))} for n in old_flat if n not in new_flat]
    changed = []
    for number in old_flat.keys() & new_flat.keys():
        old_text = _norm(old_flat[number].get("text"))
        new_text = _norm(new_flat[number].get("text"))
        if old_text != new_text:
            changed.append({"number": number, "old_text": old_text, "new_text": new_text})

    if not added and not removed and not changed:
        return None

    def _key(entry: dict):
        return [int(p) if p.isdigit() else p for p in entry["number"].split(".")]

    added.sort(key=_key)
    removed.sort(key=_key)
    changed.sort(key=_key)
    return {"added": added, "removed": removed, "changed": changed}


def _diff_dependencies(old_logic: dict, new_logic: dict) -> dict | None:
    def _deps(logic: dict) -> dict[tuple[str, str], dict]:
        return {
            (_norm(d.get("type")), _norm(d.get("name"))): d
            for d in logic.get("used_dependencies") or []
        }

    old_deps = _deps(old_logic)
    new_deps = _deps(new_logic)
    added = [{"type": t, "name": n} for t, n in sorted(new_deps.keys() - old_deps.keys())]
    removed = [{"type": t, "name": n} for t, n in sorted(old_deps.keys() - new_deps.keys())]
    if not added and not removed:
        return None
    return {"added": added, "removed": removed}


def _step_mapping_diffs(old_steps: dict[str, dict], new_steps: dict[str, dict]) -> list[dict]:
    out = []
    for number in sorted(old_steps.keys() & new_steps.keys(), key=lambda n: [int(p) if p.isdigit() else p for p in n.split(".")]):
        out.extend(
            _diff_tables_section(
                f"шаг {number}",
                old_steps[number].get("mapping_tables") or [],
                new_steps[number].get("mapping_tables") or [],
            )
        )
    return out


def diff_feature(old: dict, new: dict) -> dict | None:
    """Diff two stored feature dicts. Returns None when nothing changed.

    ``material`` is driven by the deterministic parts (identity, tables,
    steps, dependencies); a summary-only change is reported but non-material,
    since the summary is LLM-phrased and may vary between runs.
    """
    old_logic = old.get("structured_logic_json") or old.get("structured_logic") or {}
    new_logic = new.get("structured_logic_json") or new.get("structured_logic") or {}
    if not isinstance(old_logic, dict):
        old_logic = {}
    if not isinstance(new_logic, dict):
        new_logic = {}

    identity = []
    for key, label in (("method", "метод"), ("endpoint", "endpoint"), ("schedule", "расписание"), ("display_name", "название")):
        o, n = _norm(old.get(key)), _norm(new.get(key))
        if o != n:
            identity.append({"field": label, "old": o, "new": n})

    tables = []
    tables += _diff_tables_section("входные параметры", old_logic.get("input_tables") or [], new_logic.get("input_tables") or [])
    tables += _diff_tables_section("выходные параметры", old_logic.get("response_tables") or [], new_logic.get("response_tables") or [])
    tables += _step_mapping_diffs(_flatten_steps(old_logic.get("logic_steps") or []), _flatten_steps(new_logic.get("logic_steps") or []))

    steps = _diff_steps(old_logic.get("logic_steps") or [], new_logic.get("logic_steps") or [])
    dependencies = _diff_dependencies(old_logic, new_logic)
    summary_changed = _norm(old.get("summary")) != _norm(new.get("summary"))

    material = bool(identity or tables or steps or dependencies)
    if not material and not summary_changed:
        return None
    return {
        "name": new.get("name") or old.get("name"),
        "display_name": new.get("display_name") or old.get("display_name"),
        "material": material,
        "identity": identity,
        "summary_changed": summary_changed,
        "tables": tables,
        "steps": steps,
        "dependencies": dependencies,
    }


def compute_spec_diff(
    prior_features: dict[str, dict],
    current_features: dict[str, dict],
    *,
    old_version: int | None = None,
    new_version: int | None = None,
) -> dict:
    """Diff a document's features before vs after re-extraction.

    ``prior_features`` / ``current_features``: {name: stored feature dict}.
    """
    added = sorted(current_features.keys() - prior_features.keys())
    removed = sorted(prior_features.keys() - current_features.keys())

    changed: list[dict] = []
    unchanged: list[str] = []
    for name in sorted(prior_features.keys() & current_features.keys()):
        detail = diff_feature(prior_features[name], current_features[name])
        if detail is None:
            unchanged.append(name)
        else:
            changed.append(detail)

    material = bool(added or removed or any(c["material"] for c in changed))
    return {
        "computed_at": datetime.now(UTC).isoformat(),
        "old_version": old_version,
        "new_version": new_version,
        "material": material,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }
