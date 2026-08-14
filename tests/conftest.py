"""Test fixtures.

Requires a running Postgres (``docker compose up -d db``). Tests run against a
separate ``extract_agent_test`` database, created on demand, with the schema
built from the models' metadata and all tables truncated between tests.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://extract:extract@localhost:5432/extract_agent_test",
)
ADMIN_DB_URL = TEST_DB_URL.rsplit("/", 1)[0] + "/extract_agent"

os.environ["DATABASE_URL"] = TEST_DB_URL


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


async def _ensure_test_db() -> None:
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    db_name = TEST_DB_URL.rsplit("/", 1)[1]
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name})
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine():
    from app import models  # noqa: F401
    from app.db import Base

    await _ensure_test_db()
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    from app.db import Base

    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def store(session_factory):
    from app.storage import ProjectStore

    return ProjectStore(session_factory=session_factory)


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    """HTTP client over the real app, with all module-level stores pointed at the test DB."""
    import httpx

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "_session_factory", session_factory)
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
