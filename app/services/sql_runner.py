"""Execute SQL artifacts against the test stand database.

The test DB endpoint is behind pgbouncer, so connections are opened with
statement_cache_size=0 (named prepared statements don't survive transaction
pooling). Scripts run inside one transaction: either every statement applies
or none do.
"""

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import asyncpg

from app.config import settings

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
        ch = sql[i]
        two = sql[i : i + 2]
        if two == "--":
            end = sql.find("\n", i)
            end = n if end == -1 else end
            current.append(sql[i:end])
            i = end
            continue
        if two == "/*":
            end = sql.find("*/", i + 2)
            end = n if end == -1 else end + 2
            current.append(sql[i:end])
            i = end
            continue
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
            end = min(end + 1, n)
            current.append(sql[i:end])
            i = end
            continue
        if ch == "$":
            tag_match = re.match(r"\$[A-Za-z_]*\$", sql[i:])
            if tag_match:
                tag = tag_match.group(0)
                end = sql.find(tag, i + len(tag))
                end = n if end == -1 else end + len(tag)
                current.append(sql[i:end])
                i = end
                continue
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


async def execute_sql(sql: str) -> dict[str, Any]:
    """Run a SQL script on the test DB; one transaction, rollback on any error.

    Returns per-statement results: command status for DML, rows (capped at
    MAX_ROWS) for row-returning statements. Errors come back in the payload
    (not as exceptions) so the UI can show which statement failed.
    """
    statements = split_sql_statements(sql)
    if not statements:
        return {"results": [], "error": "Пустой SQL", "failed_statement": None, "duration_ms": 0}

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
        logger.warning("test-db connect failed: %s", exc)
        return {
            "results": [],
            "error": f"Не удалось подключиться к тестовой БД: {exc}",
            "failed_statement": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    try:
        try:
            async with conn.transaction():
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
