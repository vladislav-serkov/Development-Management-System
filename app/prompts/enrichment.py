"""LLM prompts for the dependency enrichment pipeline.

Field-level instructions live in the structured output schemas
(app/schemas/enrichment.py); the prompts say what the page is and what
to be careful about.
"""
from app.schemas.enrichment import (
    CacheEnrichmentBatch,
    DbEnrichmentBatch,
    ExternalApiEnrichment,
    ExternalDocEnrichment,
    KafkaTopicEnrichmentBatch,
)

_LANGUAGE = "Описания пиши на русском, сохраняя терминологию документа; идентификаторы — как в документе."

ENRICHMENT_SCHEMAS = {
    "db_table": {
        "schema": DbEnrichmentBatch,
        "prompt": (
            "Документ описывает схему базы данных (DDL, таблицы). "
            "Извлеки все таблицы документа, не только первую, с колонками, индексами "
            "и бизнес-заметками. " + _LANGUAGE
        ),
    },
    "external_api": {
        "schema": ExternalApiEnrichment,
        "prompt": (
            "Документ — спецификация внешнего API (REST/SOAP/gRPC). "
            "Извлеки все эндпоинты документа с параметрами, схемами тела запроса и ответа "
            "(как JSON-строки, если они приведены) и кодами ошибок. " + _LANGUAGE
        ),
    },
    "cache": {
        "schema": CacheEnrichmentBatch,
        "prompt": (
            "Документ описывает кеш-структуры (Redis, Hazelcast и т.п.). "
            "Извлеки все кеш-структуры документа с паттернами ключей, TTL, структурой значения "
            "(как JSON-строкой) и политикой вытеснения. " + _LANGUAGE
        ),
    },
    "kafka_topic": {
        "schema": KafkaTopicEnrichmentBatch,
        "prompt": (
            "Документ описывает Kafka-топики: структуру сообщений, ключи, партиции. "
            "Извлеки все топики документа, не только первый.\n\n"
            "Поля сообщения (message_fields) и ключа (key_fields) перечисляй плоским списком "
            "в порядке документа; вложенность задаёт parent — имя родительского элемента "
            "(null для полей верхнего уровня). Тип, обязательность, кратность, описание и "
            "источник — дословно из таблицы спецификации; чего в таблице нет — null. "
            "is_collection = true только по прямым признакам самого поля: тип List/Array/[], "
            "слова «список», «массив», «набор», «перечень» в описании, «для каждого» в "
            "контексте — не выводи его из кратности дочерних элементов. " + _LANGUAGE
        ),
    },
    "external_doc": {
        "schema": ExternalDocEnrichment,
        "prompt": (
            "Это внешний документ (спецификация, регламент, правила, справочник), на который "
            "ссылается ТЗ. Задача — сохранить его содержимое дословно в виде чистого HTML, "
            "не резюмируя и не интерпретируя: content_html читается целиком, точность важнее "
            "краткости.\n\n"
            "HTML-фрагмент без <html>/<head>/<body>, структура и порядок 1:1 с документом, "
            "текст дословно (включая инлайн-комментарии вроде `// рубли`), пустые строки "
            "между блоками — пустые параграфы.\n"
            "Теги только из списка: h1–h6, p, ul, ol, li, table, thead, tbody, tr, th, td, "
            "strong, em, code, a, pre, blockquote, br. Атрибуты только rowspan/colspan у "
            "th/td и href у a.\n\n"
            "Таблицы: каждая таблица документа — ровно одна <table>; подзаголовки и группы "
            "строк внутри неё остаются строками той же таблицы (обычно одна <td> с colspan "
            "на всю ширину). Объединённые ячейки — rowspan/colspan, шапка — в <thead> "
            "(многорядная — несколько <tr>). Иерархию строк в первой колонке передавай "
            "отступом из &nbsp;&nbsp; на уровень в начале текста ячейки.\n\n"
            "doc_name — название из заголовка документа, description — 1–2 строки на русском "
            "о том, что это за документ."
        ),
    },
}
