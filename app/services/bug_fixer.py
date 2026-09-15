"""Bug fixer: hands an exported Jira bug to a headless Claude Code run in the service repo.

The spawned `claude -p` process runs inside the service repository, so it picks up
the user's global ~/.claude/CLAUDE.md and follows the standard MTSPAY bug flow on
its own (Jira issue, Confluence spec, red regression test → green fix, MR via push
options, Jira status transitions). The prompt therefore only points the agent at
the Jira issue, passes the platform's repro context, and fixes the output contract.

Queueing: one running fix per service repo (a `bug_fix` task with target_id =
service name); other exported bugs of the same service wait as fix_status="queued"
and are picked up by the same task loop.
"""

import asyncio
import json
import logging
import os
import re
import socket
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services.task_manager import task_manager
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)


class BugFixerError(Exception):
    """User-facing bug fixer error (config, repo not found, tunnel down)."""


def is_configured() -> bool:
    return bool(settings.claude_code_oauth_token)


def resolve_repo(service_name: str | None) -> Path | None:
    """Directory of the service's git repo, searched across the configured roots."""
    if not service_name:
        return None
    for root in settings.repos_dirs.split(":"):
        candidate = Path(root).expanduser() / service_name
        if (candidate / ".git").exists():
            return candidate
    return None


def _tunnel_up() -> bool:
    host_port = settings.claude_proxy.rsplit("//", 1)[-1]
    host, _, port = host_port.partition(":")
    try:
        with socket.create_connection((host, int(port or 80)), timeout=2):
            return True
    except OSError:
        return False


async def ensure_tunnel() -> None:
    """Bring up the SSH tunnel to the Claude proxy if it is not already listening."""
    if _tunnel_up():
        return
    logger.info("[bug_fixer] Starting SSH tunnel to %s", settings.claude_proxy_ssh_host)
    proc = await asyncio.create_subprocess_exec(
        "ssh", "-fN", settings.claude_proxy_ssh_host,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if not _tunnel_up():
        detail = (stderr or b"").decode(errors="replace").strip()[:200]
        raise BugFixerError(f"SSH-туннель к claude-proxy не поднялся: {detail or 'порт не слушает'}")


def build_prompt(bug: dict, feature: dict, spec_url: str | None) -> str:
    """Task prompt for the headless run; the process' global CLAUDE.md carries the flow."""
    parts: list[str] = [
        f"Возьми в работу баг {bug['jira_key']} ({bug.get('jira_url', '')}).",
        "",
        "Это баг, заведённый тестировщиком через платформу Extract Agent; описание тикета "
        "совпадает с контекстом ниже. Работай строго по стандартному флоу для задач типа "
        "«баг» из глобального CLAUDE.md: свежий develop, ветка по тикету, ТЗ из Confluence, "
        "проверка что фактическое поведение действительно нарушает ТЗ, регрессионный тест "
        "(сначала убедиться, что он красный), фикс до зелёного, MR через push options, "
        "перевод статусов Jira.",
        "",
        "## Контекст от платформы",
        f"Фича: {feature.get('name', '')} ({feature.get('method') or ''} {feature.get('endpoint') or ''})".rstrip(" ()"),
        f"Суть: {bug.get('title', '')}",
        f"Ожидаемый результат: {bug.get('expected_result', '')}",
        f"Фактический результат: {bug.get('actual_result', '')}",
    ]
    if spec_url:
        parts.append(f"ТЗ (Confluence): {spec_url}")
    if bug.get("analyst_text"):
        parts.append(f"Наблюдение тестировщика: {bug['analyst_text']}")

    steps = bug.get("steps") or []
    if steps:
        parts += ["", "Шаги воспроизведения:"]
        for i, step in enumerate(steps, 1):
            parts.append(f"{i}. {step.get('action', '')} → {step.get('result', '')}")
            for key in ("curl_command", "sql_query", "kafka_message"):
                if step.get(key):
                    parts.append(f"   {step[key]}")

    parts += [
        "",
        "## Ограничения",
        "- Если подтвердить нарушение ТЗ не удалось, ТЗ не нашлось, фикс требует человеческого "
        "решения или что-то блокирует работу — остановись, ничего не пушь и верни failed с причиной.",
        "- Незакоммиченные чужие изменения в репозитории — тоже причина остановиться.",
        "- Ты работаешь в headless-сессии: НЕ запускай ничего в фоне (сборку, тесты — только "
        "синхронно, дожидаясь завершения). Заверши весь флоу — коммит, MR, статусы Jira — "
        "в рамках этой сессии, не откладывая «на потом».",
        "",
        "## Формат ответа",
        "В самом конце твоего ответа выведи ровно один JSON-объект, после него — никакого текста:",
        '{"status": "fix_proposed" | "failed", "branch": "...", "mr_url": "...", '
        '"summary": "1-2 предложения что сделано", "reason": "причина, если failed"}',
    ]
    return "\n".join(parts)


def extract_result_json(text: str, statuses: tuple[str, ...] = ("fix_proposed", "failed")) -> dict | None:
    """Pull the trailing {"status": ...} object out of the agent's final message."""
    matches = re.findall(r"\{[^{}]*\"status\"[^{}]*\}", text, re.DOTALL)
    for raw in reversed(matches):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("status") in statuses:
            return data
    return None


async def _update_bug(store, project_slug: str, feature_name: str, bug_index: int, **fields) -> dict | None:
    bugs = await store.get_bugs(project_slug, feature_name)
    if bug_index >= len(bugs):
        return None
    bugs[bug_index].update(fields)
    await store.save_bugs(project_slug, feature_name, bugs)
    return bugs[bug_index]


async def _service_of_feature(store, project_slug: str, feature: dict) -> tuple[str | None, str | None]:
    """(service_name, spec_url) from the feature's source document."""
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return None, None
    doc = await store.get_document(project_slug, doc_slug) or {}
    return doc.get("service_name"), doc.get("confluence_url")


async def request_fix(store, project_slug: str, feature_name: str, bug_index: int) -> dict:
    """Queue one exported bug for fixing and start the service's queue if idle.

    Returns the updated bug dict. Raises BugFixerError when the fix cannot even
    be queued (not configured, no Jira key, repo not found).
    """
    if not is_configured():
        raise BugFixerError("Bug fixer не настроен: задайте CLAUDE_CODE_OAUTH_TOKEN в .env")

    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise BugFixerError(f"Фича '{feature_name}' не найдена")
    bugs = await store.get_bugs(project_slug, feature_name)
    if bug_index < 0 or bug_index >= len(bugs):
        raise BugFixerError(f"Баг с индексом {bug_index} не найден")
    bug = bugs[bug_index]

    if not bug.get("jira_key"):
        raise BugFixerError("Сначала создайте задачу в Jira — агент работает по Jira-тикету")
    if bug.get("fix_status") in ("queued", "running"):
        raise BugFixerError(f"Фикс уже {bug['fix_status']}")

    service, _ = await _service_of_feature(store, project_slug, feature)
    repo = resolve_repo(service)
    if repo is None:
        raise BugFixerError(
            f"Репозиторий сервиса не найден (service={service or 'неизвестен'}, roots={settings.repos_dirs})"
        )

    bug = await _update_bug(
        store, project_slug, feature_name, bug_index,
        fix_status="queued", fix_service=service, fix_error=None,
        fix_requested_at=datetime.now(UTC).isoformat(),
    )
    await _maybe_start(store, project_slug, service)
    return bug


async def _find_queued(store, project_slug: str, service: str) -> tuple[str, int, dict, dict] | None:
    """Oldest queued bug of this service: (feature_name, bug_index, bug, feature)."""
    best = None
    for feature in await store.list_features(project_slug):
        f_service, _ = await _service_of_feature(store, project_slug, feature)
        if f_service != service:
            continue
        for idx, bug in enumerate(await store.get_bugs(project_slug, feature["name"])):
            if bug.get("fix_status") != "queued":
                continue
            key = bug.get("fix_requested_at") or ""
            if best is None or key < best[0]:
                best = (key, feature["name"], idx, bug, feature)
    if best is None:
        return None
    return best[1], best[2], best[3], best[4]


async def _maybe_start(store, project_slug: str, service: str) -> None:
    """Start the queue-processing task for this service repo unless one is running."""
    task_key = f"bug_fix:{project_slug}/{service}"
    active = await store.get_active_task(project_slug, kind="bug_fix", target_id=service)
    if active is not None:
        if task_manager.is_running(task_key):
            return
        logger.warning("[bug_fixer] Stuck task %s for %s/%s, recovering", active["id"], project_slug, service)
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )
    try:
        task = await store.create_task(
            project_slug, kind="bug_fix", target_type="service", target_id=service,
        )
    except ActiveTaskExistsError:
        return
    task_manager.launch(task_key, _run_queue(store, project_slug, service, task["id"]))


async def _run_queue(store, project_slug: str, service: str, task_id: str) -> None:
    """Process every queued bug of one service repo, sequentially."""
    error: str | None = None
    try:
        while True:
            item = await _find_queued(store, project_slug, service)
            if item is None:
                break
            feature_name, bug_index, bug, feature = item
            await _fix_one(store, project_slug, feature_name, bug_index, bug, feature, service)
    except Exception as exc:  # noqa: BLE001 — the task must always be finished
        logger.exception("[bug_fixer] Queue for %s/%s crashed", project_slug, service)
        error = str(exc)[:500]
    finally:
        status = "error" if error else "done"
        await store.finish_task(project_slug, task_id, status=status, error_message=error)


async def _fix_one(store, project_slug, feature_name, bug_index, bug, feature, service) -> None:
    repo = resolve_repo(service)
    _, spec_url = await _service_of_feature(store, project_slug, feature)
    started = datetime.now(UTC).isoformat()

    log_dir = Path(settings.bug_fix_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{bug['jira_key']}-{started[:19].replace(':', '-')}.jsonl"

    await _update_bug(
        store, project_slug, feature_name, bug_index,
        fix_status="running", fix_started_at=started, fix_log=str(log_path),
    )
    logger.info("[bug_fixer] Fixing %s in %s (log: %s)", bug["jira_key"], repo, log_path)

    try:
        await ensure_tunnel()
        result = await _run_claude(build_prompt(bug, feature, spec_url), repo, log_path)
    except (BugFixerError, OSError) as exc:
        await _update_bug(
            store, project_slug, feature_name, bug_index,
            fix_status="failed", fix_error=str(exc)[:500],
            fix_finished_at=datetime.now(UTC).isoformat(),
        )
        return

    await _update_bug(
        store, project_slug, feature_name, bug_index,
        fix_status=result.get("status", "failed"),
        fix_branch=result.get("branch"),
        fix_mr_url=result.get("mr_url"),
        fix_summary=result.get("summary"),
        fix_error=result.get("reason"),
        fix_finished_at=datetime.now(UTC).isoformat(),
    )
    logger.info("[bug_fixer] %s finished: %s (%s)", bug["jira_key"], result.get("status"), result.get("mr_url") or result.get("reason"))


_CONTINUE_PROMPT = (
    "Сессия продолжена. Заверши начатую работу по багу до конца: дождись/повтори проверки "
    "СИНХРОННО (без фоновых задач), закоммить, создай MR через push options, переведи статусы "
    "Jira — и выведи в самом конце ровно один итоговый JSON-объект "
    '{"status": ..., "branch": ..., "mr_url": ..., "summary": ..., "reason": ...}.'
)


async def _run_claude(
    prompt: str, repo: Path, log_path: Path,
    statuses: tuple[str, ...] = ("fix_proposed", "failed"),
    continue_prompt: str | None = None,
) -> dict:
    """Headless Claude Code run; returns the agent's final JSON verdict.

    A one-shot -p session dies the moment the agent ends its turn, even if it ended
    it "waiting" for something — so when the final message carries no verdict, the
    same session is resumed once and asked to finish the job. The autotest
    generator reuses this runner with its own verdict statuses/continue prompt.
    """
    env = os.environ.copy()
    env.update({
        "HTTPS_PROXY": settings.claude_proxy,
        "HTTP_PROXY": settings.claude_proxy,
        "https_proxy": settings.claude_proxy,
        "http_proxy": settings.claude_proxy,
        "CLAUDE_CODE_OAUTH_TOKEN": settings.claude_code_oauth_token,
    })
    # The backend itself may run under Claude Code — the child is an independent session.
    env.pop("CLAUDECODE", None)

    deadline = asyncio.get_running_loop().time() + settings.bug_fix_timeout_seconds
    result_text, session_id = await _one_pass(["-p", prompt], repo, env, log_path, deadline, mode="w")

    verdict = extract_result_json(result_text, statuses)
    if verdict is None and session_id:
        logger.warning("[bug_fixer] No verdict in final message — resuming session %s once", session_id)
        result_text, _ = await _one_pass(
            ["-p", "--resume", session_id, continue_prompt or _CONTINUE_PROMPT], repo, env, log_path, deadline, mode="a",
        )
        verdict = extract_result_json(result_text, statuses)

    if verdict is None:
        raise BugFixerError(
            f"Агент не вернул итоговый JSON (см. лог {log_path}); конец ответа: {result_text[-200:]}"
        )
    return verdict


async def _one_pass(
    args: list[str], repo: Path, env: dict, log_path: Path, deadline: float, mode: str,
) -> tuple[str, str | None]:
    """Run one claude process until its result event; returns (final_text, session_id)."""
    proc = await asyncio.create_subprocess_exec(
        settings.claude_cli, *args,
        "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions",
        cwd=repo, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )

    result_text = ""
    session_id: str | None = None
    try:
        async with asyncio.timeout(deadline - asyncio.get_running_loop().time()):
            with log_path.open(mode, encoding="utf-8") as log:
                async for raw_line in proc.stdout:
                    line = raw_line.decode(errors="replace")
                    log.write(line)
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("session_id"):
                        session_id = event["session_id"]
                    if event.get("type") == "result":
                        result_text = event.get("result") or ""
            stderr = (await proc.stderr.read()).decode(errors="replace")
            rc = await proc.wait()
    except TimeoutError:
        proc.kill()
        raise BugFixerError(
            f"Прогон превысил таймаут {settings.bug_fix_timeout_seconds}с и был остановлен"
        )

    if rc != 0 and not result_text:
        raise BugFixerError(f"claude завершился с кодом {rc}: {stderr.strip()[:300]}")
    return result_text, session_id
