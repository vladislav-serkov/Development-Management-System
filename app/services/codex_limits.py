"""Usage limits of the ChatGPT subscription that runs every Codex workflow.

Read through the Codex app-server (``account/rateLimits/read``) with the same
saved ChatGPT login the agent jobs use. A read spawns a short-lived app-server
process outside the agent queue, so it never waits for a running job; results
are cached briefly because the UI polls them.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from openai_codex import CodexConfig
from openai_codex.async_client import AsyncCodexClient
from openai_codex.generated.v2_all import GetAccountRateLimitsResponse, RateLimitSnapshot

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60
ERROR_CACHE_SECONDS = 15
MIN_REFRESH_SECONDS = 10
READ_TIMEOUT_SECONDS = 45

_lock = asyncio.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None


def _window(kind: str, window: Any) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "kind": kind,
        "window_minutes": window.window_duration_mins,
        "used_percent": max(0, min(100, window.used_percent)),
        "resets_at": _iso(window.resets_at),
    }


def _bucket(snapshot: RateLimitSnapshot) -> dict[str, Any]:
    windows = [w for w in (_window("primary", snapshot.primary), _window("secondary", snapshot.secondary)) if w]
    return {
        "id": snapshot.limit_id,
        "name": snapshot.limit_name,
        "windows": windows,
        "reached": snapshot.rate_limit_reached_type is not None or any(w["used_percent"] >= 100 for w in windows),
    }


def summarize(response: GetAccountRateLimitsResponse) -> dict[str, Any]:
    """What the UI shows; never includes the account id."""
    main = response.rate_limits
    snapshots = [main]
    if response.rate_limits_by_limit_id:
        snapshots = [RateLimitSnapshot.model_validate(raw) for raw in response.rate_limits_by_limit_id.values()]
        # The main bucket first, then the others in the backend's order
        snapshots.sort(key=lambda s: s.limit_id != main.limit_id)
    buckets = [b for b in (_bucket(s) for s in snapshots) if b["windows"]]
    credits = main.credits
    reset_credits = response.rate_limit_reset_credits
    return {
        "available": True,
        "plan": main.plan_type.value if main.plan_type else None,
        "limits": buckets,
        "usage_allowed": response.ordinary_usage_allowed,
        "credits": (
            {"has_credits": credits.has_credits, "unlimited": credits.unlimited, "balance": credits.balance}
            if credits else None
        ),
        "reset_credits": reset_credits.available_count if reset_credits else 0,
        "error": None,
    }


async def _read() -> GetAccountRateLimitsResponse:
    client = AsyncCodexClient(config=CodexConfig(
        codex_bin=settings.codex_cli or None,
        # Never select API billing via an inherited environment key.
        env={"CODEX_API_KEY": "", "OPENAI_API_KEY": "", "CLAUDE_CODE_OAUTH_TOKEN": ""},
        client_name="extract_agent",
        client_title="Extract Agent",
    ))
    await client.start()
    try:
        await client.initialize()
        account = await client.account_read()
        if account.account is None or account.account.root.type != "chatgpt":
            raise PermissionError("Codex не авторизован через ChatGPT")
        return await client.request(
            "account/rateLimits/read",
            {"excludeResetCreditDetails": True},
            response_model=GetAccountRateLimitsResponse,
        )
    finally:
        await client.close()


async def get_limits(*, refresh: bool = False) -> dict[str, Any]:
    global _cache
    if not settings.codex_enabled:
        return {"available": False, "error": "Codex отключён (CODEX_ENABLED=false)", "fetched_at": None}
    async with _lock:
        now = time.monotonic()
        if _cache is not None:
            age = now - _cache[0]
            ttl = CACHE_SECONDS if _cache[1]["available"] else ERROR_CACHE_SECONDS
            if age < (MIN_REFRESH_SECONDS if refresh else ttl):
                return _cache[1]
        try:
            async with asyncio.timeout(READ_TIMEOUT_SECONDS):
                result = summarize(await _read())
        except PermissionError as exc:
            result = {"available": False, "error": f"{exc}: выполните codex login на сервере платформы"}
        except Exception as exc:  # noqa: BLE001 — the widget shows the failure, the app keeps working
            logger.warning("codex limits read failed: %r", exc)
            result = {"available": False, "error": "Не удалось получить лимиты Codex"}
        result["fetched_at"] = datetime.now(UTC).isoformat()
        _cache = (time.monotonic(), result)
        return result
