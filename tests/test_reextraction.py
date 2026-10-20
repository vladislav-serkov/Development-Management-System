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

    monkeypatch.setattr(store, "save_feature", broken_save)
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
