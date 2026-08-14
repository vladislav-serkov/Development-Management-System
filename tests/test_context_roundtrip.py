"""Round-trip test for the .context serializer — the DMS interop contract."""

import json
from pathlib import Path

from app.services.context_serializer import dump_project, export_context_dir, load_context_project


async def _build_project(store) -> str:
    proj = await store.create_project("Round Trip")
    slug = proj["slug"]
    await store.save_feature(slug, {
        "name": "create-order",
        "type": "rest_endpoint",
        "status": "done",
        "confidence": 0.9,
        "summary": "Creates an order",
        "source_document": "spec",
        "source": {"kind": "pdf", "document": "spec", "file": None, "line": None},
        "structured_logic_json": {
            "used_dependencies": [{"type": "db_table", "name": "orders"}],
            "logic_steps": [{"number": 1, "children": []}],
        },
    })
    await store.save_gaps(slug, "create-order", [{"question": "q1", "status": "pending"}])
    await store.save_test_cases(slug, "create-order", [{"name": "t1", "status": "pending"}])
    await store.save_bugs(slug, "create-order", [{"title": "b1"}])
    await store.upsert_dependency(slug, "db_table", "orders", {
        "name": "orders", "enrichment_status": "enriched",
        "enriched_data": {"columns": [{"name": "id", "is_pk": True}]},
    })
    await store.save_project_rules(slug, {"extraction": "rule text"})
    return slug


async def test_dump_layout(store):
    slug = await _build_project(store)
    files = await dump_project(store, slug)
    assert set(files) == {
        "project.json",
        "rules.json",
        "features/create-order/feature.json",
        "gaps/create-order.json",
        "test-cases/create-order.json",
        "bugs/create-order.json",
        "dependencies/db_tables.json",
    }
    feature = json.loads(files["features/create-order/feature.json"])
    # UI fields stripped, canonical key renamed
    assert "status" not in feature
    assert "confidence" not in feature
    assert "structured_logic" in feature and "structured_logic_json" not in feature

    deps = json.loads(files["dependencies/db_tables.json"])
    assert "enrichment_status" not in deps["orders"]
    assert deps["orders"]["enriched_data"]["columns"][0]["is_pk"] is True


async def test_round_trip(store, tmp_path: Path):
    slug = await _build_project(store)
    context_dir = tmp_path / ".context"
    await export_context_dir(store, slug, context_dir)

    warnings: list[str] = []
    new_slug, adapted, _ = await load_context_project(store, context_dir, warnings=warnings)
    assert adapted == 1
    assert warnings == []
    assert new_slug != slug

    feat = await store.get_feature(new_slug, "create-order")
    assert feat["structured_logic_json"]["used_dependencies"][0]["name"] == "orders"
    assert feat["summary"] == "Creates an order"
    assert feat["gap_count"] == 1

    assert (await store.get_gaps(new_slug, "create-order"))[0]["question"] == "q1"
    assert (await store.get_test_cases(new_slug, "create-order"))[0]["name"] == "t1"
    assert (await store.get_bugs(new_slug, "create-order"))[0]["title"] == "b1"

    dep = await store.get_dependency(new_slug, "db_table", "orders")
    assert dep["enriched_data"]["columns"][0]["name"] == "id"
    # inline-enrichment wrap must mark it enriched again
    assert dep["enrichment_status"] == "enriched"

    rules = await store.get_project_rules(new_slug)
    assert rules["extraction"] == "rule text"

    # second dump equals first (modulo project.json identity; key order may differ)
    first = await dump_project(store, slug)
    second = await dump_project(store, new_slug)
    del first["project.json"], second["project.json"]
    assert set(first) == set(second)
    for path in first:
        assert json.loads(first[path]) == json.loads(second[path]), path
