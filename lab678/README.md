# Лабораторные работы 6-8: RAG-система на PostgreSQL, pgvector и локальной LLM

В папке находится локальная реализация сразу для трёх практик:

- лабораторная 6: RAG-пайплайн на Python, PostgreSQL и pgvector;
- лабораторная 7: пользовательский веб-интерфейс к RAG-системе;
- лабораторная 8: пополнение базы знаний через UI, редактирование, поиск и визуализация.

## Структура

- `rag_postgres.py` — консольный запуск лабораторной 6;
- `app.py` — Streamlit-интерфейс для лабораторных 7-8;
- `src/` — модули подключения к БД, эмбеддингов, LLM и RAG;
- `data/sample_documents.json` — пример фактов для импорта;
- `docker-compose.yml` — PostgreSQL 16 с pgvector;
- `.env.example` — пример локальных настроек;
- `report.md` — отчёт и ответы на контрольные вопросы.

## Быстрый запуск

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Поднять PostgreSQL с pgvector через Docker:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
docker compose up -d
```

Если PostgreSQL уже установлен локально, нужно создать базу `rag_db` и включить расширение:

```bash
createdb rag_db
psql -d rag_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Проверить окружение:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./.venv/bin/python scripts/check_environment.py
```

То же самое можно сделать одной командой:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./setup.sh
```

## Запуск LM Studio

По умолчанию проект уже настроен на Ollama:

```text
LM_STUDIO_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:3b
```

Команда запуска сервиса:

```bash
brew services start ollama
```

Скачать модель:

```bash
ollama pull qwen2.5:3b
```

Если вместо Ollama нужен именно LM Studio, поменяйте в `.env`:

```text
LM_STUDIO_URL=http://localhost:1234/v1
LLM_MODEL=
```

1. Открыть LM Studio.
2. Загрузить локальную модель, например GigaChat 3.1 10B или другую instruct-модель.
3. Открыть вкладку Developer и нажать Start Server.
4. Убедиться, что endpoint в `.env` равен `http://localhost:1234/v1`.

Если в LM Studio указан конкретный id модели, его можно прописать в `LLM_MODEL`.
Если поле оставить пустым, программа попробует взять первую модель из `/v1/models`.

## Консольный запуск лабораторной 6

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./.venv/bin/python rag_postgres.py
```

Или через стартовый скрипт:

```bash
./start_cli.sh
```

Запуск без обращения к LLM, только проверка эмбеддингов и pgvector:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./.venv/bin/python rag_postgres.py --no-llm
```

Пример своего вопроса:

```bash
./.venv/bin/python rag_postgres.py --question "Как работает pgvector?" --top-k 3
```

## Запуск веб-интерфейса лабораторных 7-8

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./.venv/bin/streamlit run app.py
```

Или через стартовый скрипт:

```bash
./start_ui.sh
```

После запуска Streamlit откроет интерфейс на `http://localhost:8501`.

Если всё уже установлено, можно запускать одной командой:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab678
./start_all.sh
```

В интерфейсе есть вкладки:

- `RAG-запрос` — вопрос, top_k, фильтр по источнику, ответ LLM, контекст и график релевантности;
- `База знаний` — добавление, редактирование, удаление, строковый и семантический поиск;
- `Импорт` — загрузка фактов из `.txt`, `.md`, `.json`, `.csv`;
- `Аналитика` — распределение фактов по источникам и темам, состояние компонентов;
- `Настройки` — изменение `LLM_TIMEOUT`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`, `DEFAULT_TOP_K`.

## Настройки эмбеддингов

По умолчанию используется мультиязычная модель:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Она возвращает векторы размерности 384 и лучше подходит для русскоязычных вопросов, чем базовая `all-MiniLM-L6-v2`.
Если выбрать модель с другой размерностью, нужно поменять `VECTOR_DIM` в `.env`.

## Полезные команды Make

```bash
make install
make copy-env
make db-up
make run-cli
make run-ui
make smoke
```
