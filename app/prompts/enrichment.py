"""LLM prompts for the dependency enrichment pipeline."""
from app.schemas.enrichment import (
    CacheEnrichmentBatch,
    DbEnrichmentBatch,
    ExternalApiEnrichment,
    KafkaTopicEnrichmentBatch,
)


ENRICHMENT_SCHEMAS = {
    "db_table": {
        "schema": DbEnrichmentBatch,
        "tool_name": "extract_db_schema",
        "prompt": (
            "Этот PDF содержит описание схемы базы данных (DDL, таблицы).\n"
            "Извлеки ВСЕ таблицы, описанные в документе.\n"
            "Для каждой таблицы извлеки:\n"
            "- table_name (латиница)\n"
            "- description (на русском)\n"
            "- columns: для каждой колонки — name, col_type (SQL тип), nullable, description, is_pk, is_fk, fk_references\n"
            "- indexes: список индексов (строки)\n"
            "- business_notes: бизнес-заметки (строки на русском)\n\n"
            "ВАЖНО: Извлеки ВСЕ таблицы из документа, не только первую."
        ),
    },
    "external_api": {
        "schema": ExternalApiEnrichment,
        "tool_name": "extract_api_spec",
        "prompt": (
            "Этот PDF содержит спецификацию внешнего API (REST/SOAP/gRPC).\n"
            "Извлеки:\n"
            "- api_name (латиница)\n"
            "- base_url (если указан)\n"
            "- description (на русском)\n"
            "- endpoints: для каждого эндпоинта — method (GET/POST/PUT/DELETE/PATCH), path, description,\n"
            "  params (name, param_in: query/header/path/body, param_type, required, description),\n"
            "  request_body_schema (JSON schema если есть), response_schema (JSON schema),\n"
            "  error_codes (список кодов ошибок)\n\n"
            "ВАЖНО: Извлеки ВСЕ эндпоинты из документа."
        ),
    },
    "cache": {
        "schema": CacheEnrichmentBatch,
        "tool_name": "extract_cache_schema",
        "prompt": (
            "Этот PDF содержит описание кеш-структур (Redis, Hazelcast и т.п.).\n"
            "Извлеки ВСЕ кеш-структуры из документа.\n"
            "Для каждой структуры:\n"
            "- cache_name (латиница)\n"
            "- description (на русском)\n"
            "- key_patterns: паттерны ключей (pattern, description, ttl_seconds, value_structure как JSON)\n"
            "- eviction_policy (если указана)\n"
            "- notes: дополнительные заметки\n\n"
            "ВАЖНО: Извлеки ВСЕ кеш-структуры, не только первую."
        ),
    },
    "kafka_topic": {
        "schema": KafkaTopicEnrichmentBatch,
        "tool_name": "extract_kafka_topics",
        "prompt": (
            "Этот PDF содержит описание Kafka-топиков (структура сообщений, ключи, партиции).\n"
            "Извлеки ВСЕ топики, описанные в документе.\n"
            "Для каждого топика извлеки:\n"
            "- topic_name (латиница, полное имя топика)\n"
            "- description (на русском)\n"
            "- message_fields: иерархический список полей/элементов value сообщения:\n"
            "  - element: имя поля/элемента\n"
            "  - field_type: тип данных (String, Integer, Decimal, etc., null для контейнерных элементов)\n"
            "  - required: обязательное ли поле\n"
            "  - cardinality: кратность ДОСЛОВНО из таблицы спецификации ('1', '0-1', '1-N', '0-N'). Если в таблице нет колонки кратности — null\n"
            "  - is_collection: true если поле само является списком/массивом. Определяй по прямым признакам:\n"
            "    а) Тип содержит List, Array, []\n"
            "    б) Описание содержит 'список', 'массив', 'набор', 'коллекция', 'перечень'\n"
            "    в) Контекст указывает 'для каждого', 'может повторяться'\n"
            "    НЕ выводи is_collection из кратности дочерних элементов — это делается постобработкой\n"
            "  - description: что это за поле / что оно означает (на русском из ТЗ, null если не указано)\n"
            "  - source: откуда берётся значение поля (на русском из ТЗ, null если не указано)\n"
            "  - children: вложенные поля\n"
            "- key_fields: аналогичный список для полей ключа сообщения (если описан, иначе пустой список)\n"
            "- partitions (количество партиций, если указано)\n"
            "- retention_ms (время хранения в миллисекундах, если указано)\n"
            "- notes: дополнительные заметки (строки на русском)\n\n"
            "ВАЖНО: Извлеки ВСЕ топики из документа, не только первый.\n"
            "Все описания (description, source) пиши НА РУССКОМ, сохраняя терминологию из ТЗ."
        ),
    },
}
