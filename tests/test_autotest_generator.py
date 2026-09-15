"""Autotest generator: config gate, prompt content, queueing endpoints."""

import pytest

from app.config import settings
from app.services import autotest_generator
from app.services.autotest_generator import build_prompt
from app.services.bug_fixer import extract_result_json

TEST_CASE = {
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


@pytest.fixture
def generator_configured(monkeypatch, tmp_path):
    (tmp_path / "flp-autotests" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "claude_code_oauth_token", "sk-ant-oat01-test")
    monkeypatch.setattr(settings, "autotests_repo_dir", str(tmp_path / "flp-autotests"))


async def _make_test_case(client, store, *, status="approved", with_doc=True):
    await client.post("/projects/", json={"name": "P"})
    await store.save_feature("p", dict(FEATURE))
    if with_doc:
        await store.save_document("p", dict(DOC))
    await store.save_test_cases("p", "GET /v1/balance", [{**TEST_CASE, "status": status}])


def test_configured_requires_token_and_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "claude_code_oauth_token", "token")
    monkeypatch.setattr(settings, "autotests_repo_dir", "")
    assert not autotest_generator.is_configured()

    monkeypatch.setattr(settings, "autotests_repo_dir", str(tmp_path / "nope"))
    assert not autotest_generator.is_configured()

    (tmp_path / "flp-autotests" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "autotests_repo_dir", str(tmp_path / "flp-autotests"))
    assert autotest_generator.is_configured()


def test_prompt_carries_spec_ref_conventions_and_contract():
    prompt = build_prompt("p", FEATURE, 0, TEST_CASE, DOC)
    assert 'project = "p"' in prompt
    assert 'feature = "GET /v1/balance"' in prompt
    assert "caseIndex = 0" in prompt
    assert 'pageId = "627197487"' in prompt
    assert "pageVersion = 2" in prompt
    assert "flp-card-balance" in prompt
    assert "README.md" in prompt
    assert "@SpecRef" in prompt
    assert "curl -X GET 'http://localhost:8080/v1/balance'" in prompt
    assert "DELETE FROM card_balance.card_balances;" in prompt
    assert "mvn -q test-compile" in prompt
    assert "main" in prompt
    assert '"generated" | "failed"' in prompt


def test_verdict_parsed_with_generator_statuses():
    text = 'Готово.\n{"status": "generated", "branch": "autotest/p-case-0", "mr_url": "https://gitlab/mr/2", "summary": "тест добавлен", "reason": null}'
    verdict = extract_result_json(text, autotest_generator.VERDICT_STATUSES)
    assert verdict["status"] == "generated"
    assert verdict["mr_url"] == "https://gitlab/mr/2"
    # bug-fixer statuses stay the default and reject generator verdicts
    assert extract_result_json(text) is None


async def test_autotest_unconfigured(client, store, monkeypatch):
    monkeypatch.setattr(settings, "claude_code_oauth_token", "")
    await _make_test_case(client, store)
    r = await client.post("/projects/p/features/GET __v1__balance/test-cases/0/autotest")
    assert r.status_code == 409
    assert "AUTOTESTS_REPO_DIR" in r.json()["detail"]


async def test_autotest_requires_accepted_case(client, store, generator_configured):
    await _make_test_case(client, store, status="pending")
    r = await client.post("/projects/p/features/GET __v1__balance/test-cases/0/autotest")
    assert r.status_code == 409
    assert "принятому" in r.json()["detail"]


async def test_autotest_requires_confluence_page(client, store, generator_configured):
    await _make_test_case(client, store, with_doc=False)
    r = await client.post("/projects/p/features/GET __v1__balance/test-cases/0/autotest")
    assert r.status_code == 409
    assert "Confluence" in r.json()["detail"]


async def test_autotest_queues_and_rejects_repeat(client, store, generator_configured, monkeypatch):
    started = []

    async def fake_maybe_start(store_, project_slug):
        started.append(project_slug)

    monkeypatch.setattr(autotest_generator, "_maybe_start", fake_maybe_start)

    await _make_test_case(client, store)
    r = await client.post("/projects/p/features/GET __v1__balance/test-cases/0/autotest")
    assert r.status_code == 200
    tc = r.json()["test_cases"][0]
    assert tc["autotest_status"] == "queued"
    assert started == ["p"]

    r = await client.post("/projects/p/features/GET __v1__balance/test-cases/0/autotest")
    assert r.status_code == 409


async def test_accept_auto_queues_autotest(client, store, generator_configured, monkeypatch):
    requested = []

    async def fake_request(store_, project_slug, feature_name, tc_index):
        requested.append((project_slug, feature_name, tc_index))

    monkeypatch.setattr(autotest_generator, "request_generation", fake_request)

    await _make_test_case(client, store, status="pending")
    r = await client.patch(
        "/projects/p/features/GET __v1__balance/test-cases/0",
        json={"status": "approved", "analyst_text": None},
    )
    assert r.status_code == 200
    assert requested == [("p", "GET /v1/balance", 0)]


async def test_accept_reports_unqueueable_autotest(client, store, generator_configured, monkeypatch):
    async def failing_request(store_, project_slug, feature_name, tc_index):
        raise autotest_generator.AutotestError("У фичи нет Confluence-страницы ТЗ")

    monkeypatch.setattr(autotest_generator, "request_generation", failing_request)

    await _make_test_case(client, store, status="pending")
    r = await client.patch(
        "/projects/p/features/GET __v1__balance/test-cases/0",
        json={"status": "approved", "analyst_text": None},
    )
    assert r.status_code == 200
    tc = r.json()["test_cases"][0]
    assert tc["status"] == "approved"
    assert tc["autotest_status"] == "failed"
    assert "Confluence" in tc["autotest_error"]


async def test_reject_does_not_queue(client, store, generator_configured, monkeypatch):
    async def fake_request(store_, project_slug, feature_name, tc_index):
        raise AssertionError("must not be called")

    monkeypatch.setattr(autotest_generator, "request_generation", fake_request)

    await _make_test_case(client, store, status="pending")
    r = await client.patch(
        "/projects/p/features/GET __v1__balance/test-cases/0",
        json={"status": "edited", "analyst_text": "баг"},
    )
    assert r.status_code == 200
