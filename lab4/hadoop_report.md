# Краткий отчёт по Hadoop

## Состояние текущей среды

- Java доступна: `True`
- Hadoop установлен: `True`
- HDFS-клиент доступен: `True`
- Spark установлен: `False`
- Локальный Hadoop Home: `/Users/malikmuhametzanov/PycharmProjects/burn/lab4/tools/hadoop-3.4.2`

## Рекомендуемая версия

`Hadoop 3.4.2`

## Подготовленный файл для HDFS

- Основной JSON: `/Users/malikmuhametzanov/PycharmProjects/burn/lab4/outputs/data/variant_1_patents.json`

## Команды для загрузки в HDFS

```bash
hdfs dfs -mkdir -p /user/student/patents
hdfs dfs -put /Users/malikmuhametzanov/PycharmProjects/burn/lab4/outputs/data/variant_1_patents.json /user/student/patents/variant_1_patents.json
hdfs dfs -ls /user/student/patents
```

## Что проверить после загрузки

1. Файл появился в `/user/student/patents`.
2. Размер файла в HDFS совпадает с локальным.
3. JSON корректно читается из HDFS-команд и/или Spark.

## Пример чтения в Spark

```python
df = spark.read.json('/user/student/patents/variant_1_patents.json')
df.printSchema()
df.select('patent_id', 'title', 'status_info.status').show(10, truncate=False)
```

## Примечание

В проекте подготовлена локальная установка Hadoop 3.4.2 и итоговый JSON для загрузки в HDFS. После запуска `start_hadoop.sh` команды из раздела выше можно выполнять без дополнительной настройки путей.