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
