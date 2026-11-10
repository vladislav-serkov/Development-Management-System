"""Test-case assistant: what the agent returns each step and what the UI sends."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.test_cases import AskedTestCaseResult, KafkaMessage, Priority, TestStep

# --- Agent output (structured, strict) -------------------------------------


class HttpHeader(BaseModel):
    name: str
    value: str


class StandAction(BaseModel):
    """One thing the agent asks the backend to do on the test stand."""

    kind: Literal["sql", "http", "wiremock_upload", "wiremock_mappings", "wiremock_requests", "read_cases"] = Field(
        description=(
            "sql — выполнить SQL в тестовой БД; http — вызвать сервис на стенде; "
            "wiremock_upload — загрузить мок; wiremock_mappings — найти загруженные моки; "
            "wiremock_requests — журнал запросов, пришедших в WireMock; "
            "read_cases — получить полные данные кейсов по номерам"
        ),
    )
    title: str = Field(
        description="Что сделано и зачем — одна короткая фраза в прошедшем времени для журнала, "
        "понятная тестировщику: «Проверил, есть ли тариф T-12 в tariff»",
    )
    case: int | None = Field(description="Номер кейса N из «#N», к которому относится действие, либо null")
    sql: str | None = Field(description="Для sql: скрипт целиком, таблицы с префиксом схемы")
    method: str | None = Field(description="Для http: метод запроса")
    path: str | None = Field(description="Для http: путь с query, как в curl кейса, без хоста")
    headers: list[HttpHeader] | None = Field(description="Для http: заголовки запроса")
    body: str | None = Field(description="Для http: тело запроса строкой")
    mock_config: str | None = Field(description="Для wiremock_upload: JSON mapping целиком")
    url_contains: str | None = Field(description="Для wiremock_mappings и wiremock_requests: часть URL для поиска")
    cases: list[int] | None = Field(description="Для read_cases: номера кейсов")


class CaseEdit(BaseModel):
    """Changed fields of one existing test case; null = поле не менять."""

    case: int = Field(description="Номер кейса N из «#N»")
    summary: str = Field(description="Что изменено — одна короткая фраза: «Добавил родительскую запись в tariff»")
    name: str | None
    preconditions: str | None
    steps: list[TestStep] | None = Field(description="Все шаги кейса целиком, если меняется хотя бы один")
    expected_result: str | None
    priority: Priority | None
    curl_command: str | None = Field(description="curl целиком; пустая строка — убрать артефакт")
    kafka_message: KafkaMessage | None
    sql_setup: str | None = Field(description="SQL подготовки целиком; пустая строка — убрать артефакт")
    mock_config: str | None = Field(description="WireMock mapping целиком; пустая строка — убрать артефакт")


class DeleteSuggestion(BaseModel):
    case: int = Field(description="Номер кейса, который предлагается удалить")
    reason: str = Field(description="Почему: дубликат какого кейса, чем они совпадают")


class BugSuggestion(BaseModel):
    case: int = Field(description="Номер кейса, на котором сервис ведёт себя не по ТЗ")
    text: str = Field(description="Что ожидалось по ТЗ и что вернул стенд — готовый комментарий к баг-репорту")


class AssistantStep(BaseModel):
    """One answer of the agent: either stand actions to run, or the final result."""

    actions: list[StandAction] = Field(
        description="Действия, которые нужно выполнить сейчас. Пустой список — это итоговый ответ",
    )
    reply: str | None = Field(
        description="Итоговый ответ тестировщику: 1–4 коротких предложения обычным текстом. "
        "Обязателен, когда actions пуст; иначе null",
    )
    cause: str | None = Field(
        description="Для разбора ошибки — причина одной-двумя фразами. Иначе null",
    )
    edits: list[CaseEdit] = Field(description="Правки существующих кейсов (только в итоговом ответе)")
    new_cases: list[AskedTestCaseResult] = Field(description="Новые кейсы (только в итоговом ответе)")
    delete_suggestions: list[DeleteSuggestion] = Field(
        description="Кейсы, которые стоит удалить; удаление подтверждает тестировщик",
    )
    bug_suggestions: list[BugSuggestion] = Field(
        description="Расхождения поведения сервиса с ТЗ, на которые стоит завести баг",
    )
    related_cases: list[int] = Field(description="Номера кейсов, на которые ссылается ответ")
    session_title: str | None = Field(description="Название обсуждения в 3–6 словах, без кавычек")


# --- API -------------------------------------------------------------------


class Attachment(BaseModel):
    """Context the tester pinned to a message: a case, or a failed run of its artifact."""

    kind: Literal["case", "sql_error", "http_result", "mock_error"]
    case_id: str = Field(min_length=1, max_length=64)
    error: str | None = Field(default=None, max_length=20_000)
    failed_statement: int | None = None
    status_code: int | None = None
    reason: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=4_000)
    body: str | None = None

    @field_validator("body")
    @classmethod
    def _trim_body(cls, value: str | None) -> str | None:
        return value[:8_000] if value else value


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8_000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=8)
    # Omitted = start a new session with this message
    session_id: str | None = None

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Пустое сообщение")
        return value.strip()


class ResolveSuggestionRequest(BaseModel):
    accept: bool
