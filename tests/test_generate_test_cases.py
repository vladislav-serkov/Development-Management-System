"""Tests for test-case generation: one Codex thread — coverage, cases, repair."""
import pytest

from app.services import agent_runner
from app.services import test_cases as tc_service
from app.services.test_cases import run_test_cases_pipeline

FEATURE = {
    "name": "create-order",
    "type": "rest_endpoint",
    "status": "done",
    "structured_logic_json": {"used_dependencies": [], "logic_steps": []},
}

COVERAGE = {"coverage": [
    {"covers": "валидация amount: поле обязательно", "category": "validation", "priority": "high"},
    {"covers": "logic_steps 1: заказ создаётся", "category": "positive", "priority": "medium"},
]}


def _case(item: int, name: str, **extra) -> dict:
    return {
        "item": item,
        "name": name,
        "preconditions": "Нет записей для тестируемого заказа",
        "steps": [{"action": "POST /v1/orders", "expected": "HTTP 400"}],
        "expected_result": "Запрос отклонён. Бизнес-логика не выполнялась.",
        "curl_command": "curl -X POST http://localhost:8080/v1/orders",
        **extra,
    }


def _mock_codex(monkeypatch, *answers):
    """Fake the Codex thread: each turn pops the next answer; returns the captured turns."""
    turns = []
    queue = list(answers)

    async def analyze(workspace, log_path, execute, on_started, **options):
        async def ask(prompt, schema):
            turns.append({"kind": options.get("kind"), "schema": schema.__name__, "text": prompt})
            return queue.pop(0)
        return await execute(ask)

    monkeypatch.setattr(agent_runner, "analyze", analyze)
    return turns


async def test_generation_runs_in_one_thread(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    turns = _mock_codex(monkeypatch, COVERAGE, {"test_cases": [
        _case(1, "Валидация amount — отсутствует"), _case(2, "Успешное создание заказа"),
    ]})

    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")
    result = await run_test_cases_pipeline("p", "create-order", store, task_id=task["id"])

    # coverage turn carries the feature context once; the cases turn only the request
    assert [t["schema"] for t in turns] == ["TestCaseCoverageResult", "TestCaseGenerationResult"]
    assert "## Feature" in turns[0]["text"] and "Составь перечень проверок" in turns[0]["text"]
    assert "## Feature" not in turns[1]["text"] and "с 1 по 2" in turns[1]["text"]

    # classification and the spec reference come from the coverage item, not from the case turn
    assert [(tc["name"], tc["category"], tc["priority"], tc["covers"]) for tc in result] == [
        ("Валидация amount — отсутствует", "validation", "high", "валидация amount: поле обязательно"),
        ("Успешное создание заказа", "positive", "medium", "logic_steps 1: заказ создаётся"),
    ]
    saved = await store.get_test_cases("p", "create-order")
    assert all(tc["status"] == "pending" and tc["analyst_text"] is None for tc in saved)
    assert all("origin" not in tc and "item" not in tc for tc in saved)

    tasks = await store.list_tasks("p", kind="test_cases")
    assert tasks[0]["status"] == "done"
    feat = await store.get_feature("p", "create-order")
    assert feat["test_case_count"] == 2
    assert feat["pending_test_case_count"] == 2


async def test_big_coverage_is_written_in_portions(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    monkeypatch.setattr(tc_service, "CASES_PER_TURN", 2)
    coverage = {"coverage": [
        {"covers": f"logic_steps {n}", "category": "positive", "priority": "low"} for n in (1, 2, 3)
    ]}
    turns = _mock_codex(
        monkeypatch, coverage,
        # an item outside the requested portion is ignored
        {"test_cases": [_case(1, "Кейс 1"), _case(2, "Кейс 2"), _case(3, "Чужой")]},
        {"test_cases": [_case(3, "Кейс 3")]},
    )

    result = await run_test_cases_pipeline("p", "create-order", store)

    assert [tc["name"] for tc in result] == ["Кейс 1", "Кейс 2", "Кейс 3"]
    assert ["с 1 по 2" in turns[1]["text"], "с 3 по 3" in turns[2]["text"]] == [True, True]


async def test_failed_and_missing_cases_get_one_repair_turn(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    turns = _mock_codex(
        monkeypatch, COVERAGE,
        # item 1 has no curl (REST feature), item 2 is not written at all
        {"test_cases": [_case(1, "Валидация amount — отсутствует", curl_command=None)]},
        {"test_cases": [_case(1, "Валидация amount — отсутствует"), _case(2, "Успешное создание заказа")]},
    )

    result = await run_test_cases_pipeline("p", "create-order", store)

    assert len(turns) == 3
    repair = turns[2]["text"]
    assert "Пункт 1, кейс «Валидация amount — отсутствует»" in repair and "нет curl_command" in repair
    assert "Пункт 2 «logic_steps 1: заказ создаётся»: кейс не написан" in repair
    assert [(tc["name"], bool(tc["curl_command"])) for tc in result] == [
        ("Валидация amount — отсутствует", True), ("Успешное создание заказа", True),
    ]


async def test_unrepaired_case_is_kept(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    broken = _case(1, "Кейс с плохим моком", mock_config="{not json")
    turns = _mock_codex(
        monkeypatch, {"coverage": COVERAGE["coverage"][:1]}, {"test_cases": [broken]}, {"test_cases": [broken]},
    )

    result = await run_test_cases_pipeline("p", "create-order", store)

    # one repair attempt only; the tester still gets the case
    assert len(turns) == 3
    assert [tc["name"] for tc in result] == ["Кейс с плохим моком"]


async def test_regeneration_keeps_reviewed_cases(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    kept = {
        "name": "Валидация amount — отсутствует", "category": "validation", "priority": "high",
        "preconditions": "", "steps": [], "expected_result": "", "covers": "валидация amount",
        "status": "approved", "analyst_text": None,
    }
    await store.save_test_cases("p", "create-order", [kept, dict(kept, name="Устаревший черновик", status="pending")])
    _mock_codex(monkeypatch, COVERAGE, {"test_cases": [
        _case(1, "Валидация amount — отсутствует"), _case(2, "Успешное создание заказа"),
    ]})

    await run_test_cases_pipeline("p", "create-order", store)

    saved = await store.get_test_cases("p", "create-order")
    assert [(tc["name"], tc["status"]) for tc in saved] == [
        ("Валидация amount — отсутствует", "approved"),
        ("Успешное создание заказа", "pending"),
    ]


async def test_empty_coverage_marks_task_error(store, monkeypatch):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    _mock_codex(monkeypatch, {"coverage": []})

    task = await store.create_task("p", kind="test_cases", target_type="feature", target_id="create-order")
    with pytest.raises(RuntimeError, match="empty coverage"):
        await run_test_cases_pipeline("p", "create-order", store, task_id=task["id"])

    tasks = await store.list_tasks("p", kind="test_cases")
    assert tasks[0]["status"] == "error"
    assert await store.get_test_cases("p", "create-order") == []
