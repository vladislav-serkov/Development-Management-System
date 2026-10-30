"""All coding workflows persist Codex outcomes without invoking external agents."""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services import agent_runner, autotest_generator, bug_fixer, feature_implementer
from tests.test_autotest_generator import DOC, FEATURE, TEST_CASE
from tests.test_jira import BUG


@pytest.fixture
async def workflow_data(store, monkeypatch, tmp_path):
    repo = tmp_path / "flp-card-balance"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(settings, "codex_enabled", True)
    monkeypatch.setattr(settings, "repos_dirs", str(tmp_path))
    monkeypatch.setattr(settings, "autotests_repo_dir", str(repo))
    monkeypatch.setattr(settings, "bug_fix_log_dir", str(tmp_path / "bug-logs"))
    monkeypatch.setattr(settings, "autotest_log_dir", str(tmp_path / "test-logs"))
    monkeypatch.setattr(settings, "implement_log_dir", str(tmp_path / "impl-logs"))
    await store.create_project("P")
    await store.save_document("p", dict(DOC))
    feature = {**FEATURE, "impl_jira_key": "TEST-1"}
    await store.save_feature("p", feature)
    await store.save_bugs("p", FEATURE["name"], [{**BUG, "jira_key": "TEST-2"}])
    await store.save_test_cases("p", FEATURE["name"], [dict(TEST_CASE)])
    return feature, repo


@pytest.mark.parametrize("workflow,prefix,status", [
    ("bug", "fix", "fix_proposed"),
    ("autotest", "autotest", "generated"),
    ("feature", "impl", "implemented"),
])
@pytest.mark.parametrize("failed", [False, True])
async def test_workflows_persist_sdk_result_or_failure(store, workflow_data, monkeypatch, workflow, prefix, status, failed):
    feature, repo = workflow_data
    verdict = {
        "status": status, "branch": "fix/test", "mr_url": "https://gitlab.example/mr/1",
        "summary": "Сделано", "reason": None,
    }
    runner = AsyncMock(return_value=verdict)
    if failed:
        runner.side_effect = agent_runner.AgentError("Нужно включить VPN")
    monkeypatch.setattr(agent_runner, "run", runner)

    if workflow == "bug":
        bug = (await store.get_bugs("p", FEATURE["name"]))[0]
        await bug_fixer._fix_one(store, "p", FEATURE["name"], 0, bug, feature, DOC["service_name"])
        result = (await store.get_bugs("p", FEATURE["name"]))[0]
    elif workflow == "autotest":
        await autotest_generator._generate_one(store, "p", FEATURE["name"], 0, TEST_CASE, feature)
        result = (await store.get_test_cases("p", FEATURE["name"]))[0]
    else:
        await feature_implementer._implement_one(store, "p", FEATURE["name"], feature, DOC["service_name"])
        result = await store.get_feature("p", FEATURE["name"])

    assert runner.call_args.args[1] == repo
    assert result[f"{prefix}_status"] == ("failed" if failed else status)
    assert result[f"{prefix}_started_at"]
    assert result[f"{prefix}_finished_at"]
    if failed:
        assert result[f"{prefix}_error"] == "Нужно включить VPN"
    else:
        assert result[f"{prefix}_mr_url"] == verdict["mr_url"]
        assert result[f"{prefix}_branch"] == verdict["branch"]
        assert result[f"{prefix}_summary"] == verdict["summary"]


async def test_feature_implementation_queue_uses_codex_gate(store, workflow_data, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(feature_implementer, "_maybe_start", start)
    result = await feature_implementer.request_implementation(store, "p", FEATURE["name"], "test-1")
    assert result["impl_status"] == "queued"
    assert result["impl_jira_key"] == "TEST-1"
    start.assert_awaited_once()
    monkeypatch.setattr(settings, "codex_enabled", False)
    with pytest.raises(feature_implementer.ImplementError, match="CODEX_ENABLED"):
        await feature_implementer.request_implementation(store, "p", FEATURE["name"], "TEST-1")


def test_implementation_prompt_uses_migrated_workflow():
    prompt = feature_implementer.build_prompt("TEST-1", FEATURE, DOC)
    assert "AGENTS.md" in prompt
    assert "take-task" in prompt
    assert "CLAUDE.md" not in prompt
    assert DOC["confluence_url"] in prompt
