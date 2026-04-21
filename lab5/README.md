# Лабораторная работа №5: Детекция людей с помощью Ultralytics YOLO11

В папке находится автономная реализация лабораторной по теме
`обнаружение объектов с помощью Ultralytics YOLO11`.

Используются:

- `ultralytics` — загрузка предобученной модели `YOLO11` и инференс;
- `opencv-python` — чтение изображений и видео, отрисовка рамок, вывод окна;
- `numpy` — работа с кадрами как с массивами.

## Структура

- `main.py` — основной CLI-скрипт лабораторной;
- `requirements.txt` — зависимости проекта;
- `report.md` — краткий отчёт и ответы на контрольные вопросы;
- `outputs/` — сюда можно сохранять размеченные изображения и видео.

## Рекомендуемая среда

Для `ultralytics` и `opencv-python` рекомендуется использовать `Python 3.11`.
В корне проекта сейчас есть `Python 3.14`, поэтому для `lab5` лучше создать
отдельное окружение:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab5
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

## Быстрый запуск

Изображение:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab5
./.venv/bin/python main.py --source /path/to/image.jpg --save
```

Видео:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab5
./.venv/bin/python main.py --source /path/to/video.mp4 --save
```

Веб-камера:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab5
./.venv/bin/python main.py --camera 0
```

Посмотреть классы модели:

```bash
cd /Users/malikmuhametzanov/PycharmProjects/burn/lab5
./.venv/bin/python main.py --list-classes
```

## Что умеет программа

`main.py`:

1. Загружает предобученную модель `YOLO11` (по умолчанию `yolo11n.pt`);
2. Принимает путь к изображению, видео или номер веб-камеры;
3. Выполняет детекцию объектов на каждом кадре;
4. Фильтрует результаты по нужному классу, по умолчанию это `person`;
5. Рисует рамки и подписи с уверенностью модели;
6. Показывает количество найденных объектов в левом верхнем углу;
7. Умеет сохранять размеченный результат в `outputs/`;
8. Завершает обработку видео или камеры по клавише `q`.

## Важное замечание

Класс `face` отсутствует в стандартном наборе классов `COCO`, поэтому для
детекции лиц нужно передать специализированную модель через `--model` и выбрать
`--target-class face`.
