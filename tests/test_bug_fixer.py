"""Bug fixer: repo resolution, prompt/verdict parsing, queueing endpoint."""

import pytest

from app.config import settings
from app.services import bug_fixer
from app.services.bug_fixer import build_prompt, extract_result_json, resolve_repo

from tests.test_jira import BUG, FEATURE, _make_bug


@pytest.fixture
def fixer_configured(monkeypatch):
    monkeypatch.setattr(settings, "claude_code_oauth_token", "sk-ant-oat01-test")


def test_resolve_repo_searches_roots(tmp_path, monkeypatch):
    (tmp_path / "flp" / "flp-order" / ".git").mkdir(parents=True)
    (tmp_path / "bnpl-payment" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "repos_dirs", f"{tmp_path}:{tmp_path}/flp")

    assert resolve_repo("flp-order") == tmp_path / "flp" / "flp-order"
    assert resolve_repo("bnpl-payment") == tmp_path / "bnpl-payment"
    assert resolve_repo("unknown-svc") is None
    assert resolve_repo(None) is None


def test_prompt_carries_ticket_flow_and_contract():
    bug = {**BUG, "jira_key": "MTSPAY-100", "jira_url": "https://jira.example/browse/MTSPAY-100"}
    prompt = build_prompt(bug, FEATURE, "https://confluence.example/pages/1")
    assert "MTSPAY-100" in prompt
    assert "CLAUDE.md" in prompt
    assert "регрессионный тест" in prompt
    assert "https://confluence.example/pages/1" in prompt
    assert "curl -X POST http://stand/payments" in prompt
    assert '"fix_proposed" | "failed"' in prompt


def test_extract_result_json_takes_trailing_verdict():
    text = (
        'Сделал. Промежуточный объект: {"status": "wip"}\n'
        'Итог:\n{"status": "fix_proposed", "branch": "feature/MTSPAY-100-fix", '
        '"mr_url": "https://gitlab/mr/1", "summary": "починил", "reason": null}'
    )
    verdict = extract_result_json(text)
    assert verdict["status"] == "fix_proposed"
    assert verdict["mr_url"] == "https://gitlab/mr/1"

    assert extract_result_json("никакого json тут нет") is None
    assert extract_result_json('{"status": "что-то другое"}') is None


async def test_fix_requires_jira_key(client, store, fixer_configured):
    await _make_bug(client, store)  # bug without jira_key
    r = await client.post("/projects/p/features/f1/bugs/0/fix")
    assert r.status_code == 409
    assert "Jira" in r.json()["detail"]


async def test_fix_unconfigured(client, store, monkeypatch):
    monkeypatch.setattr(settings, "claude_code_oauth_token", "")
    await _make_bug(client, store, with_jira_key=True)
    r = await client.post("/projects/p/features/f1/bugs/0/fix")
    assert r.status_code == 409
    assert "CLAUDE_CODE_OAUTH_TOKEN" in r.json()["detail"]


async def test_fix_queues_and_rejects_repeat(client, store, fixer_configured, monkeypatch, tmp_path):
    (tmp_path / "flp-order" / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "repos_dirs", str(tmp_path))

    started = []

    async def fake_maybe_start(store_, project_slug, service):
        started.append(service)

    monkeypatch.setattr(bug_fixer, "_maybe_start", fake_maybe_start)

    await _make_bug(client, store, with_jira_key=True)
    # Feature needs a source document that names the service
    await store.save_document("p", {
        "slug": "doc1", "project_slug": "p", "filename": "spec",
        "service_name": "flp-order", "confluence_url": "https://confluence.example/pages/1",
        "status": "ready", "uploaded_at": "2026-08-28T00:00:00+00:00",
    })
    feature = await store.get_feature("p", "f1")
    feature["source_document"] = "doc1"
    await store.save_feature("p", feature)

    r = await client.post("/projects/p/features/f1/bugs/0/fix")
    assert r.status_code == 200
    bug = r.json()["bugs"][0]
    assert bug["fix_status"] == "queued"
    assert bug["fix_service"] == "flp-order"
    assert started == ["flp-order"]

    r = await client.post("/projects/p/features/f1/bugs/0/fix")
    assert r.status_code == 409


async def test_export_auto_queues_fix(client, store, monkeypatch, fixer_configured):
    from app.services import jira

    async def fake_create(bug, feature, spec_url, service_name=None, feature_ticket=None):
        return {"key": "MTSPAY-42", "url": "https://jira.example/browse/MTSPAY-42"}

    requested = []

    async def fake_request_fix(store_, project_slug, feature_name, bug_index):
        requested.append((project_slug, feature_name, bug_index))

    monkeypatch.setattr(settings, "jira_base_url", "https://jira.example")
    monkeypatch.setattr(settings, "jira_pat", "token")
    monkeypatch.setattr(jira, "create_bug_issue", fake_create)
    monkeypatch.setattr(bug_fixer, "request_fix", fake_request_fix)

    await _make_bug(client, store)
    r = await client.post("/projects/p/features/f1/bugs/0/export-jira", json={})
    assert r.status_code == 200
    assert requested == [("p", "f1", 0)]


async def test_export_reports_unqueueable_fix(client, store, monkeypatch, fixer_configured):
    from app.services import jira

    async def fake_create(bug, feature, spec_url, service_name=None, feature_ticket=None):
        return {"key": "MTSPAY-43", "url": "https://jira.example/browse/MTSPAY-43"}

    async def failing_request_fix(store_, project_slug, feature_name, bug_index):
        raise bug_fixer.BugFixerError("Репозиторий сервиса не найден")

    monkeypatch.setattr(settings, "jira_base_url", "https://jira.example")
    monkeypatch.setattr(settings, "jira_pat", "token")
    monkeypatch.setattr(jira, "create_bug_issue", fake_create)
    monkeypatch.setattr(bug_fixer, "request_fix", failing_request_fix)

    await _make_bug(client, store)
    r = await client.post("/projects/p/features/f1/bugs/0/export-jira", json={})
    assert r.status_code == 200
    bug = r.json()["bugs"][0]
    assert bug["jira_key"] == "MTSPAY-43"
    assert bug["fix_status"] == "failed"
    assert "Репозиторий" in bug["fix_error"]
