"""Web UI login: protected API, login/logout flow, operator user management."""

import pytest

from app.config import settings
from app.services.auth import AuthStore, hash_password, verify_password


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)


@pytest.fixture
def auth_store(session_factory):
    return AuthStore(session_factory=session_factory)


def test_password_hash_roundtrip():
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "garbage")


async def test_auth_disabled_keeps_api_open(client):
    r = await client.get("/projects/")
    assert r.status_code == 200
    assert (await client.get("/auth/me")).json() == {"auth_enabled": False, "username": None}


async def test_api_requires_login(client, auth_on, auth_store):
    assert (await client.get("/projects/")).status_code == 401
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/")).status_code == 200  # health stays public

    await auth_store.create_user("alice", "pw")
    r = await client.post("/auth/login", json={"username": "alice", "password": "nope"})
    assert r.status_code == 401

    r = await client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert (await client.get("/projects/")).status_code == 200
    assert (await client.get("/auth/me")).json()["username"] == "alice"

    await client.post("/auth/logout")
    assert (await client.get("/projects/")).status_code == 401


async def test_password_change_drops_sessions(client, auth_on, auth_store):
    await auth_store.create_user("bob", "old")
    await client.post("/auth/login", json={"username": "bob", "password": "old"})
    assert (await client.get("/projects/")).status_code == 200

    assert await auth_store.set_password("bob", "new")
    assert (await client.get("/projects/")).status_code == 401
    assert await auth_store.authenticate("bob", "old") is None
    assert await auth_store.authenticate("bob", "new") is not None


async def test_user_management(auth_store):
    assert await auth_store.create_user("carol", "pw")
    assert not await auth_store.create_user("carol", "pw2")
    assert [u["username"] for u in await auth_store.list_users()] == ["carol"]
    assert await auth_store.delete_user("carol")
    assert not await auth_store.delete_user("carol")
    assert not await auth_store.set_password("carol", "x")


async def test_login_throttled_after_repeated_failures(client, auth_on, auth_store):
    await auth_store.create_user("dave", "pw")
    for _ in range(10):
        await client.post("/auth/login", json={"username": "dave", "password": "bad"})
    r = await client.post("/auth/login", json={"username": "dave", "password": "pw"})
    assert r.status_code == 429


async def test_login_through_single_origin_serve(session_factory, auth_on, auth_store, monkeypatch, tmp_path):
    """app.serve mounts the API at /api — the login endpoints must stay public there too."""
    import httpx

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "_session_factory", session_factory)
    (tmp_path / "index.html").write_text("<html>spa</html>")
    from fastapi import FastAPI

    from app.main import app as api_app
    from app.serve import SPAStaticFiles

    root = FastAPI()
    root.mount("/api", api_app)
    root.mount("/", SPAStaticFiles(directory=tmp_path, html=True))

    await auth_store.create_user("erin", "pw")
    transport = httpx.ASGITransport(app=root)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/projects/some/deep/route")).text == "<html>spa</html>"
        assert (await c.get("/api/projects/")).status_code == 401
        r = await c.post("/api/auth/login", json={"username": "erin", "password": "pw"})
        assert r.status_code == 200
        assert (await c.get("/api/projects/")).status_code == 200
