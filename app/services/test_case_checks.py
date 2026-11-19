"""Deterministic checks of generated test cases: can a tester actually run them?

A case is only useful if its artifacts work on the stand — the SQL prepares the
data, the mock uploads to WireMock, the Kafka payload parses. These checks need
no LLM: the SQL is executed on the test DB inside a transaction that is always
rolled back, the rest is validated structurally.
"""
import json
import logging
import re

from app.services import sql_runner
from app.services.assistant_stand import SqlNotAllowed, classify_sql, written_schemas
from app.services.wiremock import InvalidMappingError, prepare_mappings

logger = logging.getLogger(__name__)

_UUID_LIKE = re.compile(r"\b[0-9a-zA-Z]{8}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{12}\b")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _static_problems(case: dict, feature_type: str, db_schema: str | None) -> list[str]:
    problems: list[str] = []
    kind = (feature_type or "").lower()

    if "rest" in kind and not case.get("curl_command"):
        problems.append("нет curl_command: у REST-фичи каждый кейс вызывает эндпоинт")
    kafka = case.get("kafka_message")
    if "kafka" in kind and not kafka:
        problems.append("нет kafka_message: у Kafka-консюмера каждый кейс публикует сообщение")
    if kafka and case.get("category") == "positive":
        # Broken payloads are legitimate in validation/negative cases only.
        try:
            json.loads(kafka.get("value") or "")
        except ValueError as exc:
            problems.append(f"kafka_message.value — не JSON: {exc}")

    mock = case.get("mock_config")
    if mock:
        try:
            prepare_mappings(mock)
        except InvalidMappingError as exc:
            problems.append(f"mock_config: {exc}")

    for field, value in case.items():
        if isinstance(value, str):
            for match in _UUID_LIKE.findall(value):
                if not _UUID.match(match):
                    problems.append(f"{field}: UUID «{match}» содержит не-hex символы")

    sql = case.get("sql_setup")
    if sql:
        try:
            # DML only, every written table schema-qualified. The feature's own
            # schema is always allowed; other schemas the script names are judged
            # by the database itself (an adapter may keep its data elsewhere).
            # The stand is shared, so the same call refuses a DELETE/UPDATE that
            # does not name its rows — with the words the executor itself would use.
            classify_sql(sql, written_schemas(sql) | ({db_schema} if db_schema else set()))
        except SqlNotAllowed as exc:
            problems.append(f"sql_setup: {exc}")
    return problems


async def check_cases(
    cases: list[dict], *, feature_type: str, db_schema: str | None, run_sql: bool = True,
) -> list[list[str]]:
    """Problems of each case, in order (empty list = the case is runnable).

    SQL that passed the static check is executed and rolled back on the test DB
    when it is configured and reachable; an unreachable DB skips that part.
    """
    problems = [_static_problems(case, feature_type, db_schema) for case in cases]
    if not (run_sql and sql_runner.is_configured()):
        return problems

    runnable = [
        i for i, case in enumerate(cases)
        if case.get("sql_setup") and not any(p.startswith("sql_setup") for p in problems[i])
    ]
    if not runnable:
        return problems
    try:
        errors = await sql_runner.dry_run_scripts([cases[i]["sql_setup"] for i in runnable])
    except ConnectionError as exc:
        logger.warning("[test_cases:check] SQL dry-run skipped: %s", exc)
        return problems
    for i, error in zip(runnable, errors, strict=True):
        if error:
            problems[i].append(f"sql_setup не выполняется на тестовой БД: {error}")
    return problems
