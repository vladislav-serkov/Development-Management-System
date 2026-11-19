"""Execute SQL artifacts against the test stand database.

The test DB endpoint is behind pgbouncer, so connections are opened with
statement_cache_size=0 (named prepared statements don't survive transaction
pooling). Scripts run inside one transaction: either every statement applies
or none do.

The stand is shared with other teams, so the executor itself refuses statements
that would wipe or reshape their data (``destructive_statement``): DELETE and
UPDATE that are not narrowed to particular rows, TRUNCATE, DROP, ALTER. The
refusal happens before a connection is opened and has no off switch — whoever
calls ``execute_sql`` or ``dry_run_scripts`` and whatever wrote the SQL.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import asyncpg

from app.config import settings
from app.services.stand_network import describe_db_connect_error

logger = logging.getLogger(__name__)

MAX_ROWS = 100
CONNECT_TIMEOUT = 10
STATEMENT_TIMEOUT = 30

_ROW_RETURNING_RE = re.compile(
    r"^(select|with|show|values|table|explain)\b", re.IGNORECASE
)
_RETURNING_RE = re.compile(r"\breturning\b", re.IGNORECASE)


def is_configured() -> bool:
    return bool(settings.test_db_url)


def test_db_info() -> dict[str, Any]:
    """Connection target for the UI (host/database only, never credentials)."""
    if not is_configured():
        return {"configured": False, "host": None, "database": None}
    parsed = urlparse(settings.test_db_url)
    return {
        "configured": True,
        "host": parsed.hostname,
        "database": parsed.path.lstrip("/") or None,
    }


def _opaque_end(sql: str, i: int) -> tuple[str, int] | None:
    """Kind and end offset of the comment or quoted text that starts at ``i``, if any.

    Kinds: ``comment`` (-- and /* */), ``string`` ('…'), ``ident`` ("…"),
    ``dollar`` ($tag$…$tag$). The splitter and the destructive-statement check
    both rely on it, so they always agree on what is code and what is not.
    """
    n = len(sql)
    two = sql[i : i + 2]
    if two == "--":
        end = sql.find("\n", i)
        return "comment", n if end == -1 else end
    if two == "/*":
        end = sql.find("*/", i + 2)
        return "comment", n if end == -1 else end + 2
    ch = sql[i]
    if ch in ("'", '"'):
        end = i + 1
        while end < n:
            if sql[end] == ch:
                # doubled quote inside a literal ('' or "") is an escape
                if end + 1 < n and sql[end + 1] == ch:
                    end += 2
                    continue
                break
            end += 1
        return ("string" if ch == "'" else "ident"), min(end + 1, n)
    if ch == "$":
        tag_match = re.match(r"\$[A-Za-z_]*\$", sql[i:])
        if tag_match:
            tag = tag_match.group(0)
            end = sql.find(tag, i + len(tag))
            return "dollar", n if end == -1 else end + len(tag)
    return None


def split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into statements on top-level semicolons.

    Respects single/double quotes, dollar-quoted strings, line (--) and
    block (/* */) comments, so semicolons inside literals don't split.
    """
    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        opaque = _opaque_end(sql, i)
        if opaque:
            end = opaque[1]
            current.append(sql[i:end])
            i = end
            continue
        ch = sql[i]
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1

    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def _strip_leading_comments(stmt: str) -> str:
    prev = None
    while prev != stmt:
        prev = stmt
        stmt = re.sub(r"^\s*--[^\n]*\n?", "", stmt)
        stmt = re.sub(r"^\s*/\*.*?\*/", "", stmt, flags=re.DOTALL)
        stmt = stmt.lstrip()
    return stmt


def _returns_rows(stmt: str) -> bool:
    body = _strip_leading_comments(stmt)
    return bool(_ROW_RETURNING_RE.match(body)) or bool(_RETURNING_RE.search(body))


# ----------------------------------------------------------------------
# Statements the shared stand must never run
# ----------------------------------------------------------------------

_WORD_RE = re.compile(r"[^\W\d][\w$]*")
_NUMBER_RE = re.compile(r"\d[\w.]*")
_OPERATORS = ("::", "<>", "!=", "<=", ">=", "||")
# keyword -> (what it does, what to do instead)
_SCHEMA_CHANGES = {
    "truncate": ("он очищает таблицу целиком", "Удаляйте только свои записи: DELETE с WHERE по их идентификаторам."),
    "drop": ("он удаляет объекты базы", "Платформа меняет на стенде только данные."),
    "alter": ("он меняет структуру базы", "Платформа меняет на стенде только данные."),
}
# Words of a WHERE condition that are not column names
_CONSTANT_WORDS = frozenset(
    "true false null unknown not and or is in between symmetric like ilike similar to escape "
    "distinct from isnull notnull any all some array "
    "current_date current_time current_timestamp localtime localtimestamp".split()
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str  # word | number | op | string | ident | dollar
    text: str  # words lower-cased, everything else as written
    depth: int  # how many parentheses enclose it


def _tokens(stmt: str) -> list[_Token]:
    """A statement as tokens: comments dropped, every literal a single token."""
    tokens: list[_Token] = []
    depth = 0
    i, n = 0, len(stmt)
    while i < n:
        ch = stmt[i]
        if ch.isspace():
            i += 1
            continue
        opaque = _opaque_end(stmt, i)
        if opaque:
            kind, end = opaque
            if kind != "comment":
                tokens.append(_Token(kind, stmt[i:end], depth))
            i = end
            continue
        if match := _WORD_RE.match(stmt, i):
            tokens.append(_Token("word", match.group(0).lower(), depth))
            i = match.end()
            continue
        if match := _NUMBER_RE.match(stmt, i):
            tokens.append(_Token("number", match.group(0), depth))
            i = match.end()
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
        text = next((op for op in _OPERATORS if stmt.startswith(op, i)), ch)
        tokens.append(_Token("op", text, depth))
        if ch == "(":
            depth += 1
        i += len(text)
    return tokens


def _is_word(tok: _Token | None, *words: str) -> bool:
    return tok is not None and tok.kind == "word" and tok.text in words


def _is_op(tok: _Token | None, text: str) -> bool:
    return tok is not None and tok.kind == "op" and tok.text == text


def _split_at(tokens: list[_Token], text: str, depth: int) -> list[list[_Token]]:
    """Split on the keyword or operator ``text`` standing at the given depth."""
    parts: list[list[_Token]] = [[]]
    for tok in tokens:
        if tok.depth == depth and tok.kind in ("word", "op") and tok.text == text:
            parts.append([])
        else:
            parts[-1].append(tok)
    return parts


def _own_tokens(tokens: list[_Token], start: int) -> list[_Token]:
    """The statement that starts at ``start``: to the end of its parentheses
    (a data-modifying CTE) or of the text."""
    depth = tokens[start].depth
    end = start + 1
    while end < len(tokens) and tokens[end].depth >= depth:
        end += 1
    return tokens[start:end]


def _names_column(tokens: list[_Token], k: int) -> bool:
    tok = tokens[k]
    if tok.kind == "ident":
        return True
    if tok.kind != "word" or tok.text in _CONSTANT_WORDS:
        return False
    if k and _is_op(tokens[k - 1], "::"):
        return False  # cast target: '1'::int
    after = tokens[k + 1] if k + 1 < len(tokens) else None
    # function call or typed literal: now(), date '2026-01-01'
    return not (_is_op(after, "(") or (after is not None and after.kind == "string"))


def _matches_every_row(cond: list[_Token]) -> bool:
    """True when a WHERE condition does not narrow the statement to particular rows.

    A condition that names no column (``true``, ``1=1``, ``'a'='a'``) holds for
    every row or for none, and is counted as "every row". So are ``x = x`` and
    an OR with such a branch; an AND is unbounded only when each part is.
    Anything this cannot read as a constant is taken for a real condition.
    """
    while (
        len(cond) >= 2 and _is_op(cond[0], "(") and _is_op(cond[-1], ")")
        and all(tok.depth > cond[0].depth for tok in cond[1:-1])
    ):
        cond = cond[1:-1]
    if not cond:
        return True
    depth = min(tok.depth for tok in cond)
    for word, combine in (("or", any), ("and", all)):
        parts = _split_at(cond, word, depth)
        if len(parts) > 1:
            return combine(_matches_every_row(part) for part in parts)
    if _is_word(cond[0], "not"):
        return _matches_every_row(cond[1:])
    sides = _split_at(cond, "=", depth)
    if len(sides) == 2 and sides[0] and [t.text for t in sides[0]] == [t.text for t in sides[1]]:
        return True
    return not any(_names_column(cond, k) for k in range(len(cond)))


def _unbounded(tokens: list[_Token], start: int) -> str | None:
    """How the DELETE/UPDATE starting at ``start`` fails to pick its rows: ``no_where``,
    ``constant_where`` or None when it is narrowed by a real condition.

    Only a WHERE of the statement itself counts — not one inside a subquery.
    """
    depth = tokens[start].depth
    own = _own_tokens(tokens, start)
    where = next((k for k, tok in enumerate(own) if tok.depth == depth and _is_word(tok, "where")), None)
    if where is None:
        return "no_where"
    cond = own[where + 1:]
    stop = next((k for k, tok in enumerate(cond) if tok.depth == depth and _is_word(tok, "returning")), len(cond))
    return "constant_where" if _matches_every_row(cond[:stop]) else None


def _literal_body(tok: _Token) -> str:
    if tok.kind == "string":
        return tok.text[1:-1].replace("''", "'")
    tag = tok.text[: tok.text.index("$", 1) + 1]
    return tok.text[len(tag):].removesuffix(tag)


def _refusal(stmt: str) -> str | None:
    """Why the shared stand must not run this statement; None if it may."""
    tokens = _tokens(stmt)
    shown = re.sub(r"\s+", " ", _strip_leading_comments(stmt)).strip()
    shown = shown if len(shown) <= 120 else shown[:120] + "…"

    if tokens and _is_word(tokens[0], "do"):
        # An anonymous code block runs its body, so the same rules apply inside
        for tok in tokens[1:]:
            if tok.kind in ("string", "dollar"):
                for inner in split_sql_statements(_literal_body(tok)):
                    if reason := _refusal(inner):
                        return reason

    for i, tok in enumerate(tokens):
        if tok.kind != "word":
            continue
        if tok.text in _SCHEMA_CHANGES:
            effect, advice = _SCHEMA_CHANGES[tok.text]
            return f"{tok.text.upper()} отклонён: {effect}, а тестовый стенд общий. {advice} Оператор: {shown}"
        after = tokens[i + 1] if i + 1 < len(tokens) else None
        if tok.text == "delete" and _is_word(after, "from"):
            verb, effect = "DELETE", "удалит"
        elif tok.text == "update" and not _is_word(after, "set") and any(
            t.depth == tok.depth and _is_word(t, "set") for t in _own_tokens(tokens, i)
        ):
            # UPDATE <table> … SET; not FOR UPDATE, ON CONFLICT … DO UPDATE SET, ON UPDATE CASCADE
            verb, effect = "UPDATE", "изменит"
        else:
            continue
        problem = _unbounded(tokens, i)
        if problem == "no_where":
            refused = f"{verb} без WHERE отклонён: он {effect} все строки таблицы, а тестовый стенд общий."
        elif problem == "constant_where":
            refused = (
                f"{verb} отклонён: его WHERE не зависит от данных строки (true, 1=1 и подобные), "
                "то есть не выбирает свои записи, а тестовый стенд общий."
            )
        else:
            continue
        return f"{refused} Ограничьте оператор условием по идентификаторам своих записей. Оператор: {shown}"
    return None


def _first_refusal(statements: list[str]) -> tuple[int, str] | None:
    for idx, stmt in enumerate(statements):
        if reason := _refusal(stmt):
            return idx, reason
    return None


def destructive_statement(sql: str) -> tuple[int, str] | None:
    """Index and reason (Russian, for the tester) of the first statement of a
    script that the shared stand must not run; None when the script may run.

    Refused: DELETE and UPDATE without WHERE or with a WHERE that names no
    column, TRUNCATE, DROP, ALTER — as statements, inside data-modifying CTEs
    and inside DO blocks. Comments, string literals and quoted identifiers are
    never mistaken for code.
    """
    return _first_refusal(split_sql_statements(sql))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def fetch_table_columns(schema: str, tables: list[str]) -> dict[str, list[dict]]:
    """Live column info for the given tables from the test DB's information_schema.

    Returns {table_name: [{name, type, required}]}, where required means
    NOT NULL without a default — the columns every INSERT must fill. Tables
    missing on the stand are simply absent from the result.
    """
    if not is_configured() or not tables:
        return {}
    dsn = settings.test_db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(
        dsn, timeout=CONNECT_TIMEOUT, statement_cache_size=0, command_timeout=STATEMENT_TIMEOUT,
    )
    try:
        rows = await conn.fetch(
            "SELECT table_name, column_name, data_type, character_maximum_length, "
            "       is_nullable, column_default IS NOT NULL AS has_default "
            "FROM information_schema.columns "
            "WHERE table_schema = $1 AND table_name = ANY($2::text[]) "
            "ORDER BY table_name, ordinal_position",
            schema, tables,
        )
    finally:
        await conn.close()

    out: dict[str, list[dict]] = {}
    for r in rows:
        col_type = r["data_type"]
        if col_type == "character varying":
            col_type = "varchar"
        elif col_type == "character":
            col_type = "char"
        if r["character_maximum_length"]:
            col_type = f"{col_type}({r['character_maximum_length']})"
        out.setdefault(r["table_name"], []).append({
            "name": r["column_name"],
            "type": col_type,
            "required": r["is_nullable"] == "NO" and not r["has_default"],
        })
    return out


async def execute_sql(sql: str, *, readonly: bool = False) -> dict[str, Any]:
    """Run a SQL script on the test DB; one transaction, rollback on any error.

    Returns per-statement results: command status for DML, rows (capped at
    MAX_ROWS) for row-returning statements. Errors come back in the payload
    (not as exceptions) so the UI can show which statement failed.

    ``readonly`` opens a READ ONLY transaction: the database itself rejects
    any write, whatever the statements look like.

    A script with a statement the shared stand must not run (see
    ``destructive_statement``) is refused whole, before connecting; the refusal
    looks like an execution error of that statement.
    """
    statements = split_sql_statements(sql)
    if not statements:
        return {"results": [], "error": "Пустой SQL", "failed_statement": None, "duration_ms": 0}
    if refusal := _first_refusal(statements):
        failed_idx, reason = refusal
        logger.warning("test-db statement %d refused: %s", failed_idx, reason)
        return {"results": [], "error": reason, "failed_statement": failed_idx, "duration_ms": 0}

    dsn = settings.test_db_url.replace("postgresql+asyncpg://", "postgresql://")
    started = time.monotonic()
    results: list[dict[str, Any]] = []

    try:
        conn = await asyncpg.connect(
            dsn,
            timeout=CONNECT_TIMEOUT,
            statement_cache_size=0,
            command_timeout=STATEMENT_TIMEOUT,
        )
    except Exception as exc:
        reason = describe_db_connect_error(exc, CONNECT_TIMEOUT)
        logger.warning("test-db connect failed: %s", reason)
        return {
            "results": [],
            "error": f"Не удалось подключиться к тестовой БД: {reason}",
            "failed_statement": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "unreachable": True,
        }

    try:
        try:
            async with conn.transaction(readonly=readonly):
                for idx, stmt in enumerate(statements):
                    if _returns_rows(stmt):
                        rows = await conn.fetch(stmt)
                        results.append({
                            "statement": stmt,
                            "status": f"{len(rows)} строк",
                            "columns": list(rows[0].keys()) if rows else [],
                            "rows": [
                                [_json_value(v) for v in row.values()]
                                for row in rows[:MAX_ROWS]
                            ],
                            "truncated": len(rows) > MAX_ROWS,
                        })
                    else:
                        status = await conn.execute(stmt)
                        results.append({
                            "statement": stmt,
                            "status": status,
                            "columns": None,
                            "rows": None,
                            "truncated": False,
                        })
        except (asyncpg.PostgresError, asyncio.TimeoutError) as exc:
            failed_idx = len(results)
            logger.info("test-db statement %d failed: %s", failed_idx, exc)
            message = str(exc).strip() or f"Таймаут выполнения ({STATEMENT_TIMEOUT}с)"
            return {
                "results": results,
                "error": message,
                "failed_statement": failed_idx,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
    finally:
        await conn.close()

    return {
        "results": results,
        "error": None,
        "failed_statement": None,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


async def locate_tables(tables: list[str]) -> dict[str, list[str]]:
    """Schemas of the test DB that contain each of the given tables."""
    if not is_configured() or not tables:
        return {}
    dsn = settings.test_db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(
        dsn, timeout=CONNECT_TIMEOUT, statement_cache_size=0, command_timeout=STATEMENT_TIMEOUT,
    )
    try:
        rows = await conn.fetch(
            "SELECT table_name, table_schema FROM information_schema.tables "
            "WHERE table_name = ANY($1::text[]) AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY table_name, table_schema",
            tables,
        )
    finally:
        await conn.close()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["table_name"], []).append(r["table_schema"])
    return out


class _Rollback(Exception):
    """Leaves the dry-run transaction without committing."""


async def dry_run_scripts(scripts: list[str]) -> list[str | None]:
    """Execute each script on the test DB and roll it back; nothing is kept.

    Returns one entry per script: ``None`` if every statement ran, otherwise the
    database error. Raises ``ConnectionError`` when the test DB is unreachable,
    so the caller can tell "cannot check" from "the script is wrong".

    A script the shared stand must not run (see ``destructive_statement``) is
    never sent to the database, rollback or not: its entry is the refusal.
    """
    errors: list[str | None] = []
    for script in scripts:
        refusal = destructive_statement(script)
        if refusal:
            logger.warning("test-db dry-run refused: %s", refusal[1])
        errors.append(refusal[1] if refusal else None)
    if all(errors):
        return errors

    dsn = settings.test_db_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncpg.connect(
            dsn, timeout=CONNECT_TIMEOUT, statement_cache_size=0, command_timeout=STATEMENT_TIMEOUT,
        )
    except Exception as exc:
        reason = describe_db_connect_error(exc, CONNECT_TIMEOUT)
        raise ConnectionError(f"Не удалось подключиться к тестовой БД: {reason}") from exc

    try:
        for idx, script in enumerate(scripts):
            if errors[idx]:
                continue
            try:
                async with conn.transaction():
                    for stmt in split_sql_statements(script):
                        await conn.execute(stmt)
                    raise _Rollback
            except _Rollback:
                pass
            except (asyncpg.PostgresError, asyncio.TimeoutError) as exc:
                errors[idx] = str(exc).strip() or f"Таймаут выполнения ({STATEMENT_TIMEOUT}с)"
    finally:
        await conn.close()
    return errors
