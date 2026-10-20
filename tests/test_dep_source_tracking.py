"""Dependency source tracking: enrichment provenance, enrichment diff,
and the version probe over dependency source pages."""

from app.services.spec_diff import diff_enriched_data


class TestDiffEnrichedData:
    def test_db_table_column_changes(self):
        old = {
            "table_name": "credit_line",
            "columns": [
                {"name": "id", "col_type": "bigint", "nullable": False, "is_pk": True, "fk_references": None},
                {"name": "limit", "col_type": "numeric", "nullable": True, "is_pk": False, "fk_references": None},
            ],
        }
        new = {
            "table_name": "credit_line",
            "columns": [
                {"name": "id", "col_type": "bigint", "nullable": False, "is_pk": True, "fk_references": None},
                {"name": "limit", "col_type": "numeric(19,2)", "nullable": True, "is_pk": False, "fk_references": None},
                {"name": "mrp_day", "col_type": "int", "nullable": True, "is_pk": False, "fk_references": None},
            ],
        }
        diff = diff_enriched_data("db_table", old, new)
        assert diff["columns"]["added"] == ["mrp_day"]
        assert diff["columns"]["removed"] == []
        [changed] = diff["columns"]["changed"]
        assert changed["name"] == "limit"
        assert changed["changes"] == [{"field": "col_type", "old": "numeric", "new": "numeric(19,2)"}]

    def test_removed_column_is_reported(self):
        old = {"columns": [{"name": "legacy_flag", "col_type": "bool"}]}
        new = {"columns": []}
        diff = diff_enriched_data("db_table", old, new)
        assert diff["columns"]["removed"] == ["legacy_flag"]

    def test_identical_data_diffs_to_none(self):
        data = {"columns": [{"name": "id", "col_type": "bigint"}]}
        assert diff_enriched_data("db_table", data, dict(data)) is None

    def test_external_api_endpoints(self):
        old = {"endpoints": [{"method": "get", "path": "/v1/wallet", "description": ""}]}
        new = {"endpoints": [{"method": "GET", "path": "/v1/wallet", "description": ""},
                             {"method": "POST", "path": "/v1/wallet/close", "description": ""}]}
        diff = diff_enriched_data("external_api", old, new)
        assert diff["endpoints"]["added"] == ["POST /v1/wallet/close"]
        assert diff["endpoints"]["removed"] == []  # method casing is normalized

    def test_kafka_nested_fields_flatten(self):
        old = {"message_fields": [{"element": "payload", "field_type": "object", "children": [
            {"element": "amount", "field_type": "number", "children": []}]}]}
        new = {"message_fields": [{"element": "payload", "field_type": "object", "children": [
            {"element": "amount", "field_type": "string", "children": []}]}]}
        diff = diff_enriched_data("kafka_topic", old, new)
        [changed] = diff["message_fields"]["changed"]
        assert changed["name"] == "payload.amount"
        assert changed["changes"] == [{"field": "field_type", "old": "number", "new": "string"}]

    def test_external_doc_content_change(self):
        assert diff_enriched_data("external_doc", {"content_html": "<p>a</p>"}, {"content_html": "<p>b</p>"}) == {
            "content_changed": True
        }
        assert diff_enriched_data("external_doc", {"content_html": "<p>a</p>"}, {"content_html": " <p>a</p> "}) is None

    def test_missing_sides_diff_to_none(self):
        assert diff_enriched_data("db_table", None, {"columns": []}) is None
        assert diff_enriched_data("db_table", {"columns": []}, None) is None


async def test_enrichment_payload_provenance_and_diff(store):
    from app.services.enrichment import _enrichment_payload

    proj = await store.create_project("Prov")
    slug = proj["slug"]
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line",
        "enrichment_status": "enriched",
        "enriched_data": {"columns": [{"name": "id", "col_type": "bigint"}]},
        "source_page_version": 5, "source_text_hash": "old",
    })

    source_page = {"source_page_id": "777", "source_page_version": 8, "source_page_url": "https://conf/x",
                   "source_text_hash": "new"}
    payload = await _enrichment_payload(
        slug, "db_table", "credit_line",
        {"columns": [{"name": "id", "col_type": "bigint"}, {"name": "mrp_day", "col_type": "int"}]},
        "DB page", "2026-09-22T00:00:00+00:00", store, source_page,
    )

    assert payload["source_page_id"] == "777"
    assert payload["source_page_version"] == 8
    assert payload["latest_source_version"] == 8
    assert payload["source_outdated"] is False
    diff = payload["last_source_diff"]
    assert diff["old_version"] == 5 and diff["new_version"] == 8
    assert diff["columns"]["added"] == ["mrp_day"]

    # Unchanged re-enrichment clears the stale diff
    payload2 = await _enrichment_payload(
        slug, "db_table", "credit_line",
        {"columns": [{"name": "id", "col_type": "bigint"}]},
        "DB page", "2026-09-22T00:00:00+00:00", store, source_page,
    )
    assert payload2["last_source_diff"] is None


async def test_check_spec_updates_covers_dependencies(client, store, monkeypatch):
    await client.post("/projects/", json={"name": "DepChk"})
    await store.save_document("depchk", {
        "slug": "doc", "filename": "Спека", "status": "done",
        "source_type": "confluence", "confluence_page_id": "100",
        "confluence_url": "https://conf/spec", "confluence_version": 3,
        "uploaded_at": "2026-09-01T00:00:00+00:00",
    })
    await store.upsert_dependency("depchk", "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line",
        "enrichment_status": "enriched",
        "enriched_data": {"columns": []},
        "source_page_id": "200", "source_page_version": 5,
        "source_page_url": "https://conf/db",
    })
    # A stub dep without provenance must be skipped
    await store.upsert_dependency("depchk", "cache", "hazelcast", {
        "dep_type": "cache", "name": "hazelcast", "enrichment_status": "stub",
    })

    from app.routers import documents as documents_router

    versions = {"100": 3, "200": 9}

    async def fake_meta(page_id):
        return {"id": page_id, "title": "x", "version": versions[page_id]}

    monkeypatch.setattr(documents_router, "fetch_page_meta", fake_meta)

    r = await client.post("/documents/check-spec-updates?project_slug=depchk")
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] == 1 and body["outdated"] == 0  # spec page unchanged
    assert body["dependencies_checked"] == 1 and body["dependencies_outdated"] == 1
    [dep_check] = body["dependencies"]
    assert dep_check["name"] == "credit_line"
    assert dep_check["current_version"] == 5 and dep_check["latest_version"] == 9

    # Persisted on the dependency and served by the API
    r = await client.get("/projects/depchk/dependencies/")
    dep = next(d for d in r.json() if d["name"] == "credit_line")
    assert dep["source_outdated"] is True
    assert dep["latest_source_version"] == 9
    assert dep["source_page_url"] == "https://conf/db"
