"""Codex SDK protocol, subscription auth, output validation and job lifecycle."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai_codex import ApprovalMode, Sandbox
from openai_codex.models import Notification, UnknownNotification
from pydantic import BaseModel

from app.config import settings
from app.services import agent_runner

VERDICT = {
    "status": "fix_proposed", "branch": "fix/bug", "mr_url": "https://gitlab.example/mr/1",
    "summary": "Исправлено", "reason": None,
}


class Payload(BaseModel):
    item: dict | None = None
    turn: dict | None = None


def completed_events(text, *, status="completed", error=None):
    return [
        Notification("item/completed", Payload(item={
            "type": "agentMessage", "phase": "final_answer", "text": text,
        })),
        Notification("turn/completed", Payload(turn={"status": status, "error": error})),
    ]


class FakeTurn:
    def __init__(self, events):
        self.events = events
        self.interrupt = AsyncMock()

    async def stream(self):
        for event in self.events:
            yield event


@pytest.fixture
def sdk(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    thread = SimpleNamespace(id="thread-1", turn=AsyncMock())
    client = SimpleNamespace(
        account=AsyncMock(return_value=SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type="chatgpt")))),
        models=AsyncMock(return_value=SimpleNamespace(data=[
            SimpleNamespace(model="available-default", hidden=False, is_default=True),
        ])),
        thread_start=AsyncMock(return_value=thread), close=AsyncMock(),
    )
    configs = []

    def create(config):
        configs.append(config)
        return client

    monkeypatch.setattr(agent_runner, "AsyncCodex", create)
    monkeypatch.setattr(agent_runner, "_run_lock", asyncio.Lock())
    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(settings, "codex_model", "")
    monkeypatch.setattr(settings, "codex_cli", "")
    monkeypatch.setattr(settings, "bug_fix_timeout_seconds", 30)
    thread.turn.return_value = FakeTurn(completed_events(json.dumps(VERDICT)))
    return SimpleNamespace(client=client, thread=thread, configs=configs, repo=repo, log=tmp_path / "job.jsonl")


async def test_subscription_run_uses_schema_and_logs_stream(sdk):
    assert await agent_runner.run("исправь баг", sdk.repo, sdk.log) == VERDICT
    config = sdk.configs[0]
    assert config.env["CODEX_API_KEY"] == config.env["OPENAI_API_KEY"] == ""
    assert config.codex_bin is None
    kwargs = sdk.client.thread_start.call_args.kwargs
    assert kwargs["sandbox"] == Sandbox.workspace_write
    assert kwargs["approval_mode"] == ApprovalMode.auto_review
    assert kwargs["model_provider"] == "openai"
    assert kwargs["model"] == "available-default"
    assert "claude-context.py" in kwargs["developer_instructions"]
    schema = sdk.thread.turn.call_args.kwargs["output_schema"]
    assert schema["properties"]["status"]["enum"] == ["fix_proposed", "failed"]
    assert schema["additionalProperties"] is False
    events = [json.loads(line) for line in sdk.log.read_text().splitlines()]
    assert [event["method"] for event in events] == ["thread.started", "item/completed", "turn/completed"]
    assert sdk.log.stat().st_mode & 0o777 == 0o600
    sdk.client.close.assert_awaited_once()


@pytest.mark.parametrize("auth", [None, "apiKey", "amazonBedrock"])
async def test_no_fallback_to_api_billing(sdk, auth):
    sdk.client.account.return_value.account = None if auth is None else SimpleNamespace(root=SimpleNamespace(type=auth))
    with pytest.raises(agent_runner.AgentError, match="codex login"):
        await agent_runner.run("task", sdk.repo, sdk.log)
    sdk.client.thread_start.assert_not_awaited()
    sdk.client.close.assert_awaited_once()


async def test_explicit_model_and_cli_are_preserved(sdk, monkeypatch):
    monkeypatch.setattr(settings, "codex_model", "explicit-model")
    monkeypatch.setattr(settings, "codex_cli", "/custom/codex")
    await agent_runner.run("task", sdk.repo, sdk.log)
    assert sdk.configs[0].codex_bin == "/custom/codex"
    assert sdk.client.thread_start.call_args.kwargs["model"] == "explicit-model"
    sdk.client.models.assert_not_awaited()


async def test_repairs_invalid_json_once_in_the_same_thread(sdk):
    sdk.thread.turn.side_effect = [
        FakeTurn(completed_events("нет JSON")),
        FakeTurn(completed_events(json.dumps(VERDICT))),
    ]
    assert await agent_runner.run("task", sdk.repo, sdk.log) == VERDICT
    sdk.client.thread_start.assert_awaited_once()
    assert sdk.thread.turn.await_count == 2
    assert "Не повторяй" in sdk.thread.turn.call_args.args[0]


async def test_invalid_verdict_does_not_loop(sdk):
    sdk.thread.turn.return_value = FakeTurn(completed_events(json.dumps({**VERDICT, "status": "unknown"})))
    with pytest.raises(agent_runner.AgentError, match="корректный итоговый JSON"):
        await agent_runner.run("task", sdk.repo, sdk.log)
    assert sdk.thread.turn.await_count == 2


async def test_unknown_notifications_do_not_break_stream(sdk):
    sdk.thread.turn.return_value.events.insert(0, Notification(
        "future/progress", UnknownNotification(params={"progress": "running"}),
    ))
    assert await agent_runner.run("task", sdk.repo, sdk.log) == VERDICT
    assert "future/progress" in sdk.log.read_text()


async def test_success_without_mr_is_not_reported_as_complete(sdk):
    sdk.thread.turn.return_value = FakeTurn(completed_events(json.dumps({**VERDICT, "mr_url": None})))
    with pytest.raises(agent_runner.AgentError, match="корректный итоговый JSON"):
        await agent_runner.run("task", sdk.repo, sdk.log)


@pytest.mark.parametrize("status", ["failed", "interrupted"])
async def test_failed_or_interrupted_turn_never_retries(sdk, status):
    sdk.thread.turn.return_value = FakeTurn(completed_events(
        json.dumps(VERDICT), status=status, error={"message": "Usage limit reached"},
    ))
    with pytest.raises(agent_runner.AgentError, match="Usage limit reached"):
        await agent_runner.run("task", sdk.repo, sdk.log)
    assert sdk.thread.turn.await_count == 1
    sdk.client.close.assert_awaited_once()


async def test_timeout_interrupts_active_tools_and_closes_runtime(sdk, monkeypatch):
    turn = FakeTurn([])

    async def waiting():
        await asyncio.Event().wait()
        yield  # make this an async generator

    turn.stream = waiting
    sdk.thread.turn.return_value = turn
    monkeypatch.setattr(settings, "bug_fix_timeout_seconds", 0.02)
    with pytest.raises(agent_runner.AgentError, match="таймаут"):
        await agent_runner.run("task", sdk.repo, sdk.log)
    turn.interrupt.assert_awaited_once()
    sdk.client.close.assert_awaited_once()


async def test_cancellation_interrupts_active_tools(sdk):
    started = asyncio.Event()
    turn = FakeTurn([])

    async def waiting():
        started.set()
        await asyncio.Event().wait()
        yield

    turn.stream = waiting
    sdk.thread.turn.return_value = turn
    task = asyncio.create_task(agent_runner.run("task", sdk.repo, sdk.log))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    turn.interrupt.assert_awaited_once()
    sdk.client.close.assert_awaited_once()


async def test_process_serializes_jobs_across_workflows(sdk):
    started = asyncio.Event()
    release = asyncio.Event()
    turn = FakeTurn([])

    async def waiting():
        started.set()
        await release.wait()
        for event in completed_events(json.dumps(VERDICT)):
            yield event

    turn.stream = waiting
    sdk.thread.turn.return_value = turn
    first = asyncio.create_task(agent_runner.run("bug", sdk.repo, sdk.log))
    await started.wait()
    second = asyncio.create_task(agent_runner.run("autotest", sdk.repo, sdk.log.with_name("other.jsonl")))
    await asyncio.sleep(0)
    assert len(sdk.configs) == 1
    release.set()
    await asyncio.gather(first, second)
    assert len(sdk.configs) == 2


async def test_disabled_or_missing_repo_does_not_start_sdk(sdk, monkeypatch):
    monkeypatch.setattr(settings, "codex_enabled", False)
    with pytest.raises(agent_runner.AgentError, match="CODEX_ENABLED"):
        await agent_runner.run("task", sdk.repo, sdk.log)
    monkeypatch.setattr(settings, "codex_enabled", True)
    with pytest.raises(agent_runner.AgentError, match="Репозиторий"):
        await agent_runner.run("task", None, sdk.log)
    assert sdk.configs == []


@pytest.mark.parametrize("status", ["generated", "implemented", "no_changes_needed", "failed"])
async def test_workflow_specific_verdicts(sdk, status):
    result = {**VERDICT, "status": status, "reason": "Нужно решение пользователя" if status == "failed" else None}
    sdk.thread.turn.return_value = FakeTurn(completed_events(json.dumps(result)))
    assert await agent_runner.run("task", sdk.repo, sdk.log, statuses=(status,)) == result
