# Extract Agent

## What This Is

Web-сервис для извлечения структурированного контекста из PDF-файлов технических заданий (ТЗ) микросервисов. Принимает PDF с описанием Kafka-консьюмеров, REST-эндпоинтов или автозадач по расписанию, анализирует их через Claude API и создаёт структурированную папку `.context/` в корне целевого микросервиса — готовый контекст для LLM-кодинг-агентов. Включает web UI для просмотра и inline-редактирования всех артефактов.

## Core Value

Превращение неструктурированных PDF-спецификаций в идеально организованный контекст для LLM-кодинг-агентов — с автоматическим выявлением недостающей информации.

## Current State

**v1.0 MVP shipped 2026-03-28.** Full pipeline operational:
- PDF upload → Claude three-pass extraction → .context/ export
- Web UI: project grid, real-time SSE progress, artifact viewing
- Inline editing: JSON (CodeMirror + validation), Markdown (split-pane + preview), dependencies (Dialog), gaps (form)
- Tech: ~5,900 Python LOC (FastAPI + SQLAlchemy + Claude API), ~3,000 TypeScript LOC (React + Vite + shadcn/ui)

## Requirements

### Validated

- ✓ PDF upload and Claude API extraction — v1.0
- ✓ Feature type detection (Kafka consumer, REST endpoint, scheduled task) — v1.0
- ✓ Multi-feature PDF support — v1.0
- ✓ Business-logic.json and overview.md per feature — v1.0
- ✓ Shared dependency registries (external_api/, db/, cache/) without cross-feature duplicates — v1.0
- ✓ Automatic gap detection (missing schemas, API contracts, Redis structures) — v1.0
- ✓ .context/ filesystem export — v1.0
- ✓ Web UI with context tree navigation and artifact rendering — v1.0
- ✓ Real-time SSE extraction progress — v1.0
- ✓ Inline editing for all artifact types (JSON, Markdown, dependencies, gaps) — v1.0

### Active

- [ ] Версионирование: отслеживание изменений при повторной загрузке обновлённого ТЗ
- [ ] Batch processing — загрузка нескольких PDF одного микросервиса за раз

### Out of Scope

- Генерация кода — задача кодинг-агента, не этого сервиса
- IDE плагины — filesystem output (.context/) — это и есть интеграция
- Не-PDF форматы (Word, Confluence, HTML) — только PDF на старте
- OCR для сканированных PDF — целевые PDF цифровые из Confluence
- Облачный деплой — локальный инструмент разработчика
- Авторизация и multi-user — single-developer tool на localhost
- Поддержка других LLM — Claude API оптимален для structured extraction

## Context

Целевые пользователи — разработчики микросервисов в экосистеме MTS Pay (Java/Kotlin). ТЗ приходят в формате PDF из Jira/Confluence.

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

5 примеров PDF в проекте — Kafka-консьюмеры и бизнес-процессы MTS Pay.

## Constraints

- **Tech stack**: Python (FastAPI) бэкенд, React (Vite) фронтенд, Claude API для анализа PDF
- **Output format**: MD для описаний, JSON для бизнес-логики и структур зависимостей
- **Deployment**: локальный web-сервис (Docker Compose)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI + Claude API | Python удобен для PDF-парсинга, Claude хорош для structured extraction | ✓ Good |
| Общий реестр зависимостей | Одна таблица БД может использоваться в нескольких фичах — дубли нежелательны | ✓ Good |
| Business-logic в JSON | Структурированный формат лучше парсится кодинг-агентами | ✓ Good |
| tool_use + manual Pydantic validation | client.messages.parse() менее надёжен для сложных schema | ✓ Good |
| Free-text for 3rd Claude call | Сложный nested output надёжнее как free text, чем tool_use | ✓ Good |
| Prompt caching on context block | Снижение токенов при multi-pass extraction | ✓ Good |
| Two-tier structured data | structured_logic (schema) для UI, business_logic (free-form) для кодинг-агента | ✓ Good |
| SSE via StreamingResponse | Простота, нет зависимости от EventSourceResponse | ✓ Good |
| Zustand + no react-router | Достаточно для two-page SPA без URL state | ✓ Good |
| CodeMirror over Monaco | ~300KB vs ~5-10MB, достаточно для view/light-edit | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:** Requirements audit, decisions log, description check.
**After each milestone:** Full review of all sections.

---
*Last updated: 2026-03-28 after v1.0 milestone*
