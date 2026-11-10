import logging

from fastapi import APIRouter, HTTPException, Request

from app.schemas.assistant import ResolveSuggestionRequest, SendMessageRequest
from app.services import agent_runner, tc_assistant
from app.storage import ProjectStore

logger = logging.getLogger(__name__)

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/assistant",
    tags=["assistant"],
)


async def _feature(project_slug: str, feature_name: str) -> dict:
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
    return feature


def _author(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    return user["username"] if user else None


@router.get("")
async def assistant_overview(project_slug: str, feature_name: str):
    """Sessions of the feature and what the assistant can reach on the stand."""
    feature = await _feature(project_slug, feature_name)
    name = feature["name"]
    # Polling doubles as recovery: queued messages get a worker after a restart
    await tc_assistant.ensure_worker(store, project_slug, name)
    stand = await tc_assistant.feature_stand(store, project_slug, feature)
    return {
        "sessions": await store.list_assistant_sessions(project_slug, name),
        "stand": stand.capabilities(),
        "enabled": agent_runner.is_configured(),
    }


@router.get("/sessions/{session_id}")
async def get_session(project_slug: str, feature_name: str, session_id: str):
    feature = await _feature(project_slug, feature_name)
    await tc_assistant.ensure_worker(store, project_slug, feature["name"])
    session = await store.get_assistant_session(project_slug, feature["name"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(project_slug: str, feature_name: str, session_id: str):
    feature = await _feature(project_slug, feature_name)
    try:
        deleted = await store.delete_assistant_session(project_slug, feature["name"], session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return {"status": "deleted"}


@router.post("/messages")
async def send_message(project_slug: str, feature_name: str, body: SendMessageRequest, request: Request):
    """Queue a message for the assistant. Without session_id a new session is opened.
    Poll the session for the answer."""
    feature = await _feature(project_slug, feature_name)
    if feature.get("status") != "done":
        raise HTTPException(status_code=409, detail="Фича ещё извлекается — ассистент будет доступен после этого")
    try:
        turn = await tc_assistant.send_message(
            store, project_slug, feature["name"],
            text=body.text, attachments=[a.model_dump(exclude_none=True) for a in body.attachments],
            session_id=body.session_id, author=_author(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info(
        "assistant message: project=%s feature=%s session=%s turn=%s",
        project_slug, feature["name"], turn["session_id"], turn["id"],
    )
    return turn


@router.delete("/turns/{turn_id}")
async def remove_queued_turn(project_slug: str, feature_name: str, turn_id: str):
    """Take a message back while it is still waiting in the queue."""
    feature = await _feature(project_slug, feature_name)
    if not await store.delete_assistant_turn(project_slug, feature["name"], turn_id):
        raise HTTPException(status_code=409, detail="Сообщение уже в работе или не найдено")
    return {"status": "deleted"}


@router.post("/turns/{turn_id}/cancel")
async def cancel_turn(project_slug: str, feature_name: str, turn_id: str):
    feature = await _feature(project_slug, feature_name)
    if not await tc_assistant.cancel_turn(store, project_slug, feature["name"], turn_id):
        raise HTTPException(status_code=409, detail="Ассистент сейчас не работает над этим сообщением")
    return {"status": "cancelled"}


@router.post("/turns/{turn_id}/retry")
async def retry_turn(project_slug: str, feature_name: str, turn_id: str, request: Request):
    """Send a failed or cancelled message again, in the same session."""
    feature = await _feature(project_slug, feature_name)
    turn = await store.get_assistant_turn(project_slug, feature["name"], turn_id)
    if turn is None:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    if turn["status"] not in ("error", "cancelled"):
        raise HTTPException(status_code=409, detail="Повторить можно только сообщение без ответа")
    return await tc_assistant.send_message(
        store, project_slug, feature["name"],
        text=turn["text"], attachments=turn.get("attachments") or [],
        session_id=turn["session_id"], author=_author(request),
    )


async def _decide(action):
    try:
        return await action
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except tc_assistant.AssistantConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/changes/{change_id}/revert")
async def revert_change(project_slug: str, feature_name: str, turn_id: str, change_id: str):
    """Undo one saved change of a case. Stand side effects are not rolled back."""
    feature = await _feature(project_slug, feature_name)
    return await _decide(tc_assistant.set_change_state(
        store, project_slug, feature["name"], turn_id, change_id, revert=True,
    ))


@router.post("/turns/{turn_id}/changes/{change_id}/restore")
async def restore_change(project_slug: str, feature_name: str, turn_id: str, change_id: str):
    feature = await _feature(project_slug, feature_name)
    return await _decide(tc_assistant.set_change_state(
        store, project_slug, feature["name"], turn_id, change_id, revert=False,
    ))


@router.post("/turns/{turn_id}/suggestions/{suggestion_id}")
async def resolve_suggestion(
    project_slug: str, feature_name: str, turn_id: str, suggestion_id: str, body: ResolveSuggestionRequest,
):
    feature = await _feature(project_slug, feature_name)
    return await _decide(tc_assistant.resolve_suggestion(
        store, project_slug, feature["name"], turn_id, suggestion_id, accept=body.accept,
    ))
