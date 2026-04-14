import io
import json
import logging
import zipfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from app.schemas.extraction import FeaturePatchRequest, FeatureResponse, ProjectResponse
from app.services.export import create_project_zip
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])

store = ProjectStore()


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PatchProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


@router.post("/", response_model=ProjectResponse)
async def create_project(req: CreateProjectRequest):
    proj = await store.create_project(req.name)
    logger.info("create_project: name=%s, slug=%s", req.name, proj["slug"])
    return ProjectResponse(**proj)


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
async def delete_project(project_slug: str):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    logger.info("delete_project: slug=%s", project_slug)
    await store.delete_project(project_slug)
    return {"ok": True}


@router.get("/{project_slug}/export/zip")
async def export_project_zip(project_slug: str):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    zip_bytes = create_project_zip(store._project_dir(project_slug))
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

    try:
        zf = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid zip archive")

    names = zf.namelist()
    if not names:
        raise HTTPException(status_code=400, detail="Zip archive is empty")

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

    # Create a new project (handles slug collision)
    new_proj = await store.create_project(project_name)
    new_slug = new_proj["slug"]
    target_dir = store.data_dir / new_slug

    # Extract all files from zip, remapping top-level dir to new slug
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

        dest = target_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(member.filename))

    # Inject 'name' into feature.json files that lack it (Context Collector format)
    features_dir = target_dir / "features"
    if features_dir.is_dir():
        for feat_dir in features_dir.iterdir():
            if not feat_dir.is_dir():
                continue
            feat_json = feat_dir / "feature.json"
            if feat_json.exists():
                fdata = json.loads(feat_json.read_text(encoding="utf-8"))
                if "name" not in fdata:
                    fdata["name"] = feat_dir.name
                    feat_json.write_text(json.dumps(fdata, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update project.json with new slug
    pjson_path = target_dir / "project.json"
    if pjson_path.exists():
        pdata = json.loads(pjson_path.read_text(encoding="utf-8"))
        pdata["slug"] = new_slug
        pjson_path.write_text(json.dumps(pdata, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("import_project_zip: name=%s, slug=%s, files=%d", project_name, new_slug, len(names))
    result = await store.get_project(new_slug)
    return ProjectResponse(**result)


@router.get("/{project_slug}/features", response_model=list[FeatureResponse])
async def get_project_features(project_slug: str):
    """All features across all documents in this project."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")
    features = await store.list_features(project_slug)
    return [_feature_to_response(f) for f in features]


@router.patch("/{project_slug}/features/{feature_name}", response_model=FeatureResponse)
async def patch_feature(project_slug: str, feature_name: str, patch: FeaturePatchRequest):
    """Update feature metadata. Handles rename by moving the directory."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")

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
    return _feature_to_response(feature)


@router.delete("/{project_slug}/features/{feature_name}")
async def delete_feature(project_slug: str, feature_name: str):
    """Delete a feature and all its sub-files (gaps, test-cases, bugs)."""
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
    await store.delete_feature(project_slug, feature_name)
    logger.info("delete_feature: project=%s, name=%s", project_slug, feature_name)
    return {"ok": True}


def _feature_to_response(f: dict) -> FeatureResponse:
    sl = f.get("structured_logic_json") or f.get("structured_logic")
    if not isinstance(sl, dict):
        sl = None
    return FeatureResponse(
        name=f["name"],
        source_document=f.get("source_document", ""),
        type=f.get("type", "unknown"),
        confidence=f.get("confidence", 0.0),
        summary=f.get("summary"),
        status=f.get("status", "detected"),
        method=f.get("method"),
        endpoint=f.get("endpoint"),
        structured_logic=sl,
        error_message=f.get("error_message"),
        gap_count=f.get("gap_count", 0),
        pending_gap_count=f.get("pending_gap_count", 0),
        gaps_status=f.get("gaps_status"),
        apply_status=f.get("apply_status"),
        test_case_count=f.get("test_case_count", 0),
        pending_test_case_count=f.get("pending_test_case_count", 0),
        test_cases_status=f.get("test_cases_status"),
    )
