"""Stand-unreachable detection, support contact and Codex limit summaries."""
import socket

import httpx
from openai_codex.generated.v2_all import GetAccountRateLimitsResponse

from app.config import settings
from app.services import assistant_stand, codex_limits, http_runner, sql_runner, stand_network


async def test_sql_connect_failure_is_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "test_db_url", "postgresql://u:p@127.0.0.1:1/db")
    result = await sql_runner.execute_sql("SELECT 1")
    assert result["unreachable"] is True
    assert result["error"].startswith("Не удалось подключиться к тестовой БД: ")
    assert result["error"].removeprefix("Не удалось подключиться к тестовой БД: ").strip()


def test_db_timeout_has_a_readable_reason():
    # asyncpg's connect timeout is a bare TimeoutError with no text
    assert stand_network.describe_db_connect_error(TimeoutError(), 10) == "нет ответа за 10с"
    assert "имя хоста не найдено" in stand_network.describe_db_connect_error(socket.gaierror(8, "nodename"), 10)


async def test_http_connect_failure_is_unreachable():
    result = await http_runner.execute_request("GET", "http://127.0.0.1:1/x", {}, None)
    assert result["unreachable"] is True
    assert result["error"].startswith("Не удалось выполнить запрос")


def test_http_read_timeout_is_not_unreachable():
    request = httpx.Request("GET", "http://stand/x")
    assert not stand_network.http_unreachable(httpx.ReadTimeout("slow", request=request))
    assert stand_network.http_unreachable(httpx.ConnectTimeout("no route", request=request))
    assert stand_network.describe_http_error(httpx.ConnectTimeout("", request=request), 30) == (
        "нет соединения со стендом за 30с"
    )


async def test_assistant_journal_marks_unreachable_stand(monkeypatch):
    monkeypatch.setattr(settings, "test_db_url", "postgresql://u:p@127.0.0.1:1/db")
    stand = assistant_stand.Stand(service="flp-rbo-adapter", write_schemas={"flp_rbo_adapter"})
    entry = await stand.run_sql("SELECT 1", "Проверка", None)
    assert entry["status"] == "error"
    assert entry["unreachable"] is True
    # The agent is told it is not the case's fault
    assert "не ошибка кейса" in assistant_stand.result_for_model(entry)


async def test_assistant_journal_keeps_real_sql_errors_plain(monkeypatch):
    async def fake_execute(sql, readonly=False):
        return {"results": [], "error": "relation x does not exist", "failed_statement": 0, "duration_ms": 1}

    monkeypatch.setattr(settings, "test_db_url", "postgresql://u:p@db/x")
    monkeypatch.setattr(sql_runner, "execute_sql", fake_execute)
    stand = assistant_stand.Stand(service="flp-rbo-adapter", write_schemas={"flp_rbo_adapter"})
    entry = await stand.run_sql("SELECT * FROM x", "Проверка", None)
    assert entry["status"] == "error"
    assert "unreachable" not in entry


SAMPLE = {
    "accountId": "secret-account",
    "ordinaryUsageAllowed": True,
    "rateLimitResetCredits": {"availableCount": 1, "credits": None},
    "rateLimits": {
        "credits": {"balance": "0", "hasCredits": False, "unlimited": False},
        "limitId": "codex",
        "planType": "plus",
        "primary": {"resetsAt": 1794932009, "usedPercent": 28, "windowDurationMins": 300},
        "secondary": {"resetsAt": 1795518809, "usedPercent": 4, "windowDurationMins": 10080},
    },
    "rateLimitsByLimitId": {
        "other": {
            "limitId": "other", "limitName": "GPT-5 mini",
            "primary": {"usedPercent": 100, "windowDurationMins": 300, "resetsAt": 1794932009},
        },
        "codex": {
            "limitId": "codex",
            "primary": {"usedPercent": 28, "windowDurationMins": 300, "resetsAt": 1794932009},
            "secondary": {"usedPercent": 4, "windowDurationMins": 10080, "resetsAt": 1795518809},
        },
    },
}


def test_codex_limits_summary():
    summary = codex_limits.summarize(GetAccountRateLimitsResponse.model_validate(SAMPLE))
    assert "secret-account" not in repr(summary)
    assert summary["plan"] == "plus"
    assert summary["reset_credits"] == 1
    assert [b["id"] for b in summary["limits"]] == ["codex", "other"]
    codex = summary["limits"][0]
    assert codex["reached"] is False
    assert [(w["window_minutes"], w["used_percent"]) for w in codex["windows"]] == [(300, 28), (10080, 4)]
    assert codex["windows"][0]["resets_at"].startswith("2026-11-17T")
    assert summary["limits"][1]["reached"] is True


async def test_codex_limits_failure_is_reported_not_raised(monkeypatch):
    async def broken():
        raise RuntimeError("app-server died")

    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(codex_limits, "_cache", None)
    monkeypatch.setattr(codex_limits, "_read", broken)
    result = await codex_limits.get_limits()
    assert result["available"] is False
    assert result["error"] == "Не удалось получить лимиты Codex"
    # Cached: a second call does not spawn another app-server
    monkeypatch.setattr(codex_limits, "_read", None)
    assert await codex_limits.get_limits() is result
