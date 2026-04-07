from dataclasses import dataclass


@dataclass(frozen=True)
class QueryTask:
    id: int
    title: str
    query: str
    required: bool = True


def get_queries() -> list[QueryTask]:
    # 10 обязательных запросов по заданию.
    mandatory_queries = [
        QueryTask(1, "Математический расчет", "integrate x^2 sin^3 x dx"),
        QueryTask(2, "Фактологический запрос", "population of Russia 2024"),
        QueryTask(3, "Химический расчет", "molar mass of H2SO4"),
        QueryTask(4, "Физический расчет", "kinetic energy of 5kg object at 10m/s"),
        QueryTask(5, "Географический", "distance between Moscow and Saint Petersburg"),
        QueryTask(6, "Финансовый", "100 USD to RUB"),
        QueryTask(7, "Временной", "current time in Kazan"),
        QueryTask(8, "Астрономический", "distance to Mars"),
        QueryTask(9, "Медицинский", "body mass index 180cm 75kg"),
        QueryTask(10, "Лингвистический", "translate hello to Russian"),
    ]

    # 5 дополнительных запросов на выбор.
    optional_queries = [
        QueryTask(11, "Дополнительный: Решение уравнения", "solve x^2 - 5x + 6 = 0", required=False),
        QueryTask(12, "Дополнительный: Факторизация", "prime factors of 123456", required=False),
        QueryTask(13, "Дополнительный: Погода", "weather in Kazan", required=False),
        QueryTask(14, "Дополнительный: Биология", "average human heart rate", required=False),
        QueryTask(15, "Дополнительный: География", "highest mountain in Europe", required=False),
    ]

    return mandatory_queries + optional_queries
