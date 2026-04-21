"""Post-enrichment sync: propagate 'required' from enriched dependency data into feature mappings.

Zero LLM calls — pure code matching by field name.
Runs automatically after enrichment completes.
"""
import logging

logger = logging.getLogger(__name__)


def _build_required_map(enriched_data: dict, dep_type: str) -> dict[str, bool]:
    """Build a flat map of field_name → required (bool) from enriched dependency data.

    For db_table: nullable=False → required=True
    For kafka_topic: required field directly
    For external_api: params[].required directly
    """
    result: dict[str, bool] = {}

    if dep_type == "db_table":
        for col in enriched_data.get("columns", []):
            name = col.get("name", "")
            if name:
                result[name] = not col.get("nullable", True)

    elif dep_type == "kafka_topic":
        def _walk_kafka_fields(fields: list[dict]) -> None:
            for f in fields:
                name = f.get("element", "")
                if name:
                    result[name] = f.get("required", False)
                _walk_kafka_fields(f.get("children", []))
        _walk_kafka_fields(enriched_data.get("message_fields", []))
        _walk_kafka_fields(enriched_data.get("key_fields", []))

    elif dep_type == "external_api":
        for endpoint in enriched_data.get("endpoints", []):
            for param in endpoint.get("params", []):
                name = param.get("name", "")
                if name:
                    result[name] = param.get("required", False)

    return result


def _normalize_field_name(name: str) -> str:
    """Normalize for matching: lower + strip underscores vs camelCase."""
    # Convert camelCase to snake_case, then lowercase
    import re
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    return s.lower().replace("-", "_")


def _apply_required_to_fields(fields: list[dict], required_map: dict[str, bool], normalized_map: dict[str, str]) -> int:
    """Recursively apply required from enriched data to mapping fields.

    Returns count of fields updated.
    """
    count = 0
    for field in fields:
        element = field.get("element", "")
        # Try exact match first, then normalized
        if element in required_map:
            field["required"] = required_map[element]
            count += 1
        else:
            norm = _normalize_field_name(element)
            if norm in normalized_map:
                original_name = normalized_map[norm]
                field["required"] = required_map[original_name]
                count += 1

        # Recurse into children
        count += _apply_required_to_fields(
            field.get("children", []), required_map, normalized_map
        )
    return count


async def sync_required_after_enrichment(
    project_slug: str,
    dep_type: str,
    dep_name: str,
    enriched_data: dict,
    store,
) -> int:
    """After a dependency is enriched, update required fields in all feature mappings
    that reference this dependency (matched by message_type).

    Returns total number of fields updated across all features.
    """
    required_map = _build_required_map(enriched_data, dep_type)
    if not required_map:
        logger.debug("No required info in enriched data for %s/%s", dep_type, dep_name)
        return 0

    # Build normalized lookup for fuzzy matching
    normalized_map: dict[str, str] = {}
    for name in required_map:
        normalized_map[_normalize_field_name(name)] = name

    features = await store.list_features(project_slug)
    total_updated = 0

    for feature_data in features:
        logic = feature_data.get("structured_logic_json")
        if not logic:
            continue

        steps = logic.get("logic_steps", [])
        feature_updated = _sync_steps(steps, dep_name, required_map, normalized_map)

        if feature_updated > 0:
            await store.update_feature(
                project_slug,
                feature_data["name"],
                {"structured_logic_json": logic},
            )
            logger.info(
                "sync_required: updated %d fields in feature '%s' from %s/%s",
                feature_updated, feature_data["name"], dep_type, dep_name,
            )
            total_updated += feature_updated

    if total_updated:
        logger.info(
            "sync_required complete: %s/%s → %d fields updated across %s",
            dep_type, dep_name, total_updated, project_slug,
        )
    return total_updated


def _sync_steps(steps: list[dict], dep_name: str, required_map: dict[str, bool], normalized_map: dict[str, str]) -> int:
    """Recursively walk steps, apply required to mappings where message_type matches dep_name."""
    count = 0
    dep_norm = _normalize_field_name(dep_name)
    for step in steps:
        msg_type = step.get("message_type")
        mapping = step.get("message_mapping")
        if msg_type and mapping:
            # Match: exact or normalized
            msg_norm = _normalize_field_name(msg_type)
            if msg_type == dep_name or msg_norm == dep_norm:
                count += _apply_required_to_fields(mapping, required_map, normalized_map)
        count += _sync_steps(step.get("children", []), dep_name, required_map, normalized_map)
    return count
