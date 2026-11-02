"""Gap analysis jobs, evidence reports and analyst decisions."""
from fastapi import APIRouter, HTTPException, Request

from app.schemas.gaps import GapContextRequest, GapReviewRequest
from app.services import agent_runner
from app.services.gap_sources import validate_source_url
from app.services.gaps import now, run_gaps_pipeline, with_ids
from app.services.task_manager import task_manager
from app.storage import ActiveTaskExistsError, ProjectStore

store = ProjectStore()
router = APIRouter(prefix="/projects/{project_slug}/features/{feature_name}/gaps", tags=["gaps"])
context_router = APIRouter(prefix="/projects/{project_slug}/gap-context", tags=["gaps"])


async def get_feature(project_slug: str, feature_name: str) -> dict:
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(404, "Фича не найдена")
    return feature


async def active_task(project_slug: str, feature_name: str):
    active = await store.get_active_task(project_slug, kind="gaps", target_id=feature_name)
    if active and not task_manager.is_running(f"gaps:{project_slug}/{feature_name}"):
        await store.finish_task(project_slug, active["id"], status="error", error_message="Сервер перезапущен во время анализа")
        await store.update_feature(project_slug, feature_name, {
            "gaps_job": {"stage": "error", "error": "Сервер перезапущен во время анализа. Запустите проверку снова"},
        })
        return None
    return active


@router.post("/run")
async def run_gaps_analysis(project_slug: str, feature_name: str):
    feature = await get_feature(project_slug, feature_name)
    feature_name = feature["name"]
    if not agent_runner.is_configured():
        raise HTTPException(409, "Codex отключён: установите CODEX_ENABLED=true")
    if feature.get("status") != "done":
        raise HTTPException(409, "Дождитесь завершения извлечения фичи")
    if await active_task(project_slug, feature_name):
        raise HTTPException(409, "Анализ этой фичи уже выполняется")
    try:
        task = await store.create_task(project_slug, kind="gaps", target_type="feature", target_id=feature_name)
    except ActiveTaskExistsError as exc:
        raise HTTPException(409, "Анализ этой фичи уже выполняется") from exc
    await store.update_feature(project_slug, feature_name, {"gaps_job": {"stage": "sources", "error": None}})
    task_manager.launch(
        f"gaps:{project_slug}/{feature_name}",
        run_gaps_pipeline(project_slug, feature_name, store, task_id=task["id"]),
    )
    return {"status": "running"}


@router.post("/cancel")
async def cancel_gaps(project_slug: str, feature_name: str):
    feature = await get_feature(project_slug, feature_name)
    feature_name = feature["name"]
    cancelled = await task_manager.cancel(f"gaps:{project_slug}/{feature_name}")
    if cancelled:
        active = await store.get_active_task(project_slug, kind="gaps", target_id=feature_name)
        if active:
            await store.finish_task(project_slug, active["id"], status="error", error_message="Анализ остановлен пользователем")
            await store.update_feature(project_slug, feature_name, {"gaps_job": {"stage": "cancelled", "error": None}})
    else:
        await active_task(project_slug, feature_name)
    return {"status": "cancelled" if cancelled else "idle"}


@router.get("/")
async def list_gaps(project_slug: str, feature_name: str):
    feature = await get_feature(project_slug, feature_name)
    feature_name = feature["name"]
    active = await active_task(project_slug, feature_name)
    feature = await get_feature(project_slug, feature_name)
    return {
        "gaps": [g for g in with_ids(await store.get_gaps(project_slug, feature_name, include_archived=True))
                 if not g.get("archived")],
        "gaps_running": active is not None, "gaps_run_at": feature.get("gaps_run_at"),
        "analysis": feature.get("gaps_analysis"), "job": feature.get("gaps_job"),
        "stale": bool(feature.get("gaps_stale")), "configured": agent_runner.is_configured(),
    }


@router.patch("/items/{gap_id}")
async def review_gap(project_slug: str, feature_name: str, gap_id: str, body: GapReviewRequest, request: Request):
    feature = await get_feature(project_slug, feature_name)
    text = (body.analyst_text or "").strip() or None
    if body.status in ("clarified", "rejected") and not text:
        raise HTTPException(422, "Укажите уточнение или причину отклонения")
    user = getattr(request.state, "user", None)
    actor = user.get("username", "Аналитик") if isinstance(user, dict) else "Аналитик"

    def mutate(current):
        items = with_ids(current)
        gap = next((g for g in items if g["id"] == gap_id), None)
        if gap is None:
            raise HTTPException(404, "Замечание не найдено; обновите список")
        gap.update(status=body.status, analyst_text=text, needs_review=False)
        gap["history"] = [*gap.get("history", []), {
            "at": now(), "action": body.status, "text": text, "actor": actor,
        }]
        return items

    gaps = await store.mutate_gaps(project_slug, feature["name"], mutate)
    return {"gaps": [g for g in gaps if not g.get("archived")]}


@context_router.get("")
async def get_context(project_slug: str):
    context = await store.get_gap_context(project_slug)
    if context is None:
        raise HTTPException(404, "Проект не найден")
    return context


@context_router.patch("")
async def save_context(project_slug: str, body: GapContextRequest):
    urls = list(dict.fromkeys(url.strip() for url in body.source_urls if url.strip()))
    try:
        for url in urls:
            validate_source_url(url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    context = await store.save_gap_context(project_slug, {"notes": body.notes.strip(), "source_urls": urls})
    if context is None:
        raise HTTPException(404, "Проект не найден")
    return context


# The previous flow silently edited the extracted copy of a specification.
# Keep old clients from invoking it while making the removal explicit.
@router.post("/apply-preview")
@router.get("/apply-preview")
@router.post("/apply-confirm")
async def removed_apply(project_slug: str, feature_name: str):
    raise HTTPException(410, "Решения аналитика сохраняются отдельно. Изменения вносятся в исходное ТЗ")
