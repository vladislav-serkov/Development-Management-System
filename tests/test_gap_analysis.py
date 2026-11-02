"""Source grounding, analyst decisions, partial coverage and HTTP lifecycle."""
import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.schemas.gaps import GapReport, SourceSelection
from app.services import agent_runner, confluence, gaps
from app.services.gap_sources import SourceCorpus, digest, validate_source_url
from app.services.task_manager import task_manager

PRIMARY = "Сохранить внешний идентификатор paymentId в payment.external_id. После сохранения вернуть успех."
SCHEMA = "Таблица payment. Полный список колонок: id UUID NOT NULL, status VARCHAR NOT NULL."
SID = "source-" + digest({"page_id": "101"})[:16]
TABLE_SID = "source-" + digest({"page_id": "102"})[:16]


def evidence(sid=SID, quote=PRIMARY):
    return {"source_id": sid, "location": "Шаг 5" if sid == SID else "Таблица payment", "quote": quote}


def report():
    fact = {"text": "Операция сохраняет идентификатор внешнего платежа", "evidence": [evidence()]}
    return {
        "business_picture": {
            "purpose": "Зарегистрировать платёж", "purpose_evidence": [evidence()],
            "actors": [fact], "entities_and_states": [],
            "lifecycle": [fact], "business_rules": [], "unknowns": [],
        },
        "checked_source_ids": [SID, TABLE_SID], "checked_scenarios": ["Успешная регистрация платежа"],
        "limitations": [],
        "gaps": [{
            "existing_gap_id": None, "kind": "contradiction", "gap_type": "field_not_in_schema",
            "severity": "critical", "subject": "payment.external_id", "location": "Шаг 5",
            "question": "Где хранить внешний идентификатор?", "scenario": "Успешный ответ внешнего сервиса",
            "business_impact": "Не получится связать платёж с внешней операцией",
            "suggestion": "Согласовать место хранения идентификатора", "evidence": [evidence(), evidence(TABLE_SID, SCHEMA)],
            "reconsideration_reason": None,
        }],
    }


@pytest.fixture
async def setup_project(store, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "gaps_log_dir", str(tmp_path / "gaps"))
    monkeypatch.setattr(settings, "confluence_base_url", "https://confluence.example")
    await store.create_project("P")
    for slug, pid, text in [("spec", "101", PRIMARY), ("table", "102", SCHEMA)]:
        await store.save_document("p", {"slug": slug, "status": "done", "confluence_page_id": pid, "filename": slug})
        await store.save_document_source("p", slug, {
            "confluence_page_id": pid, "confluence_version": 7, "title": slug, "markdown": text,
            "links": [{"page_id": "102", "title": "payment"}] if pid == "101" else [],
        })
    await store.save_feature("p", {
        "name": "POST /payments", "status": "done", "source_document": "spec", "type": "rest_endpoint",
        "structured_logic_json": {"logic_steps": [], "used_dependencies": [{"name": "payment", "type": "db_table"}]},
    })
    # A missing enrichment is deliberately allowed; raw specifications suffice.
    await store.upsert_dependency("p", "db_table", "payment", {"enrichment_status": "stub"})
    return store


def fake_agent(monkeypatch, final=None, during=None):
    calls = []

    async def analyze(workspace, log, execute, on_started):
        await on_started()
        selected = False

        async def ask(prompt, schema):
            nonlocal selected
            calls.append(schema)
            if schema is SourceSelection:
                ids = [] if selected else [TABLE_SID]
                selected = True
                return {"requested_source_ids": ids, "rationale": "Нужна схема таблицы"}
            if during and calls.count(GapReport) == 2:
                await during()
            return schema.model_validate(copy.deepcopy(final if final is not None else report())).model_dump()

        return await execute(ask)

    monkeypatch.setattr(agent_runner, "analyze", analyze)
    return calls


async def test_pipeline_uses_originals_and_verification_without_enrichment(setup_project, monkeypatch):
    calls = fake_agent(monkeypatch)
    result = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert calls == [SourceSelection, SourceSelection, GapReport, GapReport]
    assert result[0]["evidence"][1]["quote"] == SCHEMA
    assert result[0]["id"].startswith("gap-")
    feature = await setup_project.get_feature("p", "POST /payments")
    assert feature["gaps_analysis"]["coverage"] == "complete"
    assert feature["gaps_analysis"]["sources"][0]["version"] == 7
    assert feature["gaps_job"]["stage"] == "done"
    assert not feature["gaps_stale"]


async def test_invented_quote_is_excluded_and_empty_result_is_not_complete(setup_project, monkeypatch):
    final = report()
    final["gaps"][0]["evidence"][0]["quote"] = "Текст, которого нет в исходной спецификации"
    fake_agent(monkeypatch, final)
    assert await gaps.run_gaps_pipeline("p", "POST /payments", setup_project) == []
    analysis = (await setup_project.get_feature("p", "POST /payments"))["gaps_analysis"]
    assert analysis["coverage"] == "partial"
    assert "цитаты" in " ".join(analysis["limitations"])


async def test_same_gap_preserves_concurrent_review_and_stable_id(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    first = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    gid = first[0]["id"]
    final = report()
    final["gaps"][0].update(existing_gap_id=gid, question="Новая формулировка той же проблемы")

    async def review():
        def mutate(items):
            items[0].update(status="rejected", analyst_text="Это поле описано в дополнении к ТЗ")
            return items
        await setup_project.mutate_gaps("p", "POST /payments", mutate)

    fake_agent(monkeypatch, final, review)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert len(second) == 1
    assert second[0]["id"] == gid and second[0]["status"] == "rejected"
    assert second[0]["analyst_text"] == "Это поле описано в дополнении к ТЗ"
    assert (await setup_project.get_feature("p", "POST /payments"))["gap_count"] == 0


async def test_partial_run_preserves_previous_findings(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    final = report()
    final.update(gaps=[], limitations=["Нет описания жизненного цикла"])
    fake_agent(monkeypatch, final)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert second[0]["presence"] == "unverified"
    assert second[0]["status"] == "pending"


async def test_full_run_keeps_absent_gap_in_history(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    final = report()
    final["gaps"] = []
    fake_agent(monkeypatch, final)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert second[0]["presence"] == "not_detected"
    assert (await setup_project.get_feature("p", "POST /payments"))["gap_count"] == 0


async def test_unavailable_source_is_a_limitation_not_a_gap(setup_project, monkeypatch, tmp_path):
    corpus = SourceCorpus(setup_project, "p", await setup_project.get_feature("p", "POST /payments"), tmp_path, {})
    await corpus.prepare()
    sid = corpus.add_ref({"page_id": "999"}, "Недоступный бизнес-процесс")
    fetch = AsyncMock(side_effect=confluence.ConfluenceError("secret must not leak"))
    monkeypatch.setattr(confluence, "fetch_page_by_ref", fetch)
    await corpus.load([sid])
    assert sid not in corpus.sources
    assert corpus.limitations and "secret" not in " ".join(corpus.limitations)
    await corpus.load([sid])
    fetch.assert_awaited_once()


async def test_context_change_during_run_is_partial_and_stale(setup_project, monkeypatch):
    await setup_project.update_feature("p", "POST /payments", {"gaps_run_at": "2026-01-01"})

    async def change():
        await setup_project.save_gap_context("p", {"notes": "Новое бизнес-правило", "source_urls": []})

    fake_agent(monkeypatch, during=change)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    feature = await setup_project.get_feature("p", "POST /payments")
    assert feature["gaps_analysis"]["coverage"] == "partial"
    assert feature["gaps_stale"]


async def test_failed_run_keeps_last_report_and_finishes_task(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    previous = (await setup_project.get_feature("p", "POST /payments"))["gaps_analysis"]
    monkeypatch.setattr(agent_runner, "analyze", AsyncMock(side_effect=agent_runner.AgentError("Лимит Codex")))
    task = await setup_project.create_task("p", kind="gaps", target_type="feature", target_id="POST /payments")
    with pytest.raises(agent_runner.AgentError):
        await gaps.run_gaps_pipeline("p", "POST /payments", setup_project, task_id=task["id"])
    feature = await setup_project.get_feature("p", "POST /payments")
    assert feature["gaps_analysis"] == previous
    assert feature["gaps_job"]["error"] == "Лимит Codex"
    assert await setup_project.get_active_task("p", kind="gaps", target_id="POST /payments") is None


async def test_http_review_optional_reason_and_keeps_history(client, setup_project, monkeypatch):
    fake_agent(monkeypatch)
    result = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    url = "/projects/p/features/POST%20__payments/gaps"
    r = await client.get(url + "/")
    assert r.status_code == 200 and r.json()["analysis"]["engine"] == "codex"
    gid = result[0]["id"]
    r = await client.patch(url + f"/items/{gid}", json={"status": "rejected"})
    assert r.status_code == 200
    assert r.json()["gaps"][0]["analyst_text"] is None
    r = await client.patch(url + f"/items/{gid}", json={"status": "rejected", "analyst_text": "Учтено в другом разделе"})
    assert r.status_code == 200
    assert r.json()["gaps"][0]["history"][-1]["action"] == "rejected"
    assert (await client.post(url + "/apply-confirm", json={})).status_code == 410


async def test_http_context_and_recovery(client, setup_project, monkeypatch):
    r = await client.patch("/projects/p/gap-context", json={"notes": "Бизнес-процесс", "source_urls": []})
    assert r.status_code == 404
    assert (await client.get("/projects/p/gap-context")).status_code == 404
    assert (await setup_project.get_gap_context("p"))["notes"] == ""
    await setup_project.create_task("p", kind="gaps", target_type="feature", target_id="POST /payments")
    r = await client.get("/projects/p/features/POST%20__payments/gaps/")
    assert r.status_code == 200 and not r.json()["gaps_running"]
    assert "перезапущен" in r.json()["job"]["error"]


async def test_http_cancel_and_duplicate_run(client, setup_project, monkeypatch):
    entered = asyncio.Event()

    async def wait(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(agent_runner, "analyze", wait)
    url = "/projects/p/features/POST%20__payments/gaps"
    r = await client.post(url + "/run")
    assert r.status_code == 200
    await asyncio.wait_for(entered.wait(), timeout=3)
    assert (await client.post(url + "/run")).status_code == 409
    assert (await client.post(url + "/cancel")).json()["status"] == "cancelled"
    data = (await client.get(url + "/")).json()
    assert not data["gaps_running"] and data["job"]["stage"] == "cancelled"
    assert not task_manager.is_running("gaps:p/POST /payments")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://confluence.example.evil/pages/1", "https://user@confluence.example/pages/1"])
def test_source_url_is_restricted_to_configured_confluence(monkeypatch, url):
    monkeypatch.setattr(settings, "confluence_base_url", "https://confluence.example")
    with pytest.raises(ValueError):
        validate_source_url(url)


async def test_zero_findings_and_inflight_first_run_are_invalidated(setup_project):
    from app.services.dep_impact import mark_feature_stale
    await setup_project.update_feature("p", "POST /payments", {"gap_count": 0, "gaps_run_at": "2026-01-01"})
    assert await mark_feature_stale(setup_project, "p", "POST /payments", "Изменилось ТЗ")
    feature = await setup_project.get_feature("p", "POST /payments")
    assert feature["gaps_stale"]
    await setup_project.save_feature("p", {"name": "first-run", "status": "done", "gaps_job": {"stage": "research"}})
    await setup_project.save_gap_context("p", {"notes": "Новое правило", "source_urls": []})
    assert (await setup_project.get_feature("p", "first-run"))["gaps_stale"]


async def test_legacy_ids_survive_archived_rows(client, setup_project):
    await setup_project.save_gaps("p", "POST /payments", [
        {"gap_type": "old", "question": "Архив", "status": "pending", "archived": True},
        {"gap_type": "old", "question": "Старое замечание", "status": "pending"},
    ])
    url = "/projects/p/features/POST%20__payments/gaps"
    items = (await client.get(url + "/")).json()["gaps"]
    assert len(items) == 1
    result = await client.patch(url + "/items/" + items[0]["id"], json={"status": "approved"})
    assert result.status_code == 200
    all_items = await setup_project.get_gaps("p", "POST /payments", include_archived=True)
    assert all_items[0]["archived"] and all_items[1]["status"] == "approved"


async def test_business_context_is_private_in_export_and_import(setup_project, tmp_path, monkeypatch):
    from app.services.context_serializer import dump_project, load_context_project
    secret = "Внутреннее описание назначения микросервиса"
    await setup_project.save_gap_context("p", {"notes": secret, "source_urls": []})
    final = report()
    final["business_picture"]["purpose"] = secret
    fake_agent(monkeypatch, final)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    files = await dump_project(setup_project, "p")
    assert "gap-context.json" not in files
    assert all(secret not in content.decode() for content in files.values())
    assert all("business_picture" not in content.decode() for content in files.values())
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (tmp_path / "gap-context.json").write_text('{"notes": "Не импортировать", "source_urls": []}')
    slug, _, _ = await load_context_project(setup_project, tmp_path, name="Imported")
    assert (await setup_project.get_gap_context(slug))["notes"] == ""


async def test_overview_source_version_change_invalidates_empty_report(client, setup_project, monkeypatch):
    from app.routers import documents
    await setup_project.update_feature("p", "POST /payments", {
        "gaps_run_at": "2026-01-01", "gap_count": 0,
        "gaps_analysis": {"sources": [{"page_id": "999", "version": 1}]},
    })
    probe = AsyncMock(side_effect=lambda pid: {"id": pid, "version": 2 if pid == "999" else 1})
    monkeypatch.setattr(documents, "fetch_page_meta", probe)
    r = await client.post("/documents/check-spec-updates?project_slug=p")
    assert r.status_code == 200
    assert (await setup_project.get_feature("p", "POST /payments"))["gaps_stale"]
    assert "999" in {call.args[0] for call in probe.await_args_list}


async def test_history_and_rejections_do_not_reappear_in_counts_on_import(setup_project):
    items = [
        {"id": "1", "question": "dismissed", "status": "rejected"},
        {"id": "2", "question": "old", "status": "pending", "presence": "not_detected"},
        {"id": "3", "question": "current", "status": "pending"},
    ]
    await setup_project.save_gaps("p", "POST /payments", items)
    assert (await setup_project.get_feature("p", "POST /payments"))["gap_count"] == 1
    await setup_project.update_feature("p", "POST /payments", {"gaps": items})
    assert (await setup_project.get_feature("p", "POST /payments"))["pending_gap_count"] == 1
    await setup_project.save_feature("p", {"name": "imported", "status": "done", "gaps": items})
    assert (await setup_project.get_feature("p", "imported"))["gap_count"] == 1


async def test_two_versions_of_same_page_cannot_produce_false_contradiction(setup_project, monkeypatch, tmp_path):
    corpus = SourceCorpus(setup_project, "p", await setup_project.get_feature("p", "POST /payments"), tmp_path, {})
    await corpus.prepare()
    alias = corpus.add_ref({"space": "PAY", "title": "Регистрация платежа"}, "Та же страница по названию")
    monkeypatch.setattr(confluence, "fetch_page_by_ref", AsyncMock(return_value={
        "id": "101", "version": 8, "title": "Новая версия", "markdown": "Теперь поле хранится иначе и это другая версия ТЗ",
    }))
    await corpus.load([alias])
    assert alias not in corpus.sources
    assert any("разные версии" in text for text in corpus.limitations)


async def test_changed_sources_surface_dismissed_gap_for_reconsideration(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    first = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    first[0].update(status="rejected", analyst_text="Прежняя версия не требовала такого поведения")
    await setup_project.save_gaps("p", "POST /payments", first)
    source = await setup_project.get_document_source("p", "spec")
    source["markdown"] += "\nТеперь идентификатор обязателен для возврата."
    source["confluence_version"] = 8
    await setup_project.save_document_source("p", "spec", source)
    final = report()
    final["gaps"][0]["existing_gap_id"] = first[0]["id"]
    final["gaps"][0]["reconsideration_reason"] = "В ТЗ добавлена обязательность идентификатора для возврата"
    final["gaps"][0]["evidence"].append(evidence(quote="Теперь идентификатор обязателен для возврата."))
    fake_agent(monkeypatch, final)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert second[0]["status"] == "rejected" and second[0]["needs_review"]
    feature = await setup_project.get_feature("p", "POST /payments")
    assert feature["gap_count"] == 1 and feature["pending_gap_count"] == 1
    assert second[0]["source_snapshots"][0]["version"] == 8


async def test_same_space_confluence_links_inherit_parent_space(setup_project, monkeypatch, tmp_path):
    source = await setup_project.get_document_source("p", "spec")
    source.update(space_key="PAY", links=[{"title": "Описание возврата", "space_key": None, "page_id": None}])
    await setup_project.save_document_source("p", "spec", source)
    corpus = SourceCorpus(setup_project, "p", await setup_project.get_feature("p", "POST /payments"), tmp_path, {})
    await corpus.prepare()
    ref = {"space": "PAY", "title": "Описание возврата"}
    sid = "source-" + digest(ref)[:16]
    assert corpus.catalog[sid]["ref"] == ref
    fetch = AsyncMock(return_value={"id": "999", "version": 1, "markdown": "Возврат ищет платёж по внешнему идентификатору", "space_key": "PAY"})
    monkeypatch.setattr(confluence, "fetch_page_by_ref", fetch)
    await corpus.load([sid])
    fetch.assert_awaited_once_with(ref)
    assert sid in corpus.sources


async def test_identical_legacy_rows_get_distinct_stable_ids(client, setup_project):
    old = {"gap_type": "old", "question": "Одинаковое замечание", "status": "pending"}
    await setup_project.save_gaps("p", "POST /payments", [{**old, "archived": True}, dict(old)])
    url = "/projects/p/features/POST%20__payments/gaps"
    active = (await client.get(url + "/")).json()["gaps"][0]
    assert active["id"].endswith("-1")
    response = await client.patch(url + "/items/" + active["id"], json={"status": "approved"})
    assert response.status_code == 200
    all_gaps = await setup_project.get_gaps("p", "POST /payments", include_archived=True)
    assert all_gaps[0]["status"] == "pending" and all_gaps[1]["status"] == "approved"
    assert all_gaps[0]["id"] != all_gaps[1]["id"]


async def test_context_is_only_private_orientation_and_not_evidence(setup_project, tmp_path):
    context = {"notes": "Сервис исполняет уже одобренные платежи", "source_urls": []}
    corpus = SourceCorpus(setup_project, "p", await setup_project.get_feature("p", "POST /payments"), tmp_path, context)
    await corpus.prepare()
    import json
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["business_context"] == context["notes"]
    assert "project-notes" not in corpus.sources
    assert not corpus.validate_evidence([evidence("project-notes", context["notes"])])
    assert not corpus.limitations


async def test_http_results_and_review_never_return_internal_report(client, setup_project, monkeypatch):
    import json
    secret = "Внутреннее описание сервиса только для агента"
    await setup_project.save_gap_context("p", {"notes": secret, "source_urls": []})
    final = report()
    final["business_picture"]["purpose"] = secret
    fake_agent(monkeypatch, final)
    items = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    # Simulate a previously stored report citing private context.
    internal = {**items[0], "id": "old-internal", "evidence": [evidence("project-notes", secret)]}
    await setup_project.save_gaps("p", "POST /payments", [*items, internal])
    url = "/projects/p/features/POST%20__payments/gaps"
    response = await client.get(url + "/")
    data = response.json()
    assert response.status_code == 200
    assert len(data["gaps"]) == 1
    assert "business_picture" not in data["analysis"]
    assert "checked_scenarios" not in data["analysis"]
    assert secret not in json.dumps(data, ensure_ascii=False)
    response = await client.patch(url + f"/items/{items[0]['id']}", json={"status": "approved"})
    assert len(response.json()["gaps"]) == 1
    assert secret not in response.text
    stored = await setup_project.get_feature("p", "POST /payments")
    assert stored["gaps_analysis"]["business_picture"]["purpose"] == secret
    assert stored["structured_logic_json"]["logic_steps"] == []
    assert (await setup_project.get_document_source("p", "spec"))["markdown"] == PRIMARY


async def test_db_context_edit_marks_result_stale_without_context_api(client, setup_project, monkeypatch, session_factory):
    from sqlalchemy import update

    from app.models import Project
    fake_agent(monkeypatch)
    await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    async with session_factory.begin() as session:
        await session.execute(update(Project).where(Project.slug == "p").values(
            gap_context={"notes": "Назначение уточнено оператором напрямую в БД", "source_urls": []},
        ))
    data = (await client.get("/projects/p/features/POST%20__payments/gaps/")).json()
    assert data["stale"]
    assert "Назначение уточнено" not in str(data)


@pytest.mark.parametrize("status", ["pending", "clarified", "applied"])
async def test_review_only_accepts_approve_or_reject(client, setup_project, status):
    response = await client.patch("/projects/p/features/POST%20__payments/gaps/items/unknown", json={"status": status})
    assert response.status_code == 422


@pytest.mark.parametrize("change_source", [False, True])
async def test_rejected_gap_does_not_return_without_new_grounds(setup_project, monkeypatch, change_source):
    fake_agent(monkeypatch)
    first = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    first[0].update(status="rejected", analyst_text=None)
    await setup_project.save_gaps("p", "POST /payments", first)
    if change_source:
        source = await setup_project.get_document_source("p", "spec")
        source["markdown"] += "\nНесвязанный редакционный комментарий."
        source["confluence_version"] = 8
        await setup_project.save_document_source("p", "spec", source)
    final = report()
    # No existing_gap_id, different wording and location: must still respect dismissal.
    final["gaps"][0].update(question="Иная формулировка", location="Другой заголовок")
    fake_agent(monkeypatch, final)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert len(second) == 1
    assert second[0]["id"] == first[0]["id"]
    assert second[0]["status"] == "rejected" and not second[0]["needs_review"]
    assert second[0]["question"] == first[0]["question"]
    assert (await setup_project.get_feature("p", "POST /payments"))["pending_gap_count"] == 0


async def test_new_words_without_changed_sources_cannot_reopen_dismissal(setup_project, monkeypatch):
    fake_agent(monkeypatch)
    first = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    first[0].update(status="rejected")
    await setup_project.save_gaps("p", "POST /payments", first)
    final = report()
    final["gaps"][0].update(existing_gap_id=first[0]["id"], reconsideration_reason="Другое объяснение прежнего ТЗ")
    final["gaps"][0]["evidence"][0] = evidence(quote="После сохранения вернуть успех.")
    fake_agent(monkeypatch, final)
    second = await gaps.run_gaps_pipeline("p", "POST /payments", setup_project)
    assert not second[0]["needs_review"]


async def test_empty_business_impact_is_not_a_quality_finding(setup_project, monkeypatch):
    final = report()
    final["gaps"][0]["business_impact"] = " "
    fake_agent(monkeypatch, final)
    assert await gaps.run_gaps_pipeline("p", "POST /payments", setup_project) == []


@pytest.mark.parametrize("model", [GapReport, SourceSelection])
def test_gap_agent_schemas_require_all_fields_including_nullable_ones(model):
    schema = model.model_json_schema()
    for definition in [schema, *schema.get("$defs", {}).values()]:
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])
