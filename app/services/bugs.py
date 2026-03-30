"""Bug report generation service: single Claude call to create structured bug report from test case."""
import logging
from datetime import UTC, datetime

from app.config import settings
from app.prompts.bugs import SYSTEM_PROMPT
from app.schemas.bugs import BugReportResult
from app.services.extraction import _get_client
from app.services.rules import build_system_prompt

logger = logging.getLogger(__name__)


async def generate_bug_report(
    project_slug: str,
    feature_name: str,
    tc_index: int,
    analyst_text: str | None,
    store,
) -> dict:
    """Generate a structured bug report from a test case using Claude.

    Returns a bug dict ready for storage (all BugItem fields populated).
    """
    # Load feature and test cases
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise ValueError(f"Feature '{feature_name}' not found in project '{project_slug}'")

    test_cases = await store.get_test_cases(project_slug, feature_name)
    if tc_index < 0 or tc_index >= len(test_cases):
        raise ValueError(f"Test case index {tc_index} out of range (total: {len(test_cases)})")

    tc = test_cases[tc_index]

    # Extract feature context
    f_name = feature.get("name", feature_name)
    f_method = feature.get("method") or ""
    f_endpoint = feature.get("endpoint") or ""
    f_type = feature.get("type", "")

    # Build user message: analyst_text FIRST, then feature context, then test case
    parts: list[str] = []

    if analyst_text:
        parts += [
            "## Наблюдение аналитика",
            analyst_text,
            "",
        ]

    # Feature context block
    feature_line = f_name
    if f_method and f_endpoint:
        feature_line += f" ({f_method} {f_endpoint})"
    elif f_endpoint:
        feature_line += f" ({f_endpoint})"
    parts += [
        "## Контекст фичи",
        f"Название: {feature_line}",
        f"Тип: {f_type}",
        "",
    ]

    # Test case data (simplified: name, category, steps only)
    parts += [
        "## Тест-кейс (контекст)",
        f"Название: {tc.get('name', '')}",
        f"Категория: {tc.get('category', '')}",
        "",
        "Шаги тест-кейса:",
    ]
    for i, step in enumerate(tc.get("steps", []), 1):
        parts.append(f"{i}. {step.get('action', '')}")
        parts.append(f"   Ожидалось: {step.get('expected', '')}")

    parts += ["", f"Ожидаемый результат тест-кейса: {tc.get('expected_result', '')}"]

    for artifact_key, artifact_label in [
        ("curl_command", "cURL"),
        ("kafka_message", "Kafka сообщение"),
        ("sql_setup", "SQL подготовка"),
        ("mock_config", "Mock конфигурация"),
    ]:
        val = tc.get(artifact_key)
        if val:
            parts += ["", f"{artifact_label}:", val]

    user_message = "\n".join(parts)

    # Tool schema
    tool_schema = BugReportResult.model_json_schema()
    tool_name = "create_bug_report"
    tool = {
        "name": tool_name,
        "description": "Создать минимальный воспроизводимый баг-репорт",
        "input_schema": tool_schema,
    }

    client = _get_client()
    model = settings.bugs_model

    global_rules = await store.get_global_rules()
    project_rules = await store.get_project_rules(project_slug)
    system_prompt = build_system_prompt(
        base=SYSTEM_PROMPT,
        global_rules=global_rules.get("bugs", ""),
        project_rules=project_rules.get("bugs", ""),
    )

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[
            {
                "role": "user",
                "content": user_message,
            }
        ],
    )

    tool_block = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_block = block
            break

    if tool_block is None:
        raise RuntimeError("Claude did not return tool_use block for bug report generation")

    result = BugReportResult.model_validate(tool_block.input)
    logger.info("[bugs] Generated bug report for test case '%s' (severity=%s)", tc.get("name", ""), result.severity)

    return {
        "title": result.title,
        "test_case_name": tc.get("name", ""),
        "severity": result.severity,
        "steps": [
            {
                "action": s.action,
                "result": s.result,
                "curl_command": s.curl_command,
                "sql_query": s.sql_query,
                "kafka_message": s.kafka_message,
            }
            for s in result.steps
        ],
        "expected_result": result.expected_result,
        "actual_result": result.actual_result,
        "status": "open",
        "analyst_text": analyst_text,
        "tc_index": tc_index,
        "created_at": datetime.now(UTC).isoformat(),
    }
