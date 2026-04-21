"""Adapter: DMS `.context/` feature.json → extract-agent canonical feature.json.

The DMS coding agent writes features using a schema that is close to, but not
identical to, extract-agent's on-disk format. A legacy DMS version additionally
produced ad-hoc fields (`preconditions`, `outputs`, `assumptions_and_gaps`) and
a flat `{source_field, target_field, transformation}` mapping shape that
extract-agent cannot consume.

This module contains a pure function :func:`adapt_feature` that migrates a DMS
feature dict to the extract-agent canonical shape. It is intentionally
non-destructive: it does not read or write files, so it can be covered by unit
tests and reused from a future CLI/HTTP importer.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Wiki file → extract-agent rules section. Sections can absorb multiple wikis.
_WIKI_TO_SECTIONS: dict[str, tuple[str, ...]] = {
    "shared": ("extraction", "gaps", "test_cases"),
    "code": ("extraction", "gaps"),
    "tests": ("test_cases",),
}

_FORBIDDEN_SL_FIELDS = ("preconditions", "outputs", "assumptions_and_gaps")

_FLAT_MAPPING_MARKERS = {"source_field", "target_field", "transformation"}


def adapt_feature(raw: dict[str, Any], *, warnings: list[str] | None = None) -> dict[str, Any]:
    """Return a normalised copy of a DMS / legacy feature.json payload.

    Migrations performed:

    * ``structured_logic`` → ``structured_logic_json`` (if canonical name missing)
    * ``dependencies`` → ``dependencies_json`` (if canonical name missing)
    * strip ad-hoc ``preconditions`` / ``outputs`` / ``assumptions_and_gaps``
      from ``structured_logic_json`` (they are not part of the schema)
    * convert ``error_handling`` from ``list[str]`` to
      ``dict[str, str]`` keyed as ``case_0``, ``case_1`` …
    * null out legacy flat ``message_mapping`` entries that use
      ``source_field``/``target_field`` — keep ``has_detailed_mapping=True`` so
      a subsequent mapping-enricher run can refill
    * fill missing ``source`` from ``source_document`` (pdf) or fall back to
      ``{"kind": "code"}`` when no provenance info is present
    * ensure ``status`` / ``confidence`` / ``extracted_at`` defaults are set

    The function returns a new dict; it does not mutate the input.

    Non-fatal issues are appended as human-readable strings to ``warnings``
    when the caller passes a list (useful for surfacing in import reports).
    """

    data = dict(raw)

    # structured_logic_json ← structured_logic
    if "structured_logic_json" not in data and "structured_logic" in data:
        data["structured_logic_json"] = data.pop("structured_logic")

    # dependencies_json ← dependencies
    if "dependencies_json" not in data and "dependencies" in data:
        data["dependencies_json"] = data.pop("dependencies")

    sl = data.get("structured_logic_json")
    if isinstance(sl, dict):
        sl = dict(sl)  # shallow copy so mutations don't leak
        for field in _FORBIDDEN_SL_FIELDS:
            if field in sl:
                sl.pop(field)
                _warn(warnings, f"dropped unsupported field structured_logic_json.{field} during import")

        eh = sl.get("error_handling")
        if isinstance(eh, list):
            sl["error_handling"] = {f"case_{i}": str(item) for i, item in enumerate(eh)}
            _warn(warnings, "converted error_handling from list to dict during import")

        steps = sl.get("logic_steps")
        if isinstance(steps, list):
            sl["logic_steps"] = [_adapt_logic_step(s, warnings=warnings) for s in steps]

        data["structured_logic_json"] = sl

    # source provenance
    if data.get("source") is None:
        src_doc = data.get("source_document")
        if src_doc:
            data["source"] = {"kind": "pdf", "document": src_doc, "file": None, "line": None}
        else:
            data["source"] = {"kind": "code", "document": None, "file": None, "line": None}

    # lifecycle defaults
    data.setdefault("status", "done")
    data.setdefault("confidence", 1.0)
    data.setdefault("extracted_at", datetime.now(UTC).isoformat())

    # source_document should be explicit null for code, not absent
    if "source_document" not in data:
        data["source_document"] = None

    return data


def _adapt_logic_step(step: Any, *, warnings: list[str] | None) -> Any:
    if not isinstance(step, dict):
        return step
    step = dict(step)

    mapping = step.get("message_mapping")
    if isinstance(mapping, list) and mapping and _is_flat_mapping(mapping):
        step_no = step.get("number", "?")
        _warn(warnings, f"step {step_no}: dropped legacy flat message_mapping; re-run mapping-enricher to refill")
        step["message_mapping"] = None
        step["has_detailed_mapping"] = True

    children = step.get("children")
    if isinstance(children, list):
        step["children"] = [_adapt_logic_step(c, warnings=warnings) for c in children]

    return step


def _is_flat_mapping(items: list[Any]) -> bool:
    for item in items:
        if not isinstance(item, dict):
            continue
        if _FLAT_MAPPING_MARKERS & item.keys():
            return True
    return False


def _warn(warnings: list[str] | None, msg: str) -> None:
    logger.warning("import_context: %s", msg)
    if warnings is not None:
        warnings.append(msg)


def load_wiki_sections(context_dir: Path) -> dict[str, str]:
    """Read `<context_dir>/wiki/*.md` into a ``{stem: body}`` map.

    Only files named ``shared.md``, ``code.md``, ``tests.md`` are considered —
    other files are ignored silently. Missing files yield empty map keys.
    """

    wiki_dir = context_dir / "wiki"
    out: dict[str, str] = {}
    if not wiki_dir.is_dir():
        return out
    for stem in _WIKI_TO_SECTIONS:
        path = wiki_dir / f"{stem}.md"
        if path.exists():
            try:
                out[stem] = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("import_context: could not read %s: %s", path, exc)
    return out


def merge_wiki_into_rules(
    existing: dict[str, str],
    wiki: dict[str, str],
    *,
    warnings: list[str] | None = None,
) -> dict[str, str]:
    """Return a new rules dict with wiki content merged into project rules.

    Wiki→section mapping (see ``_WIKI_TO_SECTIONS``):
    - ``shared.md`` → extraction + gaps + test_cases
    - ``code.md``   → extraction + gaps
    - ``tests.md``  → test_cases

    Safety: if a target section is already non-empty, it is left untouched
    and a warning is emitted — the operator decides whether to merge by hand.
    """

    result = dict(existing)
    for stem, body in wiki.items():
        if not body:
            continue
        for section in _WIKI_TO_SECTIONS.get(stem, ()):
            current = result.get(section, "").strip()
            if current:
                _warn(
                    warnings,
                    f"skipped wiki/{stem}.md → rules.{section}: section already populated; merge by hand",
                )
                continue
            result[section] = body
    return result
