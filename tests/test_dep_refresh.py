"""Re-import with dependencies: refresh of enriched deps whose source page moved,
and the source → feature stale cascade."""

from app.services import auto_enrich


def _feature(name, deps, **extra):
    return {
        "name": name, "display_name": name, "source_document": "doc", "type": "endpoint",
        "structured_logic_json": {"used_dependencies": [{"type": t, "name": n} for t, n in deps]},
        **extra,
    }


async def _setup(store):
    proj = await store.create_project("Refresh")
    slug = proj["slug"]
    await store.save_feature(slug, _feature("open_line", [("db_table", "credit_line")], gap_count=2, test_case_count=3))
    await store.save_feature(slug, _feature("no_analysis", [("db_table", "credit_line")]))
    await store.save_feature(slug, _feature("other", [("db_table", "payments")], gap_count=1))
    return slug


async def test_material_source_change_marks_dependents_stale(store):
    from app.services.enrichment import _enrichment_payload

    slug = await _setup(store)
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "enriched",
        "enriched_data": {"columns": [{"name": "id", "col_type": "bigint"}]},
        "source_page_version": 5,
    })
    page = {"source_page_id": "200", "source_page_version": 6, "source_page_url": "u"}

    # Prose-only change (no structural diff) → nothing goes stale
    await _enrichment_payload(slug, "db_table", "credit_line",
                              {"columns": [{"name": "id", "col_type": "bigint", "description": "новое"}]},
                              "DB", "t", store, page)
    assert not (await store.get_feature(slug, "open_line")).get("gaps_stale")

    # Column removed → the feature using the table is stale, others untouched
    await _enrichment_payload(slug, "db_table", "credit_line", {"columns": []}, "DB", "t", store, page)
    feat = await store.get_feature(slug, "open_line")
    assert feat["gaps_stale"] is True and feat["test_cases_stale"] is True
    assert feat["stale_spec_note"] == "источник «credit_line» v5 → v6"
    assert not (await store.get_feature(slug, "no_analysis")).get("gaps_stale")  # nothing to invalidate
    assert not (await store.get_feature(slug, "other")).get("gaps_stale")


async def test_reimport_refreshes_only_moved_sources(store, monkeypatch):
    slug = await _setup(store)
    base = {"dep_type": "db_table", "enrichment_status": "enriched", "enriched_data": {"columns": []}}
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        **base, "name": "credit_line", "link_ids": ["L1"], "source_page_id": "200", "source_page_version": 5})
    await store.upsert_dependency(slug, "db_table", "payments", {
        **base, "name": "payments", "link_ids": ["L2"], "source_page_id": "300", "source_page_version": 7})
    # Enriched before provenance existed, from the very page it links to → backfilled
    await store.upsert_dependency(slug, "db_table", "legacy", {
        **base, "name": "legacy", "link_ids": ["L3"], "source_pdf_name": "Legacy DB"})
    # Enriched on purpose from another page → left alone
    await store.upsert_dependency(slug, "db_table", "manual", {
        **base, "name": "manual", "link_ids": ["L1"], "source_page_id": "999", "source_page_version": 1})

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
    await auto_enrich.auto_enrich_from_links(slug, links, "SP", store)

    assert sorted(enriched) == [("Credit DB", ["credit_line"]), ("Legacy DB", ["legacy"])]


async def test_failed_refresh_keeps_enrichment(store, monkeypatch):
    slug = await _setup(store)
    await store.upsert_dependency(slug, "db_table", "credit_line", {
        "dep_type": "db_table", "name": "credit_line", "enrichment_status": "enriched",
        "enriched_data": {"columns": []}, "link_ids": ["L1"],
        "source_page_id": "200", "source_page_version": 5})

    async def fake_fetch(ref):
        return {"id": "200", "title": "Credit DB", "version": 6, "markdown": "", "links": [], "tables": []}

    async def failing_enrich(**kw):
        raise RuntimeError("claude down")

    monkeypatch.setattr(auto_enrich, "fetch_page_by_ref", fake_fetch)
    monkeypatch.setattr(auto_enrich, "enrich_group_from_page", failing_enrich)
    await auto_enrich.auto_enrich_from_links(slug, [{"id": "L1", "page_id": "200"}], "SP", store)

    dep = await store.get_dependency(slug, "db_table", "credit_line")
    assert dep["enrichment_status"] == "enriched"
    assert dep["enriched_data"] == {"columns": []}


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
