"""resolve_identity: a feature is named from what the page states — the title
included — in whatever format the page is written; nothing is invented and a
name the page already has in the project is kept while the page supports it."""

import pytest

from app.schemas.extraction import DetectedFeature, FeatureType, StructuredBusinessLogic
from app.services.feature_identity import occurs, page_header, resolve_identity, strip_service_prefix

TITLE = "pay-later.flp.rbo-adapter.product.schedule.queue"
TEXT = "Сервис слушает и пишет результат в pay-later.rbo.flp.schedule.out.queue после обработки."


def _kafka(name: str, endpoint: str | None = None) -> DetectedFeature:
    return DetectedFeature(
        structured_logic=StructuredBusinessLogic(),
        name=name, type=FeatureType.kafka_consumer, confidence=1.0,
        summary="s", method="CONSUMER", endpoint=endpoint or name,
    )


def _rest(endpoint: str | None, method: str | None = None, name: str = "x", display_name: str | None = None) -> DetectedFeature:
    return DetectedFeature(
        structured_logic=StructuredBusinessLogic(),
        name=name, type=FeatureType.rest_endpoint, confidence=1.0,
        summary="s", method=method, endpoint=endpoint, display_name=display_name,
    )


def test_kafka_correct_topic_kept():
    f = _kafka(TITLE)
    assert resolve_identity(f, title=TITLE, text=TEXT) is None
    assert f.name == TITLE


def test_kafka_hallucinated_topic_corrected_to_title():
    # the real regression: LLM dropped ".product" from the topic on re-import
    f = _kafka("pay-later.flp.rbo-adapter.schedule.queue")
    note = resolve_identity(f, title=TITLE, text=TEXT)
    assert note is not None
    assert f.name == TITLE
    assert f.endpoint == TITLE


def test_kafka_topic_from_body_kept():
    f = _kafka("pay-later.rbo.flp.schedule.out.queue")
    assert resolve_identity(f, title="Какая-то страница", text=TEXT) is None
    assert f.name == "pay-later.rbo.flp.schedule.out.queue"


def test_kafka_topic_found_in_tables():
    f = _kafka("a.b.c.queue")
    tables = [{"rows": [["Топик", "a.b.c.queue"]]}]
    assert resolve_identity(f, title="t", text="", tables=tables) is None


def test_kafka_single_feature_title_topic_wins():
    # Seen live: the body names the out-queue the consumer writes to; the LLM picked it
    f = _kafka("pay-later.rbo.flp.schedule.out.queue")
    note = resolve_identity(f, title=TITLE, text=TEXT, single_feature=True)
    assert note is not None
    assert f.name == TITLE and f.endpoint == TITLE


def test_kafka_title_with_words_around_the_topic():
    title = "[bnpl-payment] Обработчик топика pay-later.processing.payment-notification.queue"
    f = _kafka("pay-later.processing.payment-notification.queue")
    assert resolve_identity(f, title=title, text="", single_feature=True) is None
    assert f.name == "pay-later.processing.payment-notification.queue"


def test_rest_path_corrected():
    f = _rest("/v1/credit-lines", "GET")
    note = resolve_identity(f, title="ТЗ", text="Эндпоинт GET /v1/credit-line возвращает лимит")
    assert note is not None
    assert f.endpoint == "/v1/credit-line"
    assert f.name == "GET /v1/credit-line"


def test_rest_single_feature_title_path_wins():
    # Seen live: the page links the controller path in swagger; the LLM picked it
    # on one run and the gateway path from the title on another
    text = "[swagger](https://host/swagger-ui/index.html#/payment-controller/getClientDebt)"
    f = _rest("/payment-controller/getClientDebt", "GET")
    note = resolve_identity(f, title="GET /v1/client/debt", text=text, single_feature=True)
    assert note is not None
    assert f.name == "GET /v1/client/debt" and f.endpoint == "/v1/client/debt"

    # Already the title path → no note; multi-feature pages keep the LLM's pick
    assert resolve_identity(f, title="GET /v1/client/debt", text=text, single_feature=True) is None
    g = _rest("/payment-controller/getClientDebt", "GET")
    resolve_identity(g, title="GET /v1/client/debt", text=text)
    assert g.endpoint == "/payment-controller/getClientDebt"


# --- titles in the wild: the format of the title must not matter ----------------

RETRY_TITLE = "[flp-rbo-adapter] POST/v1/support/payment/retry"
RETRY_TEXT = "Повторная отправка данных о совершенном платеже в РБО\n\n**Header**\n\nЛогика работы"


def test_method_glued_to_path_in_title():
    """Seen live: the path is only in the title, with no space after the method.
    The feature was named after the first line of the body."""
    f = _rest("/v1/support/payment/retry", "POST", display_name="Повторная отправка данных о совершенном платеже в РБО")
    assert resolve_identity(f, title=RETRY_TITLE, text=RETRY_TEXT, single_feature=True) is None
    assert f.name == "POST /v1/support/payment/retry"
    assert f.endpoint == "/v1/support/payment/retry" and f.method == "POST"
    assert f.display_name == "Повторная отправка данных о совершенном платеже в РБО"


def test_model_found_no_path_title_still_names_the_feature():
    # even when the model returns nothing usable, a page named after its endpoint is named by it
    f = _rest(None, None, name="Повторная отправка данных о совершенном платеже в РБО")
    resolve_identity(f, title=RETRY_TITLE, text=RETRY_TEXT, single_feature=True)
    assert f.name == "POST /v1/support/payment/retry"


def test_method_taken_from_title_behind_service_prefix():
    # Seen live: "[bnpl-mtspay-adapter] POST /v1/notification/payment/{paymentId}" lost its method
    f = _rest("/v1/notification/payment/{paymentId}", None)
    resolve_identity(
        f, title="[bnpl-mtspay-adapter] POST /v1/notification/payment/{paymentId}", text="", single_feature=True,
    )
    assert f.method == "POST"
    assert f.name == "POST /v1/notification/payment/{paymentId}"


def test_operation_that_is_not_a_path():
    title = "[flp-ewallet-adapter] getWallet.do – Получение клиента"
    f = _rest("getWallet.do", "POST", display_name="Получение клиента")
    assert resolve_identity(f, title=title, text="", single_feature=True) is None
    assert f.endpoint == "getWallet.do" and f.name == "POST getWallet.do"
    assert f.display_name == "Получение клиента"


def test_rest_page_without_any_path_is_named_after_the_page():
    f = _rest(None, None, name="pridumannoe_imya")
    note = resolve_identity(f, title="[svc] Проверка лимита клиента", text="Описание без пути", single_feature=True)
    assert note is not None
    assert f.name == "Проверка лимита клиента" and f.endpoint is None


def test_path_stated_only_in_body():
    f = _rest("/v1/limits/check", "POST")
    text = "Метод: POST /v1/limits/check. Вызывает /v1/client/profile."
    assert resolve_identity(f, title="[svc] Проверка лимита клиента", text=text, single_feature=True) is None
    assert f.name == "POST /v1/limits/check"


# --- a page keeps its identity across re-imports ----------------------------------

def test_prior_identity_kept_while_still_on_the_page():
    # the model picked another real path this time — not a reason to rename
    text = "Метод: POST /v1/limits/check. Вызывает /v1/client/profile."
    f = _rest("/v1/client/profile", "POST")
    prior = {"type": "rest_endpoint", "name": "POST /v1/limits/check", "endpoint": "/v1/limits/check", "method": "POST"}
    note = resolve_identity(f, title="[svc] Проверка лимита", text=text, prior=prior, single_feature=True)
    assert note is not None
    assert f.name == "POST /v1/limits/check"


def test_prior_identity_gone_from_the_page_is_replaced():
    f = _rest("/v2/limits/check", "POST")
    prior = {"type": "rest_endpoint", "name": "POST /v1/limits/check", "endpoint": "/v1/limits/check", "method": "POST"}
    resolve_identity(f, title="[svc] Проверка лимита", text="Метод: POST /v2/limits/check", prior=prior, single_feature=True)
    assert f.name == "POST /v2/limits/check"


def test_title_beats_prior_identity_from_the_body():
    # the first import picked a body path; the title names the real one
    text = "Вызывает /v1/client/profile."
    f = _rest("/v1/limits/check", "POST")
    prior = {"type": "rest_endpoint", "name": "POST /v1/client/profile", "endpoint": "/v1/client/profile", "method": "POST"}
    resolve_identity(f, title="[svc] POST /v1/limits/check", text=text, prior=prior, single_feature=True)
    assert f.name == "POST /v1/limits/check"


def test_prior_of_another_type_is_ignored():
    f = _rest("/v1/x/y", "GET")
    prior = {"type": "kafka_consumer", "name": "a.b.c", "endpoint": "a.b.c"}
    resolve_identity(f, title="GET /v1/x/y", text="", prior=prior, single_feature=True)
    assert f.name == "GET /v1/x/y"


def test_scheduled_task_slug_is_kept_once_assigned():
    def task(name):
        return DetectedFeature(
            structured_logic=StructuredBusinessLogic(),
            name=name, type=FeatureType.scheduled_task, confidence=1.0,
            summary="s", method="SCHEDULED", schedule="Ежедневно в 19:00",
            display_name="Отправка запроса на проверку лимита",
        )

    f = task("send_limit_check_request")
    assert resolve_identity(f, title="ТЗ", text="что угодно") is None
    assert f.name == "send_limit_check_request"

    # the slug is the model's wording: a re-import must not produce a new one
    g = task("limit_check_sending")
    resolve_identity(g, title="ТЗ", text="что угодно", prior={"type": "scheduled_task", "name": "send_limit_check_request"})
    assert g.name == "send_limit_check_request"
    assert g.display_name == "Отправка запроса на проверку лимита"


# --- display_name of REST/Kafka features ------------------------------------------

def test_display_name_must_be_a_line_of_the_page():
    f = _rest("/v1/support/payment/retry", "POST", display_name="Ретрай платежа в РБО")  # paraphrase
    resolve_identity(f, title=RETRY_TITLE, text=RETRY_TEXT, single_feature=True)
    assert f.display_name is None

    g = _rest("/v1/support/payment/retry", "POST", display_name=RETRY_TITLE)  # the title is not a description
    resolve_identity(g, title=RETRY_TITLE, text=RETRY_TEXT, single_feature=True)
    assert g.display_name is None


def test_display_name_already_stored_is_kept():
    text = RETRY_TEXT + "\n\nМетод предназначен для сотрудников поддержки"
    f = _rest("/v1/support/payment/retry", "POST", display_name="Метод предназначен для сотрудников поддержки")
    prior = {
        "type": "rest_endpoint", "name": "POST /v1/support/payment/retry", "endpoint": "/v1/support/payment/retry",
        "method": "POST", "display_name": "Повторная отправка данных о совершенном платеже в РБО",
    }
    resolve_identity(f, title=RETRY_TITLE, text=text, prior=prior, single_feature=True)
    assert f.display_name == "Повторная отправка данных о совершенном платеже в РБО"


def test_display_name_ignores_markdown_emphasis():
    f = _rest("/v1/x/y", "GET", display_name="Получение долга клиента")
    resolve_identity(f, title="GET /v1/x/y", text="**Получение долга** клиента", single_feature=True)
    assert f.display_name == "Получение долга клиента"


# --- helpers ----------------------------------------------------------------------

@pytest.mark.parametrize("token, text, expected", [
    ("/v1/x/y", "POST /v1/x/y", True),
    ("/v1/x/y", "POST/v1/x/y", True),
    ("/v1/x/y", "вызов /v1/x/y.", True),
    ("/v1/x/y", "/v1/x/y?id=1", True),
    ("/v1/x/y", "/v1/x/y/{id}", False),
    ("/v1/x/y", "/v1/x/yz", False),
    ("/v1/x/y", "/api/v1/x/y", False),
    ("/v1/credit", "/v1/credit-line", False),
    ("a.b.c", "топик a.b.c", True),
    ("a.b.c", "топик a.b.c.", True),
    ("a.b.c", "топик a.b.c.d", False),
    ("b.c.d", "топик a.b.c.d", False),
    ("getWallet.do", "[svc] getWallet.do – Получение клиента", True),
    ("", "что угодно", False),
])
def test_occurs_as_a_whole_token(token, text, expected):
    assert occurs(token, text) is expected


def test_page_header_and_service_prefix():
    header = page_header(
        "[flp-rbo-adapter]  POST/v1/support/payment/retry",
        [{"page_id": "1", "title": "Pay Later"}, {"page_id": "2", "title": "flp-rbo-adapter"}],
        "flp-rbo-adapter",
    )
    assert "Заголовок страницы: [flp-rbo-adapter] POST/v1/support/payment/retry" in header
    assert "Расположение: Pay Later / flp-rbo-adapter" in header
    assert "Сервис: flp-rbo-adapter" in header
    assert strip_service_prefix("[flp-rbo-adapter] Автоматические задачи") == "Автоматические задачи"
    assert strip_service_prefix("POST /v1/x") == "POST /v1/x"
