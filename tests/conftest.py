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
    business_logic_responses: list[dict] | dict | None = None,
    business_logic_error: Exception | None = None,
) -> MagicMock:
    """Create a mock AsyncAnthropic client.

    Args:
        features_response: dict matching FeatureDetectionResult schema
        business_logic_responses: list of dicts (one per feature) or single dict (same for all)
        business_logic_error: if set, business logic calls raise this error
    """
    mock_client = MagicMock()
    call_count = {"n": 0}

    async def mock_create(**kwargs):
        # First call (has tools) = feature detection
        if "tools" in kwargs:
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

        # Subsequent calls = business logic extraction
        if business_logic_error:
            raise business_logic_error

        idx = call_count["n"]
        call_count["n"] += 1

        bl = None
        if isinstance(business_logic_responses, list):
            bl = business_logic_responses[idx] if idx < len(business_logic_responses) else {}
        elif isinstance(business_logic_responses, dict):
            bl = business_logic_responses
        else:
            bl = {"processing_steps": []}

        response = MagicMock()
        text_block = MagicMock()
        text_block.text = json.dumps(bl, ensure_ascii=False)
        response.content = [text_block]
        response.usage = MagicMock(
            input_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=800,
        )
        return response

    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=mock_create)
    return mock_client
