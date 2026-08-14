import asyncio

import pytest

from app.storage import ActiveTaskExistsError

# ---------------------------------------------------------------- projects

async def test_project_crud(store):
    proj = await store.create_project("My Project")
    assert proj["slug"] == "my-project"
    assert proj["status"] == "empty"
    assert proj["document_count"] == 0

    # slug collision
    proj2 = await store.create_project("My Project")
    assert proj2["slug"] == "my-project-2"

    got = await store.get_project("my-project")
    assert got["name"] == "My Project"

    updated = await store.update_project("my-project", "Renamed")
    assert updated["name"] == "Renamed"

    assert (await store.list_projects())[0]["slug"] == "my-project-2"  # newest first

    await store.delete_project("my-project")
    assert await store.get_project("my-project") is None
    assert await store.update_project("my-project", "x") is None


# ---------------------------------------------------------------- documents

async def test_document_flow(store):
    await store.create_project("P")
    slug = await store.make_doc_slug("p", "Spec Page.pdf")
    assert slug == "spec-page"

    doc = {"slug": slug, "project_slug": "p", "filename": "Spec Page.pdf",
           "status": "processing", "uploaded_at": "2026-01-01T00:00:00+00:00"}
    await store.save_document("p", doc)
    assert await store.make_doc_slug("p", "Spec Page.pdf") == "spec-page-2"

    got = await store.get_document("p", slug)
    assert got["filename"] == "Spec Page.pdf"
    assert got["features"] == []

    await store.save_document_source("p", slug, {"markdown": "# hi", "links": []})
    src = await store.get_document_source("p", slug)
    assert src["markdown"] == "# hi"

    updated = await store.update_document("p", slug, {"status": "done"})
    assert updated["status"] == "done"

    # project status computed from documents
    proj = await store.get_project("p")
    assert proj["status"] == "done"
    assert proj["document_count"] == 1

    docs = await store.list_documents("p")
    assert len(docs) == 1
    assert "features" not in docs[0]


# ---------------------------------------------------------------- features

FEATURE = {
    "name": "create-order",
    "type": "rest_endpoint",
    "status": "done",
    "structured_logic_json": {
        "used_dependencies": [{"type": "db_table", "name": "orders"}],
        "logic_steps": [],
    },
}


async def test_feature_crud(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))

    got = await store.get_feature("p", "create-order")
    assert got["type"] == "rest_endpoint"
    assert got["structured_logic_json"]["used_dependencies"][0]["name"] == "orders"

    updated = await store.update_feature("p", "create-order", {"summary": "s"})
    assert updated["summary"] == "s"
    assert updated["type"] == "rest_endpoint"

    renamed = await store.rename_feature("p", "create-order", "create-order-v2")
    assert renamed["name"] == "create-order-v2"
    assert await store.get_feature("p", "create-order") is None

    await store.save_feature("p", {**FEATURE, "name": "other"})
    with pytest.raises(ValueError):
        await store.rename_feature("p", "other", "create-order-v2")

    assert await store.delete_feature("p", "create-order-v2") is True
    assert await store.delete_feature("p", "create-order-v2") is False
    assert [f["name"] for f in await store.list_features("p")] == ["other"]


async def test_feature_name_with_slash(store):
    await store.create_project("P")
    await store.save_feature("p", {**FEATURE, "name": "api/v1/orders"})
    got = await store.get_feature("p", "api/v1/orders")
    assert got["name"] == "api/v1/orders"

    # The frontend addresses slash-named features by their path-safe form
    # ("/" -> "__", the old file-layout convention) — lookups must accept it.
    got = await store.get_feature("p", "api__v1__orders")
    assert got is not None and got["name"] == "api/v1/orders"

    # Exact match wins over the sanitized fallback.
    await store.save_feature("p", {**FEATURE, "name": "api__v1__orders"})
    got = await store.get_feature("p", "api__v1__orders")
    assert got["name"] == "api__v1__orders"


async def test_apply_preview(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    assert await store.get_apply_preview("p", "create-order") is None
    await store.save_apply_preview("p", "create-order", {"diff": "x"})
    assert (await store.get_apply_preview("p", "create-order"))["diff"] == "x"
    await store.delete_apply_preview("p", "create-order")
    assert await store.get_apply_preview("p", "create-order") is None


# ------------------------------------------------- gaps / test cases / bugs

async def test_gaps_counts_and_archive(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))

    gaps = [
        {"question": "q1", "status": "pending"},
        {"question": "q2", "status": "approved"},
        {"question": "q3", "status": "pending", "archived": True},
    ]
    await store.save_gaps("p", "create-order", gaps)

    assert len(await store.get_gaps("p", "create-order")) == 2
    assert len(await store.get_gaps("p", "create-order", include_archived=True)) == 3

    feat = await store.get_feature("p", "create-order")
    assert feat["gap_count"] == 2  # archived excluded
    assert feat["pending_gap_count"] == 1

    # order is preserved
    assert [g["question"] for g in await store.get_gaps("p", "create-order", include_archived=True)] == [
        "q1", "q2", "q3",
    ]


async def test_test_cases_and_bugs_counts(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))

    await store.save_test_cases("p", "create-order", [
        {"name": "t1", "status": "pending"}, {"name": "t2", "status": "done"},
    ])
    await store.save_bugs("p", "create-order", [{"title": "b1"}])

    feat = await store.get_feature("p", "create-order")
    assert feat["test_case_count"] == 2
    assert feat["pending_test_case_count"] == 1
    assert feat["bug_count"] == 1

    assert (await store.get_test_cases("p", "create-order"))[0]["name"] == "t1"
    assert (await store.get_bugs("p", "create-order"))[0]["title"] == "b1"


async def test_update_feature_redirects_gaps(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    await store.update_feature("p", "create-order", {"gaps": [{"question": "q", "status": "pending"}]})
    assert len(await store.get_gaps("p", "create-order")) == 1
    feat = await store.get_feature("p", "create-order")
    assert feat["gap_count"] == 1
    assert "gaps" not in feat


async def test_delete_feature_cascades_items(store):
    await store.create_project("P")
    await store.save_feature("p", dict(FEATURE))
    await store.save_gaps("p", "create-order", [{"question": "q"}])
    await store.delete_feature("p", "create-order")
    assert await store.get_gaps("p", "create-order") == []


# ---------------------------------------------------------------- deps

async def test_dependency_upsert_ci_and_no_downgrade(store):
    await store.create_project("P")
    await store.upsert_dependency("p", "db_table", "Orders", {
        "name": "Orders", "enrichment_status": "enriched", "enriched_data": {"columns": []},
    })

    # case-insensitive match; stub must not downgrade enriched
    result = await store.upsert_dependency("p", "db_table", "orders", {
        "name": "orders", "enrichment_status": "stub",
    })
    assert result["enrichment_status"] == "enriched"
    assert result["name"] == "orders"  # re-keyed to incoming case

    deps = await store.list_dependencies("p")
    assert len(deps["db_table"]) == 1

    got = await store.get_dependency("p", "db_table", "ORDERS")
    assert got is not None
    assert got["dep_type"] == "db_table"

    updated = await store.update_dependency("p", "db_table", "orders", {"source_pdf_name": "x"})
    assert updated["source_pdf_name"] == "x"

    with pytest.raises(ValueError):
        await store.upsert_dependency("p", "nope", "x", {})
    assert await store.get_dependency("p", "nope", "x") is None

    assert await store.delete_dependency("p", "db_table", "orders") is True
    assert await store.delete_dependency("p", "db_table", "orders") is False


async def test_rename_dependency_cascades_to_features(store):
    await store.create_project("P")
    await store.upsert_dependency("p", "db_table", "orders", {"name": "orders"})
    await store.save_feature("p", dict(FEATURE))

    renamed = await store.rename_dependency("p", "db_table", "orders", "orders_v2")
    assert renamed["name"] == "orders_v2"

    feat = await store.get_feature("p", "create-order")
    assert feat["structured_logic_json"]["used_dependencies"][0]["name"] == "orders_v2"

    # conflict check
    await store.upsert_dependency("p", "db_table", "other", {"name": "other"})
    with pytest.raises(ValueError):
        await store.rename_dependency("p", "db_table", "orders_v2", "OTHER")

    assert await store.rename_dependency("p", "db_table", "missing", "x") is None


# ---------------------------------------------------------------- rules

async def test_rules(store):
    rules = await store.get_global_rules()
    assert rules == {"extraction": "", "gaps": "", "test_cases": "", "bugs": "", "enrichment": ""}

    saved = await store.save_global_rules({"extraction": "be careful", "junk": "dropped"})
    assert saved["extraction"] == "be careful"
    assert "junk" not in saved
    assert (await store.get_global_rules())["extraction"] == "be careful"

    await store.create_project("P")
    assert (await store.get_project_rules("p"))["gaps"] == ""
    await store.save_project_rules("p", {"gaps": "g"})
    assert (await store.get_project_rules("p"))["gaps"] == "g"
    # global unaffected
    assert (await store.get_global_rules())["gaps"] == ""


# ---------------------------------------------------------------- tasks

async def test_task_lifecycle(store):
    await store.create_project("P")
    task = await store.create_task("p", kind="gaps", target_type="feature", target_id="f1")
    assert task["status"] == "running"

    active = await store.get_active_task("p", kind="gaps", target_id="f1")
    assert active["id"] == task["id"]
    assert await store.get_active_task("p", kind="gaps", target_id="f2") is None

    finished = await store.finish_task("p", task["id"], status="done")
    assert finished["status"] == "done"
    assert finished["duration_ms"] is not None
    assert await store.get_active_task("p", kind="gaps", target_id="f1") is None

    tasks = await store.list_tasks("p", kind="gaps")
    assert len(tasks) == 1
    assert await store.finish_task("p", "no-such-id", status="done") is None


async def test_one_running_task_per_target(store):
    await store.create_project("P")
    await store.create_task("p", kind="gaps", target_type="feature", target_id="f1")
    with pytest.raises(ActiveTaskExistsError):
        await store.create_task("p", kind="gaps", target_type="feature", target_id="f1")
    # different target / kind is fine
    await store.create_task("p", kind="gaps", target_type="feature", target_id="f2")
    await store.create_task("p", kind="test_cases", target_type="feature", target_id="f1")


async def test_concurrent_task_creation_race(store):
    await store.create_project("P")

    async def make():
        return await store.create_task("p", kind="gaps", target_type="feature", target_id="f1")

    results = await asyncio.gather(make(), make(), return_exceptions=True)
    ok = [r for r in results if isinstance(r, dict)]
    errors = [r for r in results if isinstance(r, ActiveTaskExistsError)]
    assert len(ok) == 1
    assert len(errors) == 1
