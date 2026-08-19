"""Execute curl artifacts against the test stand.

The artifact's host (usually a localhost placeholder) is replaced with the
configured stand base URL plus the service's route prefix, so only the
path/query from the artifact reaches the stand. Errors come back in the
payload (not as exceptions) so the UI can render them next to the request.

The stand's gateway does not strip service prefixes, and services mount their
controllers under service-specific prefixes (flp-order → /flp-order/v1/...,
bnpl-payment → /bnpl-payment/api/v1/...). The real prefix is derived from the
service's own OpenAPI (/{service}/v3/api-docs) and cached; /{service} is the
fallback when api-docs is unreachable.
"""

import logging
import re
import time
from collections import Counter
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
MAX_BODY_CHARS = 100_000
PREFIX_CACHE_TTL = 300

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# service name -> (monotonic timestamp, resolved route prefix)
_prefix_cache: dict[str, tuple[float, str]] = {}

# Headers the proxy must own: the target host differs from the artifact's,
# and httpx computes framing/encoding itself.
_DROPPED_REQUEST_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "accept-encoding"}


def is_configured() -> bool:
    return bool(settings.test_stand_url)


def derive_route_prefix(paths: list[str], default: str) -> str:
    """The controllers' common prefix before the API version segment.

    Spec paths in artifacts start at /vN/..., so the prefix is whatever the
    service declares before /vN/ in its OpenAPI paths (most common one wins).
    """
    counts = Counter()
    for p in paths:
        m = re.match(r"^(.*?)/v\d+/", p)
        if m is not None:
            counts[m.group(1)] += 1
    if not counts:
        return default
    return counts.most_common(1)[0][0]


async def resolve_route_prefix(service_name: str | None) -> str:
    """Route prefix for the service on the stand, from its OpenAPI (cached)."""
    if not service_name:
        return ""
    default = f"/{service_name.strip('/')}"
    cached = _prefix_cache.get(service_name)
    if cached is not None and time.monotonic() - cached[0] < PREFIX_CACHE_TTL:
        return cached[1]

    base = settings.test_stand_url.rstrip("/")
    prefix = default
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base}{default}/v3/api-docs")
            response.raise_for_status()
            paths = list((response.json().get("paths") or {}).keys())
        prefix = derive_route_prefix(paths, default)
    except Exception as exc:  # noqa: BLE001 — any failure means "use the default"
        logger.info("api-docs for %s unavailable (%s), using %s", service_name, exc, default)

    _prefix_cache[service_name] = (time.monotonic(), prefix)
    return prefix


def build_target_url(route_prefix: str, path: str) -> str:
    """Stand base + resolved route prefix + the artifact's path (with query)."""
    base = settings.test_stand_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    # The artifact may already carry the full prefixed path — don't double it
    if route_prefix and path.startswith(route_prefix + "/"):
        return base + path
    return base + route_prefix + path


async def stand_info(service_name: str | None) -> dict[str, Any]:
    if not is_configured():
        return {"configured": False, "base_url": None, "service": None, "target_base": None}
    base = settings.test_stand_url.rstrip("/")
    prefix = await resolve_route_prefix(service_name)
    return {
        "configured": True,
        "base_url": base,
        "service": service_name,
        "target_base": base + prefix,
    }


def sanitize_request_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in headers.items()
        if name.strip().lower() not in _DROPPED_REQUEST_HEADERS
    }


async def execute_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
) -> dict[str, Any]:
    started = time.monotonic()
    request_headers = sanitize_request_headers(headers)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            response = await client.request(
                method,
                url,
                headers=request_headers,
                content=body.encode("utf-8") if body is not None else None,
            )
    except httpx.HTTPError as exc:
        logger.warning("test-stand request failed: %s %s: %s", method, url, exc)
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(exc, httpx.TimeoutException):
            message = f"Таймаут запроса ({REQUEST_TIMEOUT}с)"
        return {
            "url": url,
            "method": method,
            "status_code": None,
            "reason": None,
            "headers": [],
            "body": None,
            "body_truncated": False,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error": f"Не удалось выполнить запрос: {message}",
        }

    text = response.text
    return {
        "url": url,
        "method": method,
        "status_code": response.status_code,
        "reason": response.reason_phrase,
        "headers": [{"name": name, "value": value} for name, value in response.headers.items()],
        "body": text[:MAX_BODY_CHARS],
        "body_truncated": len(text) > MAX_BODY_CHARS,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "error": None,
    }
