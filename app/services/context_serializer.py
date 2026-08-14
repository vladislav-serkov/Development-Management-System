"""Bidirectional adapter between the database and the `.context/` file layout.

The `.context/` directory structure is the interop contract with the external
DMS coding agent (and the zip export format):

    .context/
        project.json
        rules.json
        features/{safe_name}/feature.json
        gaps/{safe_name}.json
        test-cases/{safe_name}.json
        bugs/{safe_name}.json
        dependencies/{db_tables|external_apis|cache|kafka_topics|external_docs}.json

``dump_project`` renders DB state into that layout; ``load_context_project``
parses a directory in that layout and inserts a fresh project.
"""

import json
import logging
from pathlib import Path

from app.services.import_context import adapt_feature, load_wiki_sections, merge_wiki_into_rules
from app.storage import DEP_TYPE_FILE, ProjectStore

logger = logging.getLogger(__name__)

_FEATURE_UI_FIELDS = {"status", "extracted_at", "error_message", "confidence"}
_DEP_UI_FIELDS = {"enrichment_status", "source_pdf_name", "enriched_at", "created_at"}


def _dumps(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _export_feature(feature: dict) -> dict:
    out = {k: v for k, v in feature.items() if k not in _FEATURE_UI_FIELDS}
    if "structured_logic_json" in out:
        out["structured_logic"] = out.pop("structured_logic_json")
    if "dependencies_json" in out:
        out["dependencies"] = out.pop("dependencies_json")
    return out


def _export_dep(dep: dict) -> dict:
    return {k: v for k, v in dep.items() if k not in _DEP_UI_FIELDS}


async def dump_project(store: ProjectStore, project_slug: str) -> dict[str, bytes] | None:
    """Render a project's DB state as ``{relative_path: bytes}`` in the
    `.context/` layout (paths are relative to the .context root).
    Returns None if the project does not exist. Documents are not exported."""
    project = await store.get_project(project_slug)
    if project is None:
        return None

    files: dict[str, bytes] = {}
    files["project.json"] = _dumps(
        {"slug": project["slug"], "name": project["name"], "created_at": project["created_at"]}
    )

    rules = await store.get_project_rules(project_slug)
    if any((v or "").strip() for v in rules.values()):
        files["rules.json"] = _dumps(rules)

    for feature in await store.list_features(project_slug):
        name = feature.get("name")
        if not name:
            continue
        safe = ProjectStore._sanitize_feature_name(name)
        files[f"features/{safe}/feature.json"] = _dumps(_export_feature(feature))

        gaps = await store.get_gaps(project_slug, name, include_archived=True)
        if gaps:
            files[f"gaps/{safe}.json"] = _dumps({"gaps": gaps})
        test_cases = await store.get_test_cases(project_slug, name)
        if test_cases:
            files[f"test-cases/{safe}.json"] = _dumps({"test_cases": test_cases})
        bugs = await store.get_bugs(project_slug, name)
        if bugs:
            files[f"bugs/{safe}.json"] = _dumps({"bugs": bugs})

    deps_by_type = await store.list_dependencies(project_slug)
    for dep_type, filename in DEP_TYPE_FILE.items():
        deps = deps_by_type.get(dep_type) or []
        if deps:
            files[f"dependencies/{filename}"] = _dumps({d["name"]: _export_dep(d) for d in deps})

    return files


async def export_context_dir(store: ProjectStore, project_slug: str, target_dir: Path) -> int:
    """Write the project's `.context/` layout into ``target_dir``.
    Returns the number of files written."""
    files = await dump_project(store, project_slug)
    if files is None:
        raise ValueError(f"Project '{project_slug}' not found")
    for rel_path, content in files.items():
        dest = target_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    return len(files)


def _read_json_file(path: Path, warnings: list[str]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"skipped {path.name}: cannot parse ({exc})")
        return None


async def load_context_project(
    store: ProjectStore,
    context_dir: Path,
    *,
    name: str | None = None,
    warnings: list[str] | None = None,
) -> tuple[str, int, int]:
    """Import a `.context/` directory as a NEW project (one-shot copy into the DB).

    Features are normalised through :func:`adapt_feature`. Wiki sections, if
    present, are merged into empty rules sections.
    Returns ``(slug, adapted_features, merged_wiki_sections)``.
    """
    if warnings is None:
        warnings = []

    project_meta = {}
    pjson = context_dir / "project.json"
    if pjson.exists():
        project_meta = _read_json_file(pjson, warnings) or {}
    project_name = name or project_meta.get("name") or context_dir.resolve().parent.name or "project"

    proj = await store.create_project(project_name)
    slug = proj["slug"]

    # Rules (file first, then wiki fills empty sections)
    rules_data = None
    rules_path = context_dir / "rules.json"
    if rules_path.exists():
        rules_data = _read_json_file(rules_path, warnings)
    if isinstance(rules_data, dict):
        await store.save_project_rules(slug, rules_data)

    # Features. DMS may key directories by feature_id rather than name, and
    # zip exports may omit "name" — fall back to the directory name.
    adapted = 0
    safe_to_name: dict[str, str] = {}
    features_dir = context_dir / "features"
    if features_dir.is_dir():
        for feat_dir in sorted(features_dir.iterdir()):
            raw = None
            if feat_dir.is_dir() and (feat_dir / "feature.json").exists():
                raw = _read_json_file(feat_dir / "feature.json", warnings)
                fallback_name = feat_dir.name
            elif feat_dir.is_file() and feat_dir.suffix == ".json":
                # flat legacy format: features/{name}.json
                raw = _read_json_file(feat_dir, warnings)
                fallback_name = feat_dir.stem
            if raw is None:
                continue
            raw.setdefault("name", fallback_name)
            feat_name = raw["name"]
            migrated = adapt_feature(raw, warnings=warnings)
            try:
                await store.save_feature(slug, migrated)
            except ValueError as exc:
                warnings.append(f"skipped feature '{feat_name}': {exc}")
                continue
            try:
                safe_to_name[ProjectStore._sanitize_feature_name(feat_name)] = feat_name
            except ValueError:
                pass
            adapted += 1

    # Gaps / test cases / bugs, keyed by sanitized feature name
    for subdir, key, saver in (
        ("gaps", "gaps", store.save_gaps),
        ("test-cases", "test_cases", store.save_test_cases),
        ("bugs", "bugs", store.save_bugs),
    ):
        analysis_dir = context_dir / subdir
        if not analysis_dir.is_dir():
            continue
        for path in analysis_dir.glob("*.json"):
            feat_name = safe_to_name.get(path.stem)
            if feat_name is None:
                warnings.append(f"skipped {subdir}/{path.name}: no matching feature")
                continue
            data = _read_json_file(path, warnings)
            items = data.get(key, []) if isinstance(data, dict) else None
            if isinstance(items, list):
                await saver(slug, feat_name, items)

    # Dependencies: per-type {name: dep_dict} maps
    deps_dir = context_dir / "dependencies"
    if deps_dir.is_dir():
        for dep_type, filename in DEP_TYPE_FILE.items():
            path = deps_dir / filename
            if not path.exists():
                continue
            data = _read_json_file(path, warnings)
            if not isinstance(data, dict):
                continue
            for dep_name, dep_dict in data.items():
                if not isinstance(dep_dict, dict):
                    continue
                # Exports strip enrichment_status; the payload's presence implies it
                if "enriched_data" in dep_dict and "enrichment_status" not in dep_dict:
                    dep_dict["enrichment_status"] = "enriched"
                await store.upsert_dependency(slug, dep_type, dep_name, dep_dict)

    # Wiki → project rules (only fills empty sections)
    merged_sections = 0
    wiki = load_wiki_sections(context_dir)
    if wiki:
        current_rules = await store.get_project_rules(slug)
        new_rules = merge_wiki_into_rules(current_rules, wiki, warnings=warnings)
        merged_sections = sum(
            1 for k, v in new_rules.items() if v and not current_rules.get(k, "").strip()
        )
        if merged_sections > 0:
            await store.save_project_rules(slug, new_rules)

    return slug, adapted, merged_sections
