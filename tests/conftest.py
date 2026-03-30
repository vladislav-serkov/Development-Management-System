import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base, get_session
from app.main import app


@pytest.fixture
async def async_session():
    """Create a fresh in-memory SQLite database for each test."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    test_session_maker = async_sessionmaker(
        test_engine, expire_on_commit=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_maker() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def default_project_id(async_session) -> int:
    """Create a default project and return its ID for tests that need to upload documents."""
    from app.models.document import Project
    project = Project(name="default-test-project")
    async_session.add(project)
    await async_session.commit()
    await async_session.refresh(project)
    return project.id


@pytest.fixture
async def client(async_session):
    """HTTP test client with overridden DB session."""
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# Minimal valid PDF bytes for testing -- starts with %PDF- magic bytes
MINIMAL_PDF = b"%PDF-1.4 minimal test content"


def make_mock_claude_client(
    features_response: dict,
    mapping_batch: dict | None = None,
) -> MagicMock:
    """Create a mock AsyncAnthropic client for the new 1-2 call pipeline.

    Args:
        features_response: dict matching DetectedFeature schema for Call 1 (tool_use)
        mapping_batch: dict matching MappingExtractionBatch schema for Call 2 (tool_use, conditional).
                       If None and no has_detailed_mapping steps, Call 2 is never made.
    """
    mock_client = MagicMock()

    async def mock_create(**kwargs):
        tool_names = [t.get("name") for t in kwargs.get("tools", [])]

        # Call 1: detect_feature
        if "detect_feature" in tool_names:
            response = MagicMock()
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.input = features_response
            response.content = [tool_block]
            response.usage = MagicMock(
                input_tokens=1000,
                cache_creation_input_tokens=500,
                cache_read_input_tokens=0,
            )
            return response

        # Call 2: extract_message_mappings
        if "extract_message_mappings" in tool_names:
            batch = mapping_batch or {"mappings": []}
            response = MagicMock()
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.input = batch
            response.content = [tool_block]
            response.usage = MagicMock(
                input_tokens=100,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=800,
            )
            return response

        raise ValueError(f"Unexpected tools call: {tool_names}")

    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=mock_create)
    return mock_client
