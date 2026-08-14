"""Deterministic conversion of spec tables (parsed from Confluence XHTML) into
SpecTable structures — the spec's own table, verbatim, with role annotations.

A table qualifies as a field table when its headers contain a recognizable
"parameter name" column plus at least a type or requiredness column. Nesting is
encoded by column position: the name of a nested field sits one column deeper
(colspan expansion in the converter guarantees this invariant). Everything else
— column set, headers, cell contents — is preserved exactly as the spec wrote it.
"""

import logging
import re
from collections.abc import Callable

from app.schemas.extraction import FieldSourceRef, SpecColumn, SpecField, SpecTable

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

_ROLE_BY_HEADER: list[tuple[frozenset[str], str]] = [
    (frozenset(TYPE_HEADERS), "type"),
    (frozenset(REQUIRED_HEADERS), "required"),
    (frozenset(SOURCE_HEADERS), "source"),
    (frozenset(DESCRIPTION_HEADERS), "description"),
    (frozenset(EXAMPLE_HEADERS), "example"),
    (frozenset(CONSTRAINT_HEADERS), "constraint"),
]

# Where a table's fields live, read off the line the spec puts above the table
# ("query", "HTTP 200 | Тело ответа в формате JSON"). Order matters: a body caption
# often also mentions the HTTP status, and "header" must not be shadowed by "body".
_PARAM_IN_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("header", ("заголовк", "заголовок", "header")),
    ("path", ("path", "путь", "path-параметр")),
    ("query", ("query", "параметры запроса", "строка запроса")),
    ("body", ("тело", "body", "payload", "json")),
]

_STATUS_CODES_RE = re.compile(r"\b[1-5](?:\d\d|xx)\b", re.IGNORECASE)


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


def status_codes_from_context(context: str) -> str | None:
    """Read HTTP status codes off the heading above a response table, verbatim order."""
    codes = _STATUS_CODES_RE.findall(context or "")
    deduped = list(dict.fromkeys(codes))
    return ", ".join(deduped) if deduped else None


def _norm(header: str) -> str:
    return " ".join(header.split()).strip(" :.").lower()


def _clean_cell(text: str) -> str:
    return " ".join(text.split()).strip("* ")


def _column_role(header: str) -> str | None:
    h = _norm(header)
    for headers, role in _ROLE_BY_HEADER:
        if h in headers:
            return role
    return None


def table_to_spec_table(
    table: dict,
    resolve_link: LinkResolver | None = None,
    require_typed: bool = True,
) -> SpecTable | None:
    """Convert a parsed table grid into a SpecTable: columns verbatim + field tree.

    ``resolve_link`` maps a [LINK:Ln] id from a source cell to the (dep_type, dep_name)
    it points at, turning the free-text source into a structured ``source_refs`` link.

    Rows the spec struck through are skipped: a retired field must not reappear
    as a live one.

    Returns None when the table doesn't look like a field table (no name column,
    or — with ``require_typed`` — neither type nor requiredness column) — caller
    keeps it verbatim as a reference table. Pass ``require_typed=False`` for
    tables the LLM already classified as parameter tables.
    """
    headers_raw = table.get("headers", [])
    headers = [_norm(h) for h in headers_raw]
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

    # Data columns: everything outside the name span, minus columns that are
    # empty both in header and in every row (colspan padding artifacts).
    col_indexes: list[int] = []
    for i in range(len(headers)):
        if name_start <= i <= name_end:
            continue
        if not headers[i] and all(not _clean_cell(r[i]) for r in rows if i < len(r)):
            continue
        col_indexes.append(i)

    columns = [
        SpecColumn(header=headers_raw[i].strip(), role=_column_role(headers_raw[i]))
        for i in col_indexes
    ]
    roles = {i: c.role for i, c in zip(col_indexes, columns)}

    if require_typed and "type" not in roles.values() and "required" not in roles.values():
        return None

    def source_refs(row_index: int) -> list[FieldSourceRef]:
        """Dependencies linked from this row's source cell, deduped, order preserved."""
        if resolve_link is None or row_index >= len(row_links):
            return []
        cells = row_links[row_index]
        refs: list[FieldSourceRef] = []
        seen: set[tuple[str, str, str | None]] = set()
        for i in col_indexes:
            if roles.get(i) != "source" or i >= len(cells):
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

    roots: list[SpecField] = []
    stack: list[tuple[int, SpecField]] = []
    skipped_deprecated = 0
    for row_index, row in enumerate(rows):
        if row_index in deprecated_rows:
            skipped_deprecated += 1
            continue
        name_cells = row[name_start:name_end + 1]
        indent = next((i for i, c in enumerate(name_cells) if _clean_cell(c)), None)
        if indent is None:
            continue  # continuation/empty row — nothing to anchor it to reliably

        field = SpecField(
            name=_clean_cell(name_cells[indent]),
            cells=[_clean_cell(row[i]) if i < len(row) else "" for i in col_indexes],
            source_refs=source_refs(row_index),
        )

        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1].children.append(field)
        else:
            roots.append(field)
        stack.append((indent, field))

    if skipped_deprecated:
        logger.info(
            "Table %s: skipped %d row(s) struck through in the spec",
            table.get("id"), skipped_deprecated,
        )

    if not roots:
        return None

    context = table.get("context", "") or ""
    return SpecTable(
        table_id=table.get("id"),
        caption=context or None,
        location=param_in_from_context(context),
        status_codes=status_codes_from_context(context),
        columns=columns,
        fields=roots,
    )
