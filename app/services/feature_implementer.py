"""Feature implementer: hands a "реализовать/доработать метод" task to a headless
Claude Code run in the service repo.

Mirrors the bug fixer: the spawned `claude -p` session runs inside the service
repository, picks up the user's global ~/.claude/CLAUDE.md and follows the
standard MTSPAY new-functionality flow (fresh develop, branch by ticket, spec
from Confluence, implementation with tests, MR via push options, Jira status
transitions). The platform contributes what it already knows: the extracted
feature structure and the spec URL, so the agent starts with a verified
machine-readable postановка instead of re-parsing Confluence.

Queueing: one running implementation per service repo (an `implement` task with
target_id = service name); other queued features of the same service wait as
impl_status="queued".
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services import bug_fixer
from app.services.task_manager import task_manager
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)

VERDICT_STATUSES = ("implemented", "no_changes_needed", "failed")


class ImplementError(Exception):
    """User-facing implementer error (config, repo not found, no ticket)."""


def is_configured() -> bool:
    return bool(settings.claude_code_oauth_token)


def _format_logic(feature: dict) -> list[str]:
    """Flatten the extracted logic steps into prompt lines (best effort)."""
    logic = (feature.get("structured_logic_json") or {}).get("logic_steps") or []
    lines: list[str] = []

    def walk(steps, depth=0):
        for step in steps:
            if not isinstance(step, dict):
                continue
            num = step.get("number") or ""
            text = step.get("text") or step.get("description") or ""
            lines.append("  " * depth + f"{num} {text}".strip())
            walk(step.get("substeps") or step.get("children") or [], depth + 1)

    walk(logic)
    return lines[:80]


def build_prompt(jira_key: str, feature: dict, doc: dict) -> str:
    """Task prompt for the headless run; the global CLAUDE.md carries the flow."""
    parts: list[str] = [
        f"Возьми в работу задачу {jira_key}.",
        "",
        "Это задача на новый функционал (реализовать новый метод или доработать существующий). "
        "Работай строго по стандартному флоу для задач типа «новый функционал» из глобального "
        "CLAUDE.md: свежий develop, ветка по тикету, ТЗ из Confluence, реализация с тестами "
        "(TDD), MR через push options, перевод статусов Jira.",
        "",
        "## Контекст от платформы Extract Agent",
        "Платформа уже извлекла структуру фичи из ТЗ — используй её как выверенную постановку, "
        "но сверься с первоисточником в Confluence:",
        f"Фича: {feature.get('name', '')} ({feature.get('method') or ''} {feature.get('endpoint') or ''})".rstrip(" ()"),
        f"Суть: {feature.get('summary') or feature.get('description') or ''}",
    ]
    if doc.get("confluence_url"):
        parts.append(f"ТЗ (Confluence): {doc['confluence_url']}")

    logic = _format_logic(feature)
    if logic:
        parts += ["", "Шаги логики из ТЗ (извлечено платформой):", *logic]

    parts += [
        "",
        "## Ограничения",
        "- Сначала сверь текущее состояние сервиса с ТЗ. Если требуемое поведение уже полностью "
        "реализовано — остановись, ничего не пушь и верни no_changes_needed с объяснением.",
        "- Если ТЗ не найдено, постановка противоречива или решение требует человеческого выбора — "
        "остановись, ничего не пушь и верни failed с причиной.",
        "- Незакоммиченные чужие изменения в репозитории — тоже причина остановиться.",
        "- Ты работаешь в headless-сессии: ничего не запускай в фоне, сборку и тесты — только "
        "синхронно. Заверши весь флоу — коммиты, MR, статусы Jira — в рамках этой сессии.",
        "",
        "## Формат ответа",
        "В самом конце твоего ответа выведи ровно один JSON-объект, после него — никакого текста:",
        '{"status": "implemented" | "no_changes_needed" | "failed", "branch": "...", "mr_url": "...", '
        '"summary": "1-2 предложения что сделано", "reason": "причина, если failed/no_changes_needed"}',
    ]
    return "\n".join(parts)


async def _update_feature(store, project_slug: str, feature_name: str, **fields) -> dict | None:
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        return None
    feature.update(fields)
    await store.save_feature(project_slug, feature)
    return feature


async def _doc_of_feature(store, project_slug: str, feature: dict) -> dict:
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return {}
    return await store.get_document(project_slug, doc_slug) or {}


async def request_implementation(store, project_slug: str, feature_name: str, jira_key: str) -> dict:
    """Queue one feature for implementation and start the service's queue if idle.

    Returns the updated feature dict. Raises ImplementError when the run cannot
    even be queued (not configured, no ticket, repo not found).
    """
    if not is_configured():
        raise ImplementError("Агент не настроен: задайте CLAUDE_CODE_OAUTH_TOKEN в .env")

    jira_key = (jira_key or "").strip().upper()
    if not jira_key:
        raise ImplementError("Укажите Jira-задачу — агент работает по тикету (ветка, статусы)")

    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ImplementError(f"Фича '{feature_name}' не найдена")
    feature_name = feature["name"]

    if feature.get("impl_status") in ("queued", "running"):
        raise ImplementError(f"Реализация уже {feature['impl_status']}")

    doc = await _doc_of_feature(store, project_slug, feature)
    service = doc.get("service_name")
    repo = bug_fixer.resolve_repo(service)
    if repo is None:
        raise ImplementError(
            f"Репозиторий сервиса не найден (service={service or 'неизвестен'}, roots={settings.repos_dirs})"
        )

    feature = await _update_feature(
        store, project_slug, feature_name,
        impl_status="queued", impl_service=service, impl_jira_key=jira_key,
        impl_error=None, impl_requested_at=datetime.now(UTC).isoformat(),
    )
    await _maybe_start(store, project_slug, service)
    return feature


async def _find_queued(store, project_slug: str, service: str) -> tuple[str, dict] | None:
    """Oldest queued feature of this service: (feature_name, feature)."""
    best = None
    for feature in await store.list_features(project_slug):
        if feature.get("impl_status") != "queued" or feature.get("impl_service") != service:
            continue
        key = feature.get("impl_requested_at") or ""
        if best is None or key < best[0]:
            best = (key, feature["name"], feature)
    if best is None:
        return None
    return best[1], best[2]


async def _maybe_start(store, project_slug: str, service: str) -> None:
    task_key = f"implement:{project_slug}/{service}"
    active = await store.get_active_task(project_slug, kind="implement", target_id=service)
    if active is not None:
        if task_manager.is_running(task_key):
            return
        logger.warning("[implementer] Stuck task %s for %s/%s, recovering", active["id"], project_slug, service)
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )
    try:
        task = await store.create_task(
            project_slug, kind="implement", target_type="service", target_id=service,
        )
    except ActiveTaskExistsError:
        return
    task_manager.launch(task_key, _run_queue(store, project_slug, service, task["id"]))


async def _run_queue(store, project_slug: str, service: str, task_id: str) -> None:
    error: str | None = None
    try:
        while True:
            item = await _find_queued(store, project_slug, service)
            if item is None:
                break
            feature_name, feature = item
            await _implement_one(store, project_slug, feature_name, feature, service)
    except Exception as exc:  # noqa: BLE001 — the task must always be finished
        logger.exception("[implementer] Queue for %s/%s crashed", project_slug, service)
        error = str(exc)[:500]
    finally:
        status = "error" if error else "done"
        await store.finish_task(project_slug, task_id, status=status, error_message=error)


_CONTINUE_PROMPT = (
    "Сессия продолжена. Заверши начатую задачу до конца: дождись/повтори проверки СИНХРОННО "
    "(без фоновых задач), закоммить, создай MR через push options, переведи статусы Jira — "
    "и выведи в самом конце ровно один итоговый JSON-объект "
    '{"status": "implemented" | "no_changes_needed" | "failed", "branch": ..., "mr_url": ..., '
    '"summary": ..., "reason": ...}.'
)


async def _implement_one(store, project_slug, feature_name, feature, service) -> None:
    repo = bug_fixer.resolve_repo(service)
    doc = await _doc_of_feature(store, project_slug, feature)
    jira_key = feature.get("impl_jira_key") or ""
    started = datetime.now(UTC).isoformat()

    log_dir = Path(settings.implement_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{jira_key}-{started[:19].replace(':', '-')}.jsonl"

    await _update_feature(
        store, project_slug, feature_name,
        impl_status="running", impl_started_at=started, impl_log=str(log_path),
    )
    logger.info("[implementer] Implementing %s (%s) in %s (log: %s)", feature_name, jira_key, repo, log_path)

    try:
        await bug_fixer.ensure_tunnel()
        result = await bug_fixer._run_claude(
            build_prompt(jira_key, feature, doc), repo, log_path,
            statuses=VERDICT_STATUSES, continue_prompt=_CONTINUE_PROMPT,
        )
    except (bug_fixer.BugFixerError, OSError) as exc:
        await _update_feature(
            store, project_slug, feature_name,
            impl_status="failed", impl_error=str(exc)[:500],
            impl_finished_at=datetime.now(UTC).isoformat(),
        )
        return

    await _update_feature(
        store, project_slug, feature_name,
        impl_status=result.get("status", "failed"),
        impl_branch=result.get("branch"),
        impl_mr_url=result.get("mr_url"),
        impl_summary=result.get("summary"),
        impl_error=result.get("reason"),
        impl_finished_at=datetime.now(UTC).isoformat(),
    )
    logger.info("[implementer] %s finished: %s (%s)", jira_key, result.get("status"),
                result.get("mr_url") or result.get("reason"))
