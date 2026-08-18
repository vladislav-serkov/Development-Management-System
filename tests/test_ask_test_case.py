"""Tests for the on-demand test case ask pipeline (tester asks for a case on a spec item)."""
from types import SimpleNamespace

import app.services.test_cases as tc_mod
from app.services.test_cases import run_test_case_ask_pipeline

FEATURE = {
    "name": "create-order",
    "type": "rest_endpoint",
    "status": "done",
    "structured_logic_json": {"used_dependencies": [], "logic_steps": []},
}

CASE = {
    "name": "Валидация amount — отсутствует",
    "category": "validation",
    "preconditions": "Нет записей для тестируемого заказа",
    "steps": [{"action": "POST /v1/orders без amount", "expected": "HTTP 400"}],
    "expected_result": "Запрос отклонён. Бизнес-логика не выполнялась.",
    "priority": "high",
    "covers": "валидация amount",
}


def _mock_claude(monkeypatch, tool_input):
    """Point the service at a fake call_claude; returns the list of captured kwargs."""
    calls = []

    async def fake_call_claude(*, label="", **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=tool_input)],
            usage=SimpleNamespace(),
            stop_reason="tool_use",
        )

    monkeypatch.setattr(tc_mod, "call_claude", fake_call_claude)
    return calls


async def test_ask_adds_pending_case_and_finishes_task(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    calls = _mock_claude(monkeypatch, {"test_cases": [CASE], "comment": "Кейс на валидацию amount"})

    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")
    result = await run_test_case_ask_pipeline(
        "p", "create-order", "нужен кейс на валидацию amount", store, task_id=task["id"],
    )

    assert len(result["added"]) == 1
    saved = await store.get_test_cases("p", "create-order")
    assert len(saved) == 1
    assert saved[0]["status"] == "pending"
    assert saved[0]["covers"] == "валидация amount"
    assert saved[0]["analyst_text"] is None
    assert saved[0]["origin"] == "ask"

    tasks = await store.list_tasks("p", kind="test_cases")
    assert tasks[0]["status"] == "done"
    assert tasks[0]["result_message"] == "Добавлено кейсов: 1. Кейс на валидацию amount"

    # counts updated by save_test_cases
    feat = await store.get_feature("p", "create-order")
    assert feat["test_case_count"] == 1
    assert feat["pending_test_case_count"] == 1

    # the tester's request and the existing-cases block reached the prompt
    blocks = calls[0]["messages"][0]["content"]
    texts = [b["text"] for b in blocks]
    assert any("Запрос тестировщика" in t and "валидацию amount" in t for t in texts)
    assert any("Существующих тест-кейсов нет" in t for t in texts)


async def test_ask_already_covered_adds_nothing(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    existing = dict(CASE, status="approved", analyst_text=None)
    await store.save_test_cases("p", "create-order", [existing])
    _mock_claude(monkeypatch, {
        "test_cases": [],
        "comment": "Пункт уже покрыт существующим кейсом",
        # one real ref + one hallucinated — the latter must be dropped
        "covered_by": [CASE["name"], "Несуществующий кейс"],
    })

    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")
    result = await run_test_case_ask_pipeline(
        "p", "create-order", "кейс на валидацию amount", store, task_id=task["id"],
    )

    assert result["added"] == []
    assert result["covered_by"] == [CASE["name"]]
    assert len(await store.get_test_cases("p", "create-order")) == 1
    tasks = await store.list_tasks("p", kind="test_cases")
    assert tasks[0]["status"] == "done"
    assert "уже покрыт" in tasks[0]["result_message"]
    assert tasks[0]["result_data"] == {"covered_by": [CASE["name"]]}


async def test_ask_dedupes_against_existing(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    existing = dict(CASE, status="approved", analyst_text=None)
    await store.save_test_cases("p", "create-order", [existing])
    # Model ignores instructions and regenerates the same case — must not duplicate
    _mock_claude(monkeypatch, {"test_cases": [CASE], "comment": None})

    result = await run_test_case_ask_pipeline("p", "create-order", "кейс на валидацию amount", store)

    assert result["added"] == []
    assert len(await store.get_test_cases("p", "create-order")) == 1
    assert "не добавлены" in result["message"]


async def test_ask_failure_marks_task_error(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))

    async def boom(*, label="", **kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(tc_mod, "call_claude", boom)
    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")

    try:
        await run_test_case_ask_pipeline("p", "create-order", "кейс на что-нибудь", store, task_id=task["id"])
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    tasks = await store.list_tasks("p", kind="test_cases")
    assert tasks[0]["status"] == "error"
    assert "api down" in tasks[0]["error_message"]


# ---------------------------------------------------------------- API layer

async def test_ask_endpoint_404_on_missing_feature(client):
    resp = await client.post(
        "/projects/nope/features/ghost/test-cases/ask", json={"request": "кейс на пункт 1"},
    )
    assert resp.status_code == 404


async def test_list_returns_last_ask_message(store, client):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")
    await store.finish_task(
        "p", task["id"], status="done", result_message="Пункт уже покрыт.",
        result_data={"covered_by": ["Кейс А"]},
    )

    resp = await client.get("/projects/p/features/create-order/test-cases/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["test_cases_running"] is False
    assert body["last_ask_message"] == "Пункт уже покрыт."
    assert body["last_ask_at"] is not None
    assert body["last_ask_covered_by"] == ["Кейс А"]
