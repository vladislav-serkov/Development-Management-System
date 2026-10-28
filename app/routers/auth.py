from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings
from app.services.auth import (
    SESSION_COOKIE,
    AuthStore,
    is_throttled,
    record_failure,
    reset_failures,
)

store = AuthStore()
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/me")
async def me(request: Request):
    if not settings.auth_enabled:
        return {"auth_enabled": False, "username": None}
    token = request.cookies.get(SESSION_COOKIE)
    user = await store.user_for_token(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"auth_enabled": True, "username": user["username"]}


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    username = body.username.strip()
    if is_throttled(username):
        raise HTTPException(status_code=429, detail="Слишком много попыток, попробуйте позже")
    user = await store.authenticate(username, body.password)
    if user is None:
        record_failure(username)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    reset_failures(username)
    token = await store.create_session(user["id"])
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"auth_enabled": settings.auth_enabled, "username": user["username"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await store.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
