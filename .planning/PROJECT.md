# Extract Agent

## What This Is

Web-сервис для извлечения структурированного контекста из PDF-файлов технических заданий (ТЗ) микросервисов. Принимает PDF с описанием Kafka-консьюмеров, REST-эндпоинтов или автозадач по расписанию, анализирует их через Claude API и создаёт структурированную папку `.context/` в корне целевого микросервиса — готовый контекст для LLM-кодинг-агентов.

## Core Value

Превращение неструктурированных PDF-спецификаций в идеально организованный контекст для LLM-кодинг-агентов — с автоматическим выявлением недостающей информации.

## Requirements

### Validated

- [x] Парсинг PDF и извлечение контекста через Claude API — Validated in Phase 1
- [x] Определение типа функционала (Kafka-консьюмер, REST-эндпоинт, автозадача) — Validated in Phase 1
- [x] Генерация business-logic в JSON-формате для каждой фичи — Validated in Phase 1
- [x] Общий реестр зависимостей: external_api/, db/, cache/ — без дублей между фичами — Validated in Phase 2
- [x] Автоматическое обнаружение gaps: недостающие структуры таблиц, схемы API, структуры Redis — Validated in Phase 2
- [x] Сохранение .context/ папки на диск в корень указанного микросервиса — Validated in Phase 2

### Active

- [ ] Загрузка PDF через web UI
- [ ] Подробный web UI для просмотра и редактирования всех артефактов (фичи, БД, API, кеш, gaps)
- [ ] Версионирование: отслеживание изменений при повторной загрузке обновлённого ТЗ на ту же фичу

### Out of Scope

- Генерация кода — задача кодинг-агента, не этого сервиса
- Интеграция с конкретными IDE — сервис только создаёт папку контекста
- Работа с не-PDF форматами (Word, Confluence) — только PDF на старте

## Context

Целевые пользователи — разработчики микросервисов в экосистеме MTS Pay (Java/Kotlin). ТЗ приходят в формате PDF из Jira/Confluence, описывают:

- **Kafka-консьюмеры**: топик, формат сообщения, логика обработки
- **REST-эндпоинты**: path, request/response, валидация
- **Автозадачи по расписанию**: триггер, логика, зависимости

В ТЗ часто упоминаются внешние API, таблицы БД и Redis-кеш, но без полного описания их структуры — это и есть gaps, которые сервис должен выявлять.

Выходная структура `.context/`:

```
.context/
├── features/
│   ├── product-schedule-consumer/
│   │   ├── overview.md
│   │   └── business-logic.json
│   └── product-return-consumer/
│       ├── overview.md
│       └── business-logic.json
├── external_api/
│   └── some-service.json
├── db/
│   └── product_table.json
├── cache/
│   └── product-cache.json
└── gaps.md
```

5 примеров PDF уже есть в проекте — они покрывают Kafka-консьюмеры и различные бизнес-процессы MTS Pay.

## Constraints

- **Tech stack**: Python (FastAPI) бэкенд, Claude API для анализа PDF
- **Output format**: MD для описаний, JSON для бизнес-логики и структур зависимостей
- **Deployment**: локальный web-сервис (запускается на машине разработчика)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI + Claude API | Python удобен для PDF-парсинга, Claude хорош для структурированного извлечения | Validated (Phase 1-2) |
| Общий реестр зависимостей | Одна таблица БД может использоваться в нескольких фичах — дубли нежелательны | Validated (Phase 2) |
| Business-logic в JSON | Структурированный формат лучше парсится кодинг-агентами | Validated (Phase 1) |
| Версионирование контекста | ТЗ обновляются — нужно отслеживать что изменилось | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-24 after Phase 2 completion — extraction pipeline + .context/ export fully operational*
