"""Export service: produce a project zip from the file-based store."""
import io
import json
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


_FEATURE_UI_FIELDS = {"status", "extracted_at", "error_message", "confidence"}
_DEP_UI_FIELDS = {"enrichment_status", "source_pdf_name", "enriched_at", "created_at"}


def _strip_fields(raw_bytes: bytes, fields: set[str], nested: bool = False) -> bytes:
    """Strip UI-only fields from a JSON file. If nested, strip from each value dict."""
    try:
        data: dict = json.loads(raw_bytes)
    except json.JSONDecodeError:
        return raw_bytes

    if nested:
        for item in data.values():
            if isinstance(item, dict):
                for field in fields:
                    item.pop(field, None)
    else:
        for field in fields:
            data.pop(field, None)
        # Rename _json suffix keys to canonical names
        if "structured_logic_json" in data:
            data["structured_logic"] = data.pop("structured_logic_json")
        if "dependencies_json" in data:
            data["dependencies"] = data.pop("dependencies_json")

    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def create_project_zip(project_dir: Path) -> bytes:
    """Create an in-memory zip with .context/ as root, excluding documents/.

    Directory structure in zip:
        .context/
            project.json
            features/{name}/feature.json
            gaps/{name}.json
            test-cases/{name}.json
            bugs/{name}.json
            dependencies/*.json

    Feature and dependency JSONs have UI-only metadata fields stripped.
    Feature _json suffix keys are renamed to canonical names.
    Old feature-nested analysis files (gaps.json, test-cases.json, bugs.json)
    are excluded as they should have been migrated to top-level directories.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(project_dir)
                # skip documents/ folder
                if rel.parts[0] == "documents":
                    continue
                arcname = Path(".context") / rel
                rel_parts = rel.parts
                # Skip old feature-nested analysis files (stale, migrated to top-level)
                if (
                    len(rel_parts) == 3
                    and rel_parts[0] == "features"
                    and rel_parts[2] in ("gaps.json", "test-cases.json", "bugs.json")
                ):
                    continue
                # Strip UI-only fields from feature JSONs (folder-based: features/{name}/feature.json)
                if (
                    len(rel_parts) == 3
                    and rel_parts[0] == "features"
                    and rel_parts[2] == "feature.json"
                ):
                    raw = file_path.read_bytes()
                    zf.writestr(str(arcname), _strip_fields(raw, _FEATURE_UI_FIELDS))
                # Strip UI-only fields from feature JSONs (flat format: features/{name}.json, backward compat)
                elif (
                    len(rel_parts) == 2
                    and rel_parts[0] == "features"
                    and rel_parts[1].endswith(".json")
                ):
                    raw = file_path.read_bytes()
                    zf.writestr(str(arcname), _strip_fields(raw, _FEATURE_UI_FIELDS))
                # Strip UI-only fields from dependency JSONs
                elif (
                    len(rel_parts) == 2
                    and rel_parts[0] == "dependencies"
                    and rel_parts[1].endswith(".json")
                ):
                    raw = file_path.read_bytes()
                    zf.writestr(str(arcname), _strip_fields(raw, _DEP_UI_FIELDS, nested=True))
                else:
                    zf.write(file_path, arcname)
    buf.seek(0)
    return buf.read()
