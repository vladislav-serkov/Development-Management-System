"""Re-import with dependencies: refresh of enriched deps whose source page moved,
and the source → feature stale cascade (gated on the source page text)."""

from app.services import auto_enrich


def _feature(name, deps, **extra):
    """deps: (type, name) or (type, name, link_ids)."""
    return {
        "name": name, "display_name": name, "source_document": "doc", "type": "endpoint",
        "structured_logic_json": {"used_dependencies": [
            {"type": d[0], "name": d[1], "link_ids": list(d[2]) if len(d) > 2 else []} for d in deps
        ]},
        **extra,
    }


async def _setup(store):
    proj = await store.create_project("Refresh")
    slug = proj["slug"]
    await store.save_feature(slug, _feature("open_line", [("db_table", "credit_line")], gap_count=2, test_case_count=3))
    await store.save_feature(slug, _feature("no_analysis", [("db_table", "credit_line")]))
    await store.save_feature(slug, _feature("other", [("db_table", "payments")], gap_count=1))
    return slug


def _page(version, text_hash):
    return {"source_page_id": "200", "source_page_version": version, "source_page_url": "u",
            "source_text_hash": text_hash}


async def test_source_change_gated_on_page_text_then_structure(store):
    from app.services.enrichment import _enrichment_payload

    slug = await _setup(store)
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "enriched",
        "enriched_data": {"columns": [{"name": "id", "col_type": "bigint"}]},
        "source_page_version": 5, "source_text_hash": "h5",
    })

    # Same page text: a different LLM enrichment is noise, even a dropped column
    await _enrichment_payload(slug, "db_table", "credit_line", {"columns": []}, "DB", "t", store, _page(5, "h5"))
    assert not (await store.get_feature(slug, "open_line")).get("gaps_stale")

    # Text changed, structure the same (prose edit; type casing is noise) → nothing stale
    await _enrichment_payload(slug, "db_table", "credit_line",
                              {"columns": [{"name": "id", "col_type": "BIGINT", "description": "новое"}]},
                              "DB", "t", store, _page(6, "h6"))
    assert not (await store.get_feature(slug, "open_line")).get("gaps_stale")

    # Text changed and a column removed → the feature using the table is stale, others untouched
    await _enrichment_payload(slug, "db_table", "credit_line", {"columns": []}, "DB", "t", store, _page(6, "h6"))
    feat = await store.get_feature(slug, "open_line")
    assert feat["gaps_stale"] is True and feat["test_cases_stale"] is True
    assert feat["gaps_stale_at"] and feat["test_cases_stale_at"]
    assert feat["stale_spec_note"] == "источник «credit_line» v5 → v6"
    assert not (await store.get_feature(slug, "no_analysis")).get("gaps_stale")  # nothing to invalidate
    assert not (await store.get_feature(slug, "other")).get("gaps_stale")


async def test_document_source_any_text_change_counts_unknown_prior_does_not(store):
    from app.services.enrichment import _enrichment_payload

    proj = await store.create_project("Docs")
    slug = proj["slug"]
    await store.save_feature(slug, _feature("f", [("external_doc", "Коды ошибок")], gap_count=1))
    base = {"dep_type": "external_doc", "name": "Коды ошибок", "enrichment_status": "enriched",
            "enriched_data": {"content_html": "<p>a</p>"}}
    # Enriched before fingerprints existed: can't tell what changed → no claim
    await store.upsert_dependency(slug, "external_doc", "Коды ошибок", dict(base))
    await _enrichment_payload(slug, "external_doc", "Коды ошибок", {"content_html": "<p>b</p>"},
                              "Коды", "t", store, _page(3, "x"))
    assert not (await store.get_feature(slug, "f")).get("gaps_stale")

    await store.update_dependency(slug, "external_doc", "Коды ошибок", {"source_text_hash": "x"})
    await _enrichment_payload(slug, "external_doc", "Коды ошибок", {"content_html": "<p>b</p>"},
                              "Коды", "t", store, _page(4, "y"))
    assert (await store.get_feature(slug, "f"))["gaps_stale"] is True


async def test_reimport_refreshes_only_moved_sources(store, monkeypatch):
    proj = await store.create_project("Refresh2")
    slug = proj["slug"]
    await store.save_feature(slug, _feature("f", [
        ("db_table", "credit_line", ["L1"]), ("db_table", "payments", ["L2"]),
        ("db_table", "legacy", ["L3"]), ("db_table", "manual", ["L1"]),
    ]))
    # Another document's feature: its L1 is a different page — must not be touched
    await store.save_feature(slug, {**_feature("g", [("db_table", "foreign", ["L1"])]), "source_document": "other"})

    base = {"dep_type": "db_table", "enrichment_status": "enriched", "enriched_data": {"columns": []}}
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        **base, "name": "credit_line", "source_page_id": "200", "source_page_version": 5})
    await store.upsert_dependency(slug, "db_table", "payments", {
        **base, "name": "payments", "source_page_id": "300", "source_page_version": 7})
    # Enriched before provenance existed → refreshed once to start tracking
    await store.upsert_dependency(slug, "db_table", "legacy", {
        **base, "name": "legacy", "source_pdf_name": "the spec itself"})
    # Enriched on purpose from another page → left alone
    await store.upsert_dependency(slug, "db_table", "manual", {
        **base, "name": "manual", "source_page_id": "999", "source_page_version": 1})
    await store.upsert_dependency(slug, "db_table", "foreign", {
        "dep_type": "db_table", "name": "foreign", "enrichment_status": "stub", "link_ids": ["L1"]})

    pages = {
        "200": {"id": "200", "title": "Credit DB", "version": 6, "markdown": "", "links": [], "tables": []},
        "300": {"id": "300", "title": "Payments DB", "version": 7, "markdown": "", "links": [], "tables": []},
        "400": {"id": "400", "title": "Legacy DB", "version": 2, "markdown": "", "links": [], "tables": []},
    }

    async def fake_fetch(ref):
        return pages[ref["page_id"]]

    enriched: list[tuple[str, list[str]]] = []

    async def fake_enrich(**kw):
        enriched.append((kw["source_name"], sorted(kw["dep_names"])))
        return {n: object() for n in kw["dep_names"]}, kw["dep_names"]

    monkeypatch.setattr(auto_enrich, "fetch_page_by_ref", fake_fetch)
    monkeypatch.setattr(auto_enrich, "enrich_group_from_page", fake_enrich)

    links = [{"id": "L1", "page_id": "200"}, {"id": "L2", "page_id": "300"}, {"id": "L3", "page_id": "400"}]
    await auto_enrich.auto_enrich_from_links(slug, "doc", links, "SP", store)

    assert sorted(enriched) == [("Credit DB", ["credit_line"]), ("Legacy DB", ["legacy"])]


async def test_failed_refresh_keeps_enrichment(store, monkeypatch):
    slug = await _setup(store)
    await store.save_feature(slug, _feature("open_line", [("db_table", "credit_line", ["L1"])], gap_count=2))
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "enriched",
        "enriched_data": {"columns": []}, "source_page_id": "200", "source_page_version": 5})

    async def fake_fetch(ref):
        return {"id": "200", "title": "Credit DB", "version": 6, "markdown": "", "links": [], "tables": []}

    async def failing_enrich(**kw):
        raise RuntimeError("claude down")

    monkeypatch.setattr(auto_enrich, "fetch_page_by_ref", fake_fetch)
    monkeypatch.setattr(auto_enrich, "enrich_group_from_page", failing_enrich)
    await auto_enrich.auto_enrich_from_links(slug, "doc", [{"id": "L1", "page_id": "200"}], "SP", store)

    dep = await store.get_dependency(slug, "db_table", "credit_line")
    assert dep["enrichment_status"] == "enriched"
    assert dep["enriched_data"] == {"columns": []}


async def test_stub_upsert_during_refresh_keeps_data(store):
    slug = await _setup(store)
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "running",
        "enriched_data": {"columns": [{"name": "id"}]}})
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "stub", "enriched_data": None})
    dep = await store.get_dependency(slug, "db_table", "credit_line")
    assert dep["enriched_data"] == {"columns": [{"name": "id"}]}
    assert dep["enrichment_status"] == "running"


async def test_stale_flag_survives_run_started_before_it(store):
    from app.services.dep_impact import mark_feature_stale

    slug = await _setup(store)
    run_started = "2000-01-01T00:00:00+00:00"  # run began before the change below
    await mark_feature_stale(store, slug, "open_line", "спека v1 → v2")
    await store.clear_stale(slug, "open_line", "gaps", run_started, "gaps_run_at")
    feat = await store.get_feature(slug, "open_line")
    assert feat["gaps_stale"] is True and feat["gaps_run_at"]

    await store.clear_stale(slug, "open_line", "gaps", "2999-01-01T00:00:00+00:00", "gaps_run_at")
    assert (await store.get_feature(slug, "open_line"))["gaps_stale"] is False


async def test_dep_key_matches_normalized_rows():
    from app.services.dep_impact import dep_key

    assert dep_key("cache", "order status cache") == dep_key("cache", "order_status_cache")
    assert dep_key("external_doc", "Коды  ошибок") == ("external_doc", "коды ошибок")


async def test_check_spec_updates_reports_outdated_dep_sources(client, store, monkeypatch):
    await client.post("/projects/", json={"name": "DocDeps"})
    await store.save_document("docdeps", {
        "slug": "doc", "filename": "Спека", "status": "done",
        "source_type": "confluence", "confluence_page_id": "100",
        "confluence_url": "https://conf/spec", "confluence_version": 3,
        "uploaded_at": "2026-09-01T00:00:00+00:00",
    })
    await store.save_feature("docdeps", _feature("open_line", [("db_table", "credit_line")]))
    await store.upsert_dependency("docdeps", "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "enriched",
        "enriched_data": {"columns": []}, "source_page_id": "200", "source_page_version": 5,
    })

    from app.routers import documents as documents_router

    async def fake_meta(page_id):
        return {"id": page_id, "title": "x", "version": {"100": 3, "200": 9}[page_id]}

    monkeypatch.setattr(documents_router, "fetch_page_meta", fake_meta)

    body = (await client.post("/documents/check-spec-updates?project_slug=docdeps")).json()
    [doc] = body["documents"]
    assert doc["outdated"] is False and doc["deps_outdated"] == ["credit_line"]

    [listed] = (await client.get("/documents/?project_slug=docdeps")).json()
    assert listed["deps_outdated"] == ["credit_line"]
