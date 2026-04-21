"""Shared context builder for gaps and test_cases prompts.

Extracted from duplicated `_build_shared_context` in services/gaps.py and
services/test_cases.py. Handles per-type serialization of enriched_data —
most types render as JSON, external_doc renders as raw markdown.
"""
import json


def _serialize_enriched(dep_type: str, enriched: dict) -> str:
    """Render enriched_data for prompt injection based on dep type."""
    if dep_type == "external_doc":
        return enriched.get("content_html") or enriched.get("content_markdown", "")
    return json.dumps(enriched, ensure_ascii=False, indent=2)


def build_feature_context(feature: dict, enriched_deps: dict) -> str:
    """Build the feature + dependencies block shared by gaps and test_cases prompts.

    Args:
        feature: feature.json dict.
        enriched_deps: {name: dep_dict} — already filtered to enriched entries relevant to the feature.
    """
    lines: list[str] = []
    lines.append("## Feature")
    lines.append(f"Name: {feature.get('name', '')}")
    lines.append(f"Type: {feature.get('type', '')}")
    lines.append(f"Method: {feature.get('method', '')}")
    lines.append(f"Endpoint: {feature.get('endpoint', '')}")
    lines.append(f"Summary: {feature.get('summary', '')}")
    lines.append("")

    structured_logic = feature.get("structured_logic_json")
    if structured_logic:
        lines.append("### Structured Logic")
        lines.append(json.dumps(structured_logic, ensure_ascii=False, indent=2))
        lines.append("")

    lines.append("## Dependencies")
    if enriched_deps:
        for dep_name, dep_data in enriched_deps.items():
            dep_type = dep_data.get("dep_type", "")
            lines.append(f"### {dep_name} ({dep_type})")
            enriched = dep_data.get("enriched_data")
            if enriched:
                lines.append(_serialize_enriched(dep_type, enriched))
            else:
                lines.append(f"Description: {dep_data.get('description', '')}")
                lines.append(f"Status: {dep_data.get('enrichment_status', 'stub')}")
            lines.append("")
    else:
        lines.append("No enriched dependencies available.")

    return "\n".join(lines)
