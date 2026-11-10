"""ru-dsl script generator: config gate, prompt content, scenario read-back, queueing endpoints."""

import subprocess
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services import agent_runner, dsl_script_generator
from app.services.dsl_script_generator import build_prompt, extract_scenario, script_target
from app.services.task_manager import task_manager

TEST_CASE = {
    "id": "a1b2c3d4e5f6",
    "name": "Отсутствует обязательный параметр mtsBankCardPanHash",
    "category": "validation",
    "priority": "high",
    "status": "approved",
    "analyst_text": None,
    "preconditions": "В таблице card_balances отсутствуют записи",
    "steps": [
        {"action": "GET /v1/balance без параметра", "expected": "HTTP 400, error.code=1400"},
    ],
    "expected_result": "Запрос отклонён с HTTP 400",
    "curl_command": "curl -X GET 'http://localhost:8080/v1/balance'",
    "sql_setup": "DELETE FROM card_balance.card_balances;",
    "kafka_message": None,
    "mock_config": None,
}

FEATURE = {"name": "GET /v1/balance", "type": "endpoint", "status": "done", "source_document": "doc1"}

DOC = {
    "slug": "doc1", "project_slug": "p", "filename": "spec", "status": "ready",
    "uploaded_at": "2026-09-15T00:00:00+00:00",
    "service_name": "flp-card-balance",
    "confluence_url": "https://confluence.example/pages/627197487",
    "confluence_page_id": "627197487",
    "confluence_version": 2,
}

URL = "/projects/p/features/GET __v1__balance/test-cases/0"

FEATURE_FILE = '''# language: ru
@integration @flp-card-balance
Функционал: GET /v1/balance

  # Extract Agent: p / GET /v1/balance, кейс 000000000000
  @ea-case-000000000000
  Сценарий: Другой кейс
    Когда отправить GET /v1/balance
    Тогда ожидать статус 200

  # Extract Agent: p / GET /v1/balance, кейс a1b2c3d4e5f6
  @ea-case-a1b2c3d4e5f6
  Сценарий: Отсутствует обязательный параметр
    Когда отправить POST /v1/balance с телом:
      """
      {"note": "@ea-case-ffffffffffff
      Сценарий: это текст внутри тела"}
      """
    Тогда ожидать статус 400

  # Комментарий следующего сценария
  @ea-case-ffffffffffff
  Сценарий: Третий кейс
    Тогда ожидать статус 200
'''


@pytest.fixture
def generator_configured(monkeypatch, tmp_path):
    (tmp_path / "ru-dsl-v2" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(settings, "ru_dsl_repo_dir", str(tmp_path / "ru-dsl-v2"))
    monkeypatch.setattr(settings, "dsl_script_log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(settings, "dsl_script_auto", True)  # a developer .env may turn it off


async def _make_test_case(client, store, *, status="approved", with_doc=True, **fields):
    await client.post("/projects/", json={"name": "P"})
    await store.save_feature("p", dict(FEATURE))
    if with_doc:
        await store.save_document("p", dict(DOC))
    await store.save_test_cases("p", "GET /v1/balance", [{**TEST_CASE, "status": status, **fields}])


def test_configured_requires_enabled_codex_and_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(settings, "ru_dsl_repo_dir", "")
    assert not dsl_script_generator.is_configured()

    monkeypatch.setattr(settings, "ru_dsl_repo_dir", str(tmp_path / "nope"))
    assert not dsl_script_generator.is_configured()

    (tmp_path / "ru-dsl-v2" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "ru_dsl_repo_dir", str(tmp_path / "ru-dsl-v2"))
    assert dsl_script_generator.is_configured()

    monkeypatch.setattr(settings, "codex_enabled", False)
    assert not dsl_script_generator.is_configured()


def test_target_is_one_file_and_branch_per_feature():
    target = script_target(FEATURE, DOC, "a1b2c3d4e5f6")
    assert target == {
        "path": "src/test/resources/features/flp-card-balance/get-v1-balance.feature",
        "branch": "scripts/flp-card-balance-get-v1-balance",
        "tag": "@ea-case-a1b2c3d4e5f6",
        "service_tag": "@flp-card-balance",
    }
    other_case = script_target(FEATURE, DOC, "000000000000")
    assert (other_case["path"], other_case["branch"]) == (target["path"], target["branch"])
    assert other_case["tag"] != target["tag"]


def test_target_of_a_feature_named_in_russian_is_stable():
    first = script_target({"name": "Уведомление о платеже"}, DOC, "x")
    assert first == script_target({"name": "Уведомление о платеже"}, DOC, "x")
    assert first["path"] != script_target({"name": "Возврат платежа"}, DOC, "x")["path"]
    assert first["path"].isascii()


def test_prompt_carries_repo_conventions_and_contract():
    prompt = build_prompt("p", FEATURE, TEST_CASE, DOC)
    assert "docs/steps/script.md" in prompt
    assert "src/test/resources/features/flp-card-balance/get-v1-balance.feature" in prompt
    assert "scripts/flp-card-balance-get-v1-balance" in prompt
    assert "@ea-case-a1b2c3d4e5f6" in prompt
    assert "@integration @flp-card-balance" in prompt
    assert "https://confluence.example/pages/627197487 (версия 2)" in prompt
    assert "Отсутствует обязательный параметр mtsBankCardPanHash" in prompt
    assert "curl -X GET 'http://localhost:8080/v1/balance'" in prompt
    assert "DELETE FROM card_balance.card_balances;" in prompt
    assert "-Dexec.args=--dry-run -Dcucumber.filter.tags=@ea-case-a1b2c3d4e5f6" in prompt
    assert "Java-код раннера не меняй" in prompt
    assert "origin/main" in prompt
    assert '"generated" | "failed"' in prompt
    assert "SpecRef" not in prompt


def test_extract_scenario_takes_only_the_tagged_one():
    scenario = extract_scenario(FEATURE_FILE, "@ea-case-a1b2c3d4e5f6")
    assert scenario.splitlines()[0] == "# Extract Agent: p / GET /v1/balance, кейс a1b2c3d4e5f6"
    assert scenario.splitlines()[1] == "@ea-case-a1b2c3d4e5f6"
    assert scenario.splitlines()[-1] == "  Тогда ожидать статус 400"
    assert "Сценарий: это текст внутри тела" in scenario  # a docstring is not a scenario boundary
    assert "Другой кейс" not in scenario
    assert "Третий кейс" not in scenario
    assert "Комментарий следующего сценария" not in scenario


def test_extract_scenario_last_in_file_and_missing():
    assert extract_scenario(FEATURE_FILE, "@ea-case-ffffffffffff").endswith("Тогда ожидать статус 200")
    assert extract_scenario(FEATURE_FILE, "@ea-case-nope") is None
    assert extract_scenario("@ea-case-x\n", "@ea-case-x") is None


async def test_script_unconfigured(client, store, monkeypatch):
    monkeypatch.setattr(settings, "codex_enabled", False)
    await _make_test_case(client, store)
    r = await client.post(f"{URL}/script")
    assert r.status_code == 409
    assert "RU_DSL_REPO_DIR" in r.json()["detail"]


async def test_script_requires_accepted_case(client, store, generator_configured):
    await _make_test_case(client, store, status="pending")
    r = await client.post(f"{URL}/script")
    assert r.status_code == 409
    assert "принятому" in r.json()["detail"]


async def test_script_requires_known_service(client, store, generator_configured):
    await _make_test_case(client, store, with_doc=False)
    r = await client.post(f"{URL}/script")
    assert r.status_code == 409
    assert "сервис" in r.json()["detail"]


async def test_script_queues_and_rejects_repeat_while_running(client, store, generator_configured, monkeypatch):
    started = []

    async def fake_maybe_start(store_, project_slug):
        started.append(project_slug)

    monkeypatch.setattr(dsl_script_generator, "_maybe_start", fake_maybe_start)

    await _make_test_case(client, store)
    r = await client.post(f"{URL}/script")
    assert r.status_code == 200
    assert r.json()["test_cases"][0]["script_status"] == "queued"
    assert started == ["p"]

    monkeypatch.setattr(task_manager, "is_running", lambda key: True)
    r = await client.post(f"{URL}/script")
    assert r.status_code == 409

    # The queue died with the server: the leftover status must not block a retry
    monkeypatch.setattr(task_manager, "is_running", lambda key: False)
    r = await client.post(f"{URL}/script")
    assert r.status_code == 200
    assert started == ["p", "p"]


async def test_old_autotest_endpoint_is_gone(client, store, generator_configured):
    await _make_test_case(client, store)
    r = await client.post(f"{URL}/autotest")
    assert r.status_code in (404, 405)


async def test_accept_auto_queues_script(client, store, generator_configured, monkeypatch):
    monkeypatch.setattr(dsl_script_generator, "_maybe_start", AsyncMock())

    await _make_test_case(client, store, status="pending")
    r = await client.patch(URL, json={"status": "approved", "analyst_text": None})
    assert r.status_code == 200
    tc = r.json()["test_cases"][0]
    assert tc["status"] == "approved"
    assert tc["script_status"] == "queued"
    dsl_script_generator._maybe_start.assert_awaited_once()


async def test_accept_does_not_queue_when_auto_is_off(client, store, generator_configured, monkeypatch):
    monkeypatch.setattr(settings, "dsl_script_auto", False)
    monkeypatch.setattr(dsl_script_generator, "request_generation", AsyncMock(side_effect=AssertionError))

    await _make_test_case(client, store, status="pending")
    r = await client.patch(URL, json={"status": "approved", "analyst_text": None})
    assert r.status_code == 200
    assert r.json()["test_cases"][0].get("script_status") is None


async def test_accept_reports_unqueueable_script(client, store, generator_configured):
    await _make_test_case(client, store, status="pending", with_doc=False)
    r = await client.patch(URL, json={"status": "approved", "analyst_text": None})
    assert r.status_code == 200
    tc = r.json()["test_cases"][0]
    assert tc["status"] == "approved"
    assert tc["script_status"] == "failed"
    assert "сервис" in tc["script_error"]


async def test_accept_again_keeps_a_running_generation(client, store, generator_configured, monkeypatch):
    monkeypatch.setattr(task_manager, "is_running", lambda key: True)
    await _make_test_case(client, store, status="pending", script_status="running")
    r = await client.patch(URL, json={"status": "approved", "analyst_text": None})
    assert r.status_code == 200
    tc = r.json()["test_cases"][0]
    assert tc["script_status"] == "running"
    assert not tc.get("script_error")


async def test_bug_mark_does_not_queue(client, store, generator_configured, monkeypatch):
    monkeypatch.setattr(dsl_script_generator, "request_generation", AsyncMock(side_effect=AssertionError))

    await _make_test_case(client, store, status="pending")
    r = await client.patch(URL, json={"status": "edited", "analyst_text": "баг"})
    assert r.status_code == 200


async def test_return_to_review_leaves_the_queue(client, store, generator_configured):
    await _make_test_case(client, store, script_status="queued")
    r = await client.patch(URL, json={"status": "pending", "analyst_text": None})
    assert r.status_code == 200
    assert r.json()["test_cases"][0]["script_status"] is None
    assert await dsl_script_generator._find_queued(store, "p") is None


async def test_generated_scenario_is_read_back_from_the_branch(client, store, generator_configured, monkeypatch):
    repo = dsl_script_generator.repo_dir()
    target = script_target(FEATURE, DOC, TEST_CASE["id"])
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", target["branch"], str(repo)], check=True)
    path = repo / target["path"]
    path.parent.mkdir(parents=True)
    path.write_text(FEATURE_FILE, encoding="utf-8")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "scenario"], check=True)
    # The agent leaves the working copy on main: the scenario is read from the branch
    subprocess.run([*git, "checkout", "-q", "--orphan", "main"], check=True)
    subprocess.run([*git, "rm", "-q", "-rf", "."], check=True)

    verdict = {
        "status": "generated", "branch": target["branch"], "mr_url": "https://gitlab.example/mr/7",
        "summary": "Добавлен сценарий", "reason": None,
    }
    runner = AsyncMock(return_value=verdict)
    monkeypatch.setattr(agent_runner, "run", runner)

    await _make_test_case(client, store)
    feature = await store.get_feature("p", FEATURE["name"])
    await dsl_script_generator._generate_one(store, "p", FEATURE["name"], dict(TEST_CASE), feature)

    tc = (await store.get_test_cases("p", FEATURE["name"]))[0]
    assert tc["script_status"] == "generated"
    assert tc["script_path"] == target["path"]
    assert tc["script_mr_url"] == "https://gitlab.example/mr/7"
    assert tc["script_text"].startswith("# Extract Agent: p / GET /v1/balance, кейс a1b2c3d4e5f6")
    assert "Третий кейс" not in tc["script_text"]
    assert "@ea-case-a1b2c3d4e5f6" in runner.call_args.args[0]


async def test_result_lands_on_the_case_by_id_not_by_position(client, store, generator_configured, monkeypatch):
    """A case deleted above during the run must not shift the result onto a neighbour."""
    await client.post("/projects/", json={"name": "P"})
    await store.save_feature("p", dict(FEATURE))
    await store.save_document("p", dict(DOC))
    first = {**TEST_CASE, "id": "000000000000", "name": "Первый"}
    await store.save_test_cases("p", FEATURE["name"], [first, dict(TEST_CASE)])

    async def run_and_delete_first(*args, **kwargs):
        await store.save_test_cases("p", FEATURE["name"], (await store.get_test_cases("p", FEATURE["name"]))[1:])
        raise agent_runner.AgentError("Нужно включить VPN")

    monkeypatch.setattr(agent_runner, "run", run_and_delete_first)
    feature = await store.get_feature("p", FEATURE["name"])
    await dsl_script_generator._generate_one(store, "p", FEATURE["name"], dict(TEST_CASE), feature)

    cases = await store.get_test_cases("p", FEATURE["name"])
    assert [c["id"] for c in cases] == [TEST_CASE["id"]]
    assert cases[0]["script_status"] == "failed"
    assert cases[0]["script_error"] == "Нужно включить VPN"


async def test_queue_requeues_cases_interrupted_by_restart(client, store, generator_configured, monkeypatch):
    generated = []

    async def fake_generate(store_, project_slug, feature_name, tc, feature):
        generated.append(tc["id"])
        await dsl_script_generator.update_case(store_, project_slug, feature_name, tc["id"], script_status="generated")

    monkeypatch.setattr(dsl_script_generator, "_generate_one", fake_generate)
    await _make_test_case(client, store, script_status="running")
    task = await store.create_task("p", kind="dsl_script", target_type="repo", target_id="ru-dsl-v2")
    await dsl_script_generator._run_queue(store, "p", task["id"])

    assert generated == [TEST_CASE["id"]]
    assert (await store.get_active_task("p", kind="dsl_script", target_id="ru-dsl-v2")) is None
