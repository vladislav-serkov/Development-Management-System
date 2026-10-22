"""Smoke tests over the HTTP API (real app, test database)."""


async def test_health(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_project_endpoints(client):
    r = await client.post("/projects/", json={"name": "Smoke"})
    assert r.status_code == 200
    slug = r.json()["slug"]
    assert slug == "smoke"

    r = await client.get("/projects/")
    assert r.status_code == 200
    assert [p["slug"] for p in r.json()] == ["smoke"]

    r = await client.get(f"/projects/{slug}")
    assert r.status_code == 200

    r = await client.patch(f"/projects/{slug}", json={"name": "Smoke 2"})
    assert r.json()["name"] == "Smoke 2"

    r = await client.get(f"/projects/{slug}/features")
    assert r.status_code == 200
    assert r.json() == []

    r = await client.delete(f"/projects/{slug}")
    assert r.status_code == 200
    r = await client.get(f"/projects/{slug}")
    assert r.status_code == 404


async def test_rules_endpoints(client):
    r = await client.get("/rules/global")
    assert r.status_code == 200
    assert r.json()["extraction"] == ""

    r = await client.put("/rules/global", json={"extraction": "x"})
    assert r.status_code == 200
    r = await client.get("/rules/global")
    assert r.json()["extraction"] == "x"


async def test_export_import_zip(client, store):
    await client.post("/projects/", json={"name": "Zip"})
    await store.save_feature("zip", {"name": "f1", "type": "unknown", "status": "done"})

    r = await client.get("/projects/zip/export/zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    files = {"file": (".context.zip", r.content, "application/zip")}
    r = await client.post("/projects/import", files=files)
    assert r.status_code == 200
    new_slug = r.json()["slug"]
    assert new_slug == "zip-2"
    assert r.json()["feature_count"] == 1


async def test_task_log_lists_every_task_kind(client, store):
    """Regression: bug_fix / autotest_gen / implement tasks (target service/repo)
    made the whole task log fail validation with HTTP 500."""
    await client.post("/projects/", json={"name": "Tasks"})
    for kind, target_type in [
        ("extraction", "document"),
        ("gaps", "feature"),
        ("implement", "service"),
        ("bug_fix", "service"),
        ("autotest_gen", "repo"),
    ]:
        task = await store.create_task("tasks", kind=kind, target_type=target_type, target_id=f"t-{kind}")
        await store.finish_task("tasks", task["id"], status="done")

    r = await client.get("/projects/tasks/tasks")
    assert r.status_code == 200
    assert {t["kind"] for t in r.json()["tasks"]} == {"extraction", "gaps", "implement", "bug_fix", "autotest_gen"}

    r = await client.get("/projects/tasks/tasks", params={"kind": "autotest_gen"})
    assert r.status_code == 200
    assert [t["target_type"] for t in r.json()["tasks"]] == ["repo"]


async def test_feature_list_serves_bug_count(client, store):
    """Regression: bug_count was kept in the feature data but dropped by the
    response model, so the sidebar/header showed «0 багов» next to real bugs."""
    await client.post("/projects/", json={"name": "Bugs"})
    await store.save_feature("bugs", {"name": "f1", "type": "unknown", "status": "done"})
    await store.save_bugs("bugs", "f1", [{"title": "a", "status": "open"}, {"title": "b", "status": "open"}])

    r = await client.get("/projects/bugs/features")
    assert r.status_code == 200
    assert r.json()[0]["bug_count"] == 2
