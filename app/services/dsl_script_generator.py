"""ru-dsl-v2 script generator: turns an accepted test case into a Russian
Gherkin scenario via a headless Codex SDK run in the ru-dsl-v2 repo.

«Принять» on a test case queues it here. One `.feature` file and one branch
(= one MR) per feature: every accepted case adds or rewrites its own scenario,
found by the tag `@ea-case-<case id>`, so the MR of a feature accumulates its
scenarios instead of N conflicting MRs editing the same file. Where the scenario
lives (file, branch, tag) is decided here, not by the agent — that is what lets
the backend read the result back and show it on the case card.

Queueing mirrors the bug fixer: one running generation per repo (task kind
`dsl_script`, target_id = repo name) on the shared Codex runner. Cases are
addressed by their stable `id` and written under the feature lock, so a case
deleted or edited during the run is never overwritten by position.
"""

import asyncio
import hashlib
import logging
import re
import textwrap
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services import agent_runner, http_runner
from app.services.task_manager import task_manager
from app.storage import ActiveTaskExistsError

logger = logging.getLogger(__name__)

VERDICT_STATUSES = ("generated", "failed")
ACTIVE_STATUSES = ("queued", "running")
_SCENARIO_HEADERS = (
    "Сценарий:", "Структура сценария:", "Шаблон сценария:", "Пример:",
    "Scenario:", "Scenario Outline:", "Scenario Template:", "Example:",
)
_BLOCK_ENDS = (*_SCENARIO_HEADERS, "Правило:", "Rule:")


class ScriptError(Exception):
    """User-facing script generator error (config, repo, case state)."""


class ScriptActiveError(ScriptError):
    """The case is already queued or being generated."""


def repo_dir() -> Path | None:
    if not settings.ru_dsl_repo_dir:
        return None
    path = Path(settings.ru_dsl_repo_dir).expanduser()
    return path if (path / ".git").exists() else None


def is_configured() -> bool:
    return agent_runner.is_configured() and repo_dir() is not None


def _slug(text: str, fallback_prefix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-")
    if slug:
        return slug
    # Names without latin characters (a Russian page title) still need a stable address
    return f"{fallback_prefix}-{hashlib.sha1(text.encode()).hexdigest()[:8]}"


def script_target(feature: dict, doc: dict, case_id: str) -> dict:
    """Where the case's scenario lives in the ru-dsl-v2 repo."""
    service = _slug(doc.get("service_name") or "", "service")
    feature_slug = _slug(feature.get("name") or "", "feature")
    return {
        "path": f"src/test/resources/features/{service}/{feature_slug}.feature",
        "branch": f"scripts/{service}-{feature_slug}",
        "tag": f"@ea-case-{case_id}",
        "service_tag": f"@{service}",
    }


def _spec_url(doc: dict) -> str:
    """Link to the spec page; documents imported long ago keep only the page id."""
    url = doc.get("confluence_url") or ""
    if url.startswith("http"):
        return url
    page_id = doc.get("confluence_page_id") or url
    if page_id and settings.confluence_base_url:
        return f"{settings.confluence_base_url.rstrip('/')}/pages/viewpage.action?pageId={page_id}"
    return ""


def build_prompt(project_slug: str, feature: dict, tc: dict, doc: dict, stand_base: str | None = None) -> str:
    """Task prompt for the headless run in the ru-dsl-v2 repo.

    ``stand_base`` — the service's API base on the test stand, when the platform knows it.
    """
    service = doc.get("service_name") or ""
    feature_name = feature.get("name", "")
    target = script_target(feature, doc, tc.get("id", ""))
    spec = _spec_url(doc)
    spec_version = doc.get("confluence_version")
    origin = f"# Extract Agent: {project_slug} / {feature_name}, кейс {tc.get('id', '')}"
    if spec:
        origin += f"; ТЗ: {spec}" + (f" (версия {spec_version})" if spec_version else "")

    parts: list[str] = [
        "Ты работаешь в репозитории ru-dsl-v2 — раннер интеграционных автотестов: сценарии пишутся "
        "обычным Gherkin на русском языке (.feature) и выполняются Cucumber. Сначала прочитай README.md, "
        "docs/steps/script.md, docs/CONFIGURATION.md и docs/ARCHITECTURE.md и дальше строго следуй им: "
        "в сценарии допустимы только шаги из словаря.",
        "",
        "Задача: перенеси принятый тест-кейс платформы Extract Agent в сценарий ru-dsl.",
        "",
        "## Куда писать",
        f"Сервис: {service}",
        f"Фича: {feature_name}",
        f"Файл: {target['path']} — один .feature на фичу. Если файла нет, создай его: первая строка "
        f"`# language: ru`, теги фичи `@integration {target['service_tag']}`, затем `Функционал: {feature_name}`.",
        f"Сценарий этого кейса помечается тегом {target['tag']} отдельной строкой прямо над строкой "
        "`Сценарий:` (или `Структура сценария:`). Если сценарий с этим тегом в файле уже есть — перепиши "
        "его целиком. Остальные сценарии файла не трогай.",
        "Над строкой с тегом оставь комментарий-источник:",
        origin,
        f"Название сценария: {tc.get('name', '')}",
        "",
        "## Тест-кейс",
        f"Категория: {tc.get('category', '')}, приоритет: {tc.get('priority', '')}",
        f"Предусловия: {tc.get('preconditions', '')}",
    ]
    for i, step in enumerate(tc.get("steps") or [], 1):
        parts.append(f"Шаг {i}: {step.get('action', '')} → {step.get('expected', '')}")
    parts.append(f"Ожидаемый результат: {tc.get('expected_result', '')}")

    if tc.get("sql_setup"):
        parts += ["", "sql_setup (подготовка данных):", tc["sql_setup"]]
    if tc.get("curl_command"):
        parts += ["", "curl_command (запрос к сервису):", tc["curl_command"]]
    if tc.get("kafka_message"):
        parts += ["", "kafka_message:", str(tc["kafka_message"])]
    if tc.get("mock_config"):
        parts += ["", "mock_config (WireMock):", str(tc["mock_config"])]

    parts += [
        "",
        "## Правила переноса",
        "- Сценарий — детерминированный перевод кейса. Проверки берутся только из шагов и ожидаемого "
        "результата кейса; НИЧЕГО не подгонять под фактическое поведение стенда.",
        "- sql_setup: записи, которые кейс вставляет, создавай шагами `создать <entity> как \"<имя>\":` или "
        "`insert в <schema.table> как \"<имя>\":` — такие записи удаляются после сценария автоматически. "
        "`выполнить в БД` — только для того, что этими шагами не выразить. Данные только синтетические.",
        "- curl_command: метод, путь и тело переведи в шаг `отправить …`. Адрес стенда в сценарий не "
        f"пиши — он задаётся профилем. Если в профиле стенда ещё нет настроек сервиса {service} (адрес "
        "API, `entities.tables.*`), добавь их по docs/CONFIGURATION.md; при необходимости добавь рецепт "
        "`entities/<schema.table>.json` и JSON Schema ответа."
        + (
            f" Адрес API сервиса на тестовом стенде: {stand_base} — пути кейса заданы относительно него."
            if stand_base else ""
        ),
        "- kafka_message и mock_config — командами движка, как описано в документации раннера.",
        "- Java-код раннера не меняй и шаги не выдумывай. Шаг кейса, который нельзя проверить "
        "имеющимися шагами (логи, отсутствие вызова), в сценарий не переносится. Если не переносится "
        "сам кейс — остановись и верни failed с причиной (какого шага не хватает), ничего не пушь.",
        "- Доступы, пароли и токены в файлы не записывай.",
        "",
        "## Порядок работы",
        "- Если в рабочей копии есть чужие незакоммиченные изменения — остановись и верни failed.",
        f"- `git fetch origin`. Ветка {target['branch']}: если `origin/{target['branch']}` существует — "
        "переключись на неё и влей `origin/main` (в ней копятся сценарии этой фичи, MR уже открыт); "
        "иначе создай её от `origin/main`.",
        "- Раннеру нужен JDK 17+: если `java -version` старше, выставь JAVA_HOME (на macOS — "
        "`export JAVA_HOME=$(/usr/libexec/java_home -v 17)`).",
        "- Проверь привязку шагов (dry-run, ничего не выполняет): `./mvnw test-compile exec:java "
        f"-Dexec.args=--dry-run -Dcucumber.filter.tags={target['tag']} "
        "-Dqa.output=target/extract-agent-check`. Сценарии на стенде НЕ запускай — стенд и доступы "
        "из этой сессии недоступны.",
        "- Закоммить только файлы этой задачи. MR — через git push options, target-ветка main, title "
        f'"ru-dsl: {service} — {feature_name}"; в description — ссылка на ТЗ'
        + (f" ({spec})" if spec else "")
        + ". Если MR этой ветки уже открыт, тот же push его обновит — верни его URL из вывода push. "
        "Jira-строку в description не добавляй: Jira-тикета у сценария нет, статусы Jira не трогай.",
        "- После push вернись на main: `git checkout main`.",
        "- Ты в headless-сессии: никаких фоновых процессов, всё синхронно и до конца.",
        "",
        "## Формат ответа",
        "В самом конце ответа выведи ровно один JSON-объект, после него — никакого текста:",
        '{"status": "generated" | "failed", "branch": "...", "mr_url": "...", '
        '"summary": "1-2 предложения что сделано", "reason": "причина, если failed"}',
    ]
    return "\n".join(parts)


def extract_scenario(feature_text: str, tag: str) -> str | None:
    """The scenario marked with `tag` (its comment, tags, steps) out of a .feature file."""
    lines = feature_text.splitlines()
    start = end = None
    in_docstring = seen_header = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith(('"""', "```")):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if start is None:
            if line.startswith("@") and tag in line.split():
                start = i
            continue
        if not seen_header:
            seen_header = line.startswith(_SCENARIO_HEADERS)
            continue
        if line.startswith("@") or line.startswith(_BLOCK_ENDS):
            end = i
            break
    if start is None or not seen_header:
        return None
    # The source comment sits right above the tag line
    while start > 0 and lines[start - 1].strip().startswith("#"):
        start -= 1
    block = lines[start:end]
    # Comments and blank lines before the next scenario belong to that scenario
    while block and (not block[-1].strip() or block[-1].strip().startswith("#")):
        block.pop()
    return textwrap.dedent("\n".join(block)) or None


async def _read_scenario(repo: Path, branch: str, path: str, tag: str) -> str | None:
    """Best effort: the scenario as committed on the branch (None if it cannot be read)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo), "show", f"{branch}:{path}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
    except (OSError, TimeoutError):
        return None
    if proc.returncode != 0:
        return None
    return extract_scenario(out.decode("utf-8", errors="replace"), tag)


async def update_case(store, project_slug: str, feature_name: str, case_id: str, **fields) -> dict | None:
    """Write script fields on the case with this id (None if the case is gone)."""
    updated: dict | None = None

    def mutate(cases: list[dict]) -> list[dict]:
        nonlocal updated
        for case in cases:
            if case.get("id") == case_id:
                case.update(fields)
                updated = case
        return cases

    try:
        await store.mutate_test_cases(project_slug, feature_name, mutate)
    except ValueError:  # the feature was deleted meanwhile
        return None
    return updated


async def _doc_of_feature(store, project_slug: str, feature: dict) -> dict:
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return {}
    return await store.get_document(project_slug, doc_slug) or {}


def _task_key(project_slug: str) -> str:
    return f"dsl_script:{project_slug}/{repo_dir().name}"


async def request_generation(store, project_slug: str, feature_name: str, tc_index: int) -> dict:
    """Queue one accepted test case for script generation and start the queue if idle.

    Returns the updated test case dict. Raises ScriptError when the generation
    cannot even be queued (not configured, case not accepted, unknown service).
    """
    if not is_configured():
        raise ScriptError(
            "Генератор скриптов ru-dsl не настроен: задайте CODEX_ENABLED=true и RU_DSL_REPO_DIR в .env; "
            "выполните codex login"
        )

    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ScriptError(f"Фича '{feature_name}' не найдена")
    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index < 0 or tc_index >= len(test_cases):
        raise ScriptError(f"Тест-кейс с индексом {tc_index} не найден")
    tc = test_cases[tc_index]

    if tc.get("status") != "approved":
        raise ScriptError("Скрипт ru-dsl генерируется только по принятому тест-кейсу")
    # A status left by a restarted server is not a running generation: let it be re-queued
    if tc.get("script_status") in ACTIVE_STATUSES and task_manager.is_running(_task_key(project_slug)):
        raise ScriptActiveError(f"Генерация уже {tc['script_status']}")

    doc = await _doc_of_feature(store, project_slug, feature)
    if not doc.get("service_name"):
        raise ScriptError(
            "У фичи не определён сервис — неизвестно, для какого сервиса писать сценарий "
            "(импортируйте спеку из Confluence)"
        )

    tc = await update_case(
        store, project_slug, feature_name, tc["id"],
        script_status="queued", script_error=None,
        script_requested_at=datetime.now(UTC).isoformat(),
    )
    if tc is None:
        raise ScriptError("Тест-кейс удалён")
    await _maybe_start(store, project_slug)
    return tc


async def _find_queued(store, project_slug: str) -> tuple[str, dict, dict] | None:
    """Oldest queued test case: (feature_name, tc, feature)."""
    best = None
    for feature in await store.list_features(project_slug):
        for tc in await store.get_test_cases(project_slug, feature["name"]):
            if tc.get("script_status") != "queued":
                continue
            key = tc.get("script_requested_at") or ""
            if best is None or key < best[0]:
                best = (key, feature["name"], tc, feature)
    if best is None:
        return None
    return best[1], best[2], best[3]


async def _requeue_interrupted(store, project_slug: str) -> None:
    """Cases left `running` by a restarted server go back to the queue."""
    for feature in await store.list_features(project_slug):
        for tc in await store.get_test_cases(project_slug, feature["name"]):
            if tc.get("script_status") == "running":
                await update_case(store, project_slug, feature["name"], tc["id"], script_status="queued")


async def _maybe_start(store, project_slug: str) -> None:
    """Start the queue-processing task for the ru-dsl repo unless one is running."""
    target = repo_dir().name
    task_key = _task_key(project_slug)
    active = await store.get_active_task(project_slug, kind="dsl_script", target_id=target)
    if active is not None:
        if task_manager.is_running(task_key):
            return
        logger.warning("[dsl-script] Stuck task %s for %s, recovering", active["id"], project_slug)
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )
    try:
        task = await store.create_task(
            project_slug, kind="dsl_script", target_type="repo", target_id=target,
        )
    except ActiveTaskExistsError:
        return
    task_manager.launch(task_key, _run_queue(store, project_slug, task["id"]))


async def _run_queue(store, project_slug: str, task_id: str) -> None:
    """Process every queued test case of the project, sequentially."""
    error: str | None = None
    try:
        # Only one queue runs per repo, so nothing can be `running` when it starts
        await _requeue_interrupted(store, project_slug)
        while True:
            item = await _find_queued(store, project_slug)
            if item is None:
                break
            feature_name, tc, feature = item
            await _generate_one(store, project_slug, feature_name, tc, feature)
    except Exception as exc:  # noqa: BLE001 — the task must always be finished
        logger.exception("[dsl-script] Queue for %s crashed", project_slug)
        error = str(exc)[:500]
    finally:
        status = "error" if error else "done"
        await store.finish_task(project_slug, task_id, status=status, error_message=error)


async def _generate_one(store, project_slug: str, feature_name: str, tc: dict, feature: dict) -> None:
    case_id = tc["id"]
    doc = await _doc_of_feature(store, project_slug, feature)
    target = script_target(feature, doc, case_id)
    started = datetime.now(UTC).isoformat()

    log_dir = Path(settings.dsl_script_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{project_slug}-{case_id}-{started[:19].replace(':', '-')}.jsonl"

    running = await update_case(
        store, project_slug, feature_name, case_id,
        script_status="running", script_started_at=started, script_log=str(log_path),
        script_path=target["path"],
    )
    if running is None:  # deleted while it waited in the queue
        return
    logger.info("[dsl-script] Generating %s/%s case %s in %s (log: %s)",
                project_slug, feature_name, case_id, repo_dir(), log_path)

    stand = await http_runner.stand_info(doc.get("service_name"))
    try:
        result = await agent_runner.run(
            build_prompt(project_slug, feature, running, doc, stand.get("target_base")),
            repo_dir(), log_path,
            statuses=VERDICT_STATUSES,
        )
    except (agent_runner.AgentError, OSError) as exc:
        await update_case(
            store, project_slug, feature_name, case_id,
            script_status="failed", script_error=str(exc)[:500],
            script_finished_at=datetime.now(UTC).isoformat(),
        )
        return

    status = result.get("status", "failed")
    fields = {
        "script_status": status,
        "script_branch": result.get("branch"),
        "script_mr_url": result.get("mr_url"),
        "script_summary": result.get("summary"),
        "script_error": result.get("reason"),
        "script_finished_at": datetime.now(UTC).isoformat(),
    }
    if status == "generated":
        # A failed re-generation keeps the scenario of the previous successful one
        fields["script_text"] = await _read_scenario(
            repo_dir(), result.get("branch") or target["branch"], target["path"], target["tag"],
        )
    await update_case(store, project_slug, feature_name, case_id, **fields)
    logger.info("[dsl-script] %s/%s case %s finished: %s (%s)",
                project_slug, feature_name, case_id,
                status, result.get("mr_url") or result.get("reason"))
