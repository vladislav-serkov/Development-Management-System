"""Tests for .context/ export service and export endpoint (Plan 02-02)."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.models.document import Document, Feature
from app.services.export import export_feature_to_context


# ---------------------------------------------------------------------------
# Test export_feature_to_context creates the correct file structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_creates_structured_logic_json(tmp_path):
    """Test: export creates .context/features/{name}/structured-logic.json"""
    structured_logic = {"logic_steps": [{"number": "1", "text": "read message", "children": []}]}

    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        structured_logic=structured_logic,
    )

    sl_path = tmp_path / ".context" / "features" / "product-schedule-consumer" / "structured-logic.json"
    assert sl_path.exists()
    parsed = json.loads(sl_path.read_text())
    assert parsed["logic_steps"] == structured_logic["logic_steps"]


@pytest.mark.asyncio
async def test_export_repeated_feature_overwrites_files(tmp_path):
    """Test: repeated export of same feature overwrites feature files, preserves others."""
    # First export of feature-a
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        structured_logic={"version": 1},
    )

    # Export feature-b (different feature)
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-b",
        structured_logic={"version": 1},
    )

    # Second export of feature-a (should overwrite feature-a files, not feature-b)
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        structured_logic={"version": 2},
    )

    # feature-a files should be overwritten
    sl_a = json.loads((tmp_path / ".context" / "features" / "feature-a" / "structured-logic.json").read_text())
    assert sl_a["version"] == 2

    # feature-b files should be preserved
    assert (tmp_path / ".context" / "features" / "feature-b" / "structured-logic.json").exists()
    sl_b = json.loads((tmp_path / ".context" / "features" / "feature-b" / "structured-logic.json").read_text())
    assert sl_b["version"] == 1


@pytest.mark.asyncio
async def test_export_returns_files_written_list(tmp_path):
    """export_feature_to_context returns a list of written file paths."""
    files_written = await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        structured_logic={"logic_steps": []},
    )

    assert isinstance(files_written, list)
    assert len(files_written) >= 1  # structured-logic.json
    # All paths should be relative strings
    for p in files_written:
        assert isinstance(p, str)
        assert not p.startswith("/")  # relative paths


# ---------------------------------------------------------------------------
# Integration tests: POST /documents/{id}/export endpoint
# ---------------------------------------------------------------------------


async def _create_test_document_with_features(session, tmp_path_for_export=None):
    """Helper: create a Project, Document with one Feature in DB."""
    from app.models.document import Project
    project = Project(name="test-project")
    session.add(project)
    await session.flush()

    doc = Document(
        filename="test-spec.pdf",
        pdf_size_bytes=1024,
        status="done",
        feature_count=1,
        project_id=project.id,
    )
    session.add(doc)
    await session.flush()

    feature = Feature(
        document_id=doc.id,
        name="product-schedule-consumer",
        type="kafka_consumer",
        confidence=0.95,
        summary="Processes product schedule Kafka messages",
        status="done",
        structured_logic_json=json.dumps({"logic_steps": [{"number": "1", "text": "read", "children": []}]}),
        extracted_at=datetime.utcnow(),
    )
    session.add(feature)

    await session.flush()
    return doc


@pytest.mark.asyncio
async def test_export_endpoint_success(client, async_session, tmp_path):
    """POST /documents/{id}/export returns 200 with exported_features and files_written."""
    doc = await _create_test_document_with_features(async_session)
    await async_session.commit()

    target_dir = tmp_path / "myservice"
    target_dir.mkdir()

    response = await client.post(
        f"/documents/{doc.id}/export",
        json={"target_path": str(target_dir)},
    )

    assert response.status_code == 200
    data = response.json()
    assert "product-schedule-consumer" in data["exported_features"]
    assert len(data["files_written"]) > 0
    assert data["target_path"] == str(target_dir)

    # Verify structured-logic.json exists on disk
    sl_path = target_dir / ".context" / "features" / "product-schedule-consumer" / "structured-logic.json"
    assert sl_path.exists()


@pytest.mark.asyncio
async def test_export_endpoint_404_document_not_found(client):
    """POST /documents/{id}/export returns 404 for non-existent document."""
    response = await client.post(
        "/documents/9999/export",
        json={"target_path": "/tmp/myservice"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_endpoint_400_document_not_done(client, async_session, tmp_path):
    """POST /documents/{id}/export returns 400 when document status is 'processing'."""
    from app.models.document import Project
    project = Project(name="test-project-processing")
    async_session.add(project)
    await async_session.flush()
    doc = Document(
        filename="test.pdf",
        pdf_size_bytes=512,
        status="processing",
        feature_count=0,
        project_id=project.id,
    )
    async_session.add(doc)
    await async_session.commit()

    response = await client.post(
        f"/documents/{doc.id}/export",
        json={"target_path": str(tmp_path)},
    )
    assert response.status_code == 400
    assert "processing" in response.json()["detail"]


@pytest.mark.asyncio
async def test_export_endpoint_400_relative_path(client, async_session, tmp_path):
    """POST /documents/{id}/export returns 400 for relative target_path."""
    doc = await _create_test_document_with_features(async_session)
    await async_session.commit()

    response = await client.post(
        f"/documents/{doc.id}/export",
        json={"target_path": "relative/path/to/service"},
    )
    assert response.status_code == 400
    assert "absolute" in response.json()["detail"].lower()
