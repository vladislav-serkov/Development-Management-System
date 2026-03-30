"""LLM prompts for the test cases generation pipeline."""


_FEW_SHOT_COMMON = """\
### Ключевые принципы
- НЕ пиши очевидные предусловия ("сервис запущен", "подписка на топик активна", "БД доступна") — это подразумевается. Предусловия = только состояние ДАННЫХ (записи в БД, настройки моков, состояние внешних зависимостей)
- Валидация срабатывает СРАЗУ, до бизнес-логики — явно писать "бизнес-логика не выполнялась"
- Каждый кейс уникален — негативные НЕ дублируют валидационные
- Конкретные значения в preconditions и steps (не "валидные данные")
- sql_setup — DELETE затем INSERT, без backticks; UUIDs только hex-символы [0-9a-f]
- mock_config — WireMock JSON для заглушки внешней зависимости
"""

_FEW_SHOT_REST = """\
## Примеры тест-кейсов (REST API)

### Пример 1 — Positive для REST API
Название: Успешная активация кредитной линии
Категория: positive | Приоритет: high
Предусловия: В таблице `credit_line_info` существует запись с `credit_line_id`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0`, `status`=`PENDING`.
Шаги:
1. POST `/v1/credit-line/activate` с телом `{"creditLineId":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","amount":1500.00,"currency":"RUB"}` → HTTP 200, поле `status`=`ACTIVE`.
2. SELECT `status` FROM `credit_line_info` WHERE `credit_line_id`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0` → `ACTIVE`.
Результат: Кредитная линия активирована. Статус в БД обновлён на `ACTIVE`.
curl_command: curl -X POST http://localhost:8080/v1/credit-line/activate -H 'Content-Type: application/json' -d '{"creditLineId":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","amount":1500.00,"currency":"RUB"}'
sql_setup: DELETE FROM credit_line_info WHERE credit_line_id = 'a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0';
INSERT INTO credit_line_info (credit_line_id, status, amount) VALUES ('a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0', 'PENDING', 1500.00);

### Пример 2 — Validation для REST API
Название: Валидация `creditLineId` — отсутствует
Категория: validation | Приоритет: high
Предусловия: В таблице `credit_line_info` отсутствуют записи для тестируемого `creditLineId`.
Шаги:
1. POST `/v1/credit-line/activate` без поля `creditLineId` → HTTP 400 с описанием ошибки.
2. SELECT COUNT(*) FROM `credit_line_info` → 0 новых записей.
Результат: Запрос отклонён с HTTP 400. Бизнес-логика не выполнялась.
curl_command: curl -X POST http://localhost:8080/v1/credit-line/activate -H 'Content-Type: application/json' -d '{"amount":1500.00,"currency":"RUB"}'

""" + _FEW_SHOT_COMMON + """\
- curl_command — обязателен для REST API фич
"""

_FEW_SHOT_KAFKA = """\
## Примеры тест-кейсов (Kafka Consumer)

### Пример 1 — Positive для Kafka-консюмера
Название: Успешная обработка сообщения об изменении лимита
Категория: positive | Приоритет: high
Предусловия: В таблице `credit_line_info` существует запись с `credit_line_id`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0`, `status`=`ACTIVE`, `amount`=`1000.00`.
Шаги:
1. Опубликовать сообщение с `creditLineId`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0`, `amount`=`2000.00` → Сообщение успешно обработано.
2. SELECT `amount` FROM `credit_line_info` WHERE `credit_line_id`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0` → `2000.00`.
Результат: Лимит обновлён в БД. Запись в `credit_line_info` содержит новое значение `amount`=`2000.00`.
kafka_message: {"key":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","value":{"creditLineId":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","amount":2000.00,"currency":"RUB","operationType":"SCHEDULE"}}
sql_setup: DELETE FROM credit_line_info WHERE credit_line_id = 'a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0';
INSERT INTO credit_line_info (credit_line_id, status, amount) VALUES ('a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0', 'ACTIVE', 1000.00);

### Пример 2 — Validation для Kafka-консюмера
Название: Валидация `amount` — значение 0
Категория: validation | Приоритет: high
Предусловия: В таблице `credit_line_info` существует запись с `credit_line_id`=`a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0`, `status`=`ACTIVE`.
Шаги:
1. Опубликовать сообщение с `amount`=0 → Валидация: значение 0 не удовлетворяет правилу > 0.
2. Проверить логи сервиса → ERROR с описанием ошибки валидации.
3. SELECT COUNT(*) FROM `credit_line_info` WHERE `amount`=0 → 0 записей.
Результат: Сообщение отклонено на этапе валидации. Бизнес-логика не выполнялась.
kafka_message: {"key":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","value":{"creditLineId":"a1b2c3d4-0001-0002-0003-e5f6a7b8c9d0","amount":0,"currency":"RUB","operationType":"SCHEDULE"}}

""" + _FEW_SHOT_COMMON + """\
- kafka_message — обязателен для Kafka-консюмеров
"""


def get_few_shot(feature_type: str) -> str:
    """Return few-shot examples appropriate for the feature type."""
    if "kafka" in feature_type.lower():
        return _FEW_SHOT_KAFKA
    return _FEW_SHOT_REST


PLAN_SYSTEM_PROMPT = (
    "Ты — старший QA-аналитик банковского проекта. "
    "Составь план тест-кейсов на русском языке. "
    "Цель — покрыть все ветки logic_steps без дублирования. "
    "Категории: validation (входные параметры), positive (основные сценарии), "
    "negative (обработка ошибок), edge_case (граничные). "
    "validation — только входные параметры, НЕ дублируй с negative. "
    "Максимум 20 тест-кейсов."
)

DETAIL_SYSTEM_PROMPT = (
    "Ты — старший QA-аналитик. Детализируй тест-кейсы по плану. "
    "Критические правила: "
    "sql_setup — DELETE затем INSERT (без исключений). "
    "UUIDs — только hex-символы [0-9a-f], никаких букв g-z. "
    "Каждый кейс уникален — negative не дублирует validation."
)
