"""Shared context builder for test-case prompts (generation, ask, assistant).

Handles per-type serialization of enriched_data — most types render as JSON,
external_doc renders as raw markdown. JSON is rendered compactly: the stored
shapes carry many empty placeholders (``"children": []``, ``"message_type":
null`` on every logic step, ``"is_fk": false`` on every column) that only cost
input tokens on each Codex call.
"""
import json

# Flags that are noise when false: their absence reads the same.
_FALSE_IS_DEFAULT = frozenset({"is_fk", "is_pk", "has_detailed_mapping"})
# Internal bookkeeping the model cannot use (URL-encoded link fingerprints).
_INTERNAL_KEYS = frozenset({"link_keys"})


def _compact(value):
    """Drop empty placeholders; keeps every value that carries information."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in _INTERNAL_KEYS or (item is False and key in _FALSE_IS_DEFAULT):
                continue
            item = _compact(item)
            if item is None or item == "" or item == [] or item == {}:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _render_json(value) -> str:
    return json.dumps(_compact(value), ensure_ascii=False, indent=1)


def _serialize_enriched(dep_type: str, enriched: dict) -> str:
    """Render enriched_data for prompt injection based on dep type."""
    if dep_type == "external_doc":
        return enriched.get("content_html") or enriched.get("content_markdown", "")
    return _render_json(enriched)


def build_feature_context(feature: dict, enriched_deps: dict, service_name: str | None = None) -> str:
    """Build the feature + dependencies block of the test-case prompts.

    Args:
        feature: feature.json dict.
        enriched_deps: {name: dep_dict} — already filtered to enriched entries relevant to the feature.
        service_name: the feature's own service; API dependencies that belong to
            it are internal calls (nothing to stub) and are labelled as such.
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
        lines.append(_render_json(structured_logic))
        lines.append("")

    lines.append("## Dependencies")
    if enriched_deps:
        for dep_name, dep_data in enriched_deps.items():
            dep_type = dep_data.get("dep_type", "")
            lines.append(f"### {dep_name} ({dep_type})")
            if dep_type == "external_api" and service_name and dep_data.get("service_name") == service_name:
                lines.append(
                    f"Метод этого же сервиса ({service_name}) — внутренний вызов: заглушка не нужна, "
                    "результат проверяется по состоянию БД."
                )
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
