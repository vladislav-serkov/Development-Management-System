from app.services.confluence import _derive_service_name


def _page(title, ancestors):
    return {"title": title, "ancestors": [{"title": t} for t in ancestors]}


def test_service_from_bracket_in_own_title():
    page = _page("[flp-order] GET /v1/payment/amount", ["Сервисы", "flp-order"])
    assert _derive_service_name(page) == "flp-order"


def test_service_from_bracket_in_ancestor():
    page = _page(
        "POST /v1/client/purchases",
        ["MTS PAY", "Сервисы [5533e2f90e88]", "bnpl-payment", "[bnpl-payment] API"],
    )
    assert _derive_service_name(page) == "bnpl-payment"


def test_service_from_kebab_ancestor_title():
    page = _page("GET /v1/balance", ["Документация", "Сервисы", "flp-card-balance"])
    assert _derive_service_name(page) == "flp-card-balance"


def test_deepest_ancestor_wins():
    # Two service-like ancestors: the closest one to the page is the right one
    page = _page(
        "GET /v1/x",
        ["bnpl-registry", "[bnpl-registry] API", "bnpl-payment", "[bnpl-payment] API"],
    )
    assert _derive_service_name(page) == "bnpl-payment"


def test_no_service_found():
    page = _page("Решение инцидентов Авито", ["MTS PAY", "Документация"])
    assert _derive_service_name(page) is None
