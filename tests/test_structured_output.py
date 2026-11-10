"""Structured outputs: schemas stay API-compatible (no recursion, no unknown
object keys), flat LLM lists are rebuilt into trees, and call_structured
validates the answer or fails loudly."""
import json
import re

import pytest

from app.prompts.enrichment import ENRICHMENT_SCHEMAS
from app.schemas.assistant import AssistantStep
from app.schemas.bugs import BugReportResult
from app.schemas.extraction import (
    DetectedFeature,
    FeatureDetectionResult,
    LogicStep,
    MessageField,
    nest_message_fields,
    nest_steps,
)
from app.schemas.gaps import ApplyResult, GapsAnalysisResult
from app.schemas.test_cases import TestCaseAskResult, TestCaseGenerationResult, TestCasePlanResult
from app.services import agent_runner, codex_client
from app.services.codex_client import call_structured, output_schema

ALL_SCHEMAS = [
    FeatureDetectionResult, ApplyResult, GapsAnalysisResult,
    TestCasePlanResult, TestCaseGenerationResult, TestCaseAskResult, BugReportResult, AssistantStep,
    *[cfg["schema"] for cfg in ENRICHMENT_SCHEMAS.values()],
]


def _walk(node, defs, seen):
    """Yield every $ref chain to detect a definition referencing itself."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if ref:
            name = ref.rsplit("/", 1)[-1]
            assert name not in seen, f"recursive definition {name}"
            _walk(defs[name], defs, seen | {name})
        for v in node.values():
            _walk(v, defs, seen)
    elif isinstance(node, list):
        for v in node:
            _walk(v, defs, seen)


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_output_schema_is_api_compatible(schema):
    s = output_schema(schema)
    _walk(s, s.get("$defs", {}), frozenset())
    text = json.dumps(s)
    # every object closes its key set; free-form dicts would become unfillable
    assert '"additionalProperties": false' in text
    for obj in re.findall(r'"type": "object", "properties": \{\}', text):
        raise AssertionError(f"empty object in {schema.__name__}: {obj}")


def test_extraction_schema_hides_code_filled_fields():
    s = json.dumps(output_schema(FeatureDetectionResult))
    for hidden in ("children", "mapping_tables", '"fields"', '"columns"', "source_doc_title", '"dependencies"'):
        assert hidden not in s, hidden
    assert "mapping_table_ids" in s and "status_codes" in s


def test_nest_steps_by_number():
    flat = [LogicStep(number=n, text=n) for n in ["1", "1.1", "1.1.1", "1.2", "2", "2.1", "3"]]
    tree = nest_steps(flat)
    assert [s.number for s in tree] == ["1", "2", "3"]
    assert [s.number for s in tree[0].children] == ["1.1", "1.2"]
    assert [s.number for s in tree[0].children[0].children] == ["1.1.1"]
    assert [s.number for s in tree[1].children] == ["2.1"]


def test_nest_steps_tolerates_numbering_gaps():
    # "4.2" with no "4" in sight attaches under the last shallower step
    flat = [LogicStep(number=n, text=n) for n in ["1", "4.2", "4.2.1", "5"]]
    tree = nest_steps(flat)
    assert [s.number for s in tree] == ["1", "5"]
    assert [s.number for s in tree[0].children] == ["4.2"]
    assert [s.number for s in tree[0].children[0].children] == ["4.2.1"]


def test_nest_steps_keeps_existing_tree():
    tree = [LogicStep(number="1", text="a", children=[LogicStep(number="1.1", text="b")])]
    assert nest_steps(tree) is tree


def test_nest_message_fields_by_parent():
    flat = [
        MessageField(element="record"),
        MessageField(element="id", parent="record"),
        MessageField(element="attributes", parent="record"),
        MessageField(element="limit", parent="attributes"),
        MessageField(element="id", parent="attributes"),  # same name, other branch
        MessageField(element="meta"),
    ]
    tree = nest_message_fields(flat)
    assert [f.element for f in tree] == ["record", "meta"]
    record = tree[0]
    assert [f.element for f in record.children] == ["id", "attributes"]
    assert [f.element for f in record.children[1].children] == ["limit", "id"]


def test_detected_feature_nest_derives_dependencies():
    feature = DetectedFeature.model_validate({
        "name": "GET /v1/x", "type": "rest_endpoint", "confidence": 0.9, "summary": "s",
        "structured_logic": {
            "logic_steps": [{"number": "1", "text": "a"}, {"number": "1.1", "text": "b"}],
            "used_dependencies": [{"type": "db_table", "name": "orders", "description": "d"}],
        },
    }).nest()
    assert feature.dependencies == ["orders"]
    assert feature.structured_logic.logic_steps[0].children[0].number == "1.1"


async def test_call_structured_preserves_sources_and_task_instructions(monkeypatch, tmp_path):
    captured = {}

    async def analyze(workspace, log_path, execute, on_started, **options):
        captured.update(options)
        assert workspace.is_dir()
        assert not (workspace / "AGENTS.md").exists()

        async def ask(prompt, schema):
            captured["prompt"] = json.loads(prompt.split("\n", 1)[1])
            assert schema is GapsAnalysisResult
            return {"gaps": []}

        return await execute(ask)

    monkeypatch.setattr(agent_runner, "analyze", analyze)
    monkeypatch.setattr(codex_client.settings, "structured_log_dir", str(tmp_path))
    result = await call_structured(
        GapsAnalysisResult, label="extract", model="claude-old", max_tokens=10,
        system="Keep tables verbatim", effort="high", messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "text", "data": "|id|uuid|"}},
            {"type": "text", "text": "Extract", "cache_control": {"type": "ephemeral"}},
        ]}],
    )
    assert result.gaps == []
    assert captured["prompt"] == [{"role": "user", "text": "|id|uuid|\n\nExtract"}]
    assert captured["model"] == ""
    assert captured["effort"] == "high"
    assert "Keep tables verbatim" in captured["instructions"]
    assert captured["kind"] == "extract"


def test_every_object_requires_all_properties():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)

    for schema in ALL_SCHEMAS:
        check(output_schema(schema))
