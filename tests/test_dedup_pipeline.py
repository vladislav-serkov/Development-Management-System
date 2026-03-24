"""Tests for the 3rd Claude call: dependency deduplication, gap detection, and overview generation."""
import json

import pytest
from unittest.mock import patch

from sqlalchemy import select

from app.models.document import Feature
from app.models.registry import DependencyEntry, GapEntry
from tests.conftest import MINIMAL_PDF, make_mock_claude_client


FEATURES_RESPONSE = {
    "features": [
        {
            "name": "product-schedule-consumer",
            "type": "kafka_consumer",
            "confidence": 0.95,
            "summary": "Processes product schedule messages from Kafka",
            "dependencies": ["product_table", "rbo-adapter"],
        },
        {
            "name": "product-return-consumer",
            "type": "kafka_consumer",
            "confidence": 0.90,
            "summary": "Handles product return events",
            "dependencies": ["product_table"],
        },
    ]
}

BUSINESS_LOGIC_RESPONSES = [
    {
        "processing_steps": [{"step": 1, "action": "consume from kafka"}],
        "database_operations": [{"table": "product_table", "operation": "UPDATE"}],
        "external_api_calls": [{"service": "rbo-adapter", "method": "POST"}],
    },
    {
        "processing_steps": [{"step": 1, "action": "handle return event"}],
        "database_operations": [{"table": "product_table", "operation": "SELECT"}],
    },
]

DEDUP_RESPONSE = {
    "dependencies": {
        "db": [
            {
                "name": "product_table",
                "type": "db_table",
                "columns": [
                    {"name": "id", "type": "BIGINT", "nullable": False},
                    {"name": "status", "type": "VARCHAR(50)", "nullable": True},
                ],
                "used_by_features": ["product-schedule-consumer", "product-return-consumer"],
                "known_operations": ["SELECT", "UPDATE"],
            }
        ],
        "external_api": [
            {
                "name": "rbo-adapter",
                "type": "rest_api",
                "base_url": "unknown",
                "endpoints": [
                    {"method": "POST", "path": "/api/v1/product/schedule", "description": "Schedules product"}
                ],
                "used_by_features": ["product-schedule-consumer"],
            }
        ],
        "cache": [],
    },
    "overviews": {
        "product-schedule-consumer": (
            "## product-schedule-consumer\n\n"
            "**Type:** kafka_consumer\n\n"
            "Processes product schedule messages from Kafka and updates the product_table."
        ),
        "product-return-consumer": (
            "## product-return-consumer\n\n"
            "**Type:** kafka_consumer\n\n"
            "Handles product return events and reads from product_table."
        ),
    },
    "gaps": [
        {
            "category": "API",
            "name": "rbo-adapter /api/v1/product/schedule request schema",
            "affected_features": ["product-schedule-consumer"],
            "what_missing": "Request body structure and field types not described in spec",
            "priority": "critical",
            "suggestion": {"request_body": {"product_id": "Long", "schedule_date": "LocalDate"}},
        }
    ],
}


class TestDedupPipelineIntegration:
    async def test_pipeline_completes_with_dedup(self, client):
        """Pipeline completes successfully with dedup call, returning status done."""
        mock = make_mock_claude_client(
            FEATURES_RESPONSE, BUSINESS_LOGIC_RESPONSES, dedup_response=DEDUP_RESPONSE
        )

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["feature_count"] == 2

    async def test_dependency_entries_stored_via_session(self, async_session, client):
        """DependencyEntry rows are created with correct registry_type and name."""
        mock = make_mock_claude_client(
            FEATURES_RESPONSE, BUSINESS_LOGIC_RESPONSES, dedup_response=DEDUP_RESPONSE
        )

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        doc_id = resp.json()["id"]

        entries = (await async_session.execute(
            select(DependencyEntry).where(DependencyEntry.document_id == doc_id)
        )).scalars().all()

        assert len(entries) == 2  # product_table (db) + rbo-adapter (external_api)

        names = {e.name for e in entries}
        assert "product_table" in names
        assert "rbo-adapter" in names

        types = {e.registry_type for e in entries}
        assert "db" in types
        assert "external_api" in types

    async def test_gap_entries_stored_via_session(self, async_session, client):
        """GapEntry rows are created with correct category, name, and priority."""
        mock = make_mock_claude_client(
            FEATURES_RESPONSE, BUSINESS_LOGIC_RESPONSES, dedup_response=DEDUP_RESPONSE
        )

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        doc_id = resp.json()["id"]

        gaps = (await async_session.execute(
            select(GapEntry).where(GapEntry.document_id == doc_id)
        )).scalars().all()

        assert len(gaps) == 1
        gap = gaps[0]
        assert gap.category == "API"
        assert gap.name == "rbo-adapter /api/v1/product/schedule request schema"
        assert gap.priority == "critical"

    async def test_feature_overview_md_set(self, async_session, client):
        """Feature.overview_md is set for each feature with successful extraction."""
        mock = make_mock_claude_client(
            FEATURES_RESPONSE, BUSINESS_LOGIC_RESPONSES, dedup_response=DEDUP_RESPONSE
        )

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        doc_id = resp.json()["id"]

        features = (await async_session.execute(
            select(Feature).where(Feature.document_id == doc_id)
        )).scalars().all()

        for feature in features:
            assert feature.overview_md is not None
            assert len(feature.overview_md) > 0

    async def test_overview_fallback_when_missing_from_response(self, async_session, client):
        """If a feature's overview is missing from Claude response, fallback is generated from summary."""
        dedup_with_missing_overview = {
            **DEDUP_RESPONSE,
            "overviews": {
                # Only one overview provided — product-return-consumer is missing
                "product-schedule-consumer": DEDUP_RESPONSE["overviews"]["product-schedule-consumer"],
            },
        }

        mock = make_mock_claude_client(
            FEATURES_RESPONSE, BUSINESS_LOGIC_RESPONSES, dedup_response=dedup_with_missing_overview
        )

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        doc_id = resp.json()["id"]

        features = (await async_session.execute(
            select(Feature).where(Feature.document_id == doc_id)
        )).scalars().all()

        feature_map = {f.name: f for f in features}

        # The feature with overview in Claude response gets the real overview
        assert "product-schedule-consumer" in feature_map["product-schedule-consumer"].overview_md

        # The feature missing from Claude response gets a fallback
        fallback_feature = feature_map["product-return-consumer"]
        assert fallback_feature.overview_md is not None
        # Fallback should contain the feature name or summary
        assert "product-return-consumer" in fallback_feature.overview_md or \
               "Handles product return events" in fallback_feature.overview_md

    async def test_features_with_no_business_logic_skipped_in_dedup(self, async_session, client):
        """Features with business_logic=None (failed extraction) are excluded from 3rd call context."""
        features_response = {
            "features": [
                {
                    "name": "good-consumer",
                    "type": "kafka_consumer",
                    "confidence": 0.9,
                    "summary": "Works fine",
                    "dependencies": [],
                },
                {
                    "name": "bad-consumer",
                    "type": "kafka_consumer",
                    "confidence": 0.8,
                    "summary": "Will fail extraction",
                    "dependencies": [],
                },
            ]
        }
        business_logic_responses = [
            {"processing_steps": [{"step": 1, "action": "works"}]},
            None,  # second feature fails
        ]

        dedup_for_one_feature = {
            "dependencies": {"db": [], "external_api": [], "cache": []},
            "overviews": {
                "good-consumer": "## good-consumer\n\nWorks fine.",
            },
            "gaps": [],
        }

        call_count = {"n": 0}
        from unittest.mock import MagicMock, AsyncMock
        mock_client = MagicMock()

        async def mock_create(**kwargs):
            if "tools" in kwargs:
                response = MagicMock()
                tool_block = MagicMock()
                tool_block.type = "tool_use"
                tool_block.input = features_response
                response.content = [tool_block]
                response.usage = MagicMock(
                    input_tokens=100,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                )
                return response

            idx = call_count["n"]
            call_count["n"] += 1

            # First call: good business logic
            if idx == 0:
                response = MagicMock()
                text_block = MagicMock()
                text_block.text = json.dumps(business_logic_responses[0])
                response.content = [text_block]
                response.usage = MagicMock(
                    input_tokens=50,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=100,
                )
                return response
            # Second call: bad extraction
            elif idx == 1:
                raise Exception("Claude API timeout for bad-consumer")
            # Third call: dedup (only called with 1 feature)
            else:
                response = MagicMock()
                text_block = MagicMock()
                text_block.text = json.dumps(dedup_for_one_feature)
                response.content = [text_block]
                response.usage = MagicMock(
                    input_tokens=200,
                    cache_creation_input_tokens=300,
                    cache_read_input_tokens=0,
                )
                return response

        mock_client.messages = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=mock_create)

        with patch("app.services.extraction._get_client", return_value=mock_client):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("partial.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        # Document should be partial (one feature failed)
        assert data["status"] == "partial"

        doc_id = data["id"]

        # good-consumer should have overview_md set
        features = (await async_session.execute(
            select(Feature).where(Feature.document_id == doc_id)
        )).scalars().all()
        feature_map = {f.name: f for f in features}

        assert feature_map["good-consumer"].overview_md is not None
        # bad-consumer either has fallback overview (from summary) or none
        # It must not be None if we generate fallback for all features
        assert feature_map["bad-consumer"].overview_md is not None or \
               feature_map["bad-consumer"].status == "error"
