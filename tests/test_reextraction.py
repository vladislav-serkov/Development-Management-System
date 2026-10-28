"""Re-extraction flow: spec diff on the document, orphan marking, analysis
state carry-over and the stale cascade. Claude detection is mocked."""

import pytest

from app.schemas.extraction import (
    DetectedFeature,
    FeatureType,
    LogicStep,
    SpecColumn,
    SpecField,
    SpecTable,
    StructuredBusinessLogic,
)
from app.services import extraction


def _detected(name="GET /v1/x", required="да", endpoint="/v1/x"):
    return DetectedFeature(
        name=name,
        type=FeatureType.rest_endpoint,
        confidence=0.9,
        summary="Возвращает X",
        method="GET",
        endpoint=endpoint,
        structured_logic=StructuredBusinessLogic(
            input_tables=[
                SpecTable(
                    caption="Входные параметры",
                    columns=[SpecColumn(header="Параметр"), SpecColumn(header="Обяз.")],
                    fields=[SpecField(name="clientId", cells=["clientId", required])],
                )
            ],
            logic_steps=[LogicStep(number="1", text="Проверить клиента")],
        ),
    )


@pytest.fixture
def project(store):
    import asyncio

    return asyncio.get_event_loop()


def _as_grids(detected: list[DetectedFeature]) -> list[dict]:
    """The LLM only references tables by [TABLE:Tn] id; the grid itself is parsed
    from the page. Turn the fixtures' inline tables into parsed grids (one id per
    feature) and leave the features with id references, as the real call does."""
    grids = []
    for i, feature in enumerate(detected, start=1):
        refs = []
        for table in feature.structured_logic.input_tables:
            if not table.fields:
                continue
            tid = f"T{i}"
            grids.append({
                "id": tid,
                "context": table.caption or "",
                "headers": [c.header for c in table.columns],
                "rows": [list(f.cells) for f in table.fields],
            })
            refs.append(SpecTable(table_id=tid))
        if refs:
            feature.structured_logic.input_tables = refs
    return grids


async def _run_pipeline(store, monkeypatch, project_slug, doc_slug, detected, prev_version=None, new_version=None):
    async def fake_detect(*args, **kwargs):
        return detected

    monkeypatch.setattr(extraction, "_detect_features", fake_detect)
    if new_version is not None:
        await store.update_document(project_slug, doc_slug, {"confluence_version": new_version})
    # The endpoint value literally occurs in text_content so identity enforcement keeps it
    await extraction.run_extraction_pipeline(
        filename="doc",
        text_content="GET /v1/x и GET /v1/y — тестовое ТЗ",
        store=store,
        project_slug=project_slug,
        doc_slug=doc_slug,
        tables=_as_grids(detected),
        prev_confluence_version=prev_version,
    )


async def test_reextraction_diff_orphan_and_stale(store, monkeypatch):
    proj = await store.create_project("Re")
    slug = proj["slug"]
    await store.save_document(slug, {"slug": "doc", "filename": "doc", "status": "pending"})

    # First import: two features
    await _run_pipeline(
        store, monkeypatch, slug, "doc",
        [_detected("GET /v1/x"), _detected("GET /v1/y", endpoint="/v1/y")],
        new_version=12,
    )
    doc = await store.get_document(slug, "doc")
    assert doc["status"] == "done"
    assert "last_diff" not in doc  # first import has no prior state to diff

    # Simulate accumulated analysis on the feature that will change
    await store.save_gaps(slug, "GET /v1/x", [{"question": "?", "status": "pending"}])
    await store.update_feature(slug, "GET /v1/x", {"impl_status": "implemented"})

    # Re-import v15: /v1/x changed materially (required flag), /v1/y is gone
    await _run_pipeline(
        store, monkeypatch, slug, "doc",
        [_detected("GET /v1/x", required="нет")],
        prev_version=12, new_version=15,
    )

    doc = await store.get_document(slug, "doc")
    diff = doc["last_diff"]
    assert diff["old_version"] == 12 and diff["new_version"] == 15
    assert diff["material"] is True
    assert diff["removed"] == ["GET /v1/y"]
    [changed] = diff["changed"]
    assert changed["name"] == "GET /v1/x"
    assert changed["tables"][0]["changed_fields"][0]["changes"] == [
        {"column": "Обяз.", "old": "да", "new": "нет"}
    ]
    assert doc["latest_confluence_version"] == 15
    assert doc["spec_outdated"] is False

    # Changed feature: analysis carried over + marked stale
    feat = await store.get_feature(slug, "GET /v1/x")
    assert feat["gap_count"] == 1
    assert feat["impl_status"] == "implemented"
    assert feat["gaps_stale"] is True
    assert feat["stale_spec_note"] == "спека v12 → v15"
    assert not feat.get("test_cases_stale")  # had no test cases
    assert (await store.get_gaps(slug, "GET /v1/x")) != []

    # Removed feature: orphaned, not deleted
    gone = await store.get_feature(slug, "GET /v1/y")
    assert gone is not None
    assert gone["orphaned"] is True

    # Third import: /v1/y is back and /v1/x is unchanged → orphan flag cleared, no stale piling
    await _run_pipeline(
        store, monkeypatch, slug, "doc",
        [_detected("GET /v1/x", required="нет"), _detected("GET /v1/y", endpoint="/v1/y")],
        prev_version=15, new_version=16,
    )
    back = await store.get_feature(slug, "GET /v1/y")
    assert not back.get("orphaned")
    doc = await store.get_document(slug, "doc")
    assert doc["last_diff"]["material"] is True
    assert doc["last_diff"]["added"] == ["GET /v1/y"]  # reappearance counts as added
    assert "GET /v1/x" in doc["last_diff"]["unchanged"]


async def test_single_feature_rename_carries_analysis(store, monkeypatch):
    """One prior + one detected of the same type = rename, not remove+add."""
    proj = await store.create_project("Ren")
    slug = proj["slug"]
    await store.save_document(slug, {"slug": "doc", "filename": "doc", "status": "pending"})
    await _run_pipeline(store, monkeypatch, slug, "doc", [_detected("GET /v1/x")], new_version=12)
    await store.save_test_cases(slug, "GET /v1/x", [{"name": "tc", "status": "approved"}])

    # Re-extraction picks the other path from the same page
    await _run_pipeline(
        store, monkeypatch, slug, "doc",
        [_detected("GET /v1/y", endpoint="/v1/y")],
        prev_version=12, new_version=13,
    )

    assert await store.get_feature(slug, "GET /v1/x") is None
    feat = await store.get_feature(slug, "GET /v1/y")
    assert feat["test_case_count"] == 1
    assert not feat.get("orphaned")
    assert (await store.get_test_cases(slug, "GET /v1/y")) != []

    doc = await store.get_document(slug, "doc")
    diff = doc["last_diff"]
    assert diff["added"] == [] and diff["removed"] == []
    [changed] = diff["changed"]
    assert {"field": "endpoint", "old": "/v1/x", "new": "/v1/y"} in changed["identity"]
    # Material identity change on a feature with test cases → stale cascade
    assert feat["test_cases_stale"] is True


async def test_failed_feature_keeps_prior_record(store, monkeypatch):
    proj = await store.create_project("Fail")
    slug = proj["slug"]
    await store.save_document(slug, {"slug": "doc", "filename": "doc", "status": "pending"})
    await _run_pipeline(store, monkeypatch, slug, "doc", [_detected("GET /v1/x")])
    await store.save_gaps(slug, "GET /v1/x", [{"question": "?", "status": "pending"}])

    # Re-extraction where saving the feature blows up mid-way
    async def broken_save(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "merge_feature", broken_save)
    await _run_pipeline(store, monkeypatch, slug, "doc", [_detected("GET /v1/x")])

    feat = await store.get_feature(slug, "GET /v1/x")
    assert feat is not None  # prior record survived the failed re-extraction
    assert feat["gap_count"] == 1


async def test_check_spec_updates_endpoints(client, store, monkeypatch):
    await client.post("/projects/", json={"name": "Chk"})
    await store.save_document("chk", {
        "slug": "doc", "filename": "Спека", "status": "done",
        "source_type": "confluence", "confluence_page_id": "123",
        "confluence_url": "https://conf/x", "confluence_version": 12,
        "uploaded_at": "2026-09-01T00:00:00+00:00",
    })

    from app.routers import documents as documents_router

    async def fake_meta(page_id):
        assert page_id == "123"
        return {"id": page_id, "title": "Спека", "version": 15}

    monkeypatch.setattr(documents_router, "fetch_page_meta", fake_meta)

    r = await client.post("/documents/check-spec-updates?project_slug=chk")
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] == 1 and body["outdated"] == 1
    assert body["documents"][0]["latest_version"] == 15

    r = await client.get("/documents/?project_slug=chk")
    assert r.status_code == 200
    [doc] = r.json()
    assert doc["spec_outdated"] is True
    assert doc["confluence_version"] == 12
    assert doc["latest_confluence_version"] == 15


TEXT = "GET /v1/x и GET /v1/y — тестовое ТЗ"


async def _pipeline(store, monkeypatch, slug, detect, **kwargs):
    # Callable detectors (failing / slow) carry no tables worth diffing
    grids = _as_grids(detect) if not callable(detect) else []

    async def fake_detect(*args, **kw):
        return await detect() if callable(detect) else detect

    monkeypatch.setattr(extraction, "_detect_features", fake_detect)
    await extraction.run_extraction_pipeline(
        filename=kwargs.pop("filename", "doc"), text_content=kwargs.pop("text", TEXT),
        store=store, project_slug=slug, doc_slug="doc", tables=grids, **kwargs,
    )


async def _doc_project(store, name):
    proj = await store.create_project(name)
    await store.save_document(proj["slug"], {
        "slug": "doc", "filename": "doc", "status": "pending", "confluence_version": 12,
    })
    return proj["slug"]


async def test_unchanged_page_text_is_never_material(store, monkeypatch):
    """Same page text → LLM variance (a changed table, a missed feature) is noise."""
    slug = await _doc_project(store, "Gate")
    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x"), _detected("GET /v1/y", endpoint="/v1/y")])
    await store.save_gaps(slug, "GET /v1/x", [{"question": "?", "status": "pending"}])

    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x", required="нет")],
                    prev_confluence_version=12, prev_text=TEXT + "\n  ", new_version=12)

    diff = (await store.get_document(slug, "doc"))["last_diff"]
    assert diff["source_unchanged"] is True and diff["material"] is False
    assert diff["changed"][0]["material"] is False  # reported, but not material
    assert not (await store.get_feature(slug, "GET /v1/x")).get("gaps_stale")
    assert not (await store.get_feature(slug, "GET /v1/y")).get("orphaned")  # LLM missed it

    # The same difference on a changed page is material
    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x", required="да"), _detected("GET /v1/y", endpoint="/v1/y")],
                    prev_confluence_version=12, prev_text=TEXT + " правка", new_version=13)
    assert (await store.get_document(slug, "doc"))["last_diff"]["material"] is True
    assert (await store.get_feature(slug, "GET /v1/x"))["gaps_stale"] is True


async def test_failed_reimport_keeps_old_version(store, monkeypatch):
    slug = await _doc_project(store, "FailVer")

    async def broken():
        raise ValueError("ответ обрезан")

    source = {"markdown": "новый текст", "links": []}
    await _pipeline(store, monkeypatch, slug, broken, prev_confluence_version=12, prev_text=TEXT,
                    new_version=15, new_source=source)
    doc = await store.get_document(slug, "doc")
    assert doc["status"] == "error"
    assert doc["confluence_version"] == 12  # features still come from v12
    assert doc["spec_outdated"] is True and doc["latest_confluence_version"] == 15
    assert await store.get_document_source(slug, "doc") is None  # new text not committed

    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x")], prev_confluence_version=12,
                    prev_text=TEXT, new_version=15, new_source=source)
    doc = await store.get_document(slug, "doc")
    assert doc["status"] == "done" and doc["confluence_version"] == 15 and doc["spec_outdated"] is False
    assert (await store.get_document_source(slug, "doc"))["markdown"] == "новый текст"


async def test_analysis_written_during_llm_call_survives(store, monkeypatch):
    slug = await _doc_project(store, "Race")
    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x")])

    async def slow_detect():
        # A gaps run finishes while the LLM call is in flight
        await store.save_gaps(slug, "GET /v1/x", [{"question": "?", "status": "pending"}])
        await store.update_feature(slug, "GET /v1/x", {"impl_status": "implemented"})
        return [_detected("GET /v1/x")]

    await _pipeline(store, monkeypatch, slug, slow_detect, prev_confluence_version=12, prev_text=TEXT)
    feat = await store.get_feature(slug, "GET /v1/x")
    assert feat["gap_count"] == 1 and feat["impl_status"] == "implemented"


async def test_name_of_another_documents_feature_is_not_overwritten(store, monkeypatch):
    slug = await _doc_project(store, "Foreign")
    await store.save_feature(slug, {"name": "GET /v1/x", "source_document": "other", "type": "rest_endpoint",
                                    "gap_count": 4})
    await _pipeline(store, monkeypatch, slug, [_detected("GET /v1/x"), _detected("GET /v1/y", endpoint="/v1/y")])

    foreign = await store.get_feature(slug, "GET /v1/x")
    assert foreign["source_document"] == "other" and foreign["gap_count"] == 4
    doc = await store.get_document(slug, "doc")
    assert doc["status"] == "partial" and "other" in doc["error_message"]


async def test_multi_feature_rename_by_display_name(store, monkeypatch):
    def task(name, display):
        return DetectedFeature(
            name=name, display_name=display, type=FeatureType.scheduled_task, confidence=0.9,
            summary="s", method="SCHEDULED", schedule="ежедневно",
            structured_logic=StructuredBusinessLogic(logic_steps=[LogicStep(number="1", text="шаг")]),
        )

    slug = await _doc_project(store, "Multi")
    await _pipeline(store, monkeypatch, slug, [task("close_expired_loans", "Закрытие просроченных"),
                                               task("send_reminders", "Напоминания")])
    await store.save_test_cases(slug, "close_expired_loans", [{"name": "tc", "status": "approved"}])

    await _pipeline(store, monkeypatch, slug, [task("close-expired-loans", "Закрытие просроченных"),
                                               task("send_reminders", "Напоминания")],
                    prev_confluence_version=12, prev_text=TEXT)

    assert await store.get_feature(slug, "close_expired_loans") is None
    feat = await store.get_feature(slug, "close-expired-loans")
    assert feat["test_case_count"] == 1 and not feat.get("orphaned")


async def test_external_doc_name_comes_from_link(store, monkeypatch):
    from app.schemas.extraction import UsedDependency

    slug = await _doc_project(store, "DocName")
    detected = _detected("GET /v1/x")
    detected.structured_logic.used_dependencies = [UsedDependency(
        type="external_doc", name="PL-Авито Коды ошибок ответа", description="коды", link_ids=["L1"],
    )]
    detected.structured_logic.logic_steps[0].external_doc_refs = ["PL-Авито Коды ошибок ответа"]
    source = {"markdown": TEXT, "links": [{"id": "L1", "page_id": "5", "title": "[PL-Авито] Коды ошибок ответа"}]}
    await _pipeline(store, monkeypatch, slug, [detected], new_source=source)

    logic = (await store.get_feature(slug, "GET /v1/x"))["structured_logic_json"]
    assert logic["used_dependencies"][0]["name"] == "[PL-Авито] Коды ошибок ответа"
    assert logic["logic_steps"][0]["external_doc_refs"] == ["[PL-Авито] Коды ошибок ответа"]
    deps = await store.list_dependencies(slug)
    assert [d["name"] for d in deps["external_doc"]] == ["[PL-Авито] Коды ошибок ответа"]


async def test_dep_names_canonical_and_existing_rows_follow(store, monkeypatch):
    from app.schemas.extraction import UsedDependency

    slug = await _doc_project(store, "DepCanon")
    # Rows created by an earlier extraction under the LLM's names
    await store.upsert_dependency(slug, "external_doc", "Коды ошибок ответа", {
        "dep_type": "external_doc", "name": "Коды ошибок ответа", "enrichment_status": "enriched",
        "enriched_data": {"content_html": "<p>x</p>"}})
    await store.upsert_dependency(slug, "external_api", "GET_/v1/working-day", {
        "dep_type": "external_api", "name": "GET_/v1/working-day", "enrichment_status": "enriched",
        "enriched_data": {"endpoints": []}})

    detected = _detected("GET /v1/x")
    detected.structured_logic.used_dependencies = [
        UsedDependency(type="external_doc", name="Коды ошибок ответа", description="коды", link_ids=["L1"]),
        UsedDependency(type="external_api", name="GET /v1/working-day", description="рабочий день"),
    ]
    source = {"markdown": TEXT, "links": [{"id": "L1", "page_id": "5", "title": "[BE] Коды ошибок ответа"}]}
    await _pipeline(store, monkeypatch, slug, [detected], new_source=source)

    deps = await store.list_dependencies(slug)
    assert [(d["name"], d["enrichment_status"]) for d in deps["external_doc"]] == [("[BE] Коды ошибок ответа", "enriched")]
    assert [(d["name"], d["enrichment_status"]) for d in deps["external_api"]] == [("/v1/working-day", "enriched")]
    used = (await store.get_feature(slug, "GET /v1/x"))["structured_logic_json"]["used_dependencies"]
    assert used[1]["name"] == "/v1/working-day" and used[1]["method"] == "GET"


async def test_prior_dep_row_follows_link_when_llm_already_canonical(store, monkeypatch):
    from app.schemas.extraction import UsedDependency

    slug = await _doc_project(store, "DepPrior")
    links = [{"id": "L1", "page_id": "5", "title": "Получение остатка (GetCardBalanceList)"}]
    first = _detected("GET /v1/x")
    first.structured_logic.used_dependencies = [
        UsedDependency(type="external_api", name="GetCardBalanceList", description="api", link_ids=["L1"]),
    ]
    # Extracted before canonical names existed: the LLM name was stored as is
    monkeypatch.setattr(extraction, "_canonicalize_dep_names", lambda *a: [])
    await _pipeline(store, monkeypatch, slug, [first], new_source={"markdown": TEXT, "links": links})
    monkeypatch.undo()
    await store.update_dependency(slug, "external_api", "GetCardBalanceList", {"enrichment_status": "enriched"})

    again = _detected("GET /v1/x")
    again.structured_logic.used_dependencies = [
        UsedDependency(type="external_api", name="Получение остатка (GetCardBalanceList)", description="api", link_ids=["L1"]),
    ]
    await _pipeline(store, monkeypatch, slug, [again], prev_text=TEXT, new_source={"markdown": TEXT, "links": links})

    deps = await store.list_dependencies(slug)
    assert [(d["name"], d["enrichment_status"]) for d in deps["external_api"]] == [
        ("Получение_остатка_(GetCardBalanceList)", "enriched")
    ]


async def test_prior_dep_without_link_keys_follows_by_name(store, monkeypatch):
    """Features extracted before link keys existed: the old row is found by name."""
    from app.schemas.extraction import UsedDependency

    slug = await _doc_project(store, "DepLegacy")
    await store.save_feature(slug, {
        "name": "GET /v1/x", "source_document": "doc", "type": "rest_endpoint",
        "structured_logic_json": {"used_dependencies": [
            {"type": "external_doc", "name": "flp-order Алгоритм подсчета задолженности"},
        ]},
    })
    await store.upsert_dependency(slug, "external_doc", "flp-order Алгоритм подсчета задолженности", {
        "dep_type": "external_doc", "name": "flp-order Алгоритм подсчета задолженности",
        "enrichment_status": "enriched", "enriched_data": {"content_html": "<p>x</p>"}})

    detected = _detected("GET /v1/x")
    detected.structured_logic.used_dependencies = [UsedDependency(
        type="external_doc", name="[flp-order] Алгоритм подсчета задолженности", description="алгоритм",
    )]
    await _pipeline(store, monkeypatch, slug, [detected], prev_text=TEXT)

    deps = await store.list_dependencies(slug)
    assert [(d["name"], d["enrichment_status"]) for d in deps["external_doc"]] == [
        ("[flp-order] Алгоритм подсчета задолженности", "enriched")
    ]
