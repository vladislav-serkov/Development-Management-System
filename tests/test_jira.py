"""Jira export: wiki-markup rendering and the export/sync endpoints."""

import pytest

from app.config import settings
from app.services import jira
from app.services.jira import format_bug_description


BUG = {
    "title": "Дубликат платежа при повторном POST",
    "test_case_name": "Повторный запрос с тем же ключом",
    "severity": "critical",
    "steps": [
        {
            "action": "Отправить POST /payments",
            "result": "201 Created",
            "curl_command": "curl -X POST http://stand/payments",
            "sql_query": "SELECT count(*) FROM flp_order.payment",
            "kafka_message": None,
        },
    ],
    "expected_result": "409 Conflict",
    "actual_result": "201 Created, дубликат",
    "status": "open",
    "analyst_text": "Второй платёж не должен создаваться",
    "created_at": "2026-08-28T00:00:00+00:00",
}

FEATURE = {"name": "Создание платежа", "method": "POST", "endpoint": "/payments", "type": "endpoint"}


@pytest.fixture
def jira_configured(monkeypatch):
    monkeypatch.setattr(settings, "jira_base_url", "https://jira.example")
    monkeypatch.setattr(settings, "jira_pat", "token")


def test_description_renders_wiki_markup():
    text = format_bug_description(BUG, FEATURE, "https://confluence.example/pages/1")
    assert "*Фича:* Создание платежа (POST /payments)" in text
    assert "*Тест-кейс:* Повторный запрос с тем же ключом" in text
    assert "*ТЗ:* [https://confluence.example/pages/1]" in text
    assert "Второй платёж не должен создаваться" in text
    assert "{code:bash}\ncurl -X POST http://stand/payments\n{code}" in text
    assert "{code:sql}" in text
    assert "h3. ОР — ожидаемый результат\n409 Conflict" in text
    assert "h3. ФР — фактический результат\n201 Created, дубликат" in text


def test_description_without_spec_url_and_artifacts():
    bug = {**BUG, "analyst_text": None, "steps": [{"action": "Шаг", "result": ""}]}
    text = format_bug_description(bug, FEATURE, None)
    assert "*ТЗ:*" not in text
    assert "Наблюдение" not in text
    assert "{code" not in text


def test_severity_priority_mapping():
    assert jira.SEVERITY_TO_PRIORITY == {
        "critical": "Blocker", "major": "High", "minor": "Medium", "trivial": "Low",
    }


def test_issue_fields_payload(monkeypatch):
    monkeypatch.setattr(settings, "jira_developer", "VSerkov")
    monkeypatch.setattr(settings, "jira_fix_version", "BNPL Backend 1.0.20")
    fields = jira.build_issue_fields(BUG, FEATURE, None, "flp-order", sprint_id=12905, feature_ticket="mtspay-14684 ")
    assert fields["summary"] == "[flp-order] Дубликат платежа при повторном POST"
    assert fields["issuetype"] == {"name": "Bug"}
    assert fields["priority"] == {"name": "Blocker"}
    assert fields["customfield_10519"] == {"value": "Feature testing"}
    assert fields["customfield_10523"] == [{"value": "UMP"}]
    assert fields["customfield_20600"] == [{"value": "Flex core"}]
    assert fields["customfield_10402"] == [{"name": "VSerkov"}]
    assert fields["fixVersions"] == [{"name": "BNPL Backend 1.0.20"}]
    assert fields["customfield_10108"] == 12905
    assert fields["customfield_10107"] == "MTSPAY-14684"


def test_issue_fields_keeps_existing_bracket_prefix(monkeypatch):
    bug = {**BUG, "title": "[bnpl-payment] Уже с префиксом"}
    fields = jira.build_issue_fields(bug, FEATURE, None, "flp-order")
    assert fields["summary"] == "[bnpl-payment] Уже с префиксом"
    # Empty custom-field settings omit the fields entirely
    monkeypatch.setattr(settings, "jira_bug_type", "")
    monkeypatch.setattr(settings, "jira_system", "")
    monkeypatch.setattr(settings, "jira_team", "")
    monkeypatch.setattr(settings, "jira_developer", "")
    monkeypatch.setattr(settings, "jira_fix_version", "")
    fields = jira.build_issue_fields(bug, FEATURE, None, None)
    assert "customfield_10519" not in fields
    assert "customfield_10523" not in fields
    assert "customfield_20600" not in fields
    # Optional per-team fields default to empty settings → omitted; no sprint → omitted
    assert "customfield_10402" not in fields
    assert "fixVersions" not in fields
    assert "customfield_10108" not in fields
    assert "customfield_10107" not in fields


async def _make_bug(client, store, *, with_jira_key=False):
    await client.post("/projects/", json={"name": "P"})
    await store.save_feature("p", {"name": "f1", "type": "endpoint", "status": "done"})
    bug = dict(BUG)
    if with_jira_key:
        bug.update(jira_key="MTSPAY-1", jira_url="https://jira.example/browse/MTSPAY-1")
    await store.save_bugs("p", "f1", [bug])


async def test_export_unconfigured_returns_503(client, store, monkeypatch):
    monkeypatch.setattr(settings, "jira_base_url", "")
    await _make_bug(client, store)
    r = await client.post("/projects/p/features/f1/bugs/0/export-jira")
    assert r.status_code == 503


async def test_export_sets_key_and_rejects_repeat(client, store, jira_configured, monkeypatch):
    async def fake_create(bug, feature, spec_url, service_name=None, feature_ticket=None):
        assert feature["name"] == "f1"
        assert feature_ticket == "MTSPAY-14684"
        return {"key": "MTSPAY-42", "url": "https://jira.example/browse/MTSPAY-42"}

    monkeypatch.setattr(jira, "create_bug_issue", fake_create)
    await _make_bug(client, store)

    r = await client.post(
        "/projects/p/features/f1/bugs/0/export-jira",
        json={"feature_ticket": "MTSPAY-14684"},
    )
    assert r.status_code == 200
    bug = r.json()["bugs"][0]
    assert bug["jira_key"] == "MTSPAY-42"
    assert bug["jira_url"] == "https://jira.example/browse/MTSPAY-42"

    r = await client.post("/projects/p/features/f1/bugs/0/export-jira")
    assert r.status_code == 409

    r = await client.get("/projects/p/features/f1/bugs/")
    assert r.json()["jira_configured"] is True
    assert r.json()["bugs"][0]["jira_key"] == "MTSPAY-42"


async def test_export_jira_error_returns_502(client, store, jira_configured, monkeypatch):
    async def fake_create(bug, feature, spec_url, service_name=None, feature_ticket=None):
        raise jira.JiraError("Jira отклонила токен (401)")

    monkeypatch.setattr(jira, "create_bug_issue", fake_create)
    await _make_bug(client, store)
    r = await client.post("/projects/p/features/f1/bugs/0/export-jira")
    assert r.status_code == 502
    assert "401" in r.json()["detail"]


async def test_sync_updates_status(client, store, jira_configured, monkeypatch):
    async def fake_statuses(keys):
        assert keys == ["MTSPAY-1"]
        return {"MTSPAY-1": "In Development"}

    monkeypatch.setattr(jira, "fetch_issue_statuses", fake_statuses)
    await _make_bug(client, store, with_jira_key=True)

    r = await client.post("/projects/p/features/f1/bugs/sync-jira")
    assert r.status_code == 200
    assert r.json()["synced"] is True
    assert r.json()["bugs"][0]["jira_status"] == "In Development"

    # Persisted, not just echoed
    bugs = await store.get_bugs("p", "f1")
    assert bugs[0]["jira_status"] == "In Development"


async def test_sync_without_exported_bugs_is_noop(client, store, jira_configured):
    await _make_bug(client, store)
    r = await client.post("/projects/p/features/f1/bugs/sync-jira")
    assert r.status_code == 200
    assert r.json()["synced"] is False
