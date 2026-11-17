from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["validation", "positive", "negative", "edge_case"]
Priority = Literal["high", "medium", "low"]


class KafkaMessage(BaseModel):
    key: str = Field(description="Kafka message key")
    value: str = Field(description="JSON-строка значения Kafka-сообщения")


class TestStep(BaseModel):
    action: str = Field(description="Действие: REST-запрос, Kafka-сообщение или SQL-запрос для проверки БД")
    expected: str = Field(description="Ожидаемый результат: HTTP-код, значения полей, состояние в БД")


_MOCK_DESCRIPTION = (
    "Заглушки WireMock для внешних HTTP-зависимостей кейса: один mapping {\"request\":…,\"response\":…} "
    "или {\"mappings\":[…]}, если заглушек несколько"
)


class TestCaseBody(BaseModel):
    """What a tester executes: data, steps, expected result and the artifacts."""
    name: str = Field(description="Краткое название тест-кейса на русском")
    preconditions: str = Field(description="Состояние данных перед тестом: записи в БД, настройки моков")
    steps: list[TestStep] = Field(description="Упорядоченные шаги тест-кейса")
    expected_result: str = Field(description="Итоговый ожидаемый результат после выполнения всех шагов")
    curl_command: str | None = Field(default=None, description="curl-команда для REST-эндпоинта")
    kafka_message: KafkaMessage | None = Field(default=None, description="Kafka-сообщение (key + value)")
    sql_setup: str | None = Field(default=None, description="SQL-скрипт подготовки данных. DELETE затем INSERT. Без backticks")
    mock_config: str | None = Field(default=None, description=_MOCK_DESCRIPTION)


class SingleTestCaseResult(TestCaseBody):
    """A complete test case with its classification."""
    category: Category = Field(description="Категория тест-кейса")
    priority: Priority = Field(description="Приоритет тест-кейса")


class AskedTestCaseResult(SingleTestCaseResult):
    """A test case that names the spec item it covers."""
    covers: str = Field(description="Какой пункт ТЗ (ветка logic_steps, правило валидации, сценарий ошибки) покрывает кейс — короткая точная ссылка")


class CoverageItem(BaseModel):
    """One check the suite must contain — the plan line a case is written for."""
    covers: str = Field(
        description="Пункт ТЗ и что именно проверяем: «logic_steps 2.3: линия, отсутствующая в ответе, закрывается»",
    )
    category: Category
    priority: Priority


class TestCaseCoverageResult(BaseModel):
    """Turn 1 of the generation dialog: everything the spec requires to check."""
    coverage: list[CoverageItem]
    note: str | None = Field(
        default=None,
        description="Только если перечень пуст: почему по этому ТЗ нельзя написать проверяемые кейсы",
    )


class _CoverageRef(BaseModel):
    item: int = Field(description="Номер пункта перечня проверок, для которого написан кейс")


class GeneratedTestCaseResult(TestCaseBody, _CoverageRef):
    """A case written for one coverage item; category, priority and covers come from that item."""


class TestCaseGenerationResult(BaseModel):
    """Turns 2+ of the generation dialog: detailed cases for the requested coverage items."""
    test_cases: list[GeneratedTestCaseResult]


class TestCaseAskResult(BaseModel):
    """Tool output schema for the on-demand ask call.

    Empty test_cases + comment = the requested spec item is already covered
    (or not found in the spec) — comment explains which/why.
    """
    test_cases: list[AskedTestCaseResult]
    comment: str | None = Field(
        default=None,
        description="Короткий комментарий для тестировщика: что сгенерировано, либо почему кейсы не добавлены (пункт уже покрыт / пункт не найден в ТЗ). Названия покрывающих кейсов НЕ перечислять здесь — для них есть covered_by",
    )
    covered_by: list[int] = Field(
        default_factory=list,
        description="Для каждого запрошенного пункта, который уже покрыт — номера существующих кейсов, которые его покрывают (число N из «#N» в списке существующих кейсов). Обязательно заполнять, если в comment сказано, что пункт уже покрыт",
    )


class TestCaseAskRequest(BaseModel):
    """POST body for the on-demand test case ask."""
    request: str = Field(min_length=3, description="Свободный текст: на какой пункт ТЗ нужен тест-кейс")


class TestCaseReviewRequest(BaseModel):
    """PATCH body for approving/editing/resetting a test case."""
    status: str = Field(pattern="^(pending|approved|edited)$")
    analyst_text: str | None = None
