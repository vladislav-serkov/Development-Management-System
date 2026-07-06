import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.routers.projects import store
from app.schemas.enrichment import CreateDependencyRequest, DependencyResponse
from app.schemas.extraction import ConfluenceImportRequest
from app.services.confluence import ConfluenceError, fetch_page
from app.services.enrichment import EXTERNAL_DOC_TARGETED_ONLY_MSG, run_enrichment_pipeline
from app.services.required_sync import sync_required_after_enrichment
from app.services.task_manager import task_manager
from app.storage import DEP_TYPE_FILE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_slug}/dependencies", tags=["dependencies"])


def _dep_to_response(dep: dict, project_slug: str) -> DependencyResponse:
    enriched = dep.get("enriched_data")

    created_at = dep.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.utcnow()

    enriched_at = dep.get("enriched_at")
    if isinstance(enriched_at, str):
        enriched_at = datetime.fromisoformat(enriched_at)

    return DependencyResponse(
        project_slug=project_slug,
        dep_type=dep["dep_type"],
        name=dep["name"],
        description=dep.get("description"),
        enrichment_status=dep.get("enrichment_status", "stub"),
        enriched_data=enriched,
        source_pdf_name=dep.get("source_pdf_name"),
        enriched_at=enriched_at,
        created_at=created_at,
        method=dep.get("method"),
        service_name=dep.get("service_name"),
        path=dep.get("path"),
    )


@router.get("/", response_model=list[DependencyResponse])
async def list_dependencies(project_slug: str):
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    by_type = await store.list_dependencies(project_slug)
    logger.debug("list_dependencies(%s): types=%s, counts=%s", project_slug, list(by_type.keys()), {k: len(v) for k, v in by_type.items()})
    result = []
    for dep_type, deps in by_type.items():
        for dep in sorted(deps, key=lambda d: d.get("name", "")):
            result.append(_dep_to_response(dep, project_slug))
    return result


@router.post("/", response_model=DependencyResponse, status_code=201)
async def create_dependency(project_slug: str, req: CreateDependencyRequest):
    """Manually create a new stub dependency entry."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    if req.dep_type not in DEP_TYPE_FILE:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dep_type: {req.dep_type}. Must be one of: {', '.join(DEP_TYPE_FILE.keys())}",
        )

    existing = await store.get_dependency(project_slug, req.dep_type, req.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Dependency '{req.name}' of type '{req.dep_type}' already exists")

    now = datetime.now(UTC).isoformat()
    dep_dict: dict = {
        "dep_type": req.dep_type,
        "name": req.name,
        "description": req.description,
        "enrichment_status": "stub",
        "created_at": now,
    }
    if req.method is not None:
        dep_dict["method"] = req.method
    if req.service_name is not None:
        dep_dict["service_name"] = req.service_name
    if req.path is not None:
        dep_dict["path"] = req.path

    dep = await store.upsert_dependency(project_slug, req.dep_type, req.name, dep_dict)
    logger.info("create_dependency: project=%s, dep_type=%s, name=%s", project_slug, req.dep_type, req.name)
    return _dep_to_response(dep, project_slug)


@router.patch("/{dep_name:path}", response_model=DependencyResponse)
async def patch_dependency(
    project_slug: str,
    dep_name: str,
    patch: dict,
    dep_type: str = Query(..., description="db_table | external_api | cache | kafka_topic | external_doc"),
):
    dep = await store.get_dependency(project_slug, dep_type, dep_name)
    if dep is None:
        raise HTTPException(status_code=404, detail=f"Dependency '{dep_name}' not found")

    actual_name = dep_name

    # Handle rename
    if "name" in patch and patch["name"] != dep_name:
        try:
            renamed = await store.rename_dependency(project_slug, dep_type, dep_name, patch["name"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if renamed is None:
            raise HTTPException(status_code=404, detail=f"Dependency '{dep_name}' not found")
        actual_name = patch["name"]
        dep = renamed

    updates = {}
    if "enriched_data" in patch:
        updates["enriched_data"] = patch["enriched_data"]
    if "description" in patch:
        updates["description"] = patch["description"]
    if "method" in patch:
        updates["method"] = patch["method"]
    if "service_name" in patch:
        updates["service_name"] = patch["service_name"]
    if "path" in patch:
        updates["path"] = patch["path"]

    if updates:
        dep = await store.update_dependency(project_slug, dep_type, actual_name, updates)

    logger.info("patch_dependency: project=%s, dep_type=%s, name=%s -> %s", project_slug, dep_type, dep_name, actual_name)
    return _dep_to_response(dep, project_slug)


@router.delete("/{dep_name:path}")
async def delete_dependency(
    project_slug: str,
    dep_name: str,
    dep_type: str = Query(..., description="db_table | external_api | cache | kafka_topic | external_doc"),
):
    """Delete a dependency entry from the JSON file."""
    dep = await store.get_dependency(project_slug, dep_type, dep_name)
    if dep is None:
        raise HTTPException(status_code=404, detail=f"Dependency '{dep_name}' not found")
    await store.delete_dependency(project_slug, dep_type, dep_name)
    logger.info("delete_dependency: project=%s, dep_type=%s, name=%s", project_slug, dep_type, dep_name)
    return {"ok": True}


async def _run_enrichment_background(
    project_slug: str,
    dep_type: str,
    dep_name: str | None,
    text_content: str,
    source_name: str,
    *,
    task_id: str | None = None,
) -> None:
    """Background wrapper: run enrichment pipeline and handle status transitions."""
    try:
        enriched_deps = await run_enrichment_pipeline(
            project_slug=project_slug,
            dep_type=dep_type,
            text_content=text_content,
            source_name=source_name,
            store=store,
            target_dep_name=dep_name,
        )
        # enrichment_status is set to "enriched" inside run_enrichment_pipeline

        # Sync required fields from enriched data into feature mappings
        for dep_resp in enriched_deps:
            if dep_resp.enriched_data:
                try:
                    await sync_required_after_enrichment(
                        project_slug=project_slug,
                        dep_type=dep_resp.dep_type,
                        dep_name=dep_resp.name,
                        enriched_data=dep_resp.enriched_data,
                        store=store,
                    )
                except Exception as sync_exc:
                    logger.warning(
                        "required_sync failed (non-fatal): %s/%s: %s",
                        dep_resp.dep_type, dep_resp.name, sync_exc,
                    )
    except Exception as exc:
        logger.error(
            "Enrichment failed: project=%s, dep_type=%s, dep_name=%s: %s",
            project_slug, dep_type, dep_name, exc,
        )
        # Mark affected deps as error
        if dep_name:
            await store.update_dependency(project_slug, dep_type, dep_name, {
                "enrichment_status": "error",
            })
        else:
            # Bulk: mark all "running" deps of this type as error
            by_type = await store.list_dependencies(project_slug)
            for dep in by_type.get(dep_type, []):
                if dep.get("enrichment_status") == "running":
                    await store.update_dependency(project_slug, dep_type, dep["name"], {
                        "enrichment_status": "error",
                    })
        if task_id:
            await store.finish_task(
                project_slug, task_id, status="error", error_message=str(exc),
            )
        return
    if task_id:
        await store.finish_task(project_slug, task_id, status="done")


@router.post("/enrich")
async def enrich_dependency(
    project_slug: str,
    request: ConfluenceImportRequest,
    dep_type: str = Query(..., description="db_table | external_api | cache | kafka_topic | external_doc"),
    dep_name: str | None = Query(None, description="Target specific dependency by name"),
):
    """Enrich dependencies of the given type from a Confluence page URL (async)."""
    proj = await store.get_project(project_slug)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_slug}' not found")

    valid_types = ("db_table", "external_api", "cache", "kafka_topic", "external_doc")
    if dep_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dep_type: {dep_type}. Must be one of: {', '.join(valid_types)}",
        )

    # external_doc supports only targeted enrichment — fail-fast before fetching
    if dep_type == "external_doc" and not dep_name:
        raise HTTPException(status_code=400, detail=EXTERNAL_DOC_TARGETED_ONLY_MSG)

    try:
        page = await fetch_page(request.url)
    except ConfluenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info(
        "enrich_dependency: project=%s, dep_type=%s, dep_name=%s, page='%s' (%.1fKB)",
        project_slug, dep_type, dep_name, page["title"], len(page["markdown"]) / 1024,
    )

    # Mark targeted dep as "running" immediately (dep-level data state — kept
    # alongside the tasks log so the dep card keeps its running indicator).
    if dep_name:
        dep = await store.get_dependency(project_slug, dep_type, dep_name)
        if dep is None:
            raise HTTPException(status_code=404, detail=f"Dependency '{dep_name}' not found")
        await store.update_dependency(project_slug, dep_type, dep_name, {
            "enrichment_status": "running",
        })
    else:
        # Bulk: mark all stubs of this type as "running"
        by_type = await store.list_dependencies(project_slug)
        for dep in by_type.get(dep_type, []):
            if dep.get("enrichment_status") in ("stub", "error"):
                await store.update_dependency(project_slug, dep_type, dep["name"], {
                    "enrichment_status": "running",
                })

    task_key = f"enrich:{project_slug}/{dep_type}"
    if dep_name:
        task_key += f"/{dep_name}"

    target_id = dep_name if dep_name else f"bulk:{dep_type}"
    active = await store.get_active_task(project_slug, kind="enrichment", target_id=target_id)
    if active is not None:
        if task_manager.is_running(task_key):
            raise HTTPException(status_code=409, detail="Enrichment is already running")
        logger.warning(
            "enrich: stuck task %s for %s/%s, recovering",
            active["id"], project_slug, target_id,
        )
        await store.finish_task(
            project_slug, active["id"], status="error",
            error_message="Server restarted before task completed",
        )

    task = await store.create_task(
        project_slug, kind="enrichment", target_type="dependency", target_id=target_id,
    )
    task_manager.launch(
        task_key,
        _run_enrichment_background(
            project_slug, dep_type, dep_name, page["markdown"],
            page["title"], task_id=task["id"],
        ),
    )

    return {"status": "running"}
