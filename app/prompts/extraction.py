"""LLM prompts for the extraction pipeline (feature detection and message mapping)."""


DETECT_FEATURE_PROMPT = (
    "Это техническое задание (ТЗ) на один Kafka-консьюмер или REST-эндпоинт.\n"
    "Документ описывает ровно одну функциональность (feature).\n\n"
    "Извлеки:\n"
    "- name: используй РЕАЛЬНЫЙ идентификатор — для Kafka это имя топика (например pay-later.flp.rbo-adapter.product.return.queue), для REST — METHOD /path (например GET /v1/credit-line)\n"
    "- type (kafka_consumer/rest_endpoint), summary (краткое описание на русском), dependencies\n"
    "- method (для REST: GET/POST/PUT/DELETE; для Kafka: CONSUMER)\n"
    "- endpoint (для REST: путь эндпоинта как /v1/credit-line; для Kafka: имя топика как pay-later.flp.rbo-adapter.product.return.queue)\n"
    "- structured_logic:\n"
    "  - input_parameters: список параметров с полями name (латиница), field_type, description (русский), "
    "required, validation_rules (список строк на русском), param_in (body/header/query/path — только для REST, null для Kafka), "
    "children (вложенные поля для object/array типов)\n"
    "  - success_response: параметры успешного ответа (2xx) с полями name, field_type, description, required, validation_rules, param_in, children. Только для REST, для Kafka оставь пустым\n"
    "  - error_responses: массив объектов ошибок (4xx/5xx), каждый с полями status_codes (например '400', '404', '500'), description (когда возникает, на русском), parameters (поля тела ответа при ошибке). Только для REST, для Kafka оставь пустым\n"
    "  - logic_steps: шаги обработки с полями number (нумерация '1', '1.1', '1.1.2'), "
    "text (описание шага на русском — см. правило ниже), "
    "has_detailed_mapping (true если шаг содержит таблицу маппинга XML/JSON полей/элементов), "
    "children (вложенные подшаги)\n"
    "  - used_dependencies: список зависимостей с полями type (db_table/external_api/cache/kafka_topic), "
    "name (имя таблицы/кеша/топика Kafka; для external_api — path эндпоинта), "
    "description (для чего используется, на русском), "
    "method (для external_api: HTTP метод GET/POST/PUT/DELETE/PATCH, null для остальных типов), "
    "service_name (для external_api: имя целевого сервиса, null для остальных типов), "
    "path (для external_api: путь эндпоинта, null для остальных типов)\n"
    "  - error_handling: обработка ошибок (JSON)\n"
    "  - business_rules: бизнес-правила (список строк на русском)\n\n"
    "ВАЖНО:\n"
    "- Все текстовые поля заполняй НА РУССКОМ ЯЗЫКЕ, сохраняя терминологию из оригинального ТЗ\n"
    "- external_api — только REST-вызовы к внешним сервисам. Отправку сообщений в Kafka-топики указывай как kafka_topic\n"
    "- Имена параметров и ключи — на латинице\n"
    "- Используй вложенность в logic_steps для отражения структуры документа\n"
    "- Для logic_steps.text:\n"
    "  * Обычные шаги (has_detailed_mapping: false): копируй ДОСЛОВНО текст из документа, не перефразируй\n"
    "  * Шаги с маппингом (has_detailed_mapping: true): пиши ТОЛЬКО краткое описание действия "
    "(например 'Сформировать XML-сообщение с типом LoanAddRq и отправить в очередь'), "
    "БЕЗ перечисления полей/элементов маппинга — детальный маппинг будет извлечён отдельно\n"
    "- Если шаг описывает структуру XML/JSON маппинга (таблицу полей/элементов сообщения), "
    "установи has_detailed_mapping: true на этом шаге"
)


def build_mapping_prompt(feature_name: str, feature_type: str, steps_list: str) -> str:
    """Build the user message for Call 2 (message mapping extraction).

    Args:
        feature_name: Name of the feature being processed.
        feature_type: Type value of the feature (e.g. 'kafka_consumer').
        steps_list: Comma-separated step numbers that have has_detailed_mapping=True.
    """
    return (
        f"Сфокусируйся на feature '{feature_name}' (тип: {feature_type}).\n\n"
        f"Для следующих шагов обработки: {steps_list}\n"
        "Каждый из этих шагов содержит таблицу маппинга XML/JSON полей/элементов сообщения.\n\n"
        "Для каждого шага извлеки структуру маппинга:\n"
        "- step_number: номер шага (например, '7.b')\n"
        "- message_type: имя типа сообщения/объекта (например, 'AgreemtListMod')\n"
        "- queue_or_endpoint: очередь или эндпоинт (если указан)\n"
        "- fields: список полей/элементов с их иерархией:\n"
        "  - element: имя поля/элемента\n"
        "  - parent: имя родительского элемента (null если корневой)\n"
        "  - field_type: тип данных\n"
        "  - required: обязательное ли поле\n"
        "  - cardinality: кратность ДОСЛОВНО из таблицы спецификации ('1', '0-1', '1-N', '0-N'). Если в таблице нет колонки кратности — null\n"
        "  - is_collection: true если поле само является списком/массивом. Определяй по прямым признакам:\n"
        "    а) Тип содержит List, Array, []\n"
        "    б) Описание содержит 'список', 'массив', 'набор', 'коллекция', 'перечень'\n"
        "    в) Контекст указывает 'для каждого', 'может повторяться'\n"
        "    НЕ выводи is_collection из кратности дочерних элементов — это делается постобработкой\n"
        "  - description: что это за поле / что оно означает (на русском из ТЗ, null если не указано)\n"
        "  - source: откуда берётся значение поля (на русском из ТЗ, null если не указано)\n"
        "  - children: вложенные поля\n\n"
        "ВАЖНО: Все описания (description, source) пиши НА РУССКОМ, сохраняя терминологию из ТЗ."
    )
