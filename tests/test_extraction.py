import json

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MINIMAL_PDF, make_mock_claude_client


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "extract-agent"


class TestPDFValidation:
    async def test_rejects_non_pdf_content_type(self, client):
        resp = await client.post(
            "/documents/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Only PDF files" in resp.json()["detail"]

    async def test_rejects_invalid_pdf_magic_bytes(self, client):
        """File with PDF content-type but wrong magic bytes."""
        resp = await client.post(
            "/documents/upload",
            files={"file": ("fake.pdf", b"NOT-A-PDF content", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "%PDF-" in resp.json()["detail"]

    async def test_rejects_oversized_pdf(self, client):
        """PDF exceeding max size limit."""
        with patch("app.routers.documents.settings") as mock_settings:
            mock_settings.max_pdf_size_mb = 0  # 0 MB = reject everything
            resp = await client.post(
                "/documents/upload",
                files={"file": ("big.pdf", MINIMAL_PDF, "application/pdf")},
            )
            assert resp.status_code == 413
            assert "exceeds" in resp.json()["detail"]


class TestSingleFeatureExtraction:
    async def test_upload_pdf_single_feature(self, client):
        features_resp = {
            "features": [{
                "name": "product-schedule-consumer",
                "type": "kafka_consumer",
                "confidence": 0.95,
                "summary": "Processes product schedule messages",
                "dependencies": ["product_table", "schedule-api"],
            }]
        }
        business_logic = {
            "processing_steps": [
                {"step": 1, "action": "receive Kafka message"},
                {"step": 2, "action": "validate payload"},
                {"step": 3, "action": "update product_table"},
            ],
            "error_handling": {"on_parse_error": "log and skip"},
            "database_operations": [{"table": "product_table", "operation": "UPDATE"}],
        }
        mock = make_mock_claude_client(features_resp, business_logic)

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["feature_count"] == 1
        assert len(data["features"]) == 1

        feature = data["features"][0]
        assert feature["name"] == "product-schedule-consumer"
        assert feature["type"] == "kafka_consumer"
        assert feature["confidence"] == 0.95
        assert feature["status"] == "done"
        assert feature["business_logic"]["processing_steps"][0]["action"] == "receive Kafka message"


class TestMultiFeatureExtraction:
    async def test_upload_pdf_multiple_features(self, client):
        features_resp = {
            "features": [
                {
                    "name": "product-schedule-consumer",
                    "type": "kafka_consumer",
                    "confidence": 0.95,
                    "summary": "Processes schedule messages",
                    "dependencies": ["product_table"],
                },
                {
                    "name": "product-status-api",
                    "type": "rest_endpoint",
                    "confidence": 0.88,
                    "summary": "Returns product status",
                    "dependencies": ["product_table", "cache"],
                },
            ]
        }
        bl1 = {"processing_steps": [{"step": 1, "action": "consume from kafka"}]}
        bl2 = {"processing_steps": [{"step": 1, "action": "handle GET request"}]}
        mock = make_mock_claude_client(features_resp, [bl1, bl2])

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("multi.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["feature_count"] == 2
        assert len(data["features"]) == 2

        names = {f["name"] for f in data["features"]}
        assert names == {"product-schedule-consumer", "product-status-api"}
        types = {f["type"] for f in data["features"]}
        assert "kafka_consumer" in types
        assert "rest_endpoint" in types


class TestPartialFailure:
    async def test_partial_extraction_failure(self, client):
        """When some features extract and others fail, document status is 'partial'."""
        features_resp = {
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
                    "summary": "Will fail",
                    "dependencies": [],
                },
            ]
        }

        call_count = {"n": 0}
        mock_client = MagicMock()

        async def mock_create(**kwargs):
            if "tools" in kwargs:
                response = MagicMock()
                tool_block = MagicMock()
                tool_block.type = "tool_use"
                tool_block.input = features_resp
                response.content = [tool_block]
                response.usage = MagicMock(
                    input_tokens=100,
                    cache_creation_input_tokens=50,
                    cache_read_input_tokens=0,
                )
                return response

            idx = call_count["n"]
            call_count["n"] += 1
            if idx == 0:
                # First feature succeeds
                response = MagicMock()
                text_block = MagicMock()
                text_block.text = '{"steps": ["do thing"]}'
                response.content = [text_block]
                response.usage = MagicMock(
                    input_tokens=50,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=100,
                )
                return response
            else:
                # Second feature fails
                raise Exception("Claude API timeout")

        mock_client.messages = MagicMock()
        mock_client.messages.create = mock_create

        with patch("app.services.extraction._get_client", return_value=mock_client):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("partial.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert data["feature_count"] == 2

        statuses = {f["name"]: f["status"] for f in data["features"]}
        # One should be "done" and the other "error"
        assert "done" in statuses.values()
        assert "error" in statuses.values()


class TestMarkdownFenceHandling:
    async def test_json_wrapped_in_markdown_fences(self, client):
        """Claude sometimes wraps JSON in markdown code fences."""
        features_resp = {
            "features": [{
                "name": "fenced-consumer",
                "type": "kafka_consumer",
                "confidence": 0.9,
                "summary": "Returns fenced JSON",
                "dependencies": [],
            }]
        }

        mock_client = MagicMock()

        async def mock_create(**kwargs):
            if "tools" in kwargs:
                response = MagicMock()
                tool_block = MagicMock()
                tool_block.type = "tool_use"
                tool_block.input = features_resp
                response.content = [tool_block]
                response.usage = MagicMock(
                    input_tokens=100,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                )
                return response

            response = MagicMock()
            text_block = MagicMock()
            # JSON wrapped in markdown fences
            text_block.text = '```json\n{"processing_steps": [{"step": "fenced"}]}\n```'
            response.content = [text_block]
            response.usage = MagicMock(
                input_tokens=50,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=100,
            )
            return response

        mock_client.messages = MagicMock()
        mock_client.messages.create = mock_create

        with patch("app.services.extraction._get_client", return_value=mock_client):
            resp = await client.post(
                "/documents/upload",
                files={"file": ("fenced.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        feature = data["features"][0]
        assert feature["business_logic"]["processing_steps"][0]["step"] == "fenced"


class TestDocumentEndpoints:
    async def test_list_documents(self, client):
        features_resp = {
            "features": [{
                "name": "test-feature",
                "type": "kafka_consumer",
                "confidence": 0.9,
                "summary": "Test",
                "dependencies": [],
            }]
        }
        mock = make_mock_claude_client(features_resp, {"steps": []})

        with patch("app.services.extraction._get_client", return_value=mock):
            await client.post(
                "/documents/upload",
                files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            )

        resp = await client.get("/documents/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["filename"] == "test.pdf"

    async def test_get_document_by_id(self, client):
        features_resp = {
            "features": [{
                "name": "test-feature",
                "type": "kafka_consumer",
                "confidence": 0.9,
                "summary": "Test",
                "dependencies": [],
            }]
        }
        mock = make_mock_claude_client(features_resp, {"steps": []})

        with patch("app.services.extraction._get_client", return_value=mock):
            upload_resp = await client.post(
                "/documents/upload",
                files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            )

        doc_id = upload_resp.json()["id"]
        resp = await client.get(f"/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "test.pdf"

    async def test_get_document_not_found(self, client):
        resp = await client.get("/documents/999")
        assert resp.status_code == 404
