"""Stand runs of generated ru-dsl scenarios: SQL scope, stand addresses, report parsing, launch, queueing."""

import json
import subprocess
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services import agent_runner, dsl_script_generator, dsl_script_runner
from app.services.dsl_script_runner import (
    RunBlocked,
    check_sql_scope,
    parse_report,
    scenario_steps,
    stand_properties,
)
from app.services.task_manager import task_manager
from tests.test_dsl_script_generator import DOC, FEATURE, TEST_CASE

URL = "/projects/p/features/GET __v1__balance/test-cases/0"
TAG = f"@ea-case-{TEST_CASE['id']}"

SCENARIO = '''# Extract Agent: p / GET /v1/balance, кейс a1b2c3d4e5f6
@ea-case-a1b2c3d4e5f6
Сценарий: Баланс возвращается
  Допустим выполнить в БД default:
    """
    DELETE FROM card_balance.card_balances WHERE id = 'x';
    """
  И после сценария выполнить в БД default:
    """
    DELETE FROM card_balance.card_balances WHERE id = 'x';
    """
  И insert в card_balance.card_balances как "balance":
    | id | x |
  И мок ewallet на POST /wallet отвечает 200 с телом:
    """
    {"мок other на": "это текст тела, а не шаг"}
    """
  Когда отправить в топик balance.in событие с ключом x:
    """
    {"id": "x"}
    """
  Тогда ждать до 30 сек пока проверить что в БД default SELECT status FROM card_balance.card_balances WHERE id = 'x' вернёт status равно OK
  И проверить что мок ewallet получил 1 запрос на POST /wallet
'''

REPORT = [{
    "elements": [{
        "type": "scenario", "name": "Баланс возвращается",
        "steps": [
            {"keyword": "Допустим ", "name": "выполнить в БД default:", "result": {"status": "passed"}},
            {"keyword": "Когда ", "name": "отправить GET /v1/balance", "result": {"status": "passed"}},
            {"keyword": "Тогда ", "name": "ожидать статус 400", "result": {
                "status": "failed",
                "error_message": "ru.qa.framework.script.runtime.DslAssertionError: статус ответа: ожидалось 400, "
                                 "получено 200\nтело:\n{}\n\tat ru.qa.framework.Http.check(Http.java:340)\n\tat x.Y.z(Y.java:1)",
            }},
            {"keyword": "И ", "name": "проверить что \"$.error.code\" равно 1400", "result": {"status": "skipped"}},
        ],
        "after": [{"result": {"status": "passed"}}],
    }],
}]


@pytest.fixture
def stand(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(settings, "dsl_script_run", True)
    monkeypatch.setattr(settings, "dsl_script_profile", "stand")
    monkeypatch.setattr(settings, "dsl_script_log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings, "test_db_url", "postgresql://tester:p%40ss@db.example:6432/stand_db")
    monkeypatch.setattr(settings, "test_stand_url", "")
    monkeypatch.setattr(settings, "test_wiremock_url", "http://stand.example/wiremock/")
    monkeypatch.setattr(settings, "test_kafka_bootstrap", "kafka.example:9092")


def test_steps_are_read_with_their_docstrings():
    steps = scenario_steps(SCENARIO)
    assert steps[0] == ("выполнить в БД default:", "    DELETE FROM card_balance.card_balances WHERE id = 'x';")
    assert steps[2] == ('insert в card_balance.card_balances как "balance":', None)
    assert [text for text, _ in steps][-1] == "проверить что мок ewallet получил 1 запрос на POST /wallet"
    assert len(steps) == 7  # tables, tags, comments and docstring lines are not steps


def test_sql_scope_allows_the_features_own_schema():
    check_sql_scope(SCENARIO, {"card_balance"}, {})


@pytest.mark.parametrize("step", [
    'Допустим выполнить в БД default:\n  """\n  DELETE FROM other_service.payments;\n  """',
    'И после сценария выполнить в БД default:\n  """\n  UPDATE other_service.payments SET status = 1;\n  """',
    'Допустим insert в other_service.payments как "p":\n  | id | 1 |',
    'Допустим создать платёж как "p":\n  | id | 1 |',
    'Допустим выполнить в БД default:\n  """\n  DROP TABLE card_balance.card_balances;\n  """',
    "Тогда проверить что в БД default DELETE FROM other_service.payments RETURNING id вернёт 1 строку",
])
def test_sql_scope_blocks_writes_outside_the_feature(step):
    with pytest.raises(RunBlocked, match="Сценарий не запущен"):
        check_sql_scope(f"Сценарий: x\n  {step}", {"card_balance"}, {"платёж": "other_service.payments"})


def test_stand_addresses_come_from_the_platform_when_the_profile_lacks_them(stand):
    assert stand_properties(SCENARIO, {}) == {
        "mocks.ewallet": "http://stand.example/wiremock",
        "kafka.bootstrap.servers": "kafka.example:9092",
    }
    profile = {"mocks.ewallet": "http://own.example", "kafka.bootstrap.servers": "own:9092"}
    assert stand_properties(SCENARIO, profile) == {}
    assert stand_properties("Сценарий: x\n  Когда отправить GET /v1/balance", {}) == {}


def test_scenario_is_not_run_without_a_needed_address(stand, monkeypatch):
    monkeypatch.setattr(settings, "test_kafka_bootstrap", "")
    with pytest.raises(RunBlocked, match="TEST_KAFKA_BOOTSTRAP"):
        stand_properties(SCENARIO, {})
    monkeypatch.setattr(settings, "test_wiremock_url", "")
    with pytest.raises(RunBlocked, match="мока «ewallet»"):
        stand_properties(SCENARIO, {})


def test_report_gives_steps_and_the_first_failure_without_the_stack():
    result = parse_report(REPORT)
    assert result["script_run_status"] == "failed"
    assert result["script_run_error"] == "статус ответа: ожидалось 400, получено 200\nтело:\n{}"
    assert [step["status"] for step in result["script_run_steps"]] == ["passed", "passed", "failed", "skipped"]
    assert result["script_run_steps"][2]["keyword"] == "Тогда"


def test_report_passed_and_failed_cleanup():
    passed = [{"elements": [{"name": "s", "steps": [{"keyword": "Когда ", "name": "x", "result": {"status": "passed"}}]}]}]
    assert parse_report(passed)["script_run_status"] == "passed"
    assert parse_report(passed)["script_run_error"] is None

    passed[0]["elements"][0]["after"] = [{"result": {"status": "failed", "error_message": "Не удалось очистить"}}]
    result = parse_report(passed)
    assert result["script_run_status"] == "failed"
    assert result["script_run_steps"][-1]["text"] == "Очистка после сценария"

    assert parse_report([])["script_run_status"] == "error"


def _runner_repo(tmp_path, mvnw: str):
    """A git repo with a branch holding a stand profile and a fake Maven wrapper."""
    repo = tmp_path / "ru-dsl-v2"
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "scripts/x", str(repo)], check=True)
    config = repo / "src/test/resources/config"
    config.mkdir(parents=True)
    (config / "application-stand.properties").write_text("entities.tables.баланс=card_balance.card_balances\n")
    (repo / "mvnw").write_text(mvnw)
    (repo / "mvnw").chmod(0o755)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "scenario"], check=True)
    return repo


FAKE_MVNW = """#!/bin/sh
# Stands in for the runner: records how it was launched and writes the Cucumber report.
for arg in "$@"; do case "$arg" in -Dqa.output=*) out="${arg#-Dqa.output=}";; esac; done
mkdir -p "$out"
printf '%s\\n' "$@" > "$ARGS_FILE"
printf '%s|%s|%s' "$DB_URL" "$DB_USERNAME" "$DB_PASSWORD" > "$ENV_FILE"
cat > "$out/cucumber.json" <<'JSON'
REPORT_JSON
JSON
exit 1
"""


async def test_run_launches_the_runner_in_a_worktree_with_stand_access(stand, monkeypatch, tmp_path):
    repo = _runner_repo(tmp_path, FAKE_MVNW.replace("REPORT_JSON", json.dumps(REPORT, ensure_ascii=False)))
    monkeypatch.setenv("ARGS_FILE", str(tmp_path / "args"))
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "env"))
    monkeypatch.setattr(dsl_script_runner, "_reachable", AsyncMock(return_value=True))

    result = await dsl_script_runner.run_scenario(
        repo, "scripts/x", TAG, SCENARIO, {"card_balance"}, tmp_path / "logs" / "run.log",
    )

    assert result["script_run_status"] == "failed"
    assert len(result["script_run_steps"]) == 4
    args = (tmp_path / "args").read_text().splitlines()
    assert "-Denv=stand" in args
    assert f"-Dcucumber.filter.tags={TAG}" in args
    assert "-Dmocks.ewallet=http://stand.example/wiremock" in args
    assert "-Dkafka.bootstrap.servers=kafka.example:9092" in args
    # DB credentials travel in the environment, never on the command line
    assert (tmp_path / "env").read_text() == "jdbc:postgresql://db.example:6432/stand_db?prepareThreshold=0|tester|p@ss"
    assert not any("p@ss" in arg or "tester" in arg for arg in args)
    # The run leaves nothing behind in the clone
    assert subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout.count("\n") == 1
    assert subprocess.run(["git", "-C", str(repo), "status", "--short"], capture_output=True, text=True).stdout == ""


async def test_run_reports_why_it_could_not_start(stand, monkeypatch, tmp_path):
    repo = _runner_repo(tmp_path, "#!/bin/sh\necho 'COMPILATION ERROR: NativeSteps.java'\nexit 1\n")
    log = tmp_path / "logs" / "run.log"

    monkeypatch.setattr(dsl_script_runner, "_reachable", AsyncMock(return_value=False))
    result = await dsl_script_runner.run_scenario(repo, "scripts/x", TAG, SCENARIO, {"card_balance"}, log)
    assert (result["script_run_status"], "VPN" in result["script_run_error"]) == ("error", True)

    monkeypatch.setattr(dsl_script_runner, "_reachable", AsyncMock(return_value=True))
    result = await dsl_script_runner.run_scenario(repo, "scripts/x", TAG, SCENARIO, {"card_balance"}, log)
    assert result["script_run_status"] == "error"
    assert "COMPILATION ERROR" in result["script_run_error"]

    result = await dsl_script_runner.run_scenario(repo, "scripts/x", TAG, SCENARIO, {"other"}, log)
    assert result["script_run_status"] == "error"
    assert "card_balance.card_balances" in result["script_run_error"]

    result = await dsl_script_runner.run_scenario(tmp_path, "scripts/nope", TAG, SCENARIO, {"card_balance"}, log)
    assert result["script_run_status"] == "error"


@pytest.fixture
def generator(stand, monkeypatch, tmp_path):
    (tmp_path / "ru-dsl-v2" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "ru_dsl_repo_dir", str(tmp_path / "ru-dsl-v2"))
    monkeypatch.setattr(settings, "dsl_script_auto", True)


async def _make_case(client, store, **fields):
    await client.post("/projects/", json={"name": "P"})
    await store.save_feature("p", dict(FEATURE))
    await store.save_document("p", dict(DOC))
    await store.save_test_cases("p", FEATURE["name"], [{**TEST_CASE, **fields}])


async def test_generated_scenario_is_run_and_the_result_stored(client, store, generator, monkeypatch):
    verdict = {"status": "generated", "branch": "scripts/x", "mr_url": "https://gitlab.example/mr/7",
               "summary": "Добавлен сценарий", "reason": None}
    monkeypatch.setattr(agent_runner, "run", AsyncMock(return_value=verdict))
    monkeypatch.setattr(dsl_script_generator, "_read_scenario", AsyncMock(return_value=SCENARIO))
    run = AsyncMock(return_value={"script_run_status": "passed", "script_run_error": None, "script_run_steps": [
        {"keyword": "Когда", "text": "отправить GET /v1/balance", "status": "passed", "error": None},
    ]})
    monkeypatch.setattr(dsl_script_runner, "run_scenario", run)

    await _make_case(client, store, script_run_status="failed", script_run_error="старый прогон")
    feature = await store.get_feature("p", FEATURE["name"])
    await dsl_script_generator._generate_one(store, "p", FEATURE["name"], dict(TEST_CASE), feature)

    tc = (await store.get_test_cases("p", FEATURE["name"]))[0]
    assert (tc["script_status"], tc["script_run_status"], tc["script_run_error"]) == ("generated", "passed", None)
    assert len(tc["script_run_steps"]) == 1
    _, branch, tag, scenario, schemas, _ = run.call_args.args
    assert (branch, tag, scenario) == ("scripts/x", TAG, SCENARIO)
    assert schemas == {"flp_card_balance", "card_balance"}  # the service's schema + what the cases' SQL writes to


async def test_failed_generation_and_disabled_runs_do_not_run_anything(client, store, generator, monkeypatch):
    run = AsyncMock(side_effect=AssertionError("must not run"))
    monkeypatch.setattr(dsl_script_runner, "run_scenario", run)
    monkeypatch.setattr(agent_runner, "run", AsyncMock(side_effect=agent_runner.AgentError("Нужно включить VPN")))
    await _make_case(client, store)
    feature = await store.get_feature("p", FEATURE["name"])
    await dsl_script_generator._generate_one(store, "p", FEATURE["name"], dict(TEST_CASE), feature)
    assert (await store.get_test_cases("p", FEATURE["name"]))[0].get("script_run_status") is None

    monkeypatch.setattr(settings, "dsl_script_run", False)
    verdict = {"status": "generated", "branch": "scripts/x", "mr_url": "https://gitlab.example/mr/7",
               "summary": "ок", "reason": None}
    monkeypatch.setattr(agent_runner, "run", AsyncMock(return_value=verdict))
    monkeypatch.setattr(dsl_script_generator, "_read_scenario", AsyncMock(return_value=SCENARIO))
    await dsl_script_generator._generate_one(store, "p", FEATURE["name"], dict(TEST_CASE), feature)
    assert (await store.get_test_cases("p", FEATURE["name"]))[0].get("script_run_status") is None


async def test_run_endpoint_queues_a_rerun_of_a_ready_scenario(client, store, generator, monkeypatch):
    monkeypatch.setattr(dsl_script_generator, "_maybe_start", AsyncMock())

    await _make_case(client, store)
    r = await client.post(f"{URL}/script/run")
    assert r.status_code == 409
    assert "нет готового сценария" in r.json()["detail"]

    await store.save_test_cases("p", FEATURE["name"], [{
        **TEST_CASE, "script_status": "generated", "script_text": SCENARIO, "script_branch": "scripts/x",
    }])
    r = await client.post(f"{URL}/script/run")
    assert r.status_code == 200
    assert r.json()["test_cases"][0]["script_run_status"] == "queued"
    assert (await dsl_script_generator._find_queued(store, "p"))[0] == "run"

    monkeypatch.setattr(task_manager, "is_running", lambda key: True)
    assert (await client.post(f"{URL}/script/run")).status_code == 409

    monkeypatch.setattr(settings, "test_db_url", "")
    r = await client.post(f"{URL}/script/run")
    assert r.status_code == 409
    assert "TEST_DB_URL" in r.json()["detail"]


async def test_queue_runs_queued_reruns_and_survives_a_crashing_run(client, store, generator, monkeypatch):
    monkeypatch.setattr(dsl_script_runner, "run_scenario", AsyncMock(side_effect=RuntimeError("git сломался")))
    await _make_case(client, store, script_status="generated", script_text=SCENARIO, script_run_status="running")
    task = await store.create_task("p", kind="dsl_script", target_type="repo", target_id="ru-dsl-v2")
    await dsl_script_generator._run_queue(store, "p", task["id"])

    tc = (await store.get_test_cases("p", FEATURE["name"]))[0]
    assert (tc["script_run_status"], tc["script_run_error"]) == ("error", "git сломался")
    assert tc["script_status"] == "generated"
