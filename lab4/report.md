# Отчёт по лабораторной работе №4

## Тема

Создание базы знаний на основе открытых ресурсов ФИПС с использованием Selenium, BeautifulSoup4, Pandas и подготовкой данных для Hadoop.

## Входные параметры запуска

- Вариант: `1`
- Разделы: `utility_models`
- Ограничение по числу документов на раздел: `без ограничения`
- Режим возобновления: `True`
- Использование кэша: `True`
- Число потоков загрузки карточек: `12`

## Что делает программа

1. Открывает реестр ФИПС в Selenium и проходит по дереву диапазонов номеров.
2. Доходит до конечных интервалов по 100 документов и собирает HTML-ссылки карточек.
3. Загружает карточки документов через requests и BeautifulSoup4.
4. Нормализует поля в единый JSON-формат и сохраняет результаты.
5. Формирует Pandas-таблицы для краткой сводки и отчётных CSV.

## Результаты текущего прогона

- Всего собранных записей: `9`
- `Реестр полезных моделей`: `9` записей
- JSON: `/Users/malikmuhametzanov/PycharmProjects/burn/lab4/outputs/data/variant_1_utility_models.json`
- CSV: `/Users/malikmuhametzanov/PycharmProjects/burn/lab4/outputs/data/variant_1_utility_models_summary.csv`

## Пример структуры данных

Каждая запись содержит:

- `patent_id`, `patent_type`, `patent_number_full`, `title`
- `status_info`
- `application_details`
- `ipc`, `cpc`
- `inventors`, `owners`, `correspondence_address`
- `abstract`, `claims`, `description_sections`, `search_report`
- `url`

## Hadoop

- Java в системе: `True`
- Hadoop в системе: `True`
- HDFS-клиент доступен: `True`
- Spark в системе: `False`
- Локальный Hadoop Home: `/Users/malikmuhametzanov/PycharmProjects/burn/lab4/tools/hadoop-3.4.2`

Для части с Hadoop подготовлены команды загрузки JSON в HDFS и краткий сценарий проверки в файле `hadoop_report.md`.

## Вывод

Код лабораторной реализует обязательные технологии Selenium, BeautifulSoup4 и Pandas, а также формирует итоговые JSON/CSV-артефакты для последующей загрузки в Hadoop.