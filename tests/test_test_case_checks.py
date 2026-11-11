"""Deterministic checks of generated cases (no LLM, no stand in unit tests)."""
import json

from app.services.test_case_checks import check_cases

MOCK = {"request": {"method": "POST", "urlPath": "/v1/pay"}, "response": {"status": 200}}


def _case(**fields) -> dict:
    return {"name": "Кейс", "category": "positive", "steps": [], **fields}


async def _problems(case: dict, feature_type: str = "scheduled_task", db_schema: str | None = "shop") -> list[str]:
    return (await check_cases([case], feature_type=feature_type, db_schema=db_schema, run_sql=False))[0]


async def test_runnable_case_has_no_problems():
    case = _case(
        sql_setup="DELETE FROM shop.orders WHERE id = 'a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0';\n"
                  "INSERT INTO shop.orders (id) VALUES ('a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0');",
        mock_config=json.dumps({"mappings": [MOCK, MOCK]}),
    )
    assert await _problems(case) == []


async def test_required_artifact_depends_on_feature_type():
    assert any("curl_command" in p for p in await _problems(_case(), "rest_endpoint"))
    assert any("kafka_message" in p for p in await _problems(_case(), "kafka_consumer"))
    assert await _problems(_case(), "scheduled_task") == []


async def test_broken_kafka_payload_allowed_outside_positive_cases():
    message = {"key": "k", "value": "{not json"}
    assert any("не JSON" in p for p in await _problems(_case(kafka_message=message), "kafka_consumer"))
    assert await _problems(_case(category="validation", kafka_message=message), "kafka_consumer") == []


async def test_mock_must_be_uploadable():
    assert any("mock_config" in p for p in await _problems(_case(mock_config='{"mappings": []}')))
    assert any("mock_config" in p for p in await _problems(_case(mock_config='{"response": {"status": 200}}')))


async def test_sql_must_be_bounded_dml_on_qualified_tables():
    assert any("без WHERE" in p for p in await _problems(_case(sql_setup="DELETE FROM shop.orders;")))
    assert any("без WHERE" in p for p in await _problems(_case(sql_setup="UPDATE shop.orders SET status = 'X';")))
    assert any("sql_setup" in p for p in await _problems(_case(sql_setup="DELETE FROM orders WHERE id = 1;")))
    assert any("sql_setup" in p for p in await _problems(_case(sql_setup="TRUNCATE shop.orders;")))


async def test_non_hex_uuid_reported():
    found = await _problems(_case(preconditions="заказ a1b2c3d4-zzzz-0002-0003-e5f6a7b8c9d0"))
    assert any("не-hex" in p for p in found)
