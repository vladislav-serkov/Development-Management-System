# Phase 1: Foundation + PDF Processing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 01-foundation-spec-management
**Areas discussed:** Гранулярность детекции фич, Стратегия Claude API

---

## Гранулярность детекции фич

### Граница одной фичи в PDF

| Option | Description | Selected |
|--------|-------------|----------|
| 1 фича = 1 технический эндпоинт | Каждый Kafka-топик, REST-path, cron-задача — отдельная фича. Чётко мапится на код. | ✓ |
| 1 фича = бизнес-процесс | Группировка по бизнес-процессу (напр. «return» включает consumer + REST + scheduler). | |
| Claude определяет сам | Claude сам решает как разбить, основываясь на структуре документа. | |

**User's choice:** 1 фича = 1 технический эндпоинт
**Notes:** —

### Именование фич

| Option | Description | Selected |
|--------|-------------|----------|
| Из ТЗ автоматически | Claude извлекает имя из PDF (product-schedule-consumer). | ✓ |
| По шаблону {type}-{name} | Строгий формат: kafka-product-schedule, rest-product-status. | |
| На усмотрение Claude | Claude решает формат именования. | |

**User's choice:** Из ТЗ автоматически
**Notes:** —

### Обработка неясного типа фичи

| Option | Description | Selected |
|--------|-------------|----------|
| Пометить как unknown + gaps | Фича с типом unknown, в gaps.md запись. | |
| Лучшее предположение + confidence | Claude назначает вероятный тип с confidence: low. | ✓ |
| Пропустить | Извлекать только чёткие фичи. | |

**User's choice:** Лучшее предположение + confidence
**Notes:** —

### Валидация на sample PDF

| Option | Description | Selected |
|--------|-------------|----------|
| Да, все 5 PDF | Использовать все 5 образцов для проверки. | ✓ |
| Да, 1-2 как смоке-тест | Пара самых типичных для базовой проверки. | |
| Нет, только unit-тесты | Тестировать на синтетических данных. | |

**User's choice:** Да, все 5 PDF
**Notes:** —

---

## Стратегия Claude API

### Структурирование вывода Claude

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Strict Pydantic (tool_use) | Единая жёсткая схема для всего | |
| 2. Free-form JSON | Произвольный JSON без ограничений | |
| 3. Hybrid envelope (Pydantic + free dict) | Pydantic-конверт + свободное поле business_logic | |
| 4. Два отдельных вызова | Structured detection + free-form business logic | |
| 5. Pydantic + Markdown | Метаданные через tool_use, business logic как Markdown | |
| 6. Hybrid + prompt caching | Как подход 4, но с prompt caching для экономии | ✓ |

**User's choice:** Подход 6 — Hybrid envelope + prompt caching
**Notes:** Пользователь запросил глубокое исследование с таблицей сравнения всех подходов. После анализа 6 вариантов выбрал подход 6 как идеальный. Хотел реализовать полную extraction в Phase 1, а не откладывать на Phase 2. Решение: per-feature extraction переносится из Phase 2 в Phase 1.

### Модель Claude

**User's choice:** claude-sonnet-4-6 по умолчанию, конфигурируется через .env
**Notes:** Пользователь явно указал "claude-sonnet но через .env"

### Обработка PDF

| Option | Description | Selected |
|--------|-------------|----------|
| Native PDF support | Claude API native PDF (base64, type=document) | ✓ |
| Сначала экстракция текста | Парсить текст (PyMuPDF/pdfplumber), отправлять текст | |

**User's choice:** Native PDF support
**Notes:** —

---

## Claude's Discretion

- Конкретные поля Pydantic-конверта (помимо name/type/confidence/summary/dependencies)
- Промпт для 2-го вызова (свободная бизнес-логика)
- Схема SQLite (business_logic как JSON blob)

## Deferred Ideas

- Объединение Phase 1 и Phase 2 — отклонено, фазы остаются раздельными. Per-feature extraction перенесён в Phase 1.
