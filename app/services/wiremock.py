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
