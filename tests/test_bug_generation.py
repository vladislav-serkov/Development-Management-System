"""Codex report jobs return immediately and preserve stored review state."""

from unittest.mock import AsyncMock

import pytest

from app.routers import bugs


@pytest.fixture
async def queued(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", {"name": "f", "status": "done"})
    await store.save_test_cases("p", "f", [{"name": "case", "status": "pending"}])
    monkeypatch.setattr(bugs, "store", store)
    jobs = []
    monkeypatch.setattr(bugs.task_manager, "launch", lambda key, coro: jobs.append(coro) or True)
    monkeypatch.setattr(bugs.task_manager, "is_running", lambda key: bool(jobs))
    yield jobs
    for coro in jobs:
        coro.close()


async def test_queue_success_marks_case_only_after_report_is_saved(client, store, monkeypatch, queued):
    report = {"title": "bug", "tc_index": 0, "test_case_name": "case", "analyst_text": "HTTP 500"}
    generate = AsyncMock(return_value=report)
    monkeypatch.setattr(bugs, "generate_bug_report", generate)
    response = await client.post("/projects/p/features/f/bugs/generate", json={"tc_index": 0})
    assert response.json() == {"status": "started"}
    generate.assert_not_awaited()
    assert (await store.get_test_cases("p", "f"))[0]["status"] == "pending"
    assert (await client.get("/projects/p/features/f/bugs/")).json()["bugs_running"]
    duplicate = await client.post("/projects/p/features/f/bugs/generate", json={"tc_index": 0})
    assert duplicate.json() == {"status": "already_running"}
    await store.save_bugs("p", "f", [{"title": "existing", "status": "verified"}])
    await queued.pop()
    assert [bug["title"] for bug in await store.get_bugs("p", "f")] == ["existing", "bug"]
    assert (await store.get_test_cases("p", "f"))[0]["status"] == "edited"
    assert (await store.get_feature("p", "f"))["pending_test_case_count"] == 0
    task = (await store.list_tasks("p", kind="bugs"))[0]
    assert task["status"] == "done"


async def test_failure_is_visible_and_keeps_case_pending(client, store, monkeypatch, queued):
    monkeypatch.setattr(bugs, "generate_bug_report", AsyncMock(side_effect=RuntimeError("Usage limit reached")))
    await client.post("/projects/p/features/f/bugs/generate", json={"tc_index": 0})
    await queued.pop()
    response = (await client.get("/projects/p/features/f/bugs/")).json()
    assert response["generation_error"] == "Usage limit reached"
    assert not response["bugs_running"]
    assert response["bugs"] == []
    assert (await store.get_test_cases("p", "f"))[0]["status"] == "pending"


async def test_invalid_case_is_rejected_before_enqueue(client, queued):
    response = await client.post("/projects/p/features/f/bugs/generate", json={"tc_index": 8})
    assert response.status_code == 404
    assert not queued


async def test_server_restart_surfaces_interrupted_generation(client, store, queued):
    task = await store.create_task("p", kind="bugs", target_type="feature", target_id="f")
    response = (await client.get("/projects/p/features/f/bugs/")).json()
    assert response["bugs_running"] is False
    assert "Server restarted" in response["generation_error"]
    assert (await store.list_tasks("p", kind="bugs"))[0]["id"] == task["id"]
    assert (await store.list_tasks("p", kind="bugs"))[0]["status"] == "error"
