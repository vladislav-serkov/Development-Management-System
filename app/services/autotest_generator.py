"""Autotest generator: turns an accepted test case into a Java autotest via
a headless Claude Code run in the flp-autotests repo.

Mirrors the bug fixer's queueing model (one running generation per autotests
repo; a `autotest_gen` task with target_id = repo name) and reuses its headless
runner. The spawned agent follows the repo's README conventions: one test
method per test case, @SpecRef carrying the case address and the spec page
version, MR into main via push options. Assertions come only from the test
case's expected result — the agent must not adapt them to the stand's actual
behaviour.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services import bug_fixer
from app.services.task_manager import task_manager
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)

VERDICT_STATUSES = ("generated", "failed")


class AutotestError(Exception):
    """User-facing autotest generator error (config, repo, missing spec ref)."""


def repo_dir() -> Path | None:
    if not settings.autotests_repo_dir:
        return None
    path = Path(settings.autotests_repo_dir).expanduser()
    return path if (path / ".git").exists() else None


def is_configured() -> bool:
    return bool(settings.claude_code_oauth_token) and repo_dir() is not None


def build_prompt(project_slug: str, feature: dict, tc_index: int, tc: dict, doc: dict) -> str:
    """Task prompt for the headless run in the autotests repo."""
    service = doc.get("service_name") or ""
    parts: list[str] = [
        "Ты работаешь в репозитории flp-autotests (Java, JUnit 5, REST Assured) — API-автотесты "
        "сервисов flp-* против тестового стенда. Сначала прочитай README.md и дальше строго следуй "
        "его конвенциям: один класс на фичу, один метод на тест-кейс, аннотация @SpecRef на методе.",
        "",
        "Задача: добавь автотест для принятого тест-кейса из платформы Extract Agent. Если метод "
        "с таким же @SpecRef (project/feature/caseIndex) уже существует — перепиши его целиком.",
        "",
        "## Значения для @SpecRef",
        f'project = "{project_slug}"',
        f'feature = "{feature.get("name", "")}"',
        f"caseIndex = {tc_index}",
        f'pageId = "{doc.get("confluence_page_id", "")}"',
        f"pageVersion = {doc.get('confluence_version') or 0}",
        f"Сервис: {service}",
    ]
    if doc.get("confluence_url"):
        parts.append(f"ТЗ (Confluence): {doc['confluence_url']}")

    parts += [
        "",
        "## Тест-кейс",
        f"Название: {tc.get('name', '')}",
        f"Категория: {tc.get('category', '')}, приоритет: {tc.get('priority', '')}",
        f"Предусловия: {tc.get('preconditions', '')}",
    ]
    for i, step in enumerate(tc.get("steps") or [], 1):
        parts.append(f"Шаг {i}: {step.get('action', '')} → {step.get('expected', '')}")
    parts.append(f"Ожидаемый результат: {tc.get('expected_result', '')}")

    if tc.get("sql_setup"):
        parts += ["", "sql_setup (подготовка данных, выполнять через DbFixture):", tc["sql_setup"]]
    if tc.get("curl_command"):
        parts += ["", "curl_command (перевести в REST Assured):", tc["curl_command"]]
    if tc.get("kafka_message"):
        parts += ["", "kafka_message:", str(tc["kafka_message"])]
    if tc.get("mock_config"):
        parts += ["", "mock_config (WireMock):", str(tc["mock_config"])]

    parts += [
        "",
        "## Порядок работы",
        "- Свежий main: git checkout main && git pull.",
        f"- Ветка autotest/{project_slug}-case-{tc_index} от main.",
        "- Тест — детерминированный перевод артефактов кейса; ассерты только из ожидаемого "
        "результата, НИЧЕГО не подгонять под фактическое поведение стенда. Шаг кейса, который "
        "нельзя проверить через HTTP/БД (логи, отсутствие вызова мока), в тест не переносится.",
        "- Если кейс в принципе нельзя реализовать как HTTP/БД-тест — остановись и верни failed "
        "с причиной, ничего не пушь.",
        "- Проверь компиляцию: mvn -q test-compile (сами тесты НЕ запускай — стенд из этой сессии "
        "недоступен).",
        "- MR через git push options, target-ветка main (НЕ develop), title "
        f'"autotest: {feature.get("name", "")} — {tc.get("name", "")}"; в description — ссылка на ТЗ. '
        "Jira-строку в description не добавляй — Jira-тикета у автотеста нет, статусы Jira не трогай.",
        "- Ты в headless-сессии: никаких фоновых процессов, всё синхронно и до конца.",
        "",
        "## Формат ответа",
        "В самом конце ответа выведи ровно один JSON-объект, после него — никакого текста:",
        '{"status": "generated" | "failed", "branch": "...", "mr_url": "...", '
        '"summary": "1-2 предложения что сделано", "reason": "причина, если failed"}',
    ]
    return "\n".join(parts)


async def _update_tc(store, project_slug: str, feature_name: str, tc_index: int, **fields) -> dict | None:
    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index >= len(test_cases):
        return None
    test_cases[tc_index].update(fields)
    await store.save_test_cases(project_slug, feature_name, test_cases)
    return test_cases[tc_index]


async def _doc_of_feature(store, project_slug: str, feature: dict) -> dict:
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return {}
    return await store.get_document(project_slug, doc_slug) or {}


async def request_generation(store, project_slug: str, feature_name: str, tc_index: int) -> dict:
    """Queue one accepted test case for autotest generation and start the queue if idle.

    Returns the updated test case dict. Raises AutotestError when the generation
    cannot even be queued (not configured, case not accepted, no spec page ref).
    """
    if not is_configured():
        raise AutotestError(
            "Autotest generator не настроен: задайте CLAUDE_CODE_OAUTH_TOKEN и AUTOTESTS_REPO_DIR в .env"
        )

    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise AutotestError(f"Фича '{feature_name}' не найдена")
    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index < 0 or tc_index >= len(test_cases):
        raise AutotestError(f"Тест-кейс с индексом {tc_index} не найден")
    tc = test_cases[tc_index]

    if tc.get("status") != "approved":
        raise AutotestError("Автотест генерируется только по принятому тест-кейсу")
    if tc.get("autotest_status") in ("queued", "running"):
        raise AutotestError(f"Генерация уже {tc['autotest_status']}")

    doc = await _doc_of_feature(store, project_slug, feature)
    if not doc.get("confluence_page_id"):
        raise AutotestError(
            "У фичи нет Confluence-страницы ТЗ — @SpecRef не собрать (импортируйте спеку из Confluence)"
        )

    tc = await _update_tc(
        store, project_slug, feature_name, tc_index,
        autotest_status="queued", autotest_error=None,
        autotest_requested_at=datetime.now(UTC).isoformat(),
    )
    await _maybe_start(store, project_slug)
    return tc


async def _find_queued(store, project_slug: str) -> tuple[str, int, dict, dict] | None:
    """Oldest queued test case: (feature_name, tc_index, tc, feature)."""
    best = None
    for feature in await store.list_features(project_slug):
        for idx, tc in enumerate(await store.get_test_cases(project_slug, feature["name"])):
            if tc.get("autotest_status") != "queued":
                continue
            key = tc.get("autotest_requested_at") or ""
            if best is None or key < best[0]:
                best = (key, feature["name"], idx, tc, feature)
    if best is None:
        return None
    return best[1], best[2], best[3], best[4]


async def _maybe_start(store, project_slug: str) -> None:
    """Start the queue-processing task for the autotests repo unless one is running."""
    target = repo_dir().name
    task_key = f"autotest_gen:{project_slug}/{target}"
    active = await store.get_active_task(project_slug, kind="autotest_gen", target_id=target)
    if active is not None:
        if task_manager.is_running(task_key):
            return
        logger.warning("[autotest] Stuck task %s for %s, recovering", active["id"], project_slug)
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )
    try:
        task = await store.create_task(
            project_slug, kind="autotest_gen", target_type="repo", target_id=target,
        )
    except ActiveTaskExistsError:
        return
    task_manager.launch(task_key, _run_queue(store, project_slug, task["id"]))


async def _run_queue(store, project_slug: str, task_id: str) -> None:
    """Process every queued test case of the project, sequentially."""
    error: str | None = None
    try:
        while True:
            item = await _find_queued(store, project_slug)
            if item is None:
                break
            feature_name, tc_index, tc, feature = item
            await _generate_one(store, project_slug, feature_name, tc_index, tc, feature)
    except Exception as exc:  # noqa: BLE001 — the task must always be finished
        logger.exception("[autotest] Queue for %s crashed", project_slug)
        error = str(exc)[:500]
    finally:
        status = "error" if error else "done"
        await store.finish_task(project_slug, task_id, status=status, error_message=error)


_CONTINUE_PROMPT = (
    "Сессия продолжена. Заверши работу над автотестом до конца: проверь компиляцию СИНХРОННО "
    "(mvn -q test-compile, без фоновых задач), закоммить, создай MR через push options в main — "
    "и выведи в самом конце ровно один итоговый JSON-объект "
    '{"status": "generated" | "failed", "branch": ..., "mr_url": ..., "summary": ..., "reason": ...}.'
)


async def _generate_one(store, project_slug, feature_name, tc_index, tc, feature) -> None:
    doc = await _doc_of_feature(store, project_slug, feature)
    started = datetime.now(UTC).isoformat()

    log_dir = Path(settings.autotest_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{project_slug}-{tc_index}-{started[:19].replace(':', '-')}.jsonl"

    await _update_tc(
        store, project_slug, feature_name, tc_index,
        autotest_status="running", autotest_started_at=started, autotest_log=str(log_path),
    )
    logger.info("[autotest] Generating %s/%s#%d in %s (log: %s)",
                project_slug, feature_name, tc_index, repo_dir(), log_path)

    try:
        await bug_fixer.ensure_tunnel()
        result = await bug_fixer._run_claude(
            build_prompt(project_slug, feature, tc_index, tc, doc),
            repo_dir(), log_path,
            statuses=VERDICT_STATUSES, continue_prompt=_CONTINUE_PROMPT,
        )
    except (bug_fixer.BugFixerError, OSError) as exc:
        await _update_tc(
            store, project_slug, feature_name, tc_index,
            autotest_status="failed", autotest_error=str(exc)[:500],
            autotest_finished_at=datetime.now(UTC).isoformat(),
        )
        return

    await _update_tc(
        store, project_slug, feature_name, tc_index,
        autotest_status=result.get("status", "failed"),
        autotest_branch=result.get("branch"),
        autotest_mr_url=result.get("mr_url"),
        autotest_summary=result.get("summary"),
        autotest_error=result.get("reason"),
        autotest_finished_at=datetime.now(UTC).isoformat(),
    )
    logger.info("[autotest] %s/%s#%d finished: %s (%s)",
                project_slug, feature_name, tc_index,
                result.get("status"), result.get("mr_url") or result.get("reason"))
