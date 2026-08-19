import pytest

from app.config import settings
from app.services.http_runner import (
    build_target_url,
    derive_route_prefix,
    sanitize_request_headers,
    stand_info,
)


@pytest.fixture
def stand_url(monkeypatch):
    monkeypatch.setattr(settings, "test_stand_url", "http://stand.example:8090/")


def test_build_target_url_joins_base_prefix_and_path(stand_url):
    assert (
        build_target_url("/bnpl-payment/api", "/v1/balance?x=1")
        == "http://stand.example:8090/bnpl-payment/api/v1/balance?x=1"
    )


def test_build_target_url_without_prefix(stand_url):
    assert build_target_url("", "v1/balance") == "http://stand.example:8090/v1/balance"


def test_build_target_url_skips_already_prefixed_path(stand_url):
    assert (
        build_target_url("/flp-order", "/flp-order/v1/orders")
        == "http://stand.example:8090/flp-order/v1/orders"
    )


def test_derive_route_prefix_picks_most_common():
    paths = [
        "/bnpl-payment/api/v1/client/debt",
        "/bnpl-payment/api/v1/client/loans",
        "/bnpl-payment/api/v2/purchase",
        "/actuator/health",
    ]
    assert derive_route_prefix(paths, "/bnpl-payment") == "/bnpl-payment/api"


def test_derive_route_prefix_without_api_segment():
    paths = ["/flp-order/v1/orders", "/flp-order/v1/payments"]
    assert derive_route_prefix(paths, "/flp-order") == "/flp-order"


def test_derive_route_prefix_falls_back_when_no_versioned_paths():
    assert derive_route_prefix(["/actuator/health"], "/svc") == "/svc"
    assert derive_route_prefix([], "/svc") == "/svc"


@pytest.mark.anyio
async def test_stand_info_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "test_stand_url", "")
    assert await stand_info("svc") == {
        "configured": False, "base_url": None, "service": None, "target_base": None,
    }


def test_sanitize_request_headers_drops_transport_headers():
    headers = {
        "Host": "localhost:8080",
        "Content-Length": "42",
        "Content-Type": "application/json",
        "request-id": "abc",
    }
    assert sanitize_request_headers(headers) == {
        "Content-Type": "application/json",
        "request-id": "abc",
    }
