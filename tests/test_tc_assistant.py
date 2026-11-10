"""Test-case assistant: stand limits, the agent protocol, saved changes and the API.

Codex and the stand are simulated: the fake agent returns scripted steps, the
fake test DB records the scripts it was asked to run.
"""

import asyncio

import httpx
import pytest

from app.config import settings
from app.services import agent_runner, sql_runner, tc_assistant, wiremock
from app.services.assistant_stand import SqlNotAllowed, classify_sql
from app.services.task_manager import task_manager

FEATURE = {
    "name": "create-plan",
    "type": "rest_endpoint",
    "status": "done",
    "source_document": "doc",
    "structured_logic_json": {"used_dependencies": [], "logic_steps": []},
}
DOC = {"slug": "doc", "filename": "doc", "status": "done", "service_name": "bnpl-payment"}

OLD_SQL = "INSERT INTO bnpl_payment.payment_plan (id, tariff_id) VALUES ('pp-1', 'T-12');"
FIXED_SQL = (
    "INSERT INTO bnpl_payment.tariff (id) VALUES ('T-12') ON CONFLICT (id) DO NOTHING;\n" + OLD_SQL
)


def case(name: str, **fields) -> dict:
    return {
        "category": "negative", "name": name, "preconditions": "нет", "priority": "high",
        "steps": [{"action": "POST /v1/plans", "expected": "HTTP 404"}], "expected_result": "404",
        "status": "pending", "analyst_text": None, "covers": "шаг 3",
        "curl_command": None, "kafka_message": None, "sql_setup": None, "mock_config": None, **fields,
    }


def step(**fields) -> dict:
    """A full agent step (structured outputs always carry every key)."""
    return {
        "actions": [], "reply": None, "cause": None, "edits": [], "new_cases": [],
        "delete_suggestions": [], "bug_suggestions": [], "related_cases": [], "session_title": None, **fields,
    }


def action(kind: str, title: str, **fields) -> dict:
    return {
        "kind": kind, "title": title, "case": None, "sql": None, "method": None, "path": None,
        "headers": None, "body": None, "mock_config": None, "url_contains": None, "cases": None, **fields,
    }


def edit(number: int, **fields) -> dict:
    return {
        "case": number, "summary": "Поправил данные", "name": None, "preconditions": None, "steps": None,
        "expected_result": None, "priority": None, "curl_command": None, "kafka_message": None,
        "sql_setup": None, "mock_config": None, **fields,
    }


@pytest.fixture
def agent(monkeypatch):
    """Scripted Codex: each ask() returns the next step; prompts are recorded."""
    script: list[dict] = []
    prompts: list[str] = []

    async def analyze(workspace, log_path, execute, on_started, **options):
        await on_started()

        async def ask(prompt, schema):
            prompts.append(prompt)
            return script.pop(0)

        return await execute(ask)

    monkeypatch.setattr(agent_runner, "analyze", analyze)
    return script, prompts


@pytest.fixture
def test_db(monkeypatch):
    """Simulated test DB: scripts containing a failing marker return an error."""
    monkeypatch.setattr(settings, "test_db_url", "postgresql://u:p@stand.example/bnpl_test")
    runs: list[tuple[str, bool]] = []

    async def execute_sql(sql, *, readonly=False):
        runs.append((sql, readonly))
        if "bnpl_payment.tariff" not in sql and "INSERT INTO bnpl_payment.payment_plan" in sql:
            return {
                "results": [], "failed_statement": 0, "duration_ms": 3,
                "error": 'violates foreign key constraint "payment_plan_tariff_id_fkey"',
            }
        results = [
            {"statement": s, "status": "SELECT 0" if readonly else "INSERT 0 1",
             "columns": ["id"] if readonly else None, "rows": [] if readonly else None, "truncated": False}
            for s in sql_runner.split_sql_statements(sql)
        ]
        return {"results": results, "error": None, "failed_statement": None, "duration_ms": 5}

    monkeypatch.setattr(sql_runner, "execute_sql", execute_sql)
    return runs


async def seed(store, cases: list[dict]) -> list[dict]:
    await store.create_project("P")
    await store.save_document("p", dict(DOC))
    await store.save_feature("p", dict(FEATURE))
    await store.save_test_cases("p", "create-plan", cases)
    return await store.get_test_cases("p", "create-plan")


async def ask(store, text: str, *, session_id=None, attachments=None) -> dict:
    """Queue a message and wait for the feature worker to answer it."""
    turn = await tc_assistant.send_message(
        store, "p", "create-plan", text=text, attachments=attachments or [], session_id=session_id, author="qa",
    )
    for _ in range(200):
        if not task_manager.is_running(tc_assistant.worker_key("p", "create-plan")):
            break
        await asyncio.sleep(0.01)
    return await store.get_assistant_turn("p", "create-plan", turn["id"])


# --- stand limits ----------------------------------------------------------


@pytest.mark.parametrize("sql,writes", [
    ("SELECT * FROM other_schema.tariff WHERE id = 'T-12'", False),
    ("WITH t AS (SELECT 1) SELECT * FROM t; SHOW search_path", False),
    ("SELECT id FROM bnpl_payment.plan WHERE note = 'delete from x; drop table y' FOR UPDATE", False),
    ("-- cleanup\nDELETE FROM bnpl_payment.plan WHERE id = 1; INSERT INTO bnpl_payment.plan (id) VALUES (1)", True),
    ("INSERT INTO bnpl_payment.plan (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET id = 1", True),
    ('UPDATE "bnpl_payment"."plan" SET updated_at = now()', True),
    ("WITH gone AS (DELETE FROM bnpl_payment.plan RETURNING id) SELECT * FROM gone", True),
    ("INSERT INTO bnpl_payment.plan (id) VALUES (1); -- trailing note; DROP TABLE x", True),
])
def test_sql_within_limits(sql, writes):
    assert classify_sql(sql, "bnpl_payment") is writes


@pytest.mark.parametrize("sql", [
    "DELETE FROM flp_order.payment",  # another team's schema
    "INSERT INTO plan (id) VALUES (1)",  # no schema prefix
    "DROP TABLE bnpl_payment.plan",
    "TRUNCATE bnpl_payment.plan",
    "SELECT 1; ALTER TABLE bnpl_payment.plan ADD COLUMN x int",
    "SELECT * INTO bnpl_payment.copy FROM bnpl_payment.plan",
    "DO $$ BEGIN DELETE FROM flp_order.payment; END $$",
    "",
    "-- only a comment",
])
def test_sql_outside_limits_is_refused(sql):
    with pytest.raises(SqlNotAllowed):
        classify_sql(sql, "bnpl_payment")


def test_writes_refused_when_service_schema_unknown():
    assert classify_sql("SELECT 1", None) is False
    with pytest.raises(SqlNotAllowed):
        classify_sql("DELETE FROM bnpl_payment.plan", None)


# --- storage ---------------------------------------------------------------


async def test_cases_get_stable_ids_and_queue_is_ordered(store):
    cases = await seed(store, [case("A"), case("B")])
    assert len({c["id"] for c in cases}) == 2

    # ids survive deleting a neighbour; a new case gets its own
    kept = await store.mutate_test_cases("p", "create-plan", lambda current: current[1:] + [case("C")])
    assert kept[0]["id"] == cases[1]["id"]
    assert kept[1]["id"] not in {c["id"] for c in cases}
    assert (await store.get_feature("p", "create-plan"))["test_case_count"] == 2

    session = await store.create_assistant_session("p", "create-plan", title="S", author="qa")
    first = await store.add_assistant_turn("p", "create-plan", session["id"], {"text": "1"})
    second = await store.add_assistant_turn("p", "create-plan", session["id"], {"text": "2"})
    assert (await store.claim_assistant_turn("p", "create-plan"))["id"] == first["id"]
    # a queued message can be taken back, a running one cannot
    assert not await store.delete_assistant_turn("p", "create-plan", first["id"])
    assert await store.delete_assistant_turn("p", "create-plan", second["id"])
    assert await store.claim_assistant_turn("p", "create-plan") is None
    assert (await store.list_assistant_sessions("p", "create-plan"))[0]["state"] == "running"


# --- a turn ----------------------------------------------------------------


async def test_assistant_fixes_sql_runs_it_and_saves_the_case(store, agent, test_db):
    script, prompts = agent
    cases = await seed(store, [case("Таймаут скоринга", sql_setup=OLD_SQL)])
    script += [
        step(actions=[action("sql", "Проверил, есть ли тариф T-12", case=1,
                             sql="SELECT id FROM bnpl_payment.tariff WHERE id = 'T-12'")]),
        step(reply="Добавил тариф перед вставкой плана, #1 теперь выполняется.", cause="Нет тарифа T-12",
             edits=[edit(1, summary="Добавил родительскую запись в tariff", sql_setup=FIXED_SQL)],
             related_cases=[1], session_title="Ошибка SQL в кейсе"),
    ]

    turn = await ask(store, "Почему SQL не выполнился?", attachments=[
        {"kind": "sql_error", "case_id": cases[0]["id"], "error": "violates foreign key", "failed_statement": 0},
    ])

    assert turn["status"] == "done"
    assert turn["cause"] == "Нет тарифа T-12"
    # the read ran read-only, the fixed script ran for real before the case was saved
    assert test_db == [("SELECT id FROM bnpl_payment.tariff WHERE id = 'T-12'", True), (FIXED_SQL, False)]
    assert [(a["write"], a["status"]) for a in turn["actions"]] == [(False, "ok"), (True, "ok")]
    change = turn["changes"][0]
    assert change["fields"] == ["sql_setup"] and change["stand_check"]["status"] == "ok"
    assert (await store.get_test_cases("p", "create-plan"))[0]["sql_setup"] == FIXED_SQL
    assert turn["numbering"] == {"1": cases[0]["id"]}

    # the agent saw the attached error, the full case and the stand limits; then the action result
    assert "violates foreign key" in prompts[0] and "### Кейс #1" in prompts[0]
    assert "только в схему bnpl_payment" in prompts[0]
    assert "Проверил, есть ли тариф T-12" in prompts[1] and "SELECT 0" in prompts[1]

    session = (await store.list_assistant_sessions("p", "create-plan"))[0]
    assert session["title"] == "Ошибка SQL в кейсе" and session["author"] == "qa"
    tasks = await store.list_tasks("p", kind="tc_assistant")
    assert [t["status"] for t in tasks] == ["done"]


async def test_case_untouched_after_three_failed_fixes(store, agent, test_db):
    script, prompts = agent
    await seed(store, [case("Таймаут скоринга", sql_setup=OLD_SQL)])
    broken = [OLD_SQL.replace("pp-1", f"pp-{n}") for n in (2, 3, 4)]
    script += [step(reply="Исправил", edits=[edit(1, sql_setup=sql)]) for sql in broken]
    script.append(step(reply="Не получилось: мешает внешний ключ."))

    turn = await ask(store, "Почини SQL в #1")

    assert turn["status"] == "done" and turn["changes"] == []
    assert turn["failures"][0]["attempts"] == 3 and "foreign key" in turn["failures"][0]["error"]
    assert (await store.get_test_cases("p", "create-plan"))[0]["sql_setup"] == OLD_SQL
    assert [sql for sql, _ in test_db] == broken
    assert "попытка 1 из 3" in prompts[1] and "Попытки исчерпаны" in prompts[3]


async def test_write_outside_service_schema_never_reaches_the_stand(store, agent, test_db):
    script, _ = agent
    await seed(store, [case("A")])
    script += [
        step(actions=[action("sql", "Почистил чужую таблицу", sql="DELETE FROM flp_order.payment")]),
        step(reply="Запись в чужую схему запрещена."),
    ]

    turn = await ask(store, "Почисти данные")

    assert test_db == []
    assert turn["actions"][0]["status"] == "blocked"
    assert "только в схему bnpl_payment" in turn["actions"][0]["summary"]


async def test_changes_can_be_reverted_and_restored(store, agent, test_db):
    script, _ = agent
    cases = await seed(store, [case("A", preconditions="клиент c-1001"), case("B")])
    new_case = {k: v for k, v in case("Новый кейс").items() if k not in ("status", "analyst_text")}
    script.append(step(
        reply="Заменил клиента и добавил кейс.",
        edits=[edit(1, preconditions="клиент c-1007")], new_cases=[new_case],
        delete_suggestions=[{"case": 2, "reason": "Дубликат #1"}],
        bug_suggestions=[{"case": 1, "text": "Сервис вернул 500 вместо 404"}],
    ))
    turn = await ask(store, "Замени клиента на c-1007 в #1")
    edit_change, add_change = turn["changes"]
    assert test_db == []  # no SQL changed — nothing to run on the stand

    async def names():
        return [(c["name"], c["preconditions"]) for c in await store.get_test_cases("p", "create-plan")]

    assert await names() == [("A", "клиент c-1007"), ("B", "нет"), ("Новый кейс", "нет")]

    args = (store, "p", "create-plan", turn["id"])
    await tc_assistant.set_change_state(*args, add_change["id"], revert=True)
    reverted = await tc_assistant.set_change_state(*args, edit_change["id"], revert=True)
    assert [c["state"] for c in reverted["changes"]] == ["reverted", "reverted"]
    assert await names() == [("A", "клиент c-1001"), ("B", "нет")]

    await tc_assistant.set_change_state(*args, edit_change["id"], revert=False)
    await tc_assistant.set_change_state(*args, add_change["id"], revert=False)
    assert await names() == [("A", "клиент c-1007"), ("B", "нет"), ("Новый кейс", "нет")]

    # a later manual change of the same field blocks the undo instead of overwriting it
    await store.mutate_test_cases(
        "p", "create-plan", lambda current: [{**current[0], "preconditions": "руками"}] + current[1:],
    )
    with pytest.raises(tc_assistant.AssistantConflict):
        await tc_assistant.set_change_state(*args, edit_change["id"], revert=True)

    # deletion is only suggested; the case goes away when the tester accepts
    delete, bug = turn["suggestions"]
    assert (delete["kind"], delete["case_id"], bug["kind"]) == ("delete", cases[1]["id"], "bug")
    resolved = await tc_assistant.resolve_suggestion(*args, delete["id"], accept=True)
    assert resolved["suggestions"][0]["state"] == "accepted"
    assert [n for n, _ in await names()] == ["A", "Новый кейс"]


async def test_session_history_reaches_the_next_message(store, agent, test_db):
    script, prompts = agent
    await seed(store, [case("A")])
    script += [step(reply="Покрыто кейсом #1.", related_cases=[1]), step(reply="Да.")]

    first = await ask(store, "Покрыт ли шаг 3?")
    await ask(store, "Точно?", session_id=first["session_id"])

    assert "История этой сессии" not in prompts[0]
    assert "Покрыт ли шаг 3?" in prompts[1] and "Покрыто кейсом #1." in prompts[1]
    # a new session starts with a clean context
    script.append(step(reply="Привет."))
    await ask(store, "Новая тема")
    assert "История этой сессии" not in prompts[2]


# --- API -------------------------------------------------------------------


async def _wait_idle():
    for _ in range(200):
        if not task_manager.is_running(tc_assistant.worker_key("p", "create-plan")):
            return
        await asyncio.sleep(0.01)


async def test_api_message_flow_and_failure(client, store, agent, monkeypatch):
    script, _ = agent
    await seed(store, [case("A")])
    base = "/projects/p/features/create-plan/assistant"

    overview = (await client.get(base)).json()
    assert overview["sessions"] == [] and overview["stand"]["write_schema"] is None  # no test DB configured

    script.append(step(reply="Готово.", session_title="Проверка"))
    r = await client.post(f"{base}/messages", json={"text": "  Проверь покрытие  "})
    assert r.status_code == 200 and r.json()["status"] == "queued" and r.json()["text"] == "Проверь покрытие"
    session_id = r.json()["session_id"]
    await _wait_idle()

    session = (await client.get(f"{base}/sessions/{session_id}")).json()
    assert session["title"] == "Проверка"
    assert [(t["status"], t["reply"]) for t in session["turns"]] == [("done", "Готово.")]

    # Codex failure: the message stays with an error and can be sent again
    async def failing(*args, **kwargs):
        raise agent_runner.AgentError("Codex не авторизован через ChatGPT. Выполните codex login")

    monkeypatch.setattr(agent_runner, "analyze", failing)
    r = await client.post(f"{base}/messages", json={"text": "Ещё вопрос", "session_id": session_id})
    failed_id = r.json()["id"]
    await _wait_idle()
    failed = (await client.get(f"{base}/sessions/{session_id}")).json()["turns"][1]
    assert failed["status"] == "error" and "codex login" in failed["error"]
    assert (await client.post(f"{base}/turns/{session['turns'][0]['id']}/retry")).status_code == 409
    retried = await client.post(f"{base}/turns/{failed_id}/retry")
    assert retried.status_code == 200 and retried.json()["text"] == "Ещё вопрос"
    await _wait_idle()

    assert (await client.post(f"{base}/messages", json={"text": "x", "session_id": "nope"})).status_code == 404
    assert (await client.post(f"{base}/messages", json={"text": "   "})).status_code == 422
    assert (await client.delete(f"{base}/sessions/{session_id}")).status_code == 200
    assert (await client.get(base)).json()["sessions"] == []

    kinds = {t["kind"] for t in (await client.get("/projects/p/tasks")).json()["tasks"]}
    assert kinds == {"tc_assistant"}


async def test_running_turn_can_be_cancelled_and_queue_continues(client, store, monkeypatch):
    await seed(store, [case("A")])
    base = "/projects/p/features/create-plan/assistant"
    started = asyncio.Event()
    calls = 0

    async def analyze(workspace, log_path, execute, on_started, **options):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.sleep(60)

        async def ask(prompt, schema):
            return step(reply="Второе сообщение обработано.")

        return await execute(ask)

    monkeypatch.setattr(agent_runner, "analyze", analyze)
    first = (await client.post(f"{base}/messages", json={"text": "Долгий вопрос"})).json()
    second = (await client.post(
        f"{base}/messages", json={"text": "Следом", "session_id": first["session_id"]},
    )).json()
    await asyncio.wait_for(started.wait(), timeout=2)

    assert (await client.post(f"{base}/turns/{second['id']}/cancel")).status_code == 409  # still queued
    assert (await client.post(f"{base}/turns/{first['id']}/cancel")).status_code == 200
    await _wait_idle()

    turns = (await client.get(f"{base}/sessions/{first['session_id']}")).json()["turns"]
    assert [t["status"] for t in turns] == ["cancelled", "done"]
    assert turns[1]["reply"] == "Второе сообщение обработано."


# --- WireMock journal ------------------------------------------------------


async def test_wiremock_mappings_and_request_journal(monkeypatch):
    monkeypatch.setattr(settings, "test_wiremock_url", "http://stand.example/bnpl-wiremock/")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/__admin/mappings"):
            return httpx.Response(200, json={"mappings": [
                {"id": "1", "request": {"urlPath": "/scoring/v1/check"}, "response": {"status": 504}},
                {"id": "2", "request": {"urlPattern": ".*/payment.do"}, "response": {"status": 200}},
            ]})
        return httpx.Response(200, json={"requests": [
            {"request": {"url": "/scoring/v1/check", "method": "POST", "body": "{}"}, "wasMatched": False,
             "responseDefinition": {"status": 404}},
            {"request": {"url": "/other", "method": "GET"}, "wasMatched": True, "response": {"status": 200}},
        ]})

    original = httpx.AsyncClient
    monkeypatch.setattr(wiremock.httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler),
    ))

    found = await wiremock.find_mappings("SCORING")
    assert (found["total"], [m["id"] for m in found["mappings"]]) == (2, ["1"])
    journal = await wiremock.recent_requests("scoring")
    assert journal["requests"] == [{
        "time": None, "method": "POST", "url": "/scoring/v1/check", "body": "{}",
        "matched": False, "stub_id": None, "response_status": 404,
    }]
