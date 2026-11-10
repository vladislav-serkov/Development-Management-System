"""Upload a test-case mapping to the configured test WireMock instance."""

import json
import time
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.config import settings

REQUEST_TIMEOUT = 30


class WireMockError(Exception):
    """A mapping could not be uploaded to the test stand."""


class InvalidMappingError(ValueError):
    """The artifact is not a valid WireMock mapping envelope."""


def mappings_url() -> str | None:
    base = settings.test_wiremock_url.strip().rstrip("/")
    return f"{base}/__admin/mappings" if base else None


def prepare_mapping(value: str) -> dict[str, Any]:
    """Validate the envelope; response bodies may intentionally be malformed JSON."""
    try:
        mapping = json.loads(value)
        # Python accepts NaN/Infinity in json.loads, but HTTP JSON does not.
        json.dumps(mapping, allow_nan=False)
    except ValueError as exc:
        raise InvalidMappingError("Мок должен содержать корректный JSON mapping WireMock") from exc
    if not isinstance(mapping, dict):
        raise InvalidMappingError("Ожидается один JSON mapping WireMock с request и response")
    request = mapping.get("request")
    if not isinstance(request, dict) or not request:
        raise InvalidMappingError("В моке отсутствует объект request")
    if not isinstance(mapping.get("response"), dict) or not mapping["response"]:
        raise InvalidMappingError("В моке отсутствует объект response")

    # Honour explicit ids, including the legacy uuid alias used by the stand.
    ids = []
    for key in ("id", "uuid"):
        if key in mapping:
            try:
                ids.append(str(UUID(str(mapping[key]))))
            except ValueError as exc:
                raise InvalidMappingError(f"Поле {key} должно быть UUID") from exc
    if len(set(ids)) > 1:
        raise InvalidMappingError("Поля id и uuid должны совпадать")
    # Reuse one app-owned id for the same matcher so switching case responses
    # updates the stub instead of leaving competing mappings on a shared stand.
    identity = {key: mapping[key] for key in ("request", "scenarioName", "requiredScenarioState") if key in mapping}
    mapping["id"] = ids[0] if ids else str(uuid5(
        NAMESPACE_URL, "extract-agent:wiremock:" + json.dumps(identity, sort_keys=True, ensure_ascii=False),
    ))
    if "uuid" in mapping:
        mapping["uuid"] = mapping["id"]
    return mapping


async def upload_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    url = mappings_url()
    if not url:
        raise WireMockError("WireMock не настроен — задайте TEST_WIREMOCK_URL в .env")
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            response = await client.put(f"{url}/{mapping['id']}", json=mapping)
            if response.status_code == 404:
                response = await client.post(url, json=mapping)
    except httpx.HTTPError as exc:
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(exc, httpx.TimeoutException):
            message = f"Таймаут запроса ({REQUEST_TIMEOUT}с)"
        raise WireMockError(f"Не удалось загрузить мок в WireMock: {message}") from exc
    if not 200 <= response.status_code < 300:
        detail = response.text[:2000].strip()
        raise WireMockError(f"WireMock вернул HTTP {response.status_code}" + (f": {detail}" if detail else ""))
    return {
        "mapping_id": mapping["id"],
        "target_url": url,
        "status_code": response.status_code,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


async def _admin_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read-only call to the WireMock admin API of the test stand."""
    url = mappings_url()
    if not url:
        raise WireMockError("WireMock не настроен — задайте TEST_WIREMOCK_URL в .env")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            response = await client.get(url.removesuffix("/mappings") + path, params=params)
    except httpx.HTTPError as exc:
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(exc, httpx.TimeoutException):
            message = f"Таймаут запроса ({REQUEST_TIMEOUT}с)"
        raise WireMockError(f"WireMock недоступен: {message}") from exc
    if not 200 <= response.status_code < 300:
        raise WireMockError(f"WireMock вернул HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise WireMockError("WireMock вернул ответ не в формате JSON") from exc
    if not isinstance(payload, dict):
        raise WireMockError("WireMock вернул неожиданный ответ")
    return payload


def _request_urls(request: dict[str, Any]) -> list[str]:
    return [str(request[key]) for key in ("url", "urlPath", "urlPattern", "urlPathPattern") if request.get(key)]


async def find_mappings(url_contains: str | None, *, limit: int = 15) -> dict[str, Any]:
    """Stubs registered on the stand whose URL matcher contains the given text."""
    payload = await _admin_get("/mappings")
    needle = (url_contains or "").strip().lower()
    mappings = [m for m in payload.get("mappings") or [] if isinstance(m, dict)]
    matched = [
        m for m in mappings
        if not needle or any(needle in url.lower() for url in _request_urls(m.get("request") or {}))
    ]
    return {"total": len(mappings), "matched_count": len(matched), "mappings": matched[:limit]}


async def recent_requests(url_contains: str | None, *, limit: int = 15) -> dict[str, Any]:
    """Latest requests the stand's WireMock received (its request journal), newest first."""
    payload = await _admin_get("/requests", {"limit": 300})
    needle = (url_contains or "").strip().lower()
    entries = []
    for item in payload.get("requests") or []:
        request = item.get("request") or {}
        if needle and needle not in str(request.get("url", "")).lower():
            continue
        response = item.get("response") or item.get("responseDefinition") or {}
        entries.append({
            "time": request.get("loggedDateString"),
            "method": request.get("method"),
            "url": request.get("url"),
            "body": (request.get("body") or "")[:1500],
            "matched": bool(item.get("wasMatched")),
            "stub_id": (item.get("stubMapping") or {}).get("id"),
            "response_status": response.get("status"),
        })
    return {"matched_count": len(entries), "requests": entries[:limit]}
