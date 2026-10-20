"""Deterministic diff of extracted features between two versions of a spec page.

Re-importing a Confluence page replaces the document's features; this module
answers "what actually changed" without any LLM call. The comparison leans on
the deterministic parts of extraction (tables parsed verbatim from grids,
dependency lists, feature identity) so the diff reflects the spec, not LLM
noise: a version bump with identical structures is reported as non-material.

Run-to-run LLM variance is neutralized structurally, not by thresholds:
tables are matched globally by content fingerprint (a table the LLM attached
to a different step this run is a move, not a change), steps are matched by
verbatim text first (renumbering after an inserted step is non-material), and
dependencies are matched by the stable link target behind them (an LLM-phrased
dependency name is a rename, not remove+add).

The diff dict is stored on the document (``last_diff``) and rendered by the UI.
"""

import json
import re
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


def _table_fingerprint(table: dict) -> str:
    """Content identity of a SpecTable, independent of where the LLM attached it.

    Covers the deterministic payload (columns + field tree with cells); caption,
    table_id and section are location metadata and stay out.
    """

    def _field(f: dict) -> list:
        return [
            _norm(f.get("name")),
            [_norm(c) for c in f.get("cells") or []],
            [_field(c) for c in f.get("children") or []],
        ]

    payload = [
        [_norm(c.get("header")) for c in table.get("columns") or []],
        [_field(f) for f in table.get("fields") or []],
    ]
    return json.dumps(payload, ensure_ascii=False)


def _collect_tables(logic: dict) -> list[tuple[str, dict]]:
    """All of a feature's SpecTables with their section labels, in spec order."""
    out: list[tuple[str, dict]] = []
    for table in logic.get("input_tables") or []:
        out.append(("входные параметры", table))
    for table in logic.get("response_tables") or []:
        out.append(("выходные параметры", table))
    for number, step in sorted(
        _flatten_steps(logic.get("logic_steps") or []).items(), key=_step_sort_key
    ):
        for table in step.get("mapping_tables") or []:
            out.append((f"шаг {number}", table))
    return out


def _cancel_identical_tables(
    old_tabs: list[tuple[str, dict]], new_tabs: list[tuple[str, dict]]
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    """Drop table pairs with identical content regardless of section.

    A table the LLM attached to step 12 this run but left unattached (or on
    another step) last run cancels out here instead of surfacing as
    added/removed noise. Extra copies cancel too: the LLM attaching one
    response table to steps 8–11 at once this run (once last run) repeats
    content the spec already had — the set of tables is unchanged.
    """
    new_by_fp: dict[str, list[int]] = {}
    for i, (_, table) in enumerate(new_tabs):
        new_by_fp.setdefault(_table_fingerprint(table), []).append(i)

    old_rest: list[tuple[str, dict]] = []
    consumed: set[int] = set()
    for section, table in old_tabs:
        candidates = new_by_fp.get(_table_fingerprint(table), [])
        match = next((i for i in candidates if i not in consumed), None)
        if match is None:
            old_rest.append((section, table))
        else:
            consumed.add(match)
    new_rest = [pair for i, pair in enumerate(new_tabs) if i not in consumed]

    old_fps = {_table_fingerprint(t) for _, t in old_tabs}
    new_fps = set(new_by_fp)
    old_rest = [(sec, t) for sec, t in old_rest if _table_fingerprint(t) not in new_fps]
    new_rest = [(sec, t) for sec, t in new_rest if _table_fingerprint(t) not in old_fps]
    return old_rest, new_rest


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


def _number_key(number: str) -> list:
    return [int(p) if p.isdigit() else p for p in number.split(".")]


def _step_sort_key(item: tuple[str, dict]) -> list:
    return _number_key(item[0])


def _diff_steps(old_steps: list[dict], new_steps: list[dict]) -> dict | None:
    """Diff logic steps, matching by verbatim text first and number second.

    Text is the spec's own content; numbering is the LLM's slicing of it. An
    inserted step shifts every number after it — text-first matching turns that
    shift into non-material ``renumbered`` entries instead of a wall of fake
    ``changed`` ones.
    """
    old_flat = _flatten_steps(old_steps)
    new_flat = _flatten_steps(new_steps)

    # Pass 1: identical text — same step, possibly under a new number
    new_by_text: dict[str, list[str]] = {}
    for number in sorted(new_flat, key=_number_key):
        new_by_text.setdefault(_norm(new_flat[number].get("text")), []).append(number)

    renumbered = []
    matched_old: set[str] = set()
    matched_new: set[str] = set()
    for number in sorted(old_flat, key=_number_key):
        text = _norm(old_flat[number].get("text"))
        candidates = [n for n in new_by_text.get(text, []) if n not in matched_new]
        if not candidates:
            continue
        # Prefer keeping the same number when the text occurs more than once
        target = number if number in candidates else candidates[0]
        matched_old.add(number)
        matched_new.add(target)
        if target != number:
            renumbered.append({"old_number": number, "new_number": target, "text": text})

    # Pass 2: same number, different text — a genuine edit of that step
    changed = []
    for number in sorted(old_flat.keys() & new_flat.keys(), key=_number_key):
        if number in matched_old or number in matched_new:
            continue
        matched_old.add(number)
        matched_new.add(number)
        changed.append({
            "number": number,
            "old_text": _norm(old_flat[number].get("text")),
            "new_text": _norm(new_flat[number].get("text")),
        })

    added = [
        {"number": n, "text": _norm(new_flat[n].get("text"))}
        for n in sorted(new_flat.keys() - matched_new, key=_number_key)
    ]
    removed = [
        {"number": n, "text": _norm(old_flat[n].get("text"))}
        for n in sorted(old_flat.keys() - matched_old, key=_number_key)
    ]

    # Pass 3: re-slicing — the LLM split one step into sub-steps (or merged
    # them back). The subtree's concatenated verbatim text is identical, so
    # nothing in the spec changed: cancel the fake changed+added/removed set.
    def _subtree_text(flat: dict[str, dict], number: str) -> str:
        prefix = number + "."
        numbers = [number] + sorted((n for n in flat if n.startswith(prefix)), key=_number_key)
        return _norm(" ".join(_norm(flat[n].get("text")) for n in numbers))

    resliced = []
    for entry in list(changed):
        number = entry["number"]
        if _subtree_text(old_flat, number) == _subtree_text(new_flat, number):
            prefix = number + "."
            changed.remove(entry)
            added[:] = [a for a in added if not a["number"].startswith(prefix)]
            removed[:] = [r for r in removed if not r["number"].startswith(prefix)]
            resliced.append({"number": number})

    if not added and not removed and not changed and not renumbered and not resliced:
        return None
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "renumbered": renumbered,
        "resliced": resliced,
    }


def _dep_link_keys(dep: dict) -> set[str]:
    return {k for k in dep.get("link_keys") or [] if k}


def _names_contain(a: str, b: str) -> bool:
    """One name contains the other — the usual shape of LLM rename noise
    ('Коэффициент minutesToSubtractToGetDebt' vs 'minutesToSubtractToGetDebt')."""
    # Brackets/punctuation are transcription noise too: "[PL-Авито] Коды" vs "PL-Авито Коды"
    a, b = (" ".join(re.sub(r"[^\w.\-/ ]+", " ", x).split()).lower() for x in (a, b))
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 6 and shorter in longer


def _diff_dependencies(old_logic: dict, new_logic: dict) -> dict | None:
    """Diff used dependencies. Identity, in order of trust: exact (type, name),
    the stable link target behind the dependency (``link_keys``, resolved from
    the page's [LINK:Ln] markers at extraction time), then name containment.
    Link/containment matches are renames — reported but non-material."""

    def _deps(logic: dict) -> dict[tuple[str, str], dict]:
        return {
            (_norm(d.get("type")), _norm(d.get("name"))): d
            for d in logic.get("used_dependencies") or []
        }

    old_deps = _deps(old_logic)
    new_deps = _deps(new_logic)
    old_only = {k: v for k, v in old_deps.items() if k not in new_deps}
    new_only = {k: v for k, v in new_deps.items() if k not in old_deps}

    renamed = []
    for (old_type, old_name), old_dep in sorted(old_only.items()):
        match = None
        old_links = _dep_link_keys(old_dep)
        for (new_type, new_name), new_dep in sorted(new_only.items()):
            if new_type != old_type:
                continue
            if (old_links and old_links & _dep_link_keys(new_dep)) or _names_contain(old_name, new_name):
                match = (new_type, new_name)
                break
        if match is not None:
            new_only.pop(match)
            if old_name != match[1]:
                renamed.append({"type": old_type, "old_name": old_name, "new_name": match[1]})

    added = [{"type": t, "name": n} for t, n in sorted(new_only)]
    removed = [
        {"type": t, "name": n}
        for t, n in sorted(old_only)
        if not any(r["type"] == t and r["old_name"] == n for r in renamed)
    ]
    if not added and not removed and not renamed:
        return None
    return {"added": added, "removed": removed, "renamed": renamed}


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

    # Tables: cancel content-identical ones globally first (a table attached to
    # a different section this run is a move, not a change), then diff the rest
    # within their sections.
    old_rest, new_rest = _cancel_identical_tables(_collect_tables(old_logic), _collect_tables(new_logic))
    sections = list(dict.fromkeys([s for s, _ in old_rest] + [s for s, _ in new_rest]))
    tables = []
    for section in sections:
        tables += _diff_tables_section(
            section,
            [t for s, t in old_rest if s == section],
            [t for s, t in new_rest if s == section],
        )

    steps = _diff_steps(old_logic.get("logic_steps") or [], new_logic.get("logic_steps") or [])
    dependencies = _diff_dependencies(old_logic, new_logic)
    summary_changed = _norm(old.get("summary")) != _norm(new.get("summary"))

    steps_material = steps is not None and bool(steps["added"] or steps["removed"] or steps["changed"])
    deps_material = dependencies is not None and bool(dependencies["added"] or dependencies["removed"])
    material = bool(identity or tables or steps_material or deps_material)
    if not material and not summary_changed and steps is None and dependencies is None:
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


# ----------------------------------------------------------------------
# Enriched-dependency diff (source page moved ahead → what changed in it)
# ----------------------------------------------------------------------


def _diff_named_items(old_items: list[dict], new_items: list[dict], key, fields: list[str]) -> dict | None:
    """Generic diff of two item lists keyed by ``key(item)``: added/removed
    names + per-field changes on common items."""
    old_map = {key(i): i for i in old_items or [] if key(i)}
    new_map = {key(i): i for i in new_items or [] if key(i)}
    added = sorted(new_map.keys() - old_map.keys())
    removed = sorted(old_map.keys() - new_map.keys())
    changed = []
    for name in sorted(old_map.keys() & new_map.keys()):
        field_changes = []
        for field in fields:
            o, n = _norm(old_map[name].get(field)).lower(), _norm(new_map[name].get(field)).lower()
            if o != n:
                field_changes.append({"field": field, "old": o, "new": n})
        if field_changes:
            changed.append({"name": name, "changes": field_changes})
    if not added and not removed and not changed:
        return None
    return {"added": added, "removed": removed, "changed": changed}


def _flatten_message_fields(fields: list[dict], prefix: str = "") -> list[dict]:
    out = []
    for f in fields or []:
        name = _norm(f.get("element"))
        path = f"{prefix}.{name}" if prefix else name
        out.append({**f, "element": path})
        out.extend(_flatten_message_fields(f.get("children") or [], path))
    return out


def diff_enriched_data(dep_type: str, old: dict | None, new: dict | None) -> dict | None:
    """Deterministic diff of a dependency's enrichment between source-page
    versions — the materiality gate of the source cascade: a non-None result
    marks the features using this dependency stale (``dep_impact``), so a page
    edit that leaves the structure alone does not invalidate reviewed analysis.
    Only structural fields are compared; LLM-phrased prose (descriptions) is
    run-to-run noise and deliberately ignored.

    Returns None when nothing changed. Shape by dep_type:
    db_table → {"columns": {...}}, external_api → {"endpoints": {...}},
    kafka_topic → {"message_fields": {...}}, cache → {"key_patterns": {...}},
    external_doc → {"content_changed": true}.
    """
    if not old or not new:
        return None

    if dep_type == "db_table":
        columns = _diff_named_items(
            old.get("columns") or [], new.get("columns") or [],
            key=lambda c: _norm(c.get("name")),
            fields=["col_type", "nullable", "is_pk", "fk_references"],
        )
        return {"columns": columns} if columns else None

    if dep_type == "external_api":
        endpoints = _diff_named_items(
            old.get("endpoints") or [], new.get("endpoints") or [],
            key=lambda e: f"{_norm(e.get('method')).upper()} {_norm(e.get('path'))}".strip(),
            fields=[],
        )
        return {"endpoints": endpoints} if endpoints else None

    if dep_type == "kafka_topic":
        fields = _diff_named_items(
            _flatten_message_fields(old.get("message_fields") or []),
            _flatten_message_fields(new.get("message_fields") or []),
            key=lambda f: f.get("element"),
            fields=["field_type", "required", "cardinality"],
        )
        return {"message_fields": fields} if fields else None

    if dep_type == "cache":
        patterns = _diff_named_items(
            old.get("key_patterns") or [], new.get("key_patterns") or [],
            key=lambda p: _norm(p.get("pattern")),
            fields=["ttl_seconds"],
        )
        return {"key_patterns": patterns} if patterns else None

    if dep_type == "external_doc":
        if _norm(old.get("content_html")) != _norm(new.get("content_html")):
            return {"content_changed": True}
        return None

    return None


def compute_spec_diff(
    prior_features: dict[str, dict],
    current_features: dict[str, dict],
    *,
    old_version: int | None = None,
    new_version: int | None = None,
    source_unchanged: bool = False,
) -> dict:
    """Diff a document's features before vs after re-extraction.

    ``prior_features`` / ``current_features``: {name: stored feature dict}.

    ``source_unchanged`` — the page text is identical to the one the prior
    features came from. Then nothing in the spec changed by definition and
    every difference is LLM run-to-run noise: the diff is still reported for
    transparency, but nothing is material. This is the primary materiality
    gate; the structural matching below only has to be precise for pages that
    did change.
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

    if source_unchanged:
        for detail in changed:
            detail["material"] = False
        material = False
    else:
        material = bool(added or removed or any(c["material"] for c in changed))
    return {
        "computed_at": datetime.now(UTC).isoformat(),
        "source_unchanged": source_unchanged,
        "old_version": old_version,
        "new_version": new_version,
        "material": material,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }
