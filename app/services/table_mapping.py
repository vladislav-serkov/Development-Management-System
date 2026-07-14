"""Deterministic conversion of spec tables (parsed from Confluence XHTML) into
MessageField mappings — replaces LLM Call 2 for text imports.

A table qualifies as a field mapping when its headers contain a recognizable
"parameter name" column plus at least a type or requiredness column. Nesting is
encoded by column position: the name of a nested field sits one column deeper
(colspan expansion in the converter guarantees this invariant).
"""

import logging
import re
from collections.abc import Callable

from app.schemas.extraction import FieldSourceRef, MessageField

logger = logging.getLogger(__name__)

# Resolves a [LINK:Ln] id to the dependency it points at, or None if unknown.
LinkResolver = Callable[[str], tuple[str, str] | None]

NAME_HEADERS = {
    "параметр", "параметры", "поле", "поля", "элемент", "атрибут",
    "имя", "имя поля", "наименование", "наименование поля",
    "field", "parameter", "name", "element", "attribute",
}
TYPE_HEADERS = {"тип", "тип данных", "тип поля", "type", "формат"}
REQUIRED_HEADERS = {
    "обязательность", "обяз", "обяз.", "обязательное", "обязательный",
    "обязательность заполнения", "кардинальность", "required", "mandatory",
}
SOURCE_HEADERS = {
    "источник", "источник значения", "источник данных", "заполнение",
    "правила заполнения", "откуда берется", "откуда берётся", "source", "маппинг",
}
DESCRIPTION_HEADERS = {
    "комментарий", "комментарии", "описание", "примечание", "назначение",
    "description", "comment",
}
EXAMPLE_HEADERS = {"пример", "пример значения", "example"}
CONSTRAINT_HEADERS = {"ограничения", "ограничение", "валидация", "validation"}

_CARDINALITY_RE = re.compile(r"^\d+\s*(?:-|\.\.)\s*(?:\d+|n)$", re.IGNORECASE)

# Where a table's fields live, read off the line the spec puts above the table
# ("query", "HTTP 200 | Тело ответа в формате JSON"). Order matters: a body caption
# often also mentions the HTTP status, and "header" must not be shadowed by "body".
_PARAM_IN_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("header", ("заголовк", "заголовок", "header")),
    ("path", ("path", "путь", "path-параметр")),
    ("query", ("query", "параметры запроса", "строка запроса")),
    ("body", ("тело", "body", "payload", "json")),
]


def param_in_from_context(context: str) -> str | None:
    """Infer body/header/query/path from the text introducing a table. None if unclear."""
    text = (context or "").lower()
    if not text:
        return None
    for param_in, markers in _PARAM_IN_MARKERS:
        if any(m in text for m in markers):
            return param_in
    # "HTTP 200" with no further hint: a response table with no caption is the body.
    if re.search(r"http\s*[1-5]\d\d", text):
        return "body"
    return None


def _norm(header: str) -> str:
    return " ".join(header.split()).strip(" :.").lower()


def _clean_cell(text: str) -> str:
    return " ".join(text.split()).strip("* ")


def _parse_required(value: str) -> tuple[bool | None, str | None]:
    """Parse the 'Обязательность' cell → (required, cardinality)."""
    v = _clean_cell(value).lower()
    if not v:
        return None, None
    if _CARDINALITY_RE.match(v):
        card = v.replace(" ", "")
        return not card.startswith("0"), card
    if v.startswith(("да", "yes", "true", "обяз")):
        return True, None
    if v.startswith(("нет", "no", "false", "опцион", "необяз")):
        return False, None
    if v in ("1", "1-1", "1..1"):
        return True, v
    if v in ("0", "0-1", "0..1"):
        return False, v
    return None, None


def _is_collection(field_type: str | None, cardinality: str | None) -> bool:
    if cardinality and cardinality.lower().endswith("n"):
        return True
    if field_type and re.search(r"array|массив|list|\[\]", field_type, re.IGNORECASE):
        return True
    return False


def table_to_message_fields(
    table: dict,
    resolve_link: LinkResolver | None = None,
) -> list[MessageField] | None:
    """Convert a parsed table grid into a MessageField tree.

    ``resolve_link`` maps a [LINK:Ln] id from a source cell to the (dep_type, dep_name)
    it points at, turning the free-text source into a structured ``source_refs`` link.

    Rows the spec struck through are skipped: a retired field must not reappear in the
    mapping as a live one.

    Returns None when the table doesn't look like a field mapping (no name
    column, or neither type nor requiredness column) — caller keeps it verbatim.
    """
    headers = [_norm(h) for h in table.get("headers", [])]
    rows = table.get("rows", [])
    if not headers or not rows:
        return None

    row_links: list[list[list[dict]]] = table.get("row_links") or []
    deprecated_rows: set[int] = set(table.get("deprecated_rows") or [])

    name_start = next((i for i, h in enumerate(headers) if h in NAME_HEADERS), None)
    if name_start is None:
        return None

    # Consecutive empty headers after the name column belong to the name span
    # (nesting depth columns).
    name_end = name_start
    while name_end + 1 < len(headers) and headers[name_end + 1] == "":
        name_end += 1

    roles: dict[int, str] = {}
    for i, h in enumerate(headers):
        if i <= name_end:
            continue
        if h in TYPE_HEADERS:
            roles[i] = "type"
        elif h in REQUIRED_HEADERS:
            roles[i] = "required"
        elif h in SOURCE_HEADERS:
            roles[i] = "source"
        elif h in DESCRIPTION_HEADERS:
            roles[i] = "description"
        elif h in EXAMPLE_HEADERS:
            roles[i] = "example"
        elif h in CONSTRAINT_HEADERS:
            roles[i] = "constraint"

    if "type" not in roles.values() and "required" not in roles.values():
        return None

    def cell(row: list[str], role: str) -> str | None:
        for i, r in roles.items():
            if r == role and i < len(row):
                value = _clean_cell(row[i])
                if value:
                    return value
        return None

    def source_refs(row_index: int) -> list[FieldSourceRef]:
        """Dependencies linked from this row's source cell, deduped, order preserved."""
        if resolve_link is None or row_index >= len(row_links):
            return []
        cells = row_links[row_index]
        refs: list[FieldSourceRef] = []
        seen: set[tuple[str, str, str | None]] = set()
        for i, role in roles.items():
            if role != "source" or i >= len(cells):
                continue
            for link in cells[i]:
                dep = resolve_link(link["link_id"])
                if dep is None:
                    continue
                key = (dep[0], dep[1], link.get("field"))
                if key in seen:
                    continue
                seen.add(key)
                refs.append(FieldSourceRef(dep_type=dep[0], dep_name=dep[1], field=link.get("field")))
        return refs

    roots: list[MessageField] = []
    stack: list[tuple[int, MessageField]] = []
    skipped_deprecated = 0
    for row_index, row in enumerate(rows):
        if row_index in deprecated_rows:
            skipped_deprecated += 1
            continue
        name_cells = row[name_start:name_end + 1]
        indent = next((i for i, c in enumerate(name_cells) if _clean_cell(c)), None)
        if indent is None:
            continue  # continuation/empty row — nothing to anchor it to reliably

        required, cardinality = _parse_required(cell(row, "required") or "")
        field_type = cell(row, "type")
        description = cell(row, "description")
        constraint = cell(row, "constraint")
        if constraint:
            description = f"{description} Ограничения: {constraint}" if description else f"Ограничения: {constraint}"

        field = MessageField(
            element=_clean_cell(name_cells[indent]),
            field_type=field_type,
            required=required,
            cardinality=cardinality,
            is_collection=_is_collection(field_type, cardinality),
            description=description,
            source=cell(row, "source"),
            source_refs=source_refs(row_index),
            example=cell(row, "example"),
        )

        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            field.parent = stack[-1][1].element
            stack[-1][1].children.append(field)
        else:
            roots.append(field)
        stack.append((indent, field))

    if skipped_deprecated:
        logger.info(
            "Table %s: skipped %d row(s) struck through in the spec",
            table.get("id"), skipped_deprecated,
        )

    return roots or None
