"""Minimal login for the web UI.

Accounts are issued by the operator (``python -m app.cli users ...``); there is
no self sign-up. Passwords are hashed with scrypt (stdlib), sessions are opaque
random tokens in an HttpOnly cookie — the DB keeps only their SHA-256, so a DB
dump does not leak live sessions.
"""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import get_session_factory
from app.models import User, UserSession

SESSION_COOKIE = "ea_session"

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1

# Failed-login throttle (per process): at most N failures per username per window
_MAX_FAILURES = 10
_FAILURE_WINDOW_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(digest.hex(), digest_hex)


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_throttled(username: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _failures.get(username.lower(), []) if now - t < _FAILURE_WINDOW_SECONDS]
    _failures[username.lower()] = recent
    return len(recent) >= _MAX_FAILURES


def record_failure(username: str) -> None:
    _failures.setdefault(username.lower(), []).append(time.monotonic())


def reset_failures(username: str) -> None:
    _failures.pop(username.lower(), None)


class AuthStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None):
        self._session_factory = session_factory

    @property
    def _sf(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    async def authenticate(self, username: str, password: str) -> dict | None:
        async with self._sf() as s:
            user = await s.scalar(select(User).where(User.username == username))
        if user is None or not verify_password(password, user.password_hash):
            return None
        return {"id": user.id, "username": user.username}

    async def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        async with self._sf.begin() as s:
            # Opportunistic cleanup keeps the table from growing without a cron
            await s.execute(delete(UserSession).where(UserSession.expires_at < now))
            s.add(UserSession(
                token_hash=_token_hash(token),
                user_id=user_id,
                expires_at=now + timedelta(days=settings.session_ttl_days),
            ))
        return token

    async def user_for_token(self, token: str) -> dict | None:
        async with self._sf() as s:
            row = (await s.execute(
                select(User.id, User.username)
                .join(UserSession, UserSession.user_id == User.id)
                .where(UserSession.token_hash == _token_hash(token), UserSession.expires_at > datetime.now(UTC))
            )).first()
        return {"id": row.id, "username": row.username} if row else None

    async def delete_session(self, token: str) -> None:
        async with self._sf.begin() as s:
            await s.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))

    # ── operator commands (app.cli) ──────────────────────────────────────

    async def list_users(self) -> list[dict]:
        async with self._sf() as s:
            users = (await s.scalars(select(User).order_by(User.username))).all()
        return [{"username": u.username, "created_at": u.created_at} for u in users]

    async def create_user(self, username: str, password: str) -> bool:
        async with self._sf.begin() as s:
            if await s.scalar(select(User.id).where(User.username == username)) is not None:
                return False
            s.add(User(username=username, password_hash=hash_password(password)))
        return True

    async def set_password(self, username: str, password: str) -> bool:
        """Change a password and drop the user's sessions (forces re-login everywhere)."""
        async with self._sf.begin() as s:
            user = await s.scalar(select(User).where(User.username == username).with_for_update())
            if user is None:
                return False
            user.password_hash = hash_password(password)
            await s.execute(delete(UserSession).where(UserSession.user_id == user.id))
        return True

    async def delete_user(self, username: str) -> bool:
        async with self._sf.begin() as s:
            result = await s.execute(delete(User).where(User.username == username))
        return result.rowcount > 0
