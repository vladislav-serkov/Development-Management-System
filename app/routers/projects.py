import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.schemas.extraction import FeaturePatchRequest, FeatureResponse, ProjectResponse
from app.services.context_serializer import dump_project, export_context_dir, load_context_project
from app.services.export import create_project_zip
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])

store = ProjectStore()

# Upload limits for project-zip import (guard against OOM / zip-bomb).
MAX_IMPORT_ZIP_BYTES = 50 * 1024 * 1024  # 50 MB compressed
MAX_IMPORT_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500 MB uncompressed


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PatchProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class LinkProjectRequest(BaseModel):
    path: str = Field(min_length=1)


@router.post("/", response_model=ProjectResponse)
async def create_project(req: CreateProjectRequest):
    proj = await store.create_project(req.name)
    logger.info("create_project: name=%s, slug=%s", req.name, proj["slug"])
    return ProjectResponse(**proj)


class ImportContextResponse(BaseModel):
    project: ProjectResponse
    adapted_features: int
    merged_wiki_sections: int = 0
    warnings: list[str] = Field(default_factory=list)


@router.post("/import-context", response_model=ImportContextResponse)
async def import_context(req: LinkProjectRequest):
    """Import a DMS-produced `.context/` directory into the database as a new
    project, migrating feature.json files to extract-agent's canonical shape
    (renames, legacy-field cleanup, flat-mapping nulling, `source` provenance).
    If ``.context/wiki/*.md`` exists, it is merged into the project's rules
    (empty sections only). The source path is remembered so the project can be
    synced back with `POST /projects/{slug}/export-context`."""
    base = Path(req.path).expanduser()
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {req.path}")
    resolved = base.resolve()
    context_dir = resolved / ".context"
    if not context_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"No .context/ directory inside: {req.path}")

    warnings: list[str] = []
    slug, adapted, merged_sections = await load_context_project(
        store, context_dir, name=resolved.name, warnings=warnings,
    )
    await store.set_project_context_dir(slug, str(resolved))

    logger.info(
        "import_context: path=%s, slug=%s, adapted=%d, merged_sections=%d, warnings=%d",
        req.path, slug, adapted, merged_sections, len(warnings),
    )
    proj = await store.get_project(slug)
    return ImportContextResponse(
        project=ProjectResponse(**proj),
        adapted_features=adapted,
        merged_wiki_sections=merged_sections,
        warnings=warnings,
    )


class ExportContextRequest(BaseModel):
    path: str | None = Field(default=None, description="Project root; defaults to the imported-from directory")


@router.post("/{project_slug}/export-context")
async def export_context(project_slug: str, req: ExportContextRequest):
    """Serialize the project's current DB state back into a `.context/`
    directory (the DMS interop layout). Overwrites files it owns."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    target = req.path or await store.get_project_context_dir(project_slug)
    if not target:
        raise HTTPException(
            status_code=400,
            detail="No target directory: pass 'path' or import the project from a .context directory first",
        )
    base = Path(target).expanduser()
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {target}")

    context_dir = base.resolve() / ".context"
    written = await export_context_dir(store, project_slug, context_dir)
    await store.set_project_context_dir(project_slug, str(base.resolve()))
    logger.info("export_context: slug=%s, dir=%s, files=%d", project_slug, context_dir, written)
    return {"ok": True, "path": str(context_dir), "files_written": written}


@router.get("/", response_model=list[ProjectResponse])
async def list_projects():
    projects = await store.list_projects()
    return [ProjectResponse(**p) for p in projects]


@router.get("/{project_slug}", response_model=ProjectResponse)
async def get_project(project_slug: str):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    return ProjectResponse(**proj)


@router.patch("/{project_slug}", response_model=ProjectResponse)
async def patch_project(project_slug: str, patch: PatchProjectRequest):
    logger.info("patch_project: slug=%s, new_name=%s", project_slug, patch.name)
    proj = await store.update_project(project_slug, patch.name)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    return ProjectResponse(**proj)


@router.delete("/{project_slug}")
async def delete_project(project_slug: str, remove_files: bool = False):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    logger.info("delete_project: slug=%s, remove_files=%s", project_slug, remove_files)
    await store.delete_project(project_slug, remove_files=remove_files)
    return {"ok": True}


@router.get("/{project_slug}/export/zip")
async def export_project_zip(project_slug: str):
    files = await dump_project(store, project_slug)
    if files is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    zip_bytes = create_project_zip(files)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename=".context.zip"'},
    )


@router.post("/import", response_model=ProjectResponse)
async def import_project_zip(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_IMPORT_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded archive is too large")

    try:
        zf = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip archive")

    names = zf.namelist()
    if not names:
        raise HTTPException(status_code=400, detail="Zip archive is empty")

    total_uncompressed = sum(info.file_size for info in zf.infolist())
    if total_uncompressed > MAX_IMPORT_UNCOMPRESSED_BYTES:
        raise HTTPException(status_code=413, detail="Archive contents are too large")

    # Detect top-level directory (first path component, e.g. ".context")
    top_dir = names[0].split("/")[0]
    project_json_path = f"{top_dir}/project.json"
    if project_json_path not in names:
        raise HTTPException(status_code=400, detail="Invalid zip format: missing project.json")

    # Read project metadata
    try:
        project_data = json.loads(zf.read(project_json_path))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse project.json")

    project_name = project_data.get("name")
    if not project_name:
        raise HTTPException(status_code=400, detail="project.json missing 'name' field")

    # Extract to a temp dir (with zip-slip guard), then load into the DB
    with tempfile.TemporaryDirectory(prefix="extract-agent-import-") as tmp:
        target_dir = Path(tmp).resolve()
        for member in zf.infolist():
            if member.is_dir():
                continue
            # Strip top-level dir prefix
            rel_path = member.filename
            if rel_path.startswith(top_dir + "/"):
                rel_path = rel_path[len(top_dir) + 1:]
            else:
                continue  # skip entries not under top_dir

            if not rel_path:
                continue

            # Guard against zip-slip: the resolved destination must stay under target_dir
            dest = (target_dir / rel_path).resolve()
            if dest != target_dir and target_dir not in dest.parents:
                raise HTTPException(status_code=400, detail=f"Unsafe path in archive: {member.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member.filename))

        warnings: list[str] = []
        new_slug, adapted, _ = await load_context_project(
            store, target_dir, name=project_name, warnings=warnings,
        )

    logger.info(
        "import_project_zip: name=%s, slug=%s, features=%d, warnings=%d",
        project_name, new_slug, adapted, len(warnings),
    )
    result = await store.get_project(new_slug)
    return ProjectResponse(**result)


@router.get("/{project_slug}/features", response_model=list[FeatureResponse])
async def get_project_features(project_slug: str):
    """All features across all documents in this project."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    features = await store.list_features(project_slug)
    active_tasks = await store.list_tasks(project_slug, status="running")
    return [_feature_to_response(f, active_tasks=active_tasks) for f in features]


@router.patch("/{project_slug}/features/{feature_name}", response_model=FeatureResponse)
async def patch_feature(project_slug: str, feature_name: str, patch: FeaturePatchRequest):
    """Update feature metadata. Handles rename by moving the directory."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
    feature_name = feature["name"]

    actual_name = feature_name
    updates: dict = {}

    # Handle rename first
    if patch.name is not None and patch.name != feature_name:
        try:
            renamed = await store.rename_feature(project_slug, feature_name, patch.name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if renamed is None:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
        actual_name = patch.name
        feature = renamed

    # Collect remaining metadata updates
    if patch.type is not None:
        updates["type"] = patch.type
    if patch.method is not None:
        updates["method"] = patch.method
    if patch.endpoint is not None:
        updates["endpoint"] = patch.endpoint
    if patch.summary is not None:
        updates["summary"] = patch.summary
    if patch.structured_logic_json is not None:
        updates["structured_logic_json"] = patch.structured_logic_json

    if updates:
        feature = await store.update_feature(project_slug, actual_name, updates)

    logger.info("patch_feature: project=%s, name=%s -> %s", project_slug, feature_name, actual_name)
    active_tasks = await store.list_tasks(project_slug, status="running")
    return _feature_to_response(feature, active_tasks=active_tasks)


@router.delete("/{project_slug}/features/{feature_name}")
async def delete_feature(project_slug: str, feature_name: str):
    """Delete a feature and all its sub-files (gaps, test-cases, bugs)."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
    feature_name = feature["name"]
    await store.delete_feature(project_slug, feature_name)
    logger.info("delete_feature: project=%s, name=%s", project_slug, feature_name)
    return {"ok": True}


def _feature_to_response(
    f: dict,
    *,
    active_tasks: list[dict] | None = None,
) -> FeatureResponse:
    sl = f.get("structured_logic_json") or f.get("structured_logic")
    if not isinstance(sl, dict):
        sl = None

    running_kinds: set[str] = set()
    if active_tasks:
        name = f["name"]
        for t in active_tasks:
            if t.get("target_id") == name and t.get("status") == "running":
                running_kinds.add(t.get("kind"))

    return FeatureResponse(
        name=f["name"],
        display_name=f.get("display_name"),
        source_document=f.get("source_document") or None,
        source=f.get("source"),
        type=f.get("type", "unknown"),
        confidence=f.get("confidence", 0.0),
        summary=f.get("summary"),
        status=f.get("status", "extracting"),
        method=f.get("method"),
        endpoint=f.get("endpoint"),
        schedule=f.get("schedule"),
        structured_logic=sl,
        gap_count=f.get("gap_count", 0),
        pending_gap_count=f.get("pending_gap_count", 0),
        gaps_running="gaps" in running_kinds,
        apply_running="apply_gaps" in running_kinds,
        test_case_count=f.get("test_case_count", 0),
        pending_test_case_count=f.get("pending_test_case_count", 0),
        test_cases_running="test_cases" in running_kinds,
    )
