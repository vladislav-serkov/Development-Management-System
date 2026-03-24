# Phase 2: Extraction Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 02-extraction-pipeline
**Areas discussed:** Формат реестров зависимостей, Критерии gap detection, Overview.md и .context/ экспорт, Multi-pass pipeline архитектура

---

## Формат реестров зависимостей

### Формат JSON

| Option | Description | Selected |
|--------|-------------|----------|
| Максимум структуры | name, type, columns/fields, used_by_features[], операции CRUD | ✓ |
| Свободный формат | Claude сам определяет структуру для каждой зависимости | |
| Минимум | name, description, used_by_features[] без схемы | |

**User's choice:** Максимум структуры
**Notes:** —

### Дедупликация

| Option | Description | Selected |
|--------|-------------|----------|
| Claude merge | Отдельный Claude-вызов объединяет упоминания из разных фич | ✓ |
| Программный merge | Код мержит по имени, берёт более полное описание | |
| You decide | На усмотрение Claude | |

**User's choice:** Claude merge
**Notes:** —

### Гранулярность файлов

| Option | Description | Selected |
|--------|-------------|----------|
| Файл на зависимость | db/product_table.json, external_api/rbo-adapter.json | ✓ |
| Один файл на категорию | db/all.json с массивом всех таблиц | |

**User's choice:** Файл на зависимость
**Notes:** —

---

## Критерии gap detection

### Gap engine

| Option | Description | Selected |
|--------|-------------|----------|
| Claude анализ | Claude анализирует весь контекст и находит неочевидные gaps | ✓ |
| Rules-based | Код проверяет: если зависимость без columns → gap | |
| Комбинированный | Rules-based + Claude для глубокого анализа | |

**User's choice:** Claude анализ
**Notes:** —

### Формат gaps.md

| Option | Description | Selected |
|--------|-------------|----------|
| Структурированный MD | Группировка по категориям (DB, API, Cache), приоритеты | ✓ |
| Простой список | Плоский список без категоризации | |
| You decide | На усмотрение Claude | |

**User's choice:** Структурированный MD
**Notes:** —

### Gap suggestions

| Option | Description | Selected |
|--------|-------------|----------|
| Да, с suggestions | Claude предлагает вероятную схему на основе контекста | ✓ |
| Только факты | Фиксация проблемы без предположений | |

**User's choice:** Да, с suggestions
**Notes:** —

---

## Overview.md и .context/ экспорт

### Содержимое overview.md

| Option | Description | Selected |
|--------|-------------|----------|
| Полный контекст | Тип, summary, зависимости со ссылками, бизнес-логика, ссылки на gaps | ✓ |
| Минимальный | Тип + однострочный summary | |
| You decide | На усмотрение Claude | |

**User's choice:** Полный контекст
**Notes:** —

### Поведение экспорта

**User's clarification:** Один экспорт = одна фича. Не весь .context/ целиком.

Экспорт per-feature создаёт:
- features/{name}/overview.md + business-logic.json
- Зависимости этой фичи в db/, external_api/, cache/
- Обновление gaps.md

При повторном экспорте той же фичи — перезаписать её файлы. Shared зависимости дополняются (добавить used_by + новые поля), не перезаписываются.

---

## Multi-pass pipeline архитектура

### Когда запускать dedup + gaps

| Option | Description | Selected |
|--------|-------------|----------|
| Автоматически после extraction | Часть единого pipeline, готовый результат за один заход | ✓ |
| Отдельный шаг | Пользователь явно запускает dedup/gaps | |
| You decide | На усмотрение Claude | |

**User's choice:** Автоматически после extraction
**Notes:** —

### Количество Claude-вызовов

| Option | Description | Selected |
|--------|-------------|----------|
| 1 общий вызов | Все business-logic.json → merged dependencies + gaps + overviews | ✓ |
| 2 вызова | Один для dedup (tool_use), другой для gaps (свободный текст) | |
| You decide | На усмотрение Claude | |

**User's choice:** 1 общий вызов
**Notes:** —

### Prompt caching для 3-го вызова

| Option | Description | Selected |
|--------|-------------|----------|
| Кешировать JSON фич | Все business-logic.json как один блок с cache_control | |
| Без кеширования | Одноразовый вызов, кеш не нужен | |
| You decide | На усмотрение Claude | ✓ |

**User's choice:** You decide
**Notes:** —

---

## Claude's Discretion

- Prompt caching для 3-го вызова (dedup+gaps)
- Конкретная структура промпта для dedup+gaps вызова
- Формат tool_use vs свободный текст для 3-го вызова

## Deferred Ideas

None — discussion stayed within phase scope
