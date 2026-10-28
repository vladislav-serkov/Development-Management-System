"""Structured outputs: schemas stay API-compatible (no recursion, no unknown
object keys), flat LLM lists are rebuilt into trees, and call_structured
validates the answer or fails loudly."""
import json
import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.services.claude_client as claude_client
from app.prompts.enrichment import ENRICHMENT_SCHEMAS
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
from app.services.claude_client import TruncatedOutputError, call_structured, output_schema

ALL_SCHEMAS = [
    FeatureDetectionResult, ApplyResult, GapsAnalysisResult,
    TestCasePlanResult, TestCaseGenerationResult, TestCaseAskResult, BugReportResult,
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


def _fake_response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(),
        stop_reason=stop_reason,
    )


async def test_call_structured_validates_and_passes_schema(monkeypatch):
    captured = {}

    async def fake(*, label="", **kwargs):
        captured.update(kwargs)
        return _fake_response('{"gaps": [{"gap_type": "x", "severity": "major", "question": "q", "suggestion": "s", "actionable": true}]}')

    monkeypatch.setattr(claude_client, "call_claude", fake)
    result = await call_structured(
        GapsAnalysisResult, label="t", model="m", max_tokens=10, system="sys", effort="low",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert result.gaps[0].severity == "major"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["output_config"]["effort"] == "low"
    assert captured["system"] == "sys"
    assert "tools" not in captured and "tool_choice" not in captured


async def test_call_structured_raises_on_truncation(monkeypatch):
    async def fake(*, label="", **kwargs):
        return _fake_response('{"gaps": [', stop_reason="max_tokens")

    monkeypatch.setattr(claude_client, "call_claude", fake)
    with pytest.raises(TruncatedOutputError):
        await call_structured(GapsAnalysisResult, label="t", model="m", max_tokens=10, messages=[])


async def test_call_structured_raises_on_invalid_output(monkeypatch):
    async def fake(*, label="", **kwargs):
        return _fake_response('{"gaps": [{"gap_type": "x", "severity": "huge"}]}')

    monkeypatch.setattr(claude_client, "call_claude", fake)
    with pytest.raises(ValidationError):
        await call_structured(GapsAnalysisResult, label="t", model="m", max_tokens=10, messages=[])
