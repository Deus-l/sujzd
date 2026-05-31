<div align="center">

# СУЖЦД
### Система Управления Жизненным Циклом Документации

*Атомарное версионирование технической документации по принципам Git*  
*с каскадным распространением изменений*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![ГОСТ Р 2.503–2023](https://img.shields.io/badge/ГОСТ_Р-2.503–2023-blue?style=flat-square)](https://protect.gost.ru)

</div>

---

## О проекте

**СУЖЦД** — информационная система, реализующая концепцию **атомарного версионирования** технической документации (ЕСКД/ЕСТД/ЕСПД) на принципах распределённых систем контроля версий с каскадным распространением изменений согласно ГОСТ Р 2.503–2023, п. 4.2.

### Зачем это нужно?

Классические PLM-системы хранят документы как монолиты. При изменении одного поля (например, марки материала в чертеже) инженер вручную должен найти и обновить десятки зависимых документов. СУЖЦД решает эту проблему:

1. Каждое изменение — это **дельта** (атомарная запись: что, где, когда, кем, почему изменилось)
2. Дельта автоматически классифицируется по типу (**Ω₁–Ω₇**) через встроенный классификатор
3. Движок зависимостей вычисляет **каскад E(δ)** — все документы, которые надо обновить
4. Исполнители получают **уведомления** с дедлайнами согласно нормативным срокам

---

## Возможности

| Модуль | Что умеет |
|--------|-----------|
| **Δ-версионирование** | Атомарные дельты с SHA-256, ветвление (branch/merge), diff, blame, checkout на произвольную точку времени |
| **Классификатор Ω** | Детерминированная классификация изменений (Ω₁–Ω₇): редакционные, конструктивные, технологические, нормативные и т.д. |
| **Движок зависимостей** | Матрица M[DocType][Field][Ω] × 49 правил, DSR-ссылки, жизненный цикл (ТП/РД/ИЗГОТ/ЭКСПЛ), каскадный граф |
| **IA-модуль** | AI-анализ дельт через OpenRouter / Groq / Anthropic / HuggingFace; парсинг изменений из DOCX/XLSX/текста |
| **Документооборот** | Генерация DOCX (ГОСТ 2.105–2019), хранилище файлов, версии, паспорта изменений |
| **Уведомления** | Задачи по каскаду с дедлайнами, назначение исполнителей по ролям (конструктор/технолог/программист) |
| **REST API** | 45+ эндпоинтов, OpenAPI/Swagger UI, Pydantic-схемы |
| **SPA-интерфейс** | Встроенный дашборд (Vanilla JS, без фреймворков): дельты, каскад, ветки, уведомления, матрица, DSR |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      Браузер (SPA)                          │
│          Vanilla JS · fetch API · без фреймворков           │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / REST
┌────────────────────────▼────────────────────────────────────┐
│                   FastAPI (main.py)                         │
│   45+ маршрутов · Pydantic-валидация · CORS · OpenAPI       │
└──┬──────────────┬───────────────┬───────────────┬───────────┘
   │              │               │               │
   ▼              ▼               ▼               ▼
delta_repo   dependency_      ia_module      generate_docs
(Δ-вер-      engine          (AI + класс-   (DOCX · ГОСТ
сионирова-   (движок зав-    сификатор Ω)   2.105–2019)
ние, ветки)  исимостей,
             матрица M)
   │              │               │               │
   └──────────────┴───────────────┴───────────────┘
                         │
              ┌──────────▼──────────┐
              │   SQLite (models)   │
              │ documents · deltas  │
              │ notifications       │
              │ branches · conflicts│
              │ audit_events        │
              └─────────────────────┘
```

### Ключевые концепции

**Дельта δ** — минимальная единица изменения:

```
δ = ⟨DocType, DocID, FieldID, V_before, V_after, Ω, Author, IIN, Branch, Timestamp⟩
```

**Классификация Ω** — тип изменения определяет дедлайны и каскад:

| Класс | Смысл | Срок (обязат.) |
|-------|-------|----------------|
| Ω₁ | Редакционное (опечатки, форматирование) | — |
| Ω₂ | Конструктивное без изменения функции | 2–3 дня |
| Ω₃ | Конструктивное с изменением состава | 3 дня |
| Ω₄ | Изменение технических требований | 3 дня |
| Ω₅ | Замена материала / покупного изделия | 4 дня |
| Ω₆ | Изменение нормативных ссылок | 5 дней |
| Ω₇ | Срочные исправления | 2 дня |

---

## Быстрый старт

### Требования

- Python 3.11+
- Bash (macOS / Linux / WSL)

### Запуск одной командой

```bash
git clone https://github.com/YOUR_USERNAME/sujzd.git
cd sujzd
./run.sh
```

Скрипт автоматически создаёт `.venv`, устанавливает зависимости, освобождает порт 8877 если занят, запускает сервер с авто-перезагрузкой.

Открыть в браузере: **http://localhost:8877**  
Swagger UI: **http://localhost:8877/api/docs**

### Ручной запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8877
```

### AI-анализ (опционально)

Для работы IA-модуля укажите хотя бы один ключ через переменные окружения:

```bash
# OpenRouter — рекомендуется (есть бесплатный тариф)
# Регистрация: https://openrouter.ai → Keys → Create Key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Groq — бесплатный (llama3, mixtral)
# Регистрация: https://console.groq.com
export GROQ_API_KEY="gsk_..."

# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# HuggingFace
export HF_TOKEN="hf_..."

./run.sh
```

---

## Структура проекта

```
sujzd/
├── main.py               # FastAPI-приложение, все 45+ маршрутов
├── models.py             # SQLAlchemy ORM-модели
├── schemas.py            # Pydantic-схемы (входные/выходные)
├── database.py           # Подключение к SQLite, миграции
│
├── delta_repo.py         # Δ-версионирование: commit, checkout, diff, blame, merge
├── dependency_engine.py  # Движок зависимостей: матрица M, каскад E(δ), уведомления
├── ia_module.py          # IA-модуль: классификатор Ω, AI-анализ, парсинг файлов
├── generate_docs.py      # Генерация DOCX по ГОСТ 2.105–2019
├── doc_storage.py        # Файловое хранилище документов (DOCX/PDF/метаданные)
├── health_check.py       # Эндпоинт /health
│
├── data/
│   ├── matrix.json       # Матрица зависимостей (49 правил, ЕСКД ↔ ЕСТД ↔ ЕСПД)
│   └── dsr.json          # Document Schema Registry (26 типов, поля, ссылки, ЖЦ)
│
├── static/
│   └── index.html        # SPA-интерфейс (Vanilla JS, ~2200 строк)
│
├── requirements.txt
└── run.sh                # Скрипт запуска с авто-настройкой venv
```

---

## API — основные эндпоинты

### Документы

```
GET    /api/documents                          Список документов
POST   /api/documents                          Создать документ
POST   /api/documents/upload                   Загрузить DOCX/PDF
GET    /api/documents/{id}                     Получить документ
PATCH  /api/documents/{id}                     Обновить статус/название
DELETE /api/documents/{id}                     Удалить
GET    /api/documents/{id}/fields              Все поля документа
GET    /api/documents/{id}/blame/{field}       История изменений поля
GET    /api/documents/{id}/checkout?timestamp= Срез на момент времени
GET    /api/documents/{id}/diff                Разница между версиями
```

### Дельты

```
GET    /api/deltas                  История изменений
POST   /api/deltas                  Зафиксировать изменение (запускает каскад)
GET    /api/deltas/{id}             Дельта по ID
GET    /api/deltas/{id}/cascade     Граф каскадных зависимостей E(δ)
```

### Ветки и слияния

```
GET    /api/branches                Список веток
POST   /api/branches                Создать ветку
POST   /api/branches/merge          Слить ветки (3-way merge, обнаружение конфликтов)
```

### Каскад и уведомления

```
GET    /api/notifications           Задачи по зависимым документам
PUT    /api/notifications/{id}/resolve   Закрыть задачу
PUT    /api/notifications/{id}/skip      Пропустить (только рекомендуемые)
GET    /api/conflicts               Конфликты слияния
POST   /api/conflicts/resolve       Разрешить конфликт
```

### IA-модуль

```
POST   /api/ia/classify     Классифицировать изменение → Ω₁…Ω₇
POST   /api/ia/significance  Оценить значимость S(δ)
POST   /api/ia/analyze      AI-анализ дельты (OpenRouter / Groq / Anthropic)
POST   /api/ia/step         Распарсить изменение из plain text
POST   /api/ia/xlsx         Распарсить изменение из XLSX-строк
POST   /api/ia/docx         Распарсить изменение из DOCX-параграфов
```

### Матрица и DSR

```
GET    /api/matrix            Правила матрицы зависимостей
GET    /api/matrix/stats      Статистика (49 правил: 29 обязательных, 20 рекомендуемых)
POST   /api/matrix/reload     Перезагрузить matrix.json без перезапуска сервера
GET    /api/matrix/lifecycle  Карта жизненного цикла документов
GET    /api/dsr               Реестр схем документов (26 типов)
POST   /api/dsr               Зарегистрировать новый тип документа
```

### Дашборд и администрирование

```
GET    /api/stats             Сводная статистика системы
GET    /api/audit             Журнал аудита (все события)
GET    /api/snapshot          Снимок состояния БД
POST   /api/admin/recalculate-cascade   Пересчитать уведомления (идемпотентно)
```

---

## Матрица зависимостей

Система содержит **49 нормативных правил** (ГОСТ Р 2.503–2023, ГОСТ 3.1119-83, ГОСТ 19.101–77), связывающих поля документов ЕСКД ↔ ЕСТД ↔ ЕСПД:

```
ESKD_DETAIL.material   →  ESTD_MK.material            (обязательная, Ω₂,Ω₃)
ESKD_DETAIL.material   →  ESKD_PASSPORT.tech_chars     (обязательная, Ω₂,Ω₄)
ESKD_DETAIL.coating    →  ESTD_TI.coating_procedure    (рекомендуемая, Ω₂)
ESKD_SPEC.composition  →  ESTD_KK.assembly_composition (обязательная, Ω₃)
ESPD_TZ.func_req       →  ESPD_OP.functions            (обязательная, Ω₂)
...ещё 44 правила
```

**DSR (Document Schema Registry)** — реестр из **26 типов документов** (ЕСКД, ЕСТД, ЕСПД) с описанием полей, межполевых ссылок (`links`), чувствительности к Ω-типам и стадий жизненного цикла.

---

## Технологии

| Слой | Технология |
|------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| ORM | SQLAlchemy 2.0 |
| База данных | SQLite 3 |
| Валидация | Pydantic 2 |
| Документы | python-docx, pypdf |
| AI-провайдеры | OpenRouter, Groq, Anthropic, HuggingFace |
| Frontend | Vanilla JS (ES2022), CSS Variables, без npm |
| Деплой | Shell-скрипт с автонастройкой venv |

---

## Нормативная база

| ГОСТ | Применение |
|------|-----------|
| ГОСТ Р 2.503–2023 | Правила внесения изменений, сроки, каскадное обновление |
| ГОСТ 2.102–2013 | Виды и комплектность конструкторских документов (ЕСКД) |
| ГОСТ 2.105–2019 | Общие требования к текстовым документам |
| ГОСТ 3.1102–2011 | Стадии разработки и виды документов (ЕСТД) |
| ГОСТ 19.101–77 | Виды программных документов (ЕСПД) |
| ГОСТ 3.1119–83 | Требования к комплектности документации |

---

## Разработка

### Добавить правило в матрицу

Отредактировать `data/matrix.json`:

```json
{
  "id": "R_050",
  "source_type": "ESKD_DETAIL",
  "source_field": "mass",
  "target_type": "ESKD_PASSPORT",
  "target_field": "tech_chars",
  "dep_type": "1",
  "omega_types": ["Ω₂", "Ω₃", "Ω₄"],
  "description": "Изменение массы → паспорт изделия",
  "norm_ref": "ГОСТ Р 2.503–2023, п. 4.2"
}
```

Затем нажать «Перезагрузить матрицу» в UI или `POST /api/matrix/reload`.

### Зарегистрировать новый тип документа

```bash
curl -X POST http://localhost:8877/api/dsr \
  -H "Content-Type: application/json" \
  -d '{
    "code": "ESKD_NEW",
    "name": "Новый тип документа",
    "std": "ЕСКД",
    "fields": [
      {"id": "field1", "name": "Наименование поля", "type": "string"}
    ]
  }'
```

---

## Лицензия

MIT — свободное использование в учебных и исследовательских целях.

---

<div align="center">

FastAPI + SQLite + Vanilla JS &nbsp;·&nbsp; ГОСТ Р 2.503–2023 &nbsp;·&nbsp; 2025

</div>
