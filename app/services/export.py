"""Export service: write .context/ folder structure to disk or produce zip."""
import io
import json
import logging
import zipfile
from pathlib import Path

import aiofiles

from app.schemas.export import ExportResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level file I/O helpers
# ---------------------------------------------------------------------------


async def _write_json(path: Path, data: dict) -> None:
    """Write JSON content to path using async I/O."""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Core export function
# ---------------------------------------------------------------------------


async def export_feature_to_context(
    target_root: Path,
    feature_name: str,
    structured_logic: dict,
) -> list[str]:
    """Export one feature to .context/ folder structure.

    Args:
        target_root: filesystem path to the microservice root (e.g., /projects/my-service)
        feature_name: name of the feature being exported
        structured_logic: dict with feature structured logic (will be written as JSON)

    Returns:
        list of file paths written (relative to target_root)
    """
    context_root = target_root / ".context"
    feature_dir = context_root / "features" / feature_name
    feature_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    sl_path = feature_dir / "structured-logic.json"
    await _write_json(sl_path, structured_logic)
    files_written.append(str(sl_path.relative_to(target_root)))

    return files_written


# ---------------------------------------------------------------------------
# Document-level export (reads from file-based store)
# ---------------------------------------------------------------------------


async def export_document_context(
    project_slug: str,
    doc_slug: str,
    feature_name: str | None,
    store,
    target_path: str | None = None,
) -> ExportResponse:
    """Export all (or one) feature's .context/ from file store to the filesystem.

    Args:
        project_slug: slug of the project
        doc_slug: slug of the document
        feature_name: if specified, only export this feature; else export all done features
        store: ProjectStore instance
        target_path: absolute path to the target microservice root

    Returns:
        ExportResponse with list of exported features and files written
    """
    features = await store.list_features(project_slug)

    # Filter to desired feature(s) and only from this document
    if feature_name is not None:
        features = [f for f in features if f["name"] == feature_name and f.get("source_document") == doc_slug]
    else:
        features = [f for f in features if f.get("status") == "done" and f.get("source_document") == doc_slug]

    if target_path is None:
        target_path = str(store.get_context_dir(project_slug))

    target_root = Path(target_path)

    exported_features: list[str] = []
    all_files_written: list[str] = []

    for feature in features:
        sl_dict: dict = {}
        sl_raw = feature.get("structured_logic_json")
        if sl_raw:
            try:
                sl_dict = json.loads(sl_raw) if isinstance(sl_raw, str) else sl_raw
            except json.JSONDecodeError:
                sl_dict = {"_raw": sl_raw}

        files = await export_feature_to_context(
            target_root=target_root,
            feature_name=feature["name"],
            structured_logic=sl_dict,
        )

        exported_features.append(feature["name"])
        all_files_written.extend(files)

    return ExportResponse(
        exported_features=exported_features,
        target_path=target_path,
        files_written=all_files_written,
    )


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

    Feature and dependency JSONs have UI-only metadata fields stripped.
    Feature _json suffix keys are renamed to canonical names.
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
