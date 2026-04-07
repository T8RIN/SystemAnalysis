# Лабораторная работа 1: Wolfram Alpha API (Python)

Проект выполняет 15 запросов к Wolfram Alpha API (10 обязательных + 5 дополнительных), извлекает ключевые данные из JSON-ответов и сохраняет результаты в файлы.

## Структура проекта

- `main.py` — точка входа
- `config.json` — конфигурация (AppID, URL, таймаут, пути)
- `app/config.py` — загрузка и валидация конфигурации
- `app/wolfram_client.py` — HTTP-клиент для Wolfram Alpha API
- `app/parser.py` — парсинг JSON и извлечение ключевых данных
- `app/queries.py` — список обязательных и дополнительных запросов
- `app/runner.py` — последовательный запуск запросов и сохранение результатов
- `logs/app.log` — лог выполнения
- `outputs/raw_responses/*.json` — полные ответы API
- `outputs/extracted_results.json` — извлеченные ключевые данные
- `outputs/human_readable_report.txt` — удобочитаемый отчет

## Подготовка

1. Убедитесь, что установлен Python 3.10+.
2. (Рекомендуется) создать и активировать виртуальное окружение.
3. Установить зависимости:

```bash
pip install -r requirements.txt
```

4. Проверьте `config.json`:

```json
{
  "appid": "3XVYH9L93Q",
  "base_url": "https://api.wolframalpha.com/v2/query",
  "output_dir": "outputs",
  "log_file": "logs/app.log",
  "timeout_seconds": 20,
  "max_retries": 2
}
```

## Запуск

```bash
python main.py
```

Для сохранения вывода консоли в файл (удобно для скриншота):

```bash
python main.py | tee outputs/console_output.txt
```

## Реализованные запросы

### 10 обязательных
1. `integrate x^2 sin^3 x dx`
2. `population of Russia 2024`
3. `molar mass of H2SO4`
4. `kinetic energy of 5kg object at 10m/s`
5. `distance between Moscow and Saint Petersburg`
6. `100 USD to RUB`
7. `current time in Kazan`
8. `distance to Mars`
9. `body mass index 180cm 75kg`
10. `translate hello to Russian`

### 5 дополнительных
11. `solve x^2 - 5x + 6 = 0`
12. `prime factors of 123456`
13. `weather in Kazan`
14. `average human heart rate`
15. `highest mountain in Europe`

## Что проверяется по требованиям

- Четкое разделение на модули: есть
- Обработка сетевых/API ошибок: есть (`RuntimeError`, повторные попытки запроса, статус `error`/`api_no_result`)
- Логирование процесса: есть (`logs/app.log`)
- Чтение API-ключа из конфигурации: есть (`config.json`)
- Последовательное выполнение всех запросов: есть
- Парсинг JSON с извлечением ключевых данных: есть (`summary`, `pods`, `success`)
- Сохранение полных и извлеченных данных в отдельные файлы: есть

## Пример вывода программы

```text
Lab 1 completed successfully
Total queries: 15
Extracted data file: /.../lab1/outputs/extracted_results.json
Human-readable report: /.../lab1/outputs/human_readable_report.txt
Raw API responses folder: /.../lab1/outputs/raw_responses
```
