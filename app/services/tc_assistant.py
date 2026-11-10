"""Test-case assistant: a tester's chat about the test cases of one feature.

A message is queued as a *turn*; one worker per feature answers turns in order
on the shared Codex queue. The agent runs read-only and without network, so a
turn is a short protocol driven from here:

1. the agent answers with stand actions (SQL, HTTP, WireMock) — the backend
   runs them within ``assistant_stand`` limits and feeds the results back;
2. the agent returns its final answer with case edits;
3. an edited ``sql_setup`` is executed on the stand before it is saved — a
   failing script goes back to the agent, and after three failed attempts the
   case is left untouched.

Everything done on the stand lands in the turn's journal as it happens, so the
tester sees it even if the turn later fails or is cancelled. Edits are applied
by stable case id under the feature lock and each one can be reverted.
"""

import asyncio
import copy
import json
import logging
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.prompts.tc_assistant import CONTINUE, INSTRUCTIONS, LAST_ROUND
from app.schemas.assistant import AssistantStep
from app.services import agent_runner, wiremock
from app.services.assistant_stand import Stand, normalize_sql, result_for_model
from app.services.rules import build_system_prompt
from app.services.task_manager import task_manager
from app.services.test_cases import _prepare_feature_context
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)

TASK_KIND = "tc_assistant"
MAX_ACTIONS_PER_STEP = 5
MAX_FIX_ATTEMPTS = 3
MAX_FOCUS_CASES = 12
HISTORY_TURNS = 12

EDIT_FIELDS = (
    "name", "preconditions", "steps", "expected_result", "priority",
    "curl_command", "kafka_message", "sql_setup", "mock_config",
)
# An empty string in these fields removes the artifact from the case
CLEARABLE_FIELDS = ("curl_command", "sql_setup", "mock_config")
_PROMPT_CASE_FIELDS = (
    "name", "category", "priority", "status", "covers", "preconditions", "steps", "expected_result",
    "curl_command", "kafka_message", "sql_setup", "mock_config", "analyst_text",
)
_STATUS_LABEL = {"pending": "не просмотрен", "approved": "принят", "edited": "с багом"}
_ARTIFACT_LABEL = (("curl_command", "curl"), ("kafka_message", "kafka"), ("sql_setup", "sql"), ("mock_config", "мок"))
_CASE_REF_RE = re.compile(r"#(\d{1,4})\b")


class AssistantConflict(ValueError):
    """The requested change no longer fits the current state (HTTP 409)."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def worker_key(project_slug: str, feature_name: str) -> str:
    return f"{TASK_KIND}:{project_slug}/{feature_name}"


async def feature_stand(store, project_slug: str, feature: dict) -> Stand:
    """Stand toolbox for the feature: its service and the schema it may write to
    (schema name == service name, dashes → underscores)."""
    service = None
    doc_slug = feature.get("source_document")
    if doc_slug:
        doc = await store.get_document(project_slug, doc_slug)
        service = (doc or {}).get("service_name")
    return Stand(service, service.replace("-", "_") if service else None)


# ----------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------


def _case_line(number: int, case: dict) -> str:
    artifacts = ", ".join(label for key, label in _ARTIFACT_LABEL if case.get(key)) or "нет"
    status = _STATUS_LABEL.get(case.get("status"), case.get("status") or "?")
    return (
        f"#{number} [{case.get('category', '?')}][{status}] {case.get('name', '')} "
        f"(покрывает: {case.get('covers') or '—'}; артефакты: {artifacts})"
    )


def _case_full(number: int, case: dict) -> str:
    data = {key: case.get(key) for key in _PROMPT_CASE_FIELDS}
    return f"### Кейс #{number}\n" + json.dumps(data, ensure_ascii=False, indent=2)


def _attachment_text(attachment: dict, number_of: dict[str, int]) -> str:
    number = number_of.get(attachment.get("case_id"))
    ref = f"кейс #{number}" if number else "кейс, которого уже нет в списке"
    kind = attachment["kind"]
    if kind == "sql_error":
        failed = attachment.get("failed_statement")
        where = f" в выражении {failed + 1}" if failed is not None else ""
        return f"- Ошибка выполнения SQL ({ref}){where}: {attachment.get('error')}"
    if kind == "http_result":
        if attachment.get("error"):
            return f"- Запрос ({ref}) не выполнился: {attachment['error']}"
        status = f"HTTP {attachment.get('status_code')} {attachment.get('reason') or ''}".strip()
        return f"- Ответ стенда на запрос ({ref}): {status}\n{attachment.get('body') or ''}".rstrip()
    if kind == "mock_error":
        return f"- Ошибка загрузки мока ({ref}): {attachment.get('error')}"
    return f"- Прикреплён {ref}"


def _history_text(turn: dict, number_of: dict[str, int]) -> str:
    lines = [f"Тестировщик: {turn.get('text', '')}"]
    lines += [_attachment_text(a, number_of) for a in turn.get("attachments") or []]
    for action in turn.get("actions") or []:
        lines.append(f"  · на стенде: {action['title']} → {action['summary']}")
    if turn["status"] != "done":
        lines.append(f"Ассистент не ответил: {turn.get('error') or turn['status']}")
        return "\n".join(lines)
    lines.append(f"Ассистент: {turn.get('reply', '')}")
    if turn.get("cause"):
        lines.append(f"Причина: {turn['cause']}")
    for change in turn.get("changes") or []:
        what = "добавлен кейс" if change["kind"] == "add" else "правка кейса"
        state = " — отменена тестировщиком" if change.get("state") == "reverted" else ""
        lines.append(f"  · {what} «{change['case_name']}»: {change.get('summary') or ''}{state}")
    for failure in turn.get("failures") or []:
        lines.append(f"  · правка кейса «{failure['case_name']}» не сохранена: {failure['error']}")
    return "\n".join(lines)


def _stand_text(caps: dict) -> str:
    lines = ["## Стенд"]
    if caps["sql"]:
        write = (
            f"Запись — только в схему {caps['write_schema']}." if caps["write_schema"]
            else "Запись запрещена: схема сервиса этой фичи неизвестна."
        )
        lines.append(f"- Тестовая БД {caps['database'] or ''}: чтение доступно. {write}")
    else:
        lines.append(
            "- Тестовая БД не подключена: действия sql недоступны, правки SQL сохраняются без проверки на стенде."
        )
    lines.append(
        f"- Сервис {caps['service'] or 'этой фичи'} на стенде: действия http доступны." if caps["http"]
        else "- Сервис на стенде не подключён: действия http недоступны."
    )
    lines.append(
        "- WireMock: загрузка моков и чтение журнала доступны." if caps["wiremock"]
        else "- WireMock не подключён: действия wiremock_* недоступны."
    )
    return "\n".join(lines)


def _focus_numbers(turn: dict, history: list[dict], cases: list[dict], number_of: dict[str, int]) -> list[int]:
    """Cases whose full data goes into the prompt: attached, mentioned as #N, or
    touched earlier in the session — most relevant first."""
    numbers: list[int] = []

    def add(number: int | None) -> None:
        if number and 1 <= number <= len(cases) and number not in numbers:
            numbers.append(number)

    for attachment in turn.get("attachments") or []:
        add(number_of.get(attachment.get("case_id")))
    for match in _CASE_REF_RE.finditer(turn.get("text") or ""):
        add(int(match.group(1)))
    for past in reversed(history):
        for attachment in past.get("attachments") or []:
            add(number_of.get(attachment.get("case_id")))
        for change in past.get("changes") or []:
            add(number_of.get(change.get("case_id")))
    return numbers[:MAX_FOCUS_CASES]


def build_prompt(shared_ctx: str, cases: list[dict], history: list[dict], turn: dict, caps: dict) -> str:
    number_of = {case["id"]: number for number, case in enumerate(cases, start=1)}
    parts = [shared_ctx, _stand_text(caps)]
    if cases:
        parts.append(
            "## Тест-кейсы фичи\n" + "\n".join(_case_line(n, c) for n, c in enumerate(cases, start=1))
        )
        focus = _focus_numbers(turn, history, cases, number_of)
        if focus:
            parts.append(
                "## Полные данные кейсов из обсуждения\n"
                + "\n\n".join(_case_full(n, cases[n - 1]) for n in focus)
                + "\n\nПолные данные остальных кейсов запроси действием read_cases."
            )
    else:
        parts.append("## Тест-кейсы фичи\nТест-кейсов пока нет.")
    if history:
        parts.append(
            "## История этой сессии\n"
            "Номера кейсов в старых ответах могли сдвинуться — сверяйся по названиям.\n\n"
            + "\n\n".join(_history_text(t, number_of) for t in history[-HISTORY_TURNS:])
        )
    message = "## Новое сообщение тестировщика\n" + turn.get("text", "")
    attachments = turn.get("attachments") or []
    if attachments:
        message += "\n\n### Вложения\n" + "\n".join(_attachment_text(a, number_of) for a in attachments)
    parts.append(message)
    return "\n\n".join(parts)


# ----------------------------------------------------------------------
# One turn
# ----------------------------------------------------------------------


class _TurnRun:
    """State of one turn: the stand journal, fix attempts and verified edits."""

    def __init__(self, store, project_slug: str, feature_name: str, turn: dict, stand: Stand, cases: list[dict]):
        self.store = store
        self.project_slug = project_slug
        self.feature_name = feature_name
        self.turn = turn
        self.stand = stand
        self.cases = cases
        self.numbering: dict[int, str] = {n: case["id"] for n, case in enumerate(cases, start=1)}
        self.prompt = ""
        self.journal: list[dict] = []
        self.attempts: dict[str, int] = {}
        self.failures: dict[str, dict] = {}
        # case id -> how its new sql_setup was checked on the stand
        self.checks: dict[str, dict] = {}

    async def progress(self, stage: str, current: str | None = None) -> None:
        await self.store.update_assistant_turn(
            self.project_slug, self.feature_name, self.turn["id"],
            patch={"stage": stage, "current": current, "actions": self.journal}, only_status="running",
        )

    async def execute(self, ask) -> dict:
        """The protocol with the agent; returns its final step."""
        prompt = self.prompt
        rounds = settings.assistant_max_rounds
        for round_no in range(rounds + 1):
            last = round_no == rounds
            await self.progress("thinking")
            step = await ask(prompt + (LAST_ROUND if last else ""), AssistantStep)
            if step["actions"] and not last:
                prompt = await self._do_actions(step["actions"]) + CONTINUE
                continue
            problems = await self._verify(step["edits"], final=last)
            if problems and not last:
                prompt = (
                    "## Правки не прошли проверку перед сохранением\n" + "\n".join(problems)
                    + "\n\nИсправь их и верни итог заново; при необходимости сначала запроси действия на стенде."
                )
                continue
            return step
        raise AssertionError("unreachable")

    def _read_cases(self, numbers: list[int]) -> str:
        found = [n for n in numbers if n in self.numbering][:MAX_FOCUS_CASES]
        if not found:
            return "### Полные данные кейсов\nКейсов с такими номерами нет."
        return "\n\n".join(_case_full(n, self.cases[n - 1]) for n in found)

    async def _do_actions(self, actions: list[dict]) -> str:
        results: list[str] = []
        for action in actions[:MAX_ACTIONS_PER_STEP]:
            if action["kind"] == "read_cases":
                results.append(self._read_cases(action.get("cases") or []))
                continue
            await self.progress("acting", action.get("title"))
            try:
                entry = await self.stand.run(action, self.numbering.get(action.get("case")))
            except Exception as exc:  # noqa: BLE001 — a stand failure is a result, not a crash
                logger.exception("tc_assistant: stand action failed")
                entry = Stand._fail(
                    Stand._entry(action["kind"], action.get("title") or "", None, write=False),
                    "error", f"Действие не выполнено: {exc}",
                )
            self.journal.append(entry)
            results.append(result_for_model(entry))
        if len(actions) > MAX_ACTIONS_PER_STEP:
            results.append(f"Остальные действия не выполнены: не больше {MAX_ACTIONS_PER_STEP} за один ответ.")
        await self.progress("thinking")
        return "## Результаты действий\n\n" + "\n\n".join(results)

    async def _check_sql(self, number: int, case_id: str, sql: str) -> str | None:
        """Run the edited sql_setup on the stand unless this exact script already
        ran in this turn. Returns the error, or None when the script works."""
        if not self.stand.capabilities()["sql"]:
            self.checks[case_id] = {"status": "skipped"}
            return None
        entry = self.stand.applied_sql.get(normalize_sql(sql))
        if entry is None:
            await self.progress("verifying", f"Выполняет обновлённый SQL кейса #{number}")
            try:
                entry = await self.stand.run_sql(sql, f"Выполнил обновлённый SQL кейса #{number}", case_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("tc_assistant: sql check failed")
                entry = Stand._fail(
                    Stand._entry("sql", f"Выполнил обновлённый SQL кейса #{number}", case_id, write=True),
                    "error", f"SQL не выполнен: {exc}",
                )
            self.journal.append(entry)
        if entry["status"] != "ok":
            return entry["summary"] or "SQL не выполнился"
        self.checks[case_id] = {
            "status": "ok", "summary": entry["summary"], "duration_ms": entry["duration_ms"], "action_id": entry["id"],
        }
        return None

    async def _verify(self, edits: list[dict], *, final: bool) -> list[str]:
        """Check edits before they are saved; returns what the agent must fix."""
        problems: list[str] = []
        for edit in edits:
            number = edit["case"]
            case_id = self.numbering.get(number)
            if case_id is None:
                problems.append(f"- Кейса #{number} нет в списке: исправь номер или убери правку.")
                continue
            if case_id in self.failures:
                continue
            field, error = None, None
            mock = edit.get("mock_config")
            if mock and mock.strip():
                try:
                    wiremock.prepare_mapping(mock)
                except wiremock.InvalidMappingError as exc:
                    field, error = "mock_config", str(exc)
            sql = edit.get("sql_setup")
            if error is None and sql and sql.strip():
                error = await self._check_sql(number, case_id, sql)
                field = "sql_setup" if error else None
            if error is None:
                continue
            self.checks.pop(case_id, None)
            count = self.attempts[case_id] = self.attempts.get(case_id, 0) + 1
            if count >= MAX_FIX_ATTEMPTS or final:
                self.failures[case_id] = {
                    "case_id": case_id, "case_name": self.cases[number - 1].get("name", ""),
                    "field": field, "attempts": count, "error": error,
                }
                problems.append(
                    f"- Кейс #{number}, {field}: {error}. Попытки исчерпаны ({count}) — правка этого кейса "
                    "не будет сохранена. Больше не присылай её; в reply скажи, что не получилось и почему."
                )
            else:
                problems.append(f"- Кейс #{number}, {field}: {error} (попытка {count} из {MAX_FIX_ATTEMPTS}).")
        await self.progress("thinking")
        return problems

    async def apply(self, step: dict) -> dict:
        """Save the final step: edits and new cases by stable id, under the feature lock."""
        changes: list[dict] = []

        def mutate(current: list[dict]) -> list[dict]:
            changes.clear()
            by_id = {case["id"]: case for case in current}
            for edit in step["edits"]:
                case_id = self.numbering.get(edit["case"])
                case = by_id.get(case_id) if case_id not in self.failures else None
                if case is None:
                    continue
                before, after = {}, {}
                for field in EDIT_FIELDS:
                    value = edit.get(field)
                    if value is None:
                        continue
                    if value == "":
                        if field not in CLEARABLE_FIELDS:
                            continue
                        value = None
                    if case.get(field) != value:
                        before[field], after[field] = case.get(field), value
                if not after:
                    continue
                case.update(after)
                change = {
                    "id": uuid.uuid4().hex[:8], "kind": "edit", "case_id": case_id,
                    "case_name": case.get("name", ""), "summary": edit.get("summary") or "",
                    "fields": list(after), "before": before, "after": after, "state": "applied",
                }
                if "sql_setup" in after and case_id in self.checks:
                    change["stand_check"] = self.checks[case_id]
                changes.append(change)
            identities = {(c.get("category"), (c.get("name") or "")[:80]) for c in current}
            for new in step["new_cases"]:
                identity = (new["category"], new["name"][:80])
                if identity in identities:
                    continue
                identities.add(identity)
                case = {
                    "id": uuid.uuid4().hex[:12],
                    "category": new["category"], "name": new["name"], "preconditions": new["preconditions"],
                    "steps": new["steps"], "expected_result": new["expected_result"], "priority": new["priority"],
                    "status": "pending", "analyst_text": None, "origin": "ask", "covers": new["covers"],
                    "curl_command": new["curl_command"], "kafka_message": new["kafka_message"],
                    "sql_setup": new["sql_setup"], "mock_config": new["mock_config"],
                }
                current.append(case)
                changes.append({
                    "id": uuid.uuid4().hex[:8], "kind": "add", "case_id": case["id"], "case_name": case["name"],
                    "summary": new["covers"], "case": copy.deepcopy(case), "state": "applied",
                })
            return current

        if step["edits"] or step["new_cases"]:
            await self.progress("saving")
            await self.store.mutate_test_cases(self.project_slug, self.feature_name, mutate)

        def named(number: int) -> dict | None:
            case_id = self.numbering.get(number)
            return {"case_id": case_id, "case_name": self.cases[number - 1].get("name", "")} if case_id else None

        suggestions = []
        for kind, items, text_key in (
            ("delete", step["delete_suggestions"], "reason"), ("bug", step["bug_suggestions"], "text"),
        ):
            for item in items:
                ref = named(item["case"])
                if ref:
                    suggestions.append({
                        "id": uuid.uuid4().hex[:8], "kind": kind, **ref, "text": item[text_key], "state": "open",
                    })
        refs: list[dict] = []
        for number in step["related_cases"]:
            ref = named(number)
            if ref and ref not in refs:
                refs.append(ref)
        return {
            "reply": (step["reply"] or "").strip() or "Не успел закончить за отведённое число шагов.",
            "cause": (step["cause"] or "").strip() or None,
            "actions": self.journal,
            "changes": changes,
            "failures": list(self.failures.values()),
            "suggestions": suggestions,
            "case_refs": refs,
            # #N in the reply refers to this snapshot; the UI links by stable id
            "numbering": {str(number): case_id for number, case_id in self.numbering.items()},
        }


async def run_turn(store, project_slug: str, feature_name: str, turn: dict) -> tuple[dict, str | None]:
    """Answer one turn. Returns (data to store on the turn, session title for a first turn)."""
    feature, _, shared_ctx = await _prepare_feature_context(
        project_slug, feature_name, store, enforce_gate=False,
    )
    stand = await feature_stand(store, project_slug, feature)
    cases = await store.get_test_cases(project_slug, feature_name)
    if any(not case.get("id") for case in cases):
        cases = await store.mutate_test_cases(project_slug, feature_name, lambda current: current)

    session = await store.get_assistant_session(project_slug, feature_name, turn["session_id"])
    history = []
    for past in (session or {}).get("turns", []):
        if past["id"] == turn["id"]:
            break
        if past["status"] in ("done", "error", "cancelled"):
            history.append(past)

    run = _TurnRun(store, project_slug, feature_name, turn, stand, cases)
    run.prompt = build_prompt(shared_ctx, cases, history, turn, stand.capabilities())

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    instructions = build_system_prompt(
        INSTRUCTIONS, global_rules.get("test_cases", ""), project_rules.get("test_cases", ""),
    )
    model = settings.test_cases_model
    log_path = Path(settings.assistant_log_dir).resolve() / f"{turn['id']}.jsonl"

    await run.progress("waiting")
    with tempfile.TemporaryDirectory(prefix="extract-assistant-") as directory:
        step = await agent_runner.analyze(
            Path(directory), log_path, run.execute, lambda: run.progress("thinking"),
            instructions=instructions, model="" if model.startswith("claude-") else model,
            timeout=settings.assistant_timeout_seconds, kind=TASK_KIND,
        )
    outcome = await run.apply(step)
    title = (step.get("session_title") or "").strip()[:80] or None
    return outcome, (title if not history else None)


# ----------------------------------------------------------------------
# Queue
# ----------------------------------------------------------------------


async def _open_task(store, project_slug: str, feature_name: str) -> str | None:
    """Task-log row for the turn. A leftover running row can only be stale here:
    the feature has one worker, and it is the caller."""
    for _ in range(2):
        try:
            task = await store.create_task(
                project_slug, kind=TASK_KIND, target_type="feature", target_id=feature_name,
            )
            return task["id"]
        except ActiveTaskExistsError:
            stale = await store.get_active_task(project_slug, kind=TASK_KIND, target_id=feature_name)
            if stale is not None:
                await store.finish_task(
                    project_slug, stale["id"], status="error",
                    error_message="Сервер перезапустился до завершения задачи",
                )
    return None


def _error_text(exc: Exception) -> str:
    if isinstance(exc, agent_runner.AgentError):
        if "таймаут" in str(exc).lower():
            minutes = max(1, settings.assistant_timeout_seconds // 60)
            return f"Ассистент не ответил за {minutes} мин. Сообщение сохранено — его можно отправить повторно."
        return str(exc)
    if isinstance(exc, ValueError):
        return str(exc)
    return "Не удалось получить ответ ассистента"


async def _process(store, project_slug: str, feature_name: str, turn: dict) -> None:
    task_id = await _open_task(store, project_slug, feature_name)

    async def close(status: str, patch: dict, *, error: str | None = None) -> None:
        await store.update_assistant_turn(
            project_slug, feature_name, turn["id"], status=status,
            patch={**patch, "stage": None, "current": None, "finished_at": _now()}, only_status="running",
        )
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error" if error else "done", error_message=error,
            )

    try:
        outcome, title = await run_turn(store, project_slug, feature_name, turn)
        await close("done", outcome)
        if title:
            await store.rename_assistant_session(project_slug, feature_name, turn["session_id"], title)
    except asyncio.CancelledError:
        await close("cancelled", {"error": "Остановлено"}, error="Остановлено пользователем")
        raise
    except Exception as exc:  # noqa: BLE001 — the turn carries the error to the tester
        logger.exception("tc_assistant: turn %s failed", turn["id"])
        message = _error_text(exc)
        await close("error", {"error": message}, error=message)


async def _worker(store, project_slug: str, feature_name: str) -> None:
    while True:
        turn = await store.claim_assistant_turn(project_slug, feature_name)
        if turn is None:
            return
        await _process(store, project_slug, feature_name, turn)


async def ensure_worker(store, project_slug: str, feature_name: str) -> None:
    """Start the feature's worker if messages are waiting. Turns left running by
    a previous process are closed as errors first (their journal stays)."""
    key = worker_key(project_slug, feature_name)
    if task_manager.is_running(key):
        return
    activity = await store.assistant_activity(project_slug, feature_name)
    for turn_id in activity["running"]:
        await store.update_assistant_turn(
            project_slug, feature_name, turn_id, status="error", only_status="running",
            patch={
                "error": "Сервер перезапустился, пока ассистент работал. Действия из журнала уже выполнены на стенде.",
                "stage": None, "current": None, "finished_at": _now(),
            },
        )
    if activity["queued"]:
        task_manager.launch(key, _worker(store, project_slug, feature_name))


def _draft_title(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Новая сессия"
    return line if len(line) <= 60 else line[:57].rstrip() + "…"


async def send_message(
    store, project_slug: str, feature_name: str, *,
    text: str, attachments: list[dict], session_id: str | None, author: str | None,
) -> dict:
    """Queue a message (opening a new session when ``session_id`` is None)."""
    if session_id is None:
        session = await store.create_assistant_session(
            project_slug, feature_name, title=_draft_title(text), author=author,
        )
        if session is None:
            raise LookupError("Фича не найдена")
        session_id = session["id"]
    turn = await store.add_assistant_turn(project_slug, feature_name, session_id, {
        "text": text, "attachments": attachments, "author": author,
        "stage": None, "current": None, "actions": [],
    })
    if turn is None:
        raise LookupError("Сессия не найдена")
    await ensure_worker(store, project_slug, feature_name)
    return turn


async def cancel_turn(store, project_slug: str, feature_name: str, turn_id: str) -> bool:
    """Stop the turn if it is the one being answered; the queue then continues."""
    turn = await store.get_assistant_turn(project_slug, feature_name, turn_id)
    if turn is None or turn["status"] != "running":
        return False
    await task_manager.cancel(worker_key(project_slug, feature_name))
    # No live worker (e.g. after a restart) — close the turn directly
    await store.update_assistant_turn(
        project_slug, feature_name, turn_id, status="cancelled", only_status="running",
        patch={"error": "Остановлено", "stage": None, "current": None, "finished_at": _now()},
    )
    await ensure_worker(store, project_slug, feature_name)
    return True


# ----------------------------------------------------------------------
# Tester's decisions on a finished turn
# ----------------------------------------------------------------------


async def _finished_turn(store, project_slug: str, feature_name: str, turn_id: str) -> dict:
    turn = await store.get_assistant_turn(project_slug, feature_name, turn_id)
    if turn is None or turn["status"] != "done":
        raise LookupError("Ответ ассистента не найден")
    return turn


async def set_change_state(
    store, project_slug: str, feature_name: str, turn_id: str, change_id: str, *, revert: bool,
) -> dict:
    """Undo an applied change, or bring a reverted one back."""
    turn = await _finished_turn(store, project_slug, feature_name, turn_id)
    change = next((c for c in turn.get("changes") or [] if c["id"] == change_id), None)
    if change is None:
        raise LookupError("Правка не найдена")
    state = "reverted" if revert else "applied"
    if change["state"] == state:
        return turn

    def mutate(cases: list[dict]) -> list[dict]:
        index = next((i for i, case in enumerate(cases) if case["id"] == change["case_id"]), None)
        if change["kind"] == "add":
            if revert and index is not None:
                cases.pop(index)
            elif not revert and index is None:
                cases.append(copy.deepcopy(change["case"]))
            return cases
        if index is None:
            raise AssistantConflict("Кейс удалён — эту правку уже нельзя " + ("отменить" if revert else "вернуть"))
        source, target = (change["after"], change["before"]) if revert else (change["before"], change["after"])
        if any(cases[index].get(field) != source.get(field) for field in change["fields"]):
            raise AssistantConflict(
                "Кейс изменился после этой правки. Сначала отмените более поздние правки этого кейса."
            )
        cases[index].update({field: target.get(field) for field in change["fields"]})
        return cases

    await store.mutate_test_cases(project_slug, feature_name, mutate)

    def mark(data: dict) -> dict:
        for item in data.get("changes") or []:
            if item["id"] == change_id:
                item["state"] = state
        return data

    return await store.update_assistant_turn(project_slug, feature_name, turn_id, mutate=mark)


async def resolve_suggestion(
    store, project_slug: str, feature_name: str, turn_id: str, suggestion_id: str, *, accept: bool,
) -> dict:
    """Accept or dismiss a suggestion. Accepting a deletion removes the case;
    a bug suggestion is filed by the UI through the regular bug-report flow."""
    turn = await _finished_turn(store, project_slug, feature_name, turn_id)
    suggestion = next((s for s in turn.get("suggestions") or [] if s["id"] == suggestion_id), None)
    if suggestion is None:
        raise LookupError("Предложение не найдено")
    if suggestion["state"] != "open":
        return turn
    if accept and suggestion["kind"] == "delete":
        await store.mutate_test_cases(
            project_slug, feature_name,
            lambda cases: [case for case in cases if case["id"] != suggestion["case_id"]],
        )

    def mark(data: dict) -> dict:
        for item in data.get("suggestions") or []:
            if item["id"] == suggestion_id:
                item["state"] = "accepted" if accept else "dismissed"
        return data

    return await store.update_assistant_turn(project_slug, feature_name, turn_id, mutate=mark)
