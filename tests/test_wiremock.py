"""WireMock upload behaviour, using a simulated stand without external writes."""

import json

import httpx
import pytest

from app.config import settings
from app.services import wiremock

MAPPING = {
    "request": {"urlPathPattern": ".*/payment.do", "method": "POST"},
    "response": {"status": 200, "body": '{"errorCode":20998}', "headers": {"content-type": "application/json"}},
}
MAPPING_ID = "8ab9374c-702a-4c3f-9aa4-d693192eb745"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "test_wiremock_url", "http://stand.example/bnpl-wiremock/")


def simulate_stand(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(wiremock.httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler),
    ))


def test_explicit_ids_and_response_body_preserved():
    # A deliberately malformed external JSON response must remain testable.
    body = '{"bindings":[{"bindingId":"abc"},],"errorCode":0}'
    mapping = {**MAPPING, "id": MAPPING_ID, "uuid": MAPPING_ID, "response": {"status": 200, "body": body}}
    assert wiremock.prepare_mapping(json.dumps(mapping)) == mapping


def test_derived_id_reuses_matcher_when_switching_response():
    first = wiremock.prepare_mapping(json.dumps(MAPPING))
    changed = {**MAPPING, "response": {"status": 500}}
    assert wiremock.prepare_mapping(json.dumps(changed))["id"] == first["id"]
    scenario = {**MAPPING, "scenarioName": "payment", "requiredScenarioState": "Started"}
    assert wiremock.prepare_mapping(json.dumps(scenario))["id"] != first["id"]
    assert "id" not in MAPPING


def test_uuid_alias_becomes_id():
    assert wiremock.prepare_mapping(json.dumps({**MAPPING, "uuid": MAPPING_ID}))["id"] == MAPPING_ID


@pytest.mark.parametrize("value", [
    "not json", "null", "[]", '{}', '{"request":[],"response":{}}',
    '{"request":{"method":"GET","url":"/"},"response":{"status":NaN}}',
    json.dumps({**MAPPING, "id": "../reset"}),
    json.dumps({**MAPPING, "id": MAPPING_ID, "uuid": "ccaae906-c839-4a4e-90f7-39487a37459e"}),
])
def test_invalid_mapping_rejected(value):
    with pytest.raises(ValueError):
        wiremock.prepare_mapping(value)


@pytest.mark.anyio
@pytest.mark.parametrize("exists", [False, True])
async def test_upload_creates_or_updates_only_one_mapping(configured, monkeypatch, exists):
    calls = []
    mapping = wiremock.prepare_mapping(json.dumps({**MAPPING, "id": MAPPING_ID, "uuid": MAPPING_ID}))

    def handler(request):
        calls.append((request.method, str(request.url)))
        assert json.loads(request.content) == mapping
        if request.method == "PUT":
            return httpx.Response(200 if exists else 404)
        return httpx.Response(201)

    simulate_stand(monkeypatch, handler)
    result = await wiremock.upload_mapping(mapping)
    base = "http://stand.example/bnpl-wiremock/__admin/mappings"
    assert calls == [("PUT", f"{base}/{MAPPING_ID}")] + ([] if exists else [("POST", base)])
    assert result["mapping_id"] == MAPPING_ID
    assert result["status_code"] == (200 if exists else 201)
    assert result["target_url"] == base


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", "connect", "reject", "redirect"])
async def test_upload_failures_are_reported(configured, monkeypatch, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("", request=request)
        if failure == "connect":
            raise httpx.ConnectError("unreachable", request=request)
        return httpx.Response(302 if failure == "redirect" else 422, text="stand error")

    simulate_stand(monkeypatch, handler)
    with pytest.raises(wiremock.WireMockError, match="Таймаут" if failure == "timeout" else "WireMock"):
        await wiremock.upload_mapping(wiremock.prepare_mapping(json.dumps(MAPPING)))


@pytest.mark.anyio
async def test_api_status_validation_and_upload(configured, monkeypatch):
    # Real router registration and middleware, without startup migrations or a DB.
    from app.main import app

    monkeypatch.setattr(settings, "auth_enabled", False)
    original = httpx.AsyncClient
    simulate_stand(monkeypatch, lambda request: httpx.Response(200))
    async with original(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test-wiremock/status")
        assert response.json() == {
            "configured": True, "target_url": "http://stand.example/bnpl-wiremock/__admin/mappings",
        }
        response = await client.post("/test-wiremock/upload", json={"mock_config": "bad JSON"})
        assert response.status_code == 422
        response = await client.post("/test-wiremock/upload", json={"mock_config": json.dumps(MAPPING)})
        assert response.status_code == 200
        assert response.json()["mapping_id"]
        monkeypatch.setattr(settings, "test_wiremock_url", "")
        assert (await client.get("/test-wiremock/status")).json() == {"configured": False, "target_url": None}
        assert (await client.post("/test-wiremock/upload", json={"mock_config": json.dumps(MAPPING)})).status_code == 503


@pytest.mark.anyio
async def test_api_reports_stand_rejection(configured, monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "auth_enabled", False)
    original = httpx.AsyncClient
    simulate_stand(monkeypatch, lambda request: httpx.Response(401, text="Access denied"))
    async with original(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/test-wiremock/upload", json={"mock_config": json.dumps(MAPPING)})
    assert response.status_code == 502
    assert "401" in response.json()["detail"]
