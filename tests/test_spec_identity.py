"""_enforce_spec_identity: feature identity must be verbatim from the spec."""

from app.schemas.extraction import DetectedFeature, FeatureType
from app.services.extraction import _enforce_spec_identity

TITLE = "pay-later.flp.rbo-adapter.product.schedule.queue"
TEXT = "Сервис слушает и пишет результат в pay-later.rbo.flp.schedule.out.queue после обработки."


def _kafka(name: str, endpoint: str | None = None) -> DetectedFeature:
    return DetectedFeature(
        name=name, type=FeatureType.kafka_consumer, confidence=1.0,
        summary="s", method="CONSUMER", endpoint=endpoint or name,
    )


def test_kafka_correct_topic_kept():
    f = _kafka(TITLE)
    assert _enforce_spec_identity(f, title=TITLE, text=TEXT, tables=None) is None
    assert f.name == TITLE


def test_kafka_hallucinated_topic_corrected_to_title():
    # the real regression: LLM dropped ".product" from the topic on re-import
    f = _kafka("pay-later.flp.rbo-adapter.schedule.queue")
    warning = _enforce_spec_identity(f, title=TITLE, text=TEXT, tables=None)
    assert warning is not None
    assert f.name == TITLE
    assert f.endpoint == TITLE


def test_kafka_topic_from_body_kept():
    f = _kafka("pay-later.rbo.flp.schedule.out.queue")
    assert _enforce_spec_identity(f, title="Какая-то страница", text=TEXT, tables=None) is None
    assert f.name == "pay-later.rbo.flp.schedule.out.queue"


def test_kafka_topic_found_in_tables():
    f = _kafka("a.b.c.queue")
    tables = [{"rows": [["Топик", "a.b.c.queue"]]}]
    assert _enforce_spec_identity(f, title="t", text="", tables=tables) is None


def test_rest_path_corrected():
    f = DetectedFeature(
        name="GET /v1/credit-lines", type=FeatureType.rest_endpoint, confidence=1.0,
        summary="s", method="GET", endpoint="/v1/credit-lines",
    )
    warning = _enforce_spec_identity(
        f, title="ТЗ", text="Эндпоинт GET /v1/credit-line возвращает лимит", tables=None,
    )
    assert warning is not None
    assert f.endpoint == "/v1/credit-line"
    assert f.name == "GET /v1/credit-line"


def test_rest_single_feature_title_path_wins():
    # Seen live: the page links the controller path in swagger; the LLM picked it
    # on one run and the gateway path from the title on another
    text = "[swagger](https://host/swagger-ui/index.html#/payment-controller/getClientDebt)"
    f = DetectedFeature(
        name="GET /payment-controller/getClientDebt", type=FeatureType.rest_endpoint, confidence=1.0,
        summary="s", method="GET", endpoint="/payment-controller/getClientDebt",
    )
    warning = _enforce_spec_identity(
        f, title="GET /v1/client/debt", text=text, tables=None, single_feature=True,
    )
    assert warning is not None
    assert f.name == "GET /v1/client/debt" and f.endpoint == "/v1/client/debt"

    # Already the title path → no warning; multi-feature pages keep the LLM's pick
    assert _enforce_spec_identity(f, title="GET /v1/client/debt", text=text, tables=None, single_feature=True) is None
    g = DetectedFeature(
        name="GET /payment-controller/getClientDebt", type=FeatureType.rest_endpoint, confidence=1.0,
        summary="s", method="GET", endpoint="/payment-controller/getClientDebt",
    )
    _enforce_spec_identity(g, title="GET /v1/client/debt", text=text, tables=None)
    assert g.endpoint == "/payment-controller/getClientDebt"


def test_kafka_single_feature_title_topic_wins():
    # Seen live: the body names the out-queue the consumer writes to; the LLM picked it
    f = _kafka("pay-later.rbo.flp.schedule.out.queue")
    warning = _enforce_spec_identity(f, title=TITLE, text=TEXT, tables=None, single_feature=True)
    assert warning is not None
    assert f.name == TITLE and f.endpoint == TITLE


def test_scheduled_task_untouched():
    f = DetectedFeature(
        name="send_limit_check_request", type=FeatureType.scheduled_task, confidence=1.0,
        summary="s", method="SCHEDULED", schedule="Ежедневно в 19:00",
        display_name="Отправка запроса на проверку лимита",
    )
    assert _enforce_spec_identity(f, title="ТЗ", text="что угодно", tables=None) is None
    assert f.name == "send_limit_check_request"
