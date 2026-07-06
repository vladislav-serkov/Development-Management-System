"""Deterministic conversion of spec tables (parsed from Confluence XHTML) into
MessageField mappings — replaces LLM Call 2 for text imports.

A table qualifies as a field mapping when its headers contain a recognizable
"parameter name" column plus at least a type or requiredness column. Nesting is
encoded by column position: the name of a nested field sits one column deeper
(colspan expansion in the converter guarantees this invariant).
"""

import logging
import re

from app.schemas.extraction import MessageField

logger = logging.getLogger(__name__)

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


def table_to_message_fields(table: dict) -> list[MessageField] | None:
    """Convert a parsed table grid into a MessageField tree.

    Returns None when the table doesn't look like a field mapping (no name
    column, or neither type nor requiredness column) — caller falls back to Call 2.
    """
    headers = [_norm(h) for h in table.get("headers", [])]
    rows = table.get("rows", [])
    if not headers or not rows:
        return None

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

    roots: list[MessageField] = []
    stack: list[tuple[int, MessageField]] = []
    for row in rows:
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

    return roots or None
