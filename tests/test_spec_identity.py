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


def test_scheduled_task_untouched():
    f = DetectedFeature(
        name="send_limit_check_request", type=FeatureType.scheduled_task, confidence=1.0,
        summary="s", method="SCHEDULED", schedule="Ежедневно в 19:00",
        display_name="Отправка запроса на проверку лимита",
    )
    assert _enforce_spec_identity(f, title="ТЗ", text="что угодно", tables=None) is None
    assert f.name == "send_limit_check_request"
