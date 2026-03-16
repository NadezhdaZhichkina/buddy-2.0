# Buddy — полная документация и аналитика

> Техническая документация в формате Claude Code: архитектура, потоки данных, структуры, конфигурация.

---

## 1. Обзор системы

Buddy — AI-агент онбординга, который:
- Ведёт новичка по сценарию адаптации (по роли)
- Отвечает на вопросы из базы знаний (с LLM или без)
- Передаёт неизвестные вопросы модератору через тикеты
- Сохраняет ответы модератора в базу знаний

**Два интерфейса:**
1. **FastAPI** (`app/main.py`) — для Mattermost webhook
2. **Streamlit** (`streamlit_app.py`) — для тестирования чата и модерации

---

## 2. Структура проекта

```
buddy/
├── streamlit_app.py          # UI: чат, роли (Пользователь/Модератор), тикеты
├── app/
│   ├── streamlit_chat.py     # StreamlitChatService: поиск, LLM, тикеты, БЗ
│   ├── main.py               # FastAPI: Mattermost webhook
│   ├── chat_service.py       # ChatService для FastAPI (LLM, база знаний)
│   ├── llm_client.py         # OpenRouter API
│   ├── mattermost_client.py  # Mattermost REST API
│   ├── onboarding.py         # Сценарии онбординга по ролям
│   ├── models.py             # ORM: User, Question, Answer, KnowledgeItem
│   └── config.py             # Settings из .env
├── scripts/
│   ├── seed_knowledge.py     # SEED_ITEMS → SQLite (основная БЗ)
│   ├── seed_knowledge_curated.py
│   └── export_knowledge_to_excel.py
├── knowledge_moderator.json  # Резерв: ответы модератора (fallback при сбое БД)
└── buddy_streamlit.db        # SQLite (локально, если нет PostgreSQL)
```

---

## 3. Поток данных (Streamlit)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT UI (streamlit_app.py)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Выбор роли: Пользователь | Модератор                                      │
│  • Чат (user1/user2) — если Пользователь                                     │
│  • Панель тикетов + ответы — если Модератор                                  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    StreamlitChatService (app/streamlit_chat.py)               │
├─────────────────────────────────────────────────────────────────────────────┤
│  • chat_reply_generative()  — LLM + факты из БЗ, живой диалог               │
│  • answer_with_meta()       — поиск в БЗ, нужна ли модерация                 │
│  • create_moderation_ticket() — создание тикета при «нет в базе»             │
│  • resolve_ticket()         — модератор отправляет ответ → БЗ + пользователю│
│  • save_manual_knowledge()  — добавление Q/A вручную                         │
│  • _retrieve_candidates()   — поиск по question/answer/tags (скор + алиасы)   │
└──────────────────────────────┬──────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
┌───────────────────┐ ┌───────────────┐ ┌─────────────────────────┐
│  PostgreSQL/      │ │ OpenRouter    │ │ knowledge_moderator.json │
│  SQLite           │ │ (LLM)         │ │ (резерв ответов          │
│  • knowledge_     │ │               │ │  модератора)            │
│    items          │ │               │ │                         │
│  • moderation_    │ │               │ │                         │
│    tickets        │ │               │ │                         │
└───────────────────┘ └───────────────┘ └─────────────────────────┘
```

---

## 4. Модели данных (Streamlit)

### knowledge_items

| Поле     | Тип   | Описание                    |
|----------|-------|-----------------------------|
| id       | int   | PK                          |
| question | text  | Вопрос                      |
| answer   | text  | Ответ                       |
| tags     | text  | Теги (через запятую)        |

### moderation_tickets

| Поле              | Тип   | Описание                             |
|-------------------|-------|--------------------------------------|
| id                | int   | PK                                   |
| requester_username| text  | Кто задал вопрос (user1, user2)     |
| question          | text  | Текст вопроса                        |
| user_role, user_circle | text | Профиль пользователя          |
| draft_answer      | text  | Черновик ответа модератора           |
| final_answer      | text  | Финальный ответ (после «Отправить»)  |
| status            | text  | in_progress \| sent \| rejected      |
| moderator_username| text  | Кто ответил                          |
| delivered_to_user | int   | 0/1 — доставлено ли пользователю     |

---

## 5. Поиск в базе знаний

### Алгоритм (streamlit_chat.py)

1. **Извлечение терминов** (`_extract_search_terms`):
   - Разбивка по пробелам, удаление стоп-слов (что, как, где, …), цифр
   - Минимум 2 символа на слово

2. **Расширение терминов** (`_expand_search_terms`):
   - **Алиасы:** мм→mchat, кб→корпоративная база знаний
   - **Стемминг:** каналов→канал, вопросы→вопрос
   - **Аббревиатуры:** из запроса извлекаются заглавные (КБ, ММ)

3. **Скоринг** (`_score`):
   - Термин в question: +3
   - Термин в answer: +2
   - Термин в tags: +1
   - Совпадение целой фразы: +5

4. **Фильтрация:**
   - Оставляются только записи с score ≥ 3
   - Порог: `max(3, top_score - 2)`
   - Возвращается до 8 кандидатов

### Контекст для поиска

В поиск попадают **только сообщения пользователя** из последних 4 сообщений истории. Ответы Buddy не учитываются, чтобы не «засорять» поиск.

---

## 6. Логика ответа (answer_with_meta)

```
question
    │
    ├─ Точное совпадение (normalize) в knowledge_items?
    │     └─ ДА → ответ из БЗ, needs_moderation=False
    │
    ├─ Сильное совпадение (score ≥ 6) + LLM включён?
    │     └─ ДА → _answer_with_llm() → ответ
    │
    ├─ Запрос об аббревиатуре (КБ, ИПР) + нет в БЗ?
    │     └─ ДА → needs_moderation=True (тикет)
    │
    ├─ Маркеры низкой уверенности в ответе LLM?
    │     └─ ДА → needs_moderation=True
    │
    └─ Иначе → needs_moderation=True
```

---

## 7. Тикет-флоу

```
Пользователь: «Как оформить отпуск?»
    │
    ├─ Buddy ищет в БЗ → не найдено / низкая уверенность
    │
    ├─ create_moderation_ticket(question, requester, role, circle)
    │     └─ INSERT moderation_tickets (status=in_progress)
    │     └─ _notify_mattermost_new_ticket() — если настроен Mattermost
    │
    ├─ Пользователь видит: «Передал вопрос модератору, скоро ответим»
    │
    ├─ Модератор открывает панель тикетов, пишет ответ
    │
    ├─ resolve_ticket(ticket_id, answer, moderator)
    │     └─ _save_to_moderator_patch() — сразу в JSON (резерв)
    │     └─ UPDATE/INSERT knowledge_items
    │     └─ UPDATE moderation_tickets (status=sent)
    │
    └─ pop_user_updates() — пользователь получает ответ при следующем заходе в чат
```

---

## 8. Резервное хранение (moderator patch)

Файл `knowledge_moderator.json` — резерв ответов модератора:

- При `resolve_ticket` и `save_manual_knowledge` вызывается `_save_to_moderator_patch()`
- Формат: `[{"question": "...", "answer": "...", "tags": "..."}, ...]`
- При старте `_sync_seed_items()` загружает patch и записывает в БД
- При сбое PostgreSQL данные не теряются

---

## 9. База данных

### Подключение (_get_streamlit_db_url)

| Источник          | Приоритет |
|-------------------|-----------|
| BUDDY_FORCE_SQLITE=1 | 1 (fallback) |
| STREAMLIT_DATABASE_URL | 2 |
| DATABASE_URL      | 3 |
| st.secrets        | 4 (если env пусто) |
| SQLite файл       | 5 (по умолчанию) |

### Supabase

- Поддержка `postgres://` → `postgresql://`
- Автодобавление `?sslmode=require` при необходимости
- Рекомендуется **Connection pooler** (порт 6543), не direct (5432)

### Fallback при сбое PostgreSQL

1. `os.environ["BUDDY_FORCE_SQLITE"] = "1"`
2. Повторная инициализация `StreamlitChatService`
3. SQLite in-memory (`:memory:`) + `StaticPool`

---

## 10. Конфигурация (Secrets / .env)

| Ключ                      | Назначение                          |
|---------------------------|-------------------------------------|
| OPENROUTER_API_KEY        | Ключ для LLM (OpenRouter)           |
| OPENROUTER_MODEL          | Модель (gpt-4.1-mini)               |
| STREAMLIT_DATABASE_URL    | PostgreSQL URL для Streamlit Cloud   |
| MATTERMOST_BASE_URL       | URL Mattermost                      |
| MATTERMOST_BOT_TOKEN      | Токен бота                          |
| MATTERMOST_MODERATOR_CHANNEL_ID | Канал для уведомлений о тикетах |

---

## 11. Роли в Streamlit UI

| Роль          | Интерфейс                                  |
|---------------|---------------------------------------------|
| Пользователь  | Чат от имени user1/user2, ответы Buddy      |
| Модератор     | Список тикетов, черновики, отправка ответов|

Переключение — через `st.radio` в сайдбаре.

---

## 12. Аналитика (метрики, которые можно добавить)

| Метрика                    | Источник              | Описание                    |
|----------------------------|-----------------------|-----------------------------|
| Вопросов без ответа в БЗ   | answer_with_meta      | needs_moderation=True       |
| Созданных тикетов          | create_moderation_ticket | По requester, по времени |
| Ответов модератора         | resolve_ticket        | По модератору, по времени   |
| Пополнение БЗ              | knowledge_items       | Новые записи от модератора  |
| Использование LLM          | _answer_with_llm      | Успешные/неуспешные вызовы |

---

## 13. Ключевые функции (карта кода)

| Файл               | Функция/класс              | Роль                              |
|--------------------|----------------------------|-----------------------------------|
| streamlit_app.py   | _get_secret, _get_openrouter_* | Чтение секретов                |
| streamlit_app.py   | service.chat_reply_generative | Основной ответ в чате         |
| streamlit_chat.py  | StreamlitChatService       | Вся логика чата и тикетов        |
| streamlit_chat.py  | _retrieve_candidates_with_scores | Поиск в БЗ                   |
| streamlit_chat.py  | resolve_ticket             | Сохранение ответа модератора     |
| streamlit_chat.py  | _save_to_moderator_patch   | Резерв в JSON                    |
| streamlit_chat.py  | _sync_seed_items           | Загрузка seed + patch в БД       |

---

## 14. Деплой (Streamlit Cloud)

1. Репозиторий на GitHub, ветка `main`
2. [share.streamlit.io](https://share.streamlit.io) → New app
3. Main file: `streamlit_app.py`
4. Secrets: OPENROUTER_*, STREAMLIT_DATABASE_URL (Supabase pooler)
5. Rebuild после изменения секретов

---

*Документация обновлена: 2026-03*
