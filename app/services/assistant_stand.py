"""Stand actions the test-case assistant may ask for, and their limits.

The agent itself runs in a read-only sandbox without network access: it only
*asks* for an action, and this module executes it against the configured test
DB, test stand and WireMock. Every action becomes a journal entry the tester
sees. Limits enforced here, not in the prompt:

- reads run in a READ ONLY transaction;
- writes are INSERT/UPDATE/DELETE into the feature's own schemas only: the
  service schema plus the schemas its test cases already write to (an adapter
  may keep its tables in another service's schema);
- no DDL or other statements;
- HTTP goes only to the feature's service on the stand (relative paths).
"""

import json
import re
import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from app.services import http_runner, sql_runner, wiremock

RESULT_CHARS = 6000  # what the model and the journal keep of one action's output
RESULT_ROWS = 30

_READ_KEYWORDS = {"select", "with", "show", "values", "table", "explain"}
_WRITE_KEYWORDS = {"insert", "update", "delete"}
_MODIFYING_RE = re.compile(r"\b(insert|update|delete|merge|truncate)\b", re.IGNORECASE)
_SELECT_INTO_RE = re.compile(r"\bselect\b[^;]*?\binto\b", re.IGNORECASE | re.DOTALL)
_TARGET_RES = (
    re.compile(r"\binsert\s+into\s+([A-Za-z_\"][\w\".]*)", re.IGNORECASE),
    re.compile(r"\bupdate\s+(?:only\s+)?([A-Za-z_\"][\w\".]*)", re.IGNORECASE),
    re.compile(r"\bdelete\s+from\s+(?:only\s+)?([A-Za-z_\"][\w\".]*)", re.IGNORECASE),
)


class SqlNotAllowed(ValueError):
    """The script is outside what the assistant may run on the stand."""


def _strip_literals(stmt: str) -> str:
    """Drop comments, string literals and dollar-quoted bodies so keyword checks
    see only the statement's own structure."""
    out: list[str] = []
    i, n = 0, len(stmt)
    while i < n:
        two = stmt[i:i + 2]
        if two == "--":
            end = stmt.find("\n", i)
            i = n if end == -1 else end
            continue
        if two == "/*":
            end = stmt.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if stmt[i] == "'":
            end = i + 1
            while end < n:
                if stmt[end] == "'":
                    if end + 1 < n and stmt[end + 1] == "'":
                        end += 2
                        continue
                    break
                end += 1
            out.append("''")
            i = min(end + 1, n)
            continue
        if stmt[i] == "$":
            tag = re.match(r"\$[A-Za-z_]*\$", stmt[i:])
            if tag:
                end = stmt.find(tag.group(0), i + len(tag.group(0)))
                out.append("''")
                i = n if end == -1 else end + len(tag.group(0))
                continue
        out.append(stmt[i])
        i += 1
    return "".join(out)


def _statement_bodies(sql: str) -> list[str]:
    """Statements reduced to their own structure: no comments, literals, or the
    UPDATE keywords that do not name a write target."""
    bodies = []
    for stmt in sql_runner.split_sql_statements(sql):
        body = _strip_literals(stmt).strip()
        # A trailing comment after the last ";" splits off as a statement of its own
        if not body:
            continue
        # FOR UPDATE and ON CONFLICT ... DO UPDATE are not separate write targets
        body = re.sub(r"\bfor\s+(?:no\s+key\s+)?update\b", " ", body, flags=re.IGNORECASE)
        bodies.append(re.sub(r"\bdo\s+update\b", " do_upsert ", body, flags=re.IGNORECASE))
    return bodies


def _targets(body: str) -> list[list[str]]:
    """Tables a statement writes to, as lower-cased name parts ([schema, table])."""
    names = [m.group(1) for pattern in _TARGET_RES for m in pattern.finditer(body)]
    return [[part.strip('"').lower() for part in name.split(".")] for name in names]


def written_schemas(sql: str | None) -> set[str]:
    """Schemas a script writes to (schema-qualified targets only)."""
    if not sql:
        return set()
    return {parts[0] for body in _statement_bodies(sql) for parts in _targets(body) if len(parts) == 2}


def classify_sql(sql: str, write_schemas: Collection[str]) -> bool:
    """True if the script writes, False if it only reads.

    Raises SqlNotAllowed for anything but SELECT-like reads and
    INSERT/UPDATE/DELETE into one of ``write_schemas``.
    """
    allowed = {schema.lower() for schema in write_schemas}
    statements = _statement_bodies(sql)
    if not statements:
        raise SqlNotAllowed("Пустой SQL")
    writes = False
    for body in statements:
        first = re.match(r"[A-Za-z]+", body)
        keyword = first.group(0).lower() if first else ""
        modifies = bool(_MODIFYING_RE.search(body))
        if keyword in _READ_KEYWORDS and not modifies:
            if _SELECT_INTO_RE.search(body):
                raise SqlNotAllowed("SELECT ... INTO создаёт таблицу — такие запросы ассистент не выполняет")
            continue
        if keyword in _READ_KEYWORDS and keyword != "with":
            raise SqlNotAllowed("Запрос на чтение содержит изменяющую операцию — разделите чтение и запись")
        if keyword not in _WRITE_KEYWORDS and keyword != "with":
            raise SqlNotAllowed(
                f"Ассистент выполняет только SELECT и INSERT/UPDATE/DELETE, а не «{keyword.upper() or body[:20]}»"
            )
        if re.search(r"\b(merge|truncate)\b", body, re.IGNORECASE):
            raise SqlNotAllowed("MERGE и TRUNCATE ассистент не выполняет")
        if not allowed:
            raise SqlNotAllowed(
                "Неизвестно, в какие схемы пишет эта фича, поэтому запись в тестовую БД ассистенту запрещена"
            )
        targets = _targets(body)
        if not targets:
            raise SqlNotAllowed("Не удалось определить таблицу, в которую пишет запрос")
        for parts in targets:
            if len(parts) != 2 or parts[0] not in allowed:
                raise SqlNotAllowed(
                    f"Запись разрешена только в {_schemas_text(allowed)}, а запрос пишет в «{'.'.join(parts)}»"
                )
        writes = True
    return writes


def _schemas_text(schemas: Collection[str]) -> str:
    names = sorted(schemas)
    return ("схему " if len(names) == 1 else "схемы ") + ", ".join(names)


def normalize_sql(sql: str) -> str:
    """Whitespace-insensitive form used to tell that a script already ran."""
    return re.sub(r"\s+", " ", sql).strip().rstrip(";").strip()


def _clip(text: str, limit: int = RESULT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… обрезано, всего {len(text)} символов"


def _format_sql_result(result: dict[str, Any]) -> str:
    lines: list[str] = []
    for no, res in enumerate(result["results"], start=1):
        head = re.sub(r"\s+", " ", res["statement"])[:160]
        lines.append(f"[{no}] {head}\n    → {res['status']}")
        if res.get("columns"):
            lines.append("    " + " | ".join(res["columns"]))
            for row in (res.get("rows") or [])[:RESULT_ROWS]:
                lines.append("    " + " | ".join("null" if v is None else str(v) for v in row))
            if len(res.get("rows") or []) > RESULT_ROWS or res.get("truncated"):
                lines.append("    … показаны первые строки")
    if result["error"]:
        failed = result["failed_statement"]
        where = f" в выражении {failed + 1}" if failed is not None else ""
        lines.append(f"ОШИБКА{where}: {result['error']}\nИзменения отменены (транзакция откатилась).")
    return "\n".join(lines)


def _first_line(text: str, limit: int = 220) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[:limit] + "…"


class Stand:
    """Executes the assistant's actions for one feature and records the journal."""

    def __init__(self, service: str | None, write_schemas: Collection[str]) -> None:
        self.service = service
        self.write_schemas = sorted({schema.lower() for schema in write_schemas})
        # Normalized scripts that were written to the stand successfully in this run
        self.applied_sql: dict[str, dict] = {}

    def capabilities(self) -> dict[str, Any]:
        db = sql_runner.test_db_info()
        return {
            "sql": db["configured"],
            "database": db["database"],
            "write_schemas": self.write_schemas if db["configured"] else [],
            "http": http_runner.is_configured(),
            "service": self.service,
            "wiremock": wiremock.mappings_url() is not None,
        }

    @staticmethod
    def _entry(kind: str, title: str, case_id: str | None, *, write: bool) -> dict[str, Any]:
        return {
            "id": uuid.uuid4().hex[:8],
            "kind": kind,
            "title": title.strip()[:300] or "Действие на стенде",
            "case_id": case_id,
            "write": write,
            "status": "ok",
            "summary": "",
            "detail": "",
            "duration_ms": None,
            "at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _fail(entry: dict, status: str, message: str, detail: str = "") -> dict:
        entry.update(status=status, summary=_first_line(message), detail=_clip((detail + "\n" + message).strip()))
        return entry

    async def run_sql(self, sql: str, title: str, case_id: str | None) -> dict[str, Any]:
        """Run a script within the assistant's limits; returns the journal entry."""
        entry = self._entry("sql", title, case_id, write=False)
        if not sql_runner.is_configured():
            return self._fail(entry, "error", "Тестовая БД не настроена (TEST_DB_URL)", sql)
        try:
            writes = classify_sql(sql, self.write_schemas)
        except SqlNotAllowed as exc:
            return self._fail(entry, "blocked", str(exc), sql)
        entry["write"] = writes
        result = await sql_runner.execute_sql(sql, readonly=not writes)
        entry["duration_ms"] = result["duration_ms"]
        entry["detail"] = _clip(sql.strip() + "\n\n" + _format_sql_result(result))
        if result["error"]:
            failed = result["failed_statement"]
            where = f"Ошибка в выражении {failed + 1}: " if failed is not None else "Ошибка: "
            entry.update(status="error", summary=_first_line(where + result["error"]))
            return entry
        if writes:
            count = len(result["results"])
            entry["summary"] = f"{count} {_plural(count, 'запрос', 'запроса', 'запросов')} · {result['duration_ms']} мс"
            self.applied_sql[normalize_sql(sql)] = entry
        else:
            # One status per statement: the last one alone hides what earlier reads found
            entry["summary"] = _first_line("; ".join(str(res["status"]) for res in result["results"]))
        return entry

    async def run_http(
        self, method: str, path: str, headers: dict[str, str], body: str | None, title: str, case_id: str | None,
    ) -> dict[str, Any]:
        method = method.strip().upper()
        entry = self._entry("http", title, case_id, write=method not in ("GET", "HEAD", "OPTIONS"))
        request_text = f"{method} {path}" + (f"\n{body}" if body else "")
        if not http_runner.is_configured():
            return self._fail(entry, "error", "Тестовый стенд не настроен (TEST_STAND_URL)", request_text)
        if method not in http_runner.ALLOWED_METHODS:
            return self._fail(entry, "blocked", f"Метод {method} не поддерживается", request_text)
        if "://" in path.split("?", 1)[0] or path.startswith("//"):
            return self._fail(
                entry, "blocked", "Ассистент вызывает только сервис этой фичи на стенде: нужен путь без хоста",
                request_text,
            )
        prefix = await http_runner.resolve_route_prefix(self.service)
        url = http_runner.build_target_url(prefix, path)
        result = await http_runner.execute_request(method, url, headers, body)
        entry["duration_ms"] = result["duration_ms"]
        request_text = f"{method} {url}" + (f"\n{body}" if body else "")
        if result["error"]:
            return self._fail(entry, "error", result["error"], request_text)
        entry["summary"] = f"HTTP {result['status_code']} {result['reason'] or ''}".strip()
        entry["http_status"] = result["status_code"]
        entry["detail"] = _clip(
            request_text + f"\n\nHTTP {result['status_code']} {result['reason'] or ''} · {result['duration_ms']} мс\n"
            + (result["body"] or "")
        )
        return entry

    async def upload_mock(self, mock_config: str, title: str, case_id: str | None) -> dict[str, Any]:
        entry = self._entry("wiremock_upload", title, case_id, write=True)
        if wiremock.mappings_url() is None:
            return self._fail(entry, "error", "WireMock не настроен (TEST_WIREMOCK_URL)", mock_config)
        try:
            mapping = wiremock.prepare_mapping(mock_config)
            result = await wiremock.upload_mapping(mapping)
        except (wiremock.InvalidMappingError, wiremock.WireMockError) as exc:
            return self._fail(entry, "error", str(exc), mock_config)
        entry.update(
            summary=f"Мок загружен · HTTP {result['status_code']}",
            duration_ms=result["duration_ms"],
            detail=_clip(json.dumps(mapping, ensure_ascii=False, indent=2) + f"\n\nid: {result['mapping_id']}"),
        )
        return entry

    async def read_wiremock(self, kind: str, url_contains: str | None, title: str, case_id: str | None) -> dict:
        entry = self._entry(kind, title, case_id, write=False)
        query = f"Поиск: {url_contains or 'все'}"
        if wiremock.mappings_url() is None:
            return self._fail(entry, "error", "WireMock не настроен (TEST_WIREMOCK_URL)", query)
        try:
            if kind == "wiremock_mappings":
                result = await wiremock.find_mappings(url_contains)
                count = result["matched_count"]
                entry["summary"] = (
                    f"Найдено моков: {count} из {result['total']}" if count else "Подходящих моков нет"
                )
            else:
                result = await wiremock.recent_requests(url_contains)
                count = result["matched_count"]
                entry["summary"] = f"Запросов в журнале: {count}" if count else "Запросов в журнале нет"
        except wiremock.WireMockError as exc:
            return self._fail(entry, "error", str(exc), query)
        entry["detail"] = _clip(query + "\n\n" + json.dumps(result, ensure_ascii=False, indent=2))
        return entry

    async def run(self, action: dict[str, Any], case_id: str | None) -> dict[str, Any]:
        """Execute one requested action; never raises for stand-side failures."""
        kind = action["kind"]
        title = action.get("title") or ""
        if kind == "sql":
            if not (action.get("sql") or "").strip():
                return self._fail(self._entry(kind, title, case_id, write=False), "blocked", "Не передан SQL")
            return await self.run_sql(action["sql"], title, case_id)
        if kind == "http":
            if not action.get("method") or not action.get("path"):
                return self._fail(self._entry(kind, title, case_id, write=False), "blocked", "Не переданы метод и путь")
            headers = {h["name"]: h["value"] for h in action.get("headers") or []}
            return await self.run_http(action["method"], action["path"], headers, action.get("body"), title, case_id)
        if kind == "wiremock_upload":
            if not (action.get("mock_config") or "").strip():
                return self._fail(self._entry(kind, title, case_id, write=True), "blocked", "Не передан mapping")
            return await self.upload_mock(action["mock_config"], title, case_id)
        return await self.read_wiremock(kind, action.get("url_contains"), title, case_id)


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def result_for_model(entry: dict[str, Any]) -> str:
    """How one executed action is reported back to the agent."""
    status = {"ok": "выполнено", "error": "ошибка", "blocked": "отклонено правилами стенда"}[entry["status"]]
    return f"### {entry['title']}\nСтатус: {status}. {entry['summary']}\n{entry['detail']}"
