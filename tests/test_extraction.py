import json

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from tests.conftest import MINIMAL_PDF, make_mock_claude_client


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "extract-agent"


class TestPDFValidation:
    async def test_rejects_non_pdf_content_type(self, client, default_project_id):
        resp = await client.post(
            f"/documents/upload?project_id={default_project_id}",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Only PDF files" in resp.json()["detail"]

    async def test_rejects_invalid_pdf_magic_bytes(self, client, default_project_id):
        """File with PDF content-type but wrong magic bytes."""
        resp = await client.post(
            f"/documents/upload?project_id={default_project_id}",
            files={"file": ("fake.pdf", b"NOT-A-PDF content", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "%PDF-" in resp.json()["detail"]

    async def test_rejects_oversized_pdf(self, client, default_project_id):
        """PDF exceeding max size limit."""
        with patch("app.routers.documents.settings") as mock_settings:
            mock_settings.max_pdf_size_mb = 0  # 0 MB = reject everything
            resp = await client.post(
                f"/documents/upload?project_id={default_project_id}",
                files={"file": ("big.pdf", MINIMAL_PDF, "application/pdf")},
            )
            assert resp.status_code == 413
            assert "exceeds" in resp.json()["detail"]


class TestSingleFeatureExtraction:
    async def test_upload_pdf_single_feature(self, client, default_project_id):
        """Pipeline with no has_detailed_mapping steps — only Call 1 fires."""
        features_resp = {
            "name": "product-schedule-consumer",
            "type": "kafka_consumer",
            "confidence": 0.95,
            "summary": "Processes product schedule messages",
            "dependencies": ["product_table", "schedule-api"],
            "structured_logic": {
                "input_parameters": [],
                "output_parameters": [],
                "success_response": [],
                "error_responses": [],
                "logic_steps": [
                    {"number": "1", "text": "Receive Kafka message", "has_detailed_mapping": False, "children": []}
                ],
                "used_dependencies": [],
                "error_handling": None,
                "business_rules": [],
            },
        }
        mock = make_mock_claude_client(features_resp)

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                f"/documents/upload?project_id={default_project_id}",
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
        assert "business_logic" not in feature
        assert feature["structured_logic"] is not None
        assert feature["structured_logic"]["logic_steps"][0]["text"] == "Receive Kafka message"

    async def test_upload_pdf_with_mapping_steps_fires_call2(self, client, default_project_id):
        """Pipeline with has_detailed_mapping=True steps triggers Call 2."""
        features_resp = {
            "name": "agreement-consumer",
            "type": "kafka_consumer",
            "confidence": 0.90,
            "summary": "Processes agreement messages",
            "dependencies": [],
            "structured_logic": {
                "input_parameters": [],
                "output_parameters": [],
                "success_response": [],
                "error_responses": [],
                "logic_steps": [
                    {
                        "number": "1",
                        "text": "Receive message",
                        "has_detailed_mapping": False,
                        "children": [],
                    },
                    {
                        "number": "2",
                        "text": "Map AgreemtListMod fields",
                        "has_detailed_mapping": True,
                        "children": [],
                    },
                ],
                "used_dependencies": [],
                "error_handling": None,
                "business_rules": [],
            },
        }
        mapping_batch = {
            "mappings": [
                {
                    "step_number": "2",
                    "message_type": "AgreemtListMod",
                    "queue_or_endpoint": None,
                    "fields": [
                        {
                            "element": "agreementId",
                            "parent": None,
                            "field_type": "string",
                            "required": True,
                            "source": "Идентификатор договора",
                            "children": [],
                        }
                    ],
                }
            ]
        }
        mock = make_mock_claude_client(features_resp, mapping_batch)

        with patch("app.services.extraction._get_client", return_value=mock):
            resp = await client.post(
                f"/documents/upload?project_id={default_project_id}",
                files={"file": ("spec.pdf", MINIMAL_PDF, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"

        feature = data["features"][0]
        assert feature["status"] == "done"
        # Verify message_mapping was merged into logic_steps
        steps = feature["structured_logic"]["logic_steps"]
        step2 = next(s for s in steps if s["number"] == "2")
        assert step2["message_mapping"] is not None
        assert len(step2["message_mapping"]) == 1
        assert step2["message_mapping"][0]["element"] == "agreementId"


class TestDocumentEndpoints:
    async def test_list_documents(self, client, default_project_id):
        features_resp = {
            "name": "test-feature",
            "type": "kafka_consumer",
            "confidence": 0.9,
            "summary": "Test",
            "dependencies": [],
            "structured_logic": {
                "input_parameters": [], "output_parameters": [],
                "success_response": [], "error_responses": [],
                "logic_steps": [], "used_dependencies": [],
                "error_handling": None, "business_rules": [],
            },
        }
        mock = make_mock_claude_client(features_resp)

        with patch("app.services.extraction._get_client", return_value=mock):
            await client.post(
                f"/documents/upload?project_id={default_project_id}",
                files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            )

        resp = await client.get("/documents/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["filename"] == "test.pdf"

    async def test_get_document_by_id(self, client, default_project_id):
        features_resp = {
            "name": "test-feature",
            "type": "kafka_consumer",
            "confidence": 0.9,
            "summary": "Test",
            "dependencies": [],
            "structured_logic": {
                "input_parameters": [], "output_parameters": [],
                "success_response": [], "error_responses": [],
                "logic_steps": [], "used_dependencies": [],
                "error_handling": None, "business_rules": [],
            },
        }
        mock = make_mock_claude_client(features_resp)

        with patch("app.services.extraction._get_client", return_value=mock):
            upload_resp = await client.post(
                f"/documents/upload?project_id={default_project_id}",
                files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            )

        doc_id = upload_resp.json()["id"]
        resp = await client.get(f"/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "test.pdf"

    async def test_get_document_not_found(self, client):
        resp = await client.get("/documents/999")
        assert resp.status_code == 404
