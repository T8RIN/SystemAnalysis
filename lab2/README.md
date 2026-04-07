# Лабораторная работа №2: SWI-Prolog

В папке:
- `weather.pl` — основная лабораторная (задания 1–3).
- `project_car_search.pl` — **один проект на выбор**: №3 «Поиск нарушений по автомобилю».
- `report.md` — текстовая версия отчёта.
- `lab2_report_ready.docx` — готовый отчёт для сдачи.

## Запуск в SWISH

Сервис: [SWISH](https://swish.swi-prolog.org/)

### Часть 1: лабораторная (weather.pl)

1. Вставьте код `weather.pl`.
2. Нажмите `Run!`.
3. Выполните запросы:

```prolog
advice_for('Москва', A).
show_all_advices.
advice_for('Екатеринбург', A).
activity_advice(27, солнечно, X).
```

### Часть 2: проект на выбор (project_car_search.pl)

1. Откройте новый документ.
2. Вставьте `project_car_search.pl`.
3. Выполните:

```prolog
find_violations_by_car('А123ВС116', L).
show_violations_by_car('А123ВС116').
show_violations_by_car('М001ТТ116').
```

## Что сдавать

- `lab2_report_ready.docx`
- (при необходимости) скриншоты из SWISH с выполнением запросов.
