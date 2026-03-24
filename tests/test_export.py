"""Tests for .context/ export service (Plan 02-02)."""
import json
from pathlib import Path

import pytest

from app.services.export import (
    _merge_registry_data,
    _write_gaps_md,
    export_feature_to_context,
)


# ---------------------------------------------------------------------------
# Unit tests for _merge_registry_data
# ---------------------------------------------------------------------------


def test_merge_registry_data_unions_used_by_features():
    existing = {"name": "product_table", "used_by_features": ["feature-a"]}
    new_data = {"name": "product_table", "used_by_features": ["feature-b"]}

    result = _merge_registry_data(existing, new_data, "feature-c")

    assert sorted(result["used_by_features"]) == ["feature-a", "feature-b", "feature-c"]


def test_merge_registry_data_new_value_wins_over_empty():
    existing = {"name": "product_table", "base_url": "", "used_by_features": []}
    new_data = {"name": "product_table", "base_url": "https://rbo.example.com", "used_by_features": []}

    result = _merge_registry_data(existing, new_data, "feature-x")

    assert result["base_url"] == "https://rbo.example.com"


def test_merge_registry_data_existing_value_preserved_when_new_is_empty():
    existing = {"name": "product_table", "base_url": "https://existing.example.com", "used_by_features": []}
    new_data = {"name": "product_table", "base_url": "", "used_by_features": []}

    result = _merge_registry_data(existing, new_data, "feature-x")

    assert result["base_url"] == "https://existing.example.com"


# ---------------------------------------------------------------------------
# Test export_feature_to_context creates the correct file structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_creates_overview_md(tmp_path):
    """Test 1: export creates .context/features/{name}/overview.md"""
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        overview_md="## product-schedule-consumer\n\nHandles Kafka messages.",
        business_logic={"processing_steps": ["step1", "step2"]},
        dependencies=[],
        gaps=[],
    )

    overview_path = tmp_path / ".context" / "features" / "product-schedule-consumer" / "overview.md"
    assert overview_path.exists()
    assert "product-schedule-consumer" in overview_path.read_text()


@pytest.mark.asyncio
async def test_export_creates_business_logic_json(tmp_path):
    """Test 2: export creates .context/features/{name}/business-logic.json"""
    business_logic = {"processing_steps": ["read message", "validate", "save to DB"]}

    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        overview_md="Overview text",
        business_logic=business_logic,
        dependencies=[],
        gaps=[],
    )

    bl_path = tmp_path / ".context" / "features" / "product-schedule-consumer" / "business-logic.json"
    assert bl_path.exists()
    parsed = json.loads(bl_path.read_text())
    assert parsed["processing_steps"] == business_logic["processing_steps"]


@pytest.mark.asyncio
async def test_export_creates_db_dependency_file(tmp_path):
    """Test 3: export creates .context/db/{name}.json for db dependencies"""
    dep = {
        "registry_type": "db",
        "name": "product_table",
        "data": {
            "name": "product_table",
            "type": "db_table",
            "columns": [{"name": "id", "type": "BIGINT"}],
            "used_by_features": [],
        },
    }

    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        overview_md="Overview text",
        business_logic={},
        dependencies=[dep],
        gaps=[],
    )

    db_path = tmp_path / ".context" / "db" / "product_table.json"
    assert db_path.exists()
    parsed = json.loads(db_path.read_text())
    assert parsed["name"] == "product_table"
    assert "product-schedule-consumer" in parsed["used_by_features"]


@pytest.mark.asyncio
async def test_export_merges_registry_additively(tmp_path):
    """Test 4: second export merges used_by_features into existing registry file (additive, D-10)."""
    dep_a = {
        "registry_type": "db",
        "name": "product_table",
        "data": {
            "name": "product_table",
            "type": "db_table",
            "columns": [{"name": "id", "type": "BIGINT"}],
            "used_by_features": [],
        },
    }
    dep_b = {
        "registry_type": "db",
        "name": "product_table",
        "data": {
            "name": "product_table",
            "type": "db_table",
            "columns": [{"name": "id", "type": "BIGINT"}, {"name": "status", "type": "VARCHAR"}],
            "used_by_features": [],
        },
    }

    # Export feature-a
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        overview_md="Feature A overview",
        business_logic={},
        dependencies=[dep_a],
        gaps=[],
    )

    # Export feature-b (same registry file)
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-b",
        overview_md="Feature B overview",
        business_logic={},
        dependencies=[dep_b],
        gaps=[],
    )

    db_path = tmp_path / ".context" / "db" / "product_table.json"
    parsed = json.loads(db_path.read_text())

    # Both features should be in used_by_features
    assert "feature-a" in parsed["used_by_features"]
    assert "feature-b" in parsed["used_by_features"]


@pytest.mark.asyncio
async def test_export_writes_gaps_md_grouped_by_category(tmp_path):
    """Test 5: export writes gaps.md from ALL document gaps grouped by category."""
    gaps = [
        {
            "category": "API",
            "name": "rbo-adapter request schema",
            "affected_features": ["feature-a"],
            "what_missing": "Request body structure",
            "priority": "critical",
            "suggestion": {"product_id": "Long"},
        },
        {
            "category": "DB",
            "name": "product_table status field",
            "affected_features": ["feature-b"],
            "what_missing": "Status field enum values not documented",
            "priority": "medium",
            "suggestion": None,
        },
    ]

    files_written = await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        overview_md="Overview",
        business_logic={},
        dependencies=[],
        gaps=gaps,
    )

    gaps_path = tmp_path / ".context" / "gaps.md"
    assert gaps_path.exists()
    content = gaps_path.read_text()

    assert "External API Gaps" in content
    assert "rbo-adapter request schema" in content
    assert "Database Gaps" in content
    assert "product_table status field" in content
    assert "critical" in content
    assert "medium" in content


@pytest.mark.asyncio
async def test_export_repeated_feature_overwrites_files(tmp_path):
    """Test 6: repeated export of same feature overwrites feature files, preserves others."""
    # First export of feature-a
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        overview_md="Original overview",
        business_logic={"version": 1},
        dependencies=[],
        gaps=[],
    )

    # Export feature-b (different feature)
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-b",
        overview_md="Feature B overview",
        business_logic={"version": 1},
        dependencies=[],
        gaps=[],
    )

    # Second export of feature-a (should overwrite feature-a files, not feature-b)
    await export_feature_to_context(
        target_root=tmp_path,
        feature_name="feature-a",
        overview_md="Updated overview",
        business_logic={"version": 2},
        dependencies=[],
        gaps=[],
    )

    # feature-a files should be overwritten
    overview_a = (tmp_path / ".context" / "features" / "feature-a" / "overview.md").read_text()
    assert "Updated overview" in overview_a

    bl_a = json.loads((tmp_path / ".context" / "features" / "feature-a" / "business-logic.json").read_text())
    assert bl_a["version"] == 2

    # feature-b files should be preserved
    assert (tmp_path / ".context" / "features" / "feature-b" / "overview.md").exists()
    overview_b = (tmp_path / ".context" / "features" / "feature-b" / "overview.md").read_text()
    assert "Feature B overview" in overview_b


@pytest.mark.asyncio
async def test_export_returns_files_written_list(tmp_path):
    """export_feature_to_context returns a list of written file paths."""
    files_written = await export_feature_to_context(
        target_root=tmp_path,
        feature_name="product-schedule-consumer",
        overview_md="Overview text",
        business_logic={"steps": []},
        dependencies=[
            {
                "registry_type": "db",
                "name": "product_table",
                "data": {"name": "product_table", "used_by_features": []},
            }
        ],
        gaps=[],
    )

    assert isinstance(files_written, list)
    assert len(files_written) >= 3  # overview.md, business-logic.json, db/product_table.json
    # All paths should be relative strings
    for p in files_written:
        assert isinstance(p, str)
        assert not p.startswith("/")  # relative paths
