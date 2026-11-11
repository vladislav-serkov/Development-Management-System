"""Runs a generated ru-dsl scenario on the test stand and reads the result.

The backend runs the scenario itself — not the Codex agent that wrote it — so a
pass is a fact from the Cucumber report, and nobody is tempted to bend the
checks to the stand. The run happens in a throw-away git worktree of the
scenario's branch, so it never touches the clone the agent switches branches in.

Before anything is executed the scenario's SQL is checked in code: it may write
only into the feature's own schemas (the same rule the test-case assistant
follows, `assistant_stand.classify_sql`). Stand access comes from the platform's
settings and is handed to the runner at launch (DB credentials through the
environment, never through the command line or files).
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.config import settings
from app.services.assistant_stand import SqlNotAllowed, classify_sql

REPORT_DIR = "target/extract-agent-run"
_ERROR_CHARS = 2000
_STEP_RE = re.compile(r"^\s*(?:Допустим|Дано|Пусть|Когда|Если|Тогда|То|Затем|И|А|Но|Также|\*)\s+(.+?)\s*$")
_FAILING = ("failed", "undefined", "pending", "ambiguous")


class RunBlocked(Exception):
    """The scenario cannot be run; the message says what is missing or forbidden."""


def is_configured() -> bool:
    return settings.dsl_script_run and bool(settings.test_db_url)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ----------------------------------------------------------------------
# Scenario text → what it needs and what it writes
# ----------------------------------------------------------------------


def scenario_steps(scenario: str) -> list[tuple[str, str | None]]:
    """Steps of a scenario as (text without the Gherkin keyword, docstring or None)."""
    steps: list[tuple[str, str | None]] = []
    docstring: list[str] | None = None
    for raw in scenario.splitlines():
        line = raw.strip()
        if line.startswith(('"""', "```")):
            if docstring is None:
                docstring = []
            else:
                if steps:
                    steps[-1] = (steps[-1][0], "\n".join(docstring))
                docstring = None
            continue
        if docstring is not None:
            docstring.append(raw)
            continue
        match = _STEP_RE.match(raw)
        if match and not line.startswith(("#", "@", "|")):
            steps.append((match.group(1), None))
    return steps


def _scenario_sql(steps: list[tuple[str, str | None]], entity_tables: dict[str, str]) -> list[str]:
    """Every piece of SQL the scenario executes, including inserts made by entity steps."""
    scripts: list[str] = []
    for text, docstring in steps:
        command = text.removeprefix("после сценария ").strip()
        if re.match(r"выполнить в БД \S+:$", command):
            scripts.append(docstring or "")
        elif insert := re.match(r"insert в (\S+)(?: в БД \S+)? как .+:$", command):
            scripts.append(f"INSERT INTO {insert.group(1)} (x) VALUES (1)")
        elif create := re.match(r"создать (\S+) как .+:$", command):
            # An entity unknown to the profile fails in the runner itself
            if table := entity_tables.get(create.group(1)):
                scripts.append(f"INSERT INTO {table} (x) VALUES (1)")
        elif inline := re.search(r"в БД \S+ (.+) вернёт ", command):
            scripts.append(inline.group(1))
        elif remember := re.match(r"запомнить из БД \S+ (.+) колонку \S+ как \S+$", command):
            scripts.append(remember.group(1))
    return scripts


def check_sql_scope(scenario: str, write_schemas: Collection[str], entity_tables: dict[str, str]) -> None:
    """Raise RunBlocked unless the scenario only reads and writes the feature's own schemas."""
    for sql in _scenario_sql(scenario_steps(scenario), entity_tables):
        try:
            classify_sql(sql, write_schemas)
        except SqlNotAllowed as exc:
            raise RunBlocked(f"Сценарий не запущен: {str(exc).replace('ассистент', 'платформа')}") from exc


def _parse_properties(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")) and "=" in line:
            key, _, value = line.partition("=")
            props[key.strip()] = value.strip()
    return props


def stand_properties(scenario: str, profile: dict[str, str]) -> dict[str, str]:
    """JVM properties with the stand addresses the scenario needs and the profile lacks.

    Raises RunBlocked when a needed address is known neither to the profile nor to the platform.
    """
    steps = [text for text, _ in scenario_steps(scenario)]
    props: dict[str, str] = {}
    for alias in sorted({m.group(1) for text in steps for m in re.finditer(r"\bмок (\S+) (?:на|получил) ", text)}):
        if profile.get(f"mocks.{alias}"):
            continue
        if not settings.test_wiremock_url:
            raise RunBlocked(f"Сценарий не запущен: не задан адрес мока «{alias}» (TEST_WIREMOCK_URL)")
        props[f"mocks.{alias}"] = settings.test_wiremock_url.rstrip("/")
    if any(re.search(r"\bтопик[еа]? \S", text) for text in steps) and not profile.get("kafka.bootstrap.servers"):
        if not settings.test_kafka_bootstrap:
            raise RunBlocked("Сценарий не запущен: не задан адрес Kafka тестового стенда (TEST_KAFKA_BOOTSTRAP)")
        props["kafka.bootstrap.servers"] = settings.test_kafka_bootstrap
    return props


# ----------------------------------------------------------------------
# Cucumber report → result
# ----------------------------------------------------------------------


def _clean_error(message: str | None) -> str | None:
    """The assertion text without the Java stack trace."""
    if not message:
        return None
    lines = []
    for line in message.splitlines():
        if line.lstrip().startswith("at ") and line[:1] in ("\t", " "):
            break
        lines.append(line.rstrip())
    text = "\n".join(lines).strip()
    # «ru.qa…DslAssertionError: статус ответа…» → «статус ответа…»: the class name tells a tester nothing
    text = re.sub(r"^(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*(?:Error|Exception): ", "", text)
    return text[:_ERROR_CHARS] or None


def parse_report(report: list[dict]) -> dict:
    """Step-by-step result of the run: status passed/failed plus the first failure."""
    elements = [el for feature in report for el in feature.get("elements", []) if el.get("type") != "background"]
    if not elements:
        return {"script_run_status": "error", "script_run_error": "В отчёте раннера нет сценария", "script_run_steps": []}
    steps: list[dict] = []
    for element in elements:
        scenario_name = element.get("name") if len(elements) > 1 else None
        for step in element.get("steps", []):
            result = step.get("result") or {}
            entry = {
                "keyword": (step.get("keyword") or "").strip(),
                "text": step.get("name") or "",
                "status": result.get("status") or "skipped",
                "error": _clean_error(result.get("error_message")),
            }
            if scenario_name:
                entry["scenario"] = scenario_name
            steps.append(entry)
        for hook in element.get("after", []):
            result = hook.get("result") or {}
            if result.get("status") in _FAILING:
                steps.append({
                    "keyword": "", "text": "Очистка после сценария", "status": "failed",
                    "error": _clean_error(result.get("error_message")),
                })
        for hook in element.get("before", []):
            result = hook.get("result") or {}
            if result.get("status") in _FAILING:
                steps.insert(0, {
                    "keyword": "", "text": "Подготовка сценария", "status": "failed",
                    "error": _clean_error(result.get("error_message")),
                })
    failed = next((step for step in steps if step["status"] in _FAILING), None)
    return {
        "script_run_status": "failed" if failed else "passed",
        "script_run_error": (failed.get("error") or f"Шаг не выполнен: {failed['status']}") if failed else None,
        "script_run_steps": steps,
    }


# ----------------------------------------------------------------------
# Launch
# ----------------------------------------------------------------------


def _db_access() -> tuple[str, int, dict[str, str]]:
    """(host, port, runner environment) from the platform's TEST_DB_URL."""
    parsed = urlparse(settings.test_db_url.replace("postgresql+asyncpg://", "postgresql://"))
    host, port = parsed.hostname or "", parsed.port or 5432
    return host, port, {
        # prepareThreshold=0: the stand DB is reached through a transaction pooler
        "DB_URL": f"jdbc:postgresql://{host}:{port}{parsed.path}?prepareThreshold=0",
        "DB_USERNAME": unquote(parsed.username or ""),
        "DB_PASSWORD": unquote(parsed.password or ""),
    }


async def _reachable(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
    except (OSError, TimeoutError):
        return False
    writer.close()
    return True


async def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace")


async def _resolve_ref(repo: Path, branch: str) -> str | None:
    """Where the scenario lives now: its branch, or main once the feature's MR is merged."""
    for ref in (branch, f"origin/{branch}", "origin/main"):
        code, _ = await _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if code == 0:
            return ref
    return None


async def _java_home() -> str | None:
    """JDK 17 for the runner: the host's default `java` may be older."""
    finder = Path("/usr/libexec/java_home")
    if not finder.exists():
        return None
    proc = await asyncio.create_subprocess_exec(
        str(finder), "-v", "17", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode().strip() or None if proc.returncode == 0 else None


def _log_tail(log_path: Path, lines: int = 12) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.strip().splitlines()[-lines:])[-_ERROR_CHARS:]


async def run_scenario(
    repo: Path, branch: str, tag: str, scenario: str, write_schemas: Collection[str], log_path: Path,
) -> dict:
    """Run the scenario tagged `tag` from `branch` on the stand; returns the case's `script_run_*` fields."""
    profile_name = settings.dsl_script_profile
    started = _now()

    def finished(fields: dict) -> dict:
        return {**fields, "script_run_started_at": started, "script_run_finished_at": _now(),
                "script_run_log": str(log_path)}

    def error(message: str) -> dict:
        return finished({"script_run_status": "error", "script_run_error": message, "script_run_steps": []})

    ref = await _resolve_ref(repo, branch)
    if ref is None:
        return error(f"В клоне ru-dsl-v2 нет ветки {branch}")
    code, profile_text = await _git(
        repo, "show", f"{ref}:src/test/resources/config/application-{profile_name}.properties",
    )
    profile = _parse_properties(profile_text) if code == 0 else {}
    entity_tables = {
        key.removeprefix("entities.tables."): value
        for key, value in profile.items() if key.startswith("entities.tables.")
    }
    try:
        check_sql_scope(scenario, write_schemas, entity_tables)
        props = stand_properties(scenario, profile)
    except RunBlocked as exc:
        return error(str(exc))

    host, port, db_env = _db_access()
    if not await _reachable(host, port):
        return error(f"Тестовая БД {host}:{port} недоступна — проверьте VPN")

    workdir = Path(tempfile.mkdtemp(prefix="ea-dsl-run-"))
    worktree = workdir / "repo"
    try:
        code, out = await _git(repo, "worktree", "add", "--detach", str(worktree), ref)
        if code != 0:
            return error(f"Не удалось взять ветку {ref}: {out.strip()[-300:]}")
        report_dir = worktree / REPORT_DIR
        command = [
            "./mvnw", "-q", "-B", "test-compile", "exec:java",
            f"-Denv={profile_name}", f"-Dcucumber.filter.tags={tag}",
            f"-Dqa.output={report_dir}", f"-Dallure.results.directory={report_dir / 'allure-results'}",
            *(f"-D{key}={value}" for key, value in props.items()),
        ]
        env = {**os.environ, **db_env}
        if java_home := await _java_home():
            env["JAVA_HOME"] = java_home
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log:
            log_path.chmod(0o600)
            proc = await asyncio.create_subprocess_exec(
                *command, cwd=worktree, env=env, stdout=log, stderr=asyncio.subprocess.STDOUT,
            )
            try:
                exit_code = await asyncio.wait_for(proc.wait(), timeout=settings.dsl_script_run_timeout_seconds)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return error(f"Прогон превысил таймаут {settings.dsl_script_run_timeout_seconds}с и был остановлен")

        report_path = report_dir / "cucumber.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return error("Раннер не дошёл до сценария:\n" + _log_tail(log_path))
        result = parse_report(report)
        if result["script_run_status"] == "passed" and exit_code != 0:
            result = {**result, "script_run_status": "failed",
                      "script_run_error": f"Раннер завершился с кодом {exit_code}:\n" + _log_tail(log_path)}
        return finished(result)
    finally:
        await _git(repo, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(workdir, ignore_errors=True)
