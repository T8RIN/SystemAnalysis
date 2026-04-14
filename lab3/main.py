from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import skfuzzy as fuzz
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from requests import Response
from skfuzzy import control as ctrl

ROOT = Path(__file__).resolve().parent
OUTPUT_DATA_DIR = ROOT / "outputs" / "data"
OUTPUT_PLOTS_DIR = ROOT / "outputs" / "plots"
REPORT_FILE = ROOT / "report.md"
REPORT_CONTEXT_FILE = OUTPUT_DATA_DIR / "report_context.json"
README_FILE = ROOT / "README.md"

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
HISTORY_START_DATE = "2021-01-01"
HISTORY_END_DATE = "2025-12-31"

SEASON_ORDER = ["winter", "spring", "summer", "autumn"]
SEASON_NAMES = {
    "winter": "Зима",
    "spring": "Весна",
    "summer": "Лето",
    "autumn": "Осень",
}

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False


@dataclass(frozen=True)
class CityConfig:
    slug: str
    name: str
    latitude: float
    longitude: float
    expert_note: str


@dataclass
class FuzzyBundle:
    temperature: ctrl.Antecedent
    humidity: ctrl.Antecedent
    wind_speed: ctrl.Antecedent
    temp_deviation: ctrl.Antecedent
    humidity_deviation: ctrl.Antecedent
    wind_deviation: ctrl.Antecedent
    comfort: ctrl.Consequent
    anomaly: ctrl.Consequent
    comfort_system: ctrl.ControlSystem
    anomaly_system: ctrl.ControlSystem


CITIES = [
    CityConfig(
        slug="kazan",
        name="Казань",
        latitude=55.790278,
        longitude=49.134722,
        expert_note=(
            "Умеренно-континентальный климат. Зимой при ясной безветренной погоде "
            "возможны локальные перепады температуры до 5°C в разных частях города."
        ),
    ),
    CityConfig(
        slug="moscow",
        name="Москва",
        latitude=55.755864,
        longitude=37.617698,
        expert_note=(
            "Летом в центре города тепловая нагрузка ощущается сильнее из-за "
            "недостатка зелёных насаждений и выраженного эффекта городского острова тепла."
        ),
    ),
    CityConfig(
        slug="saint-petersburg",
        name="Санкт-Петербург",
        latitude=59.934280,
        longitude=30.335099,
        expert_note=(
            "Морской климат с частой сменой воздушных масс. Ветер свыше 20 м/с "
            "рассматривается как потенциально опасный, особенно в прибрежных районах."
        ),
    ),
]


def ensure_output_dirs() -> None:
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_openweather_api_key() -> str:
    env_data = load_env_file(ROOT / ".env")
    api_key = env_data.get("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Не найден ключ OpenWeatherMap. Добавьте OPENWEATHER_API_KEY в lab3/.env "
            "или в переменные окружения."
        )
    return api_key


def season_from_month(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def season_from_datetime(value: datetime) -> str:
    return season_from_month(value.month)


def clip_value(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def safe_points(values: list[float], lower: float, upper: float) -> list[float]:
    clipped = [clip_value(float(value), lower, upper) for value in values]
    for index in range(1, len(clipped)):
        if clipped[index] < clipped[index - 1]:
            clipped[index] = clipped[index - 1]
    return clipped


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def request_json(
    url: str,
    params: dict[str, Any],
    cache_path: Path,
    *,
    use_cache: bool = False,
    timeout: int = 60,
) -> Any:
    if use_cache and cache_path.exists():
        return load_json(cache_path)

    try:
        response: Response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        save_json(cache_path, payload)
        return payload
    except Exception:
        if cache_path.exists():
            return load_json(cache_path)
        raise


def fetch_current_weather(city: CityConfig, api_key: str, *, use_cache: bool = False) -> dict[str, Any]:
    cache_path = OUTPUT_DATA_DIR / f"{city.slug}_current.json"
    payload = request_json(
        OPENWEATHER_URL,
        {
            "lat": city.latitude,
            "lon": city.longitude,
            "appid": api_key,
            "units": "metric",
            "lang": "ru",
        },
        cache_path,
        use_cache=use_cache,
    )

    weather_info = payload["weather"][0]
    observed_at = datetime.fromtimestamp(payload["dt"], tz=timezone.utc).astimezone(MOSCOW_TZ)

    return {
        "city_slug": city.slug,
        "city_name": city.name,
        "observed_at": observed_at.isoformat(),
        "temperature_c": float(payload["main"]["temp"]),
        "feels_like_c": float(payload["main"]["feels_like"]),
        "humidity_pct": float(payload["main"]["humidity"]),
        "wind_speed_ms": float(payload["wind"]["speed"]),
        "wind_gust_ms": float(payload["wind"].get("gust", payload["wind"]["speed"])),
        "cloudiness_pct": float(payload.get("clouds", {}).get("all", 0.0)),
        "pressure_hpa": float(payload["main"]["pressure"]),
        "description": weather_info["description"],
        "weather_main": weather_info["main"],
        "precipitation_1h_mm": float(payload.get("rain", {}).get("1h", 0.0) + payload.get("snow", {}).get("1h", 0.0)),
    }


def fetch_historical_daily(
    city: CityConfig,
    start_date: str,
    end_date: str,
    *,
    use_cache: bool = False,
) -> pd.DataFrame:
    cache_path = OUTPUT_DATA_DIR / f"{city.slug}_historical.json"
    payload = request_json(
        OPEN_METEO_ARCHIVE_URL,
        {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": (
                "temperature_2m_mean,relative_humidity_2m_mean,"
                "wind_speed_10m_mean,wind_speed_10m_max,precipitation_sum"
            ),
            "timezone": "Europe/Moscow",
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
        },
        cache_path,
        use_cache=use_cache,
    )

    daily = payload["daily"]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(daily["time"]),
            "temperature_c": daily["temperature_2m_mean"],
            "humidity_pct": daily["relative_humidity_2m_mean"],
            "wind_speed_ms": daily["wind_speed_10m_mean"],
            "wind_speed_max_ms": daily["wind_speed_10m_max"],
            "precipitation_mm": daily["precipitation_sum"],
        }
    )

    frame["city_slug"] = city.slug
    frame["city_name"] = city.name
    frame["season"] = pd.Categorical(
        frame["date"].dt.month.map(season_from_month),
        categories=SEASON_ORDER,
        ordered=True,
    )
    frame["season_name"] = frame["season"].map(SEASON_NAMES)
    frame["year_month"] = frame["date"].dt.to_period("M").astype(str)
    return frame


def compute_seasonal_norms(history: pd.DataFrame) -> pd.DataFrame:
    grouped = history.groupby(["city_slug", "city_name", "season", "season_name"], observed=True)
    norms = grouped.agg(
        temp_mean=("temperature_c", "mean"),
        temp_std=("temperature_c", "std"),
        temp_q10=("temperature_c", lambda series: float(series.quantile(0.10))),
        temp_q25=("temperature_c", lambda series: float(series.quantile(0.25))),
        temp_q50=("temperature_c", lambda series: float(series.quantile(0.50))),
        temp_q75=("temperature_c", lambda series: float(series.quantile(0.75))),
        temp_q90=("temperature_c", lambda series: float(series.quantile(0.90))),
        humidity_mean=("humidity_pct", "mean"),
        humidity_std=("humidity_pct", "std"),
        humidity_q10=("humidity_pct", lambda series: float(series.quantile(0.10))),
        humidity_q25=("humidity_pct", lambda series: float(series.quantile(0.25))),
        humidity_q50=("humidity_pct", lambda series: float(series.quantile(0.50))),
        humidity_q75=("humidity_pct", lambda series: float(series.quantile(0.75))),
        humidity_q90=("humidity_pct", lambda series: float(series.quantile(0.90))),
        wind_mean=("wind_speed_ms", "mean"),
        wind_std=("wind_speed_ms", "std"),
        wind_q10=("wind_speed_ms", lambda series: float(series.quantile(0.10))),
        wind_q25=("wind_speed_ms", lambda series: float(series.quantile(0.25))),
        wind_q50=("wind_speed_ms", lambda series: float(series.quantile(0.50))),
        wind_q75=("wind_speed_ms", lambda series: float(series.quantile(0.75))),
        wind_q90=("wind_speed_ms", lambda series: float(series.quantile(0.90))),
        precipitation_mean=("precipitation_mm", "mean"),
    ).reset_index()

    numeric_columns = norms.select_dtypes(include=["float64", "float32", "int64", "int32"]).columns
    norms[numeric_columns] = norms[numeric_columns].round(2)
    return norms.sort_values(["city_name", "season"]).reset_index(drop=True)


def compute_monthly_trends(history: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        history.groupby(["city_slug", "city_name", "year_month"], as_index=False)
        .agg(
            temp_mean=("temperature_c", "mean"),
            humidity_mean=("humidity_pct", "mean"),
            wind_mean=("wind_speed_ms", "mean"),
            precipitation_mean=("precipitation_mm", "mean"),
        )
        .sort_values(["city_name", "year_month"])
        .reset_index(drop=True)
    )
    return monthly.round(2)


def comfort_label_from_score(score: float) -> str:
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "moderate"
    return "poor"


def anomaly_label_from_weight(weight: float) -> str:
    if weight <= 1:
        return "low"
    if weight <= 3:
        return "medium"
    if weight <= 5:
        return "high"
    return "critical"


def score_to_comfort_text(score: float) -> str:
    if score >= 80:
        return "Высокий"
    if score >= 60:
        return "Хороший"
    if score >= 40:
        return "Средний"
    return "Низкий"


def score_to_anomaly_text(score: float) -> str:
    if score >= 80:
        return "Критичная"
    if score >= 60:
        return "Сильная"
    if score >= 35:
        return "Умеренная"
    return "Слабая"


def build_fuzzy_bundle(norm_row: pd.Series) -> FuzzyBundle:
    temperature = ctrl.Antecedent(np.arange(-35, 41.1, 0.1), "temperature")
    humidity = ctrl.Antecedent(np.arange(0, 101, 1), "humidity")
    wind_speed = ctrl.Antecedent(np.arange(0, 30.1, 0.1), "wind_speed")

    temp_deviation = ctrl.Antecedent(np.arange(0, 26.1, 0.1), "temp_deviation")
    humidity_deviation = ctrl.Antecedent(np.arange(0, 51, 1), "humidity_deviation")
    wind_deviation = ctrl.Antecedent(np.arange(0, 16.1, 0.1), "wind_deviation")

    comfort = ctrl.Consequent(np.arange(0, 101, 1), "comfort")
    anomaly = ctrl.Consequent(np.arange(0, 101, 1), "anomaly")

    temperature["cold"] = fuzz.trapmf(
        temperature.universe,
        safe_points([-35, -35, norm_row["temp_q10"], norm_row["temp_q25"]], -35, 40),
    )
    temperature["normal"] = fuzz.trimf(
        temperature.universe,
        safe_points([norm_row["temp_q25"], norm_row["temp_q50"], norm_row["temp_q75"]], -35, 40),
    )
    temperature["hot"] = fuzz.trapmf(
        temperature.universe,
        safe_points([norm_row["temp_q75"], norm_row["temp_q90"], 40, 40], -35, 40),
    )

    humidity["dry"] = fuzz.trapmf(
        humidity.universe,
        safe_points([0, 0, norm_row["humidity_q10"], norm_row["humidity_q25"]], 0, 100),
    )
    humidity["normal"] = fuzz.trimf(
        humidity.universe,
        safe_points([norm_row["humidity_q25"], norm_row["humidity_q50"], norm_row["humidity_q75"]], 0, 100),
    )
    humidity["humid"] = fuzz.trapmf(
        humidity.universe,
        safe_points([norm_row["humidity_q75"], norm_row["humidity_q90"], 100, 100], 0, 100),
    )

    wind_speed["calm"] = fuzz.trapmf(
        wind_speed.universe,
        safe_points([0, 0, norm_row["wind_q10"], norm_row["wind_q50"]], 0, 30),
    )
    wind_speed["moderate"] = fuzz.trimf(
        wind_speed.universe,
        safe_points([norm_row["wind_q25"], norm_row["wind_q50"], norm_row["wind_q75"]], 0, 30),
    )
    wind_speed["strong"] = fuzz.trapmf(
        wind_speed.universe,
        safe_points([norm_row["wind_q75"], norm_row["wind_q90"], 30, 30], 0, 30),
    )

    temp_band = max(1.5, float(norm_row["temp_std"]))
    humidity_band = max(5.0, float(norm_row["humidity_std"]))
    wind_band = max(0.8, float(norm_row["wind_std"]))

    temp_deviation["small"] = fuzz.trapmf(
        temp_deviation.universe,
        safe_points([0, 0, temp_band * 0.5, temp_band], 0, 26),
    )
    temp_deviation["medium"] = fuzz.trimf(
        temp_deviation.universe,
        safe_points([temp_band * 0.5, temp_band * 1.5, temp_band * 2.5], 0, 26),
    )
    temp_deviation["large"] = fuzz.trapmf(
        temp_deviation.universe,
        safe_points([temp_band * 1.5, temp_band * 2.5, 26, 26], 0, 26),
    )

    humidity_deviation["small"] = fuzz.trapmf(
        humidity_deviation.universe,
        safe_points([0, 0, humidity_band * 0.5, humidity_band], 0, 50),
    )
    humidity_deviation["medium"] = fuzz.trimf(
        humidity_deviation.universe,
        safe_points([humidity_band * 0.5, humidity_band * 1.5, humidity_band * 2.5], 0, 50),
    )
    humidity_deviation["large"] = fuzz.trapmf(
        humidity_deviation.universe,
        safe_points([humidity_band * 1.5, humidity_band * 2.5, 50, 50], 0, 50),
    )

    wind_deviation["small"] = fuzz.trapmf(
        wind_deviation.universe,
        safe_points([0, 0, wind_band * 0.5, wind_band], 0, 16),
    )
    wind_deviation["medium"] = fuzz.trimf(
        wind_deviation.universe,
        safe_points([wind_band * 0.5, wind_band * 1.5, wind_band * 2.5], 0, 16),
    )
    wind_deviation["large"] = fuzz.trapmf(
        wind_deviation.universe,
        safe_points([wind_band * 1.5, wind_band * 2.5, 16, 16], 0, 16),
    )

    comfort["poor"] = fuzz.trapmf(comfort.universe, [0, 0, 20, 40])
    comfort["moderate"] = fuzz.trimf(comfort.universe, [30, 45, 60])
    comfort["good"] = fuzz.trimf(comfort.universe, [55, 70, 85])
    comfort["excellent"] = fuzz.trapmf(comfort.universe, [75, 90, 100, 100])

    anomaly["low"] = fuzz.trapmf(anomaly.universe, [0, 0, 15, 30])
    anomaly["medium"] = fuzz.trimf(anomaly.universe, [20, 40, 60])
    anomaly["high"] = fuzz.trimf(anomaly.universe, [50, 70, 85])
    anomaly["critical"] = fuzz.trapmf(anomaly.universe, [80, 90, 100, 100])

    comfort_penalties = {
        "temperature": {"cold": 35, "normal": 0, "hot": 30},
        "humidity": {"dry": 10, "normal": 0, "humid": 15},
        "wind": {"calm": 0, "moderate": 10, "strong": 25},
    }
    anomaly_weights = {"small": 0, "medium": 1, "large": 2}

    comfort_rules: list[ctrl.Rule] = []
    for temp_label in ("cold", "normal", "hot"):
        for humidity_label in ("dry", "normal", "humid"):
            for wind_label in ("calm", "moderate", "strong"):
                score = 100
                score -= comfort_penalties["temperature"][temp_label]
                score -= comfort_penalties["humidity"][humidity_label]
                score -= comfort_penalties["wind"][wind_label]

                if temp_label == "normal" and humidity_label == "normal" and wind_label in ("calm", "moderate"):
                    score += 5
                if temp_label == "cold" and wind_label == "strong":
                    score -= 15
                if temp_label == "hot" and humidity_label == "humid":
                    score -= 15
                if temp_label == "hot" and wind_label == "strong":
                    score -= 10

                score = clip_value(score, 0, 100)
                output_label = comfort_label_from_score(score)
                comfort_rules.append(
                    ctrl.Rule(
                        temperature[temp_label] & humidity[humidity_label] & wind_speed[wind_label],
                        comfort[output_label],
                    )
                )

    anomaly_rules: list[ctrl.Rule] = []
    for temp_label in ("small", "medium", "large"):
        for humidity_label in ("small", "medium", "large"):
            for wind_label in ("small", "medium", "large"):
                weight = (
                    2.0 * anomaly_weights[temp_label]
                    + 1.0 * anomaly_weights[humidity_label]
                    + 1.5 * anomaly_weights[wind_label]
                )
                output_label = anomaly_label_from_weight(weight)
                anomaly_rules.append(
                    ctrl.Rule(
                        temp_deviation[temp_label]
                        & humidity_deviation[humidity_label]
                        & wind_deviation[wind_label],
                        anomaly[output_label],
                    )
                )

    return FuzzyBundle(
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind_speed,
        temp_deviation=temp_deviation,
        humidity_deviation=humidity_deviation,
        wind_deviation=wind_deviation,
        comfort=comfort,
        anomaly=anomaly,
        comfort_system=ctrl.ControlSystem(comfort_rules),
        anomaly_system=ctrl.ControlSystem(anomaly_rules),
    )


def membership_degrees(variable: ctrl.Antecedent | ctrl.Consequent, value: float) -> dict[str, float]:
    lower = float(variable.universe.min())
    upper = float(variable.universe.max())
    clipped_value = clip_value(value, lower, upper)
    return {
        term_name: float(fuzz.interp_membership(variable.universe, term.mf, clipped_value))
        for term_name, term in variable.terms.items()
    }


def dominant_label(degrees: dict[str, float]) -> str:
    return max(degrees.items(), key=lambda item: item[1])[0]


def expert_adjustments(
    city: CityConfig,
    season: str,
    current: dict[str, Any],
    comfort_score: float,
    anomaly_score: float,
) -> tuple[float, float, list[str]]:
    notes: list[str] = []

    if city.slug == "kazan" and season == "winter" and current["weather_main"].lower() == "clear" and current["wind_speed_ms"] < 2:
        anomaly_score = clip_value(anomaly_score - 8, 0, 100)
        notes.append(
            "Для Казани учтён зимний микроклимат: при ясной безветренной погоде локальные перепады температуры "
            "могут быть выше средней ошибки измерения."
        )

    if city.slug == "moscow" and season == "summer" and current["temperature_c"] >= 23:
        comfort_score = clip_value(comfort_score - 5, 0, 100)
        anomaly_score = clip_value(anomaly_score + 8, 0, 100)
        notes.append(
            "Для Москвы усилен риск перегрева: в центре города летом тепловая нагрузка ощущается сильнее нормы."
        )

    if city.slug == "saint-petersburg" and max(current["wind_speed_ms"], current["wind_gust_ms"]) >= 20:
        comfort_score = clip_value(comfort_score - 10, 0, 100)
        anomaly_score = clip_value(anomaly_score + 15, 0, 100)
        notes.append(
            "Для Санкт-Петербурга сработало экспертное правило опасного ветра для прибрежных и открытых участков."
        )

    return comfort_score, anomaly_score, notes


def describe_delta(value: float, std_value: float, *, unit: str, baseline: float) -> str:
    if pd.isna(std_value):
        threshold = baseline
    else:
        threshold = max(abs(std_value) * 0.5, baseline)
    if value > threshold:
        return f"выше нормы на {value:.1f}{unit}"
    if value < -threshold:
        return f"ниже нормы на {abs(value):.1f}{unit}"
    return "близко к норме"


def deduplicate(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_recommendations(
    city: CityConfig,
    season: str,
    current: dict[str, Any],
    norm_row: pd.Series,
    comfort_score: float,
    anomaly_score: float,
    temp_delta: float,
    humidity_delta: float,
    wind_delta: float,
    dominant_terms: dict[str, str],
    expert_notes: list[str],
) -> list[str]:
    recommendations: list[str] = []

    if anomaly_score >= 70:
        recommendations.append("Погодные условия заметно отклоняются от сезонной нормы, лучше планировать выход на улицу с запасом по одежде.")
    elif anomaly_score >= 40:
        recommendations.append("Есть умеренное отклонение от сезонной нормы, поэтому одежду и активность лучше подбирать по фактической погоде.")
    else:
        recommendations.append("Текущая погода близка к сезонной климатической норме.")

    if comfort_score >= 75:
        recommendations.append("Уровень погодного комфорта высокий: стандартной сезонной одежды должно быть достаточно.")
    elif comfort_score >= 55:
        recommendations.append("Комфорт умеренный: лучше выбрать многослойную одежду и учитывать ветер.")
    else:
        recommendations.append("Комфорт понижен: стоит усилить защиту от холода, сырости или ветра.")

    temp_status = describe_delta(temp_delta, norm_row["temp_std"], unit="°C", baseline=2.0)
    humidity_status = describe_delta(humidity_delta, norm_row["humidity_std"], unit="%", baseline=5.0)
    wind_status = describe_delta(wind_delta, norm_row["wind_std"], unit=" м/с", baseline=1.0)
    recommendations.append(f"Температура {temp_status}.")
    recommendations.append(f"Влажность {humidity_status}.")
    recommendations.append(f"Скорость ветра {wind_status}.")

    if dominant_terms["humidity"] == "humid" or current["humidity_pct"] >= 80:
        recommendations.append("Высокая влажность может усиливать ощущение холода и сырости.")
    if dominant_terms["wind"] == "strong" or current["wind_speed_ms"] >= 8:
        recommendations.append("Ощутимый ветер требует ветроустойчивой верхней одежды.")
    if current["weather_main"].lower() in {"rain", "drizzle", "thunderstorm"} or current["precipitation_1h_mm"] > 0:
        recommendations.append("Желательно взять зонт или непромокаемую одежду.")
    if current["weather_main"].lower() == "snow":
        recommendations.append("Нужна тёплая одежда и обувь с хорошим сцеплением.")

    if city.slug == "kazan" and season == "winter" and current["weather_main"].lower() == "clear" and current["wind_speed_ms"] < 2:
        recommendations.append("Для Казани при тихой ясной зимней погоде возможны локальные перепады температуры в разных районах.")
    if city.slug == "moscow" and season == "summer" and current["temperature_c"] >= 23:
        recommendations.append("Для Москвы в жару лучше избегать длительной активности в плотной городской застройке.")
    if city.slug == "saint-petersburg" and max(current["wind_speed_ms"], current["wind_gust_ms"]) >= 20:
        recommendations.append("Для Санкт-Петербурга при таком ветре лучше сократить время прогулок у воды и на открытых пространствах.")

    recommendations.extend(expert_notes)
    return deduplicate(recommendations)


def analyze_city(
    city: CityConfig,
    current: dict[str, Any],
    norm_row: pd.Series,
) -> tuple[dict[str, Any], FuzzyBundle]:
    season = str(norm_row["season"])
    bundle = build_fuzzy_bundle(norm_row)

    comfort_simulation = ctrl.ControlSystemSimulation(bundle.comfort_system)
    comfort_simulation.input["temperature"] = clip_value(current["temperature_c"], -35, 40)
    comfort_simulation.input["humidity"] = clip_value(current["humidity_pct"], 0, 100)
    comfort_simulation.input["wind_speed"] = clip_value(current["wind_speed_ms"], 0, 30)
    comfort_simulation.compute()

    temp_delta = float(current["temperature_c"] - norm_row["temp_mean"])
    humidity_delta = float(current["humidity_pct"] - norm_row["humidity_mean"])
    wind_delta = float(current["wind_speed_ms"] - norm_row["wind_mean"])

    anomaly_simulation = ctrl.ControlSystemSimulation(bundle.anomaly_system)
    anomaly_simulation.input["temp_deviation"] = clip_value(abs(temp_delta), 0, 26)
    anomaly_simulation.input["humidity_deviation"] = clip_value(abs(humidity_delta), 0, 50)
    anomaly_simulation.input["wind_deviation"] = clip_value(abs(wind_delta), 0, 16)
    anomaly_simulation.compute()

    comfort_score = float(comfort_simulation.output["comfort"])
    anomaly_score = float(anomaly_simulation.output["anomaly"])

    comfort_score, anomaly_score, expert_notes = expert_adjustments(city, season, current, comfort_score, anomaly_score)

    temperature_degrees = membership_degrees(bundle.temperature, current["temperature_c"])
    humidity_degrees = membership_degrees(bundle.humidity, current["humidity_pct"])
    wind_degrees = membership_degrees(bundle.wind_speed, current["wind_speed_ms"])

    dominant_terms = {
        "temperature": dominant_label(temperature_degrees),
        "humidity": dominant_label(humidity_degrees),
        "wind": dominant_label(wind_degrees),
    }

    recommendations = build_recommendations(
        city,
        season,
        current,
        norm_row,
        comfort_score,
        anomaly_score,
        temp_delta,
        humidity_delta,
        wind_delta,
        dominant_terms,
        expert_notes,
    )

    result = {
        "city_slug": city.slug,
        "city_name": city.name,
        "season": season,
        "season_name": SEASON_NAMES[season],
        "observed_at": current["observed_at"],
        "description": current["description"],
        "weather_main": current["weather_main"],
        "temperature_c": round(current["temperature_c"], 2),
        "feels_like_c": round(current["feels_like_c"], 2),
        "humidity_pct": round(current["humidity_pct"], 2),
        "wind_speed_ms": round(current["wind_speed_ms"], 2),
        "wind_gust_ms": round(current["wind_gust_ms"], 2),
        "pressure_hpa": round(current["pressure_hpa"], 2),
        "precipitation_1h_mm": round(current["precipitation_1h_mm"], 2),
        "norm_temp_c": round(float(norm_row["temp_mean"]), 2),
        "norm_humidity_pct": round(float(norm_row["humidity_mean"]), 2),
        "norm_wind_ms": round(float(norm_row["wind_mean"]), 2),
        "temp_delta_c": round(temp_delta, 2),
        "humidity_delta_pct": round(humidity_delta, 2),
        "wind_delta_ms": round(wind_delta, 2),
        "comfort_score": round(comfort_score, 2),
        "anomaly_score": round(anomaly_score, 2),
        "comfort_label": score_to_comfort_text(comfort_score),
        "anomaly_label": score_to_anomaly_text(anomaly_score),
        "temperature_term": dominant_terms["temperature"],
        "humidity_term": dominant_terms["humidity"],
        "wind_term": dominant_terms["wind"],
        "temperature_membership": {key: round(value, 3) for key, value in temperature_degrees.items()},
        "humidity_membership": {key: round(value, 3) for key, value in humidity_degrees.items()},
        "wind_membership": {key: round(value, 3) for key, value in wind_degrees.items()},
        "recommendations": recommendations,
        "expert_note": city.expert_note,
    }
    return result, bundle


def pretty_term_name(kind: str, label: str) -> str:
    mapping = {
        "temperature": {"cold": "Холодно", "normal": "Нормально", "hot": "Жарко"},
        "humidity": {"dry": "Сухо", "normal": "Нормально", "humid": "Влажно"},
        "wind": {"calm": "Слабый", "moderate": "Умеренный", "strong": "Сильный"},
    }
    return mapping[kind][label]


def plot_membership_functions(
    city_name: str,
    season_name: str,
    result: dict[str, Any],
    bundle: FuzzyBundle,
    output_path: Path,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(f"Функции принадлежности: {city_name} ({season_name})", fontsize=14, fontweight="bold")

    inputs = [
        (
            axes[0, 0],
            bundle.temperature,
            result["temperature_c"],
            "Температура, °C",
            [("cold", "Холодно"), ("normal", "Нормально"), ("hot", "Жарко")],
        ),
        (
            axes[0, 1],
            bundle.humidity,
            result["humidity_pct"],
            "Влажность, %",
            [("dry", "Сухо"), ("normal", "Нормально"), ("humid", "Влажно")],
        ),
        (
            axes[1, 0],
            bundle.wind_speed,
            result["wind_speed_ms"],
            "Ветер, м/с",
            [("calm", "Слабый"), ("moderate", "Умеренный"), ("strong", "Сильный")],
        ),
    ]

    for axis, variable, current_value, xlabel, labels in inputs:
        for term_key, term_label in labels:
            axis.plot(variable.universe, variable[term_key].mf, label=term_label)
        axis.axvline(current_value, color="black", linestyle="--", linewidth=1.2, label=f"Текущее: {current_value:.1f}")
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Степень принадлежности")
        axis.grid(alpha=0.25)
        axis.legend(loc="best")

    output_axis = axes[1, 1]
    for term_key, term_label in [("poor", "Низкий"), ("moderate", "Средний"), ("good", "Хороший"), ("excellent", "Высокий")]:
        output_axis.plot(bundle.comfort.universe, bundle.comfort[term_key].mf, label=f"Комфорт: {term_label}")
    for term_key, term_label in [("low", "Слабая"), ("medium", "Умеренная"), ("high", "Сильная"), ("critical", "Критичная")]:
        output_axis.plot(bundle.anomaly.universe, bundle.anomaly[term_key].mf, linestyle="--", label=f"Аномалия: {term_label}")
    output_axis.axvline(result["comfort_score"], color="#1f77b4", linewidth=1.5, label=f"Комфорт = {result['comfort_score']:.1f}")
    output_axis.axvline(result["anomaly_score"], color="#d62728", linewidth=1.5, label=f"Аномалия = {result['anomaly_score']:.1f}")
    output_axis.set_xlabel("Интегральный балл")
    output_axis.set_ylabel("Степень принадлежности")
    output_axis.grid(alpha=0.25)
    output_axis.legend(loc="best", fontsize=8)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_seasonal_profiles(norms: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharex=True)
    metrics = [
        ("temp_mean", "Температура, °C"),
        ("humidity_mean", "Влажность, %"),
        ("wind_mean", "Ветер, м/с"),
    ]

    for axis, (column, ylabel) in zip(axes, metrics):
        for city_name in norms["city_name"].unique():
            city_frame = norms[norms["city_name"] == city_name].sort_values("season")
            axis.plot(city_frame["season_name"], city_frame[column], marker="o", linewidth=2, label=city_name)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25)
        axis.legend(loc="best")

    fig.suptitle("Сезонные климатические профили городов", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_monthly_temperature_trend(monthly: pd.DataFrame, output_path: Path) -> None:
    fig, axis = plt.subplots(figsize=(14, 5))
    for city_name in monthly["city_name"].unique():
        city_frame = monthly[monthly["city_name"] == city_name]
        axis.plot(city_frame["year_month"], city_frame["temp_mean"], linewidth=1.8, label=city_name)

    tick_positions = np.linspace(0, max(len(monthly["year_month"].unique()) - 1, 1), 8, dtype=int)
    unique_months = monthly["year_month"].unique()
    axis.set_xticks(tick_positions)
    axis.set_xticklabels(unique_months[tick_positions], rotation=45, ha="right")
    axis.set_ylabel("Средняя температура, °C")
    axis.set_title("Исторический тренд среднемесячной температуры (2021-2025)")
    axis.grid(alpha=0.25)
    axis.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_current_vs_norm(summary: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    categories = [
        ("temperature_c", "norm_temp_c", "Температура, °C"),
        ("humidity_pct", "norm_humidity_pct", "Влажность, %"),
        ("wind_speed_ms", "norm_wind_ms", "Ветер, м/с"),
    ]

    x = np.arange(len(summary))
    width = 0.36

    for axis, (current_column, norm_column, title) in zip(axes, categories):
        axis.bar(x - width / 2, summary[current_column], width=width, label="Текущее", color="#4e79a7")
        axis.bar(x + width / 2, summary[norm_column], width=width, label="Норма сезона", color="#f28e2b")
        axis.set_xticks(x)
        axis.set_xticklabels(summary["city_name"])
        axis.set_title(title)
        axis.grid(alpha=0.25, axis="y")
        axis.legend(loc="best")

    fig.suptitle("Сравнение текущих значений с сезонной нормой", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_architecture(output_path: Path) -> None:
    fig, axis = plt.subplots(figsize=(12, 4.5))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 5)
    axis.axis("off")

    boxes = [
        (0.4, 2.7, 2.2, 0.8, "OpenWeatherMap\nтекущая погода"),
        (0.4, 1.2, 2.2, 0.8, "Open-Meteo\nистория 2021-2025"),
        (3.2, 1.95, 2.2, 1.2, "Предобработка и\nсезонные нормы"),
        (6.0, 1.95, 2.2, 1.2, "Нечёткий вывод\nМамдани"),
        (8.8, 2.7, 2.2, 0.8, "Рекомендации и\nаномалии"),
        (8.8, 1.2, 2.2, 0.8, "CSV / JSON /\nграфики / отчёт"),
    ]

    for x, y, width, height, text in boxes:
        patch = FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.25",
            linewidth=1.4,
            edgecolor="#2f4b7c",
            facecolor="#dce6f2",
        )
        axis.add_patch(patch)
        axis.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=10)

    arrows = [
        ((2.6, 3.1), (3.2, 2.55)),
        ((2.6, 1.6), (3.2, 2.35)),
        ((5.4, 2.55), (6.0, 2.55)),
        ((8.2, 2.55), (8.8, 3.1)),
        ((8.2, 2.55), (8.8, 1.6)),
    ]

    for start, end in arrows:
        axis.add_patch(FancyArrowPatch(start, end, arrowstyle="->", mutation_scale=16, linewidth=1.4, color="#2f4b7c"))

    axis.set_title("Архитектура экспертной системы анализа погоды", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def format_float(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def make_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join([header, separator, *body])


def build_summary_display_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "Город": result["city_name"],
                "Сезон": result["season_name"],
                "Темп., °C": format_float(result["temperature_c"]),
                "Норма, °C": format_float(result["norm_temp_c"]),
                "ΔT, °C": format_float(result["temp_delta_c"]),
                "Влажн., %": format_float(result["humidity_pct"]),
                "Ветер, м/с": format_float(result["wind_speed_ms"]),
                "Комфорт": f"{result['comfort_score']:.1f} ({result['comfort_label']})",
                "Аномалия": f"{result['anomaly_score']:.1f} ({result['anomaly_label']})",
            }
        )
    return rows


def build_norms_display_rows(norms: pd.DataFrame, season: str) -> list[dict[str, Any]]:
    current_season_norms = norms[norms["season"] == season]
    rows: list[dict[str, Any]] = []
    for _, row in current_season_norms.iterrows():
        rows.append(
            {
                "Город": row["city_name"],
                "Сезон": row["season_name"],
                "Температура, °C": format_float(row["temp_mean"]),
                "Влажность, %": format_float(row["humidity_mean"]),
                "Ветер, м/с": format_float(row["wind_mean"]),
                "Осадки, мм/сутки": format_float(row["precipitation_mean"]),
            }
        )
    return rows


def analysis_paragraph(result: dict[str, Any]) -> str:
    temp_term = pretty_term_name("temperature", result["temperature_term"])
    humidity_term = pretty_term_name("humidity", result["humidity_term"])
    wind_term = pretty_term_name("wind", result["wind_term"])
    recommendations = "; ".join(result["recommendations"][:3])
    return (
        f"{result['city_name']}: текущая температура {result['temperature_c']:.1f}°C при сезонной норме "
        f"{result['norm_temp_c']:.1f}°C, влажность {result['humidity_pct']:.1f}% и ветер {result['wind_speed_ms']:.1f} м/с. "
        f"Лингвистическая интерпретация: температура — «{temp_term}», влажность — «{humidity_term}», "
        f"ветер — «{wind_term}». Интегральный комфорт = {result['comfort_score']:.1f}, аномальность = "
        f"{result['anomaly_score']:.1f}. Ключевые рекомендации: {recommendations}."
    )


def write_report_markdown(context: dict[str, Any]) -> None:
    summary_table = make_markdown_table(
        context["summary_display_rows"],
        ["Город", "Сезон", "Темп., °C", "Норма, °C", "ΔT, °C", "Влажн., %", "Ветер, м/с", "Комфорт", "Аномалия"],
    )
    norms_table = make_markdown_table(
        context["norms_display_rows"],
        ["Город", "Сезон", "Температура, °C", "Влажность, %", "Ветер, м/с", "Осадки, мм/сутки"],
    )

    lines = [
        "# Отчёт по лабораторной работе №3",
        "",
        "## Титульный лист",
        "",
        "Лабораторная работа 3: Экспертная система на основе нечеткой логики для анализа погодных условий городов России",
        "",
        "Студент: Мухаметзянов Малик",
        "Группа: ____________",
        "Преподаватель: ____________",
        f"Дата анализа: {context['generated_at_human']}",
        "",
        "## Цель работы",
        "",
        "Разработать экспертную систему нечеткого вывода на основе алгоритма Мамдани для анализа погодных условий "
        "в трех городах России (Казань, Москва, Санкт-Петербург) с использованием реальных погодных API и экспертных знаний.",
        "",
        "## Задачи",
        "",
        "1. Получить текущие погодные данные из OpenWeatherMap API.",
        "2. Получить исторические данные из Open-Meteo API за период 01.01.2021-31.12.2025.",
        "3. Рассчитать сезонные климатические нормы.",
        "4. Преобразовать числовые показатели в лингвистические переменные.",
        "5. Реализовать нечеткий вывод Мамдани с помощью `scikit-fuzzy`.",
        "6. Сравнить текущие значения с сезонными нормами и выделить аномалии.",
        "7. Сформировать рекомендации по каждому городу.",
        "8. Построить таблицы и графики для интерпретации результатов.",
        "9. Подготовить текст отчёта и `.docx`-версию.",
        "",
        "## Теоретическая часть",
        "",
        "Экспертная система в данной работе объединяет формальные данные API и экспертные климатические знания. "
        "Нечёткая логика применяется для перехода от точных измерений к понятным человеку термам вроде "
        "«холодно», «нормально», «влажно», «сильный ветер».",
        "",
        "Алгоритм Мамдани включает фаззификацию входов, применение набора правил вида "
        "«ЕСЛИ [условие], ТО [результат]», агрегацию, аккумуляцию и дефаззификацию. "
        "В работе реализованы два нечетких контура: оценка погодного комфорта и оценка степени аномальности.",
        "",
        "## Экспертные знания",
        "",
        "- Казань: умеренно-континентальный климат, зимой возможны локальные перепады температуры при тихой ясной погоде.",
        "- Москва: летом в плотной застройке тепловая нагрузка ощущается сильнее, чем на периферии города.",
        "- Санкт-Петербург: из-за морского влияния и частой смены воздушных масс ветер играет особенно важную роль.",
        "",
        "## Архитектура системы",
        "",
        "![Архитектура системы](outputs/plots/architecture.png)",
        "",
        "Система получает текущие данные из OpenWeatherMap и исторические данные из Open-Meteo, рассчитывает сезонные нормы, "
        "настраивает функции принадлежности для текущего сезона, затем выполняет нечеткий вывод Мамдани и формирует рекомендации.",
        "",
        "## Реализация",
        "",
        "- `main.py` — основной сценарий получения данных, расчёта норм, нечёткого вывода и построения графиков.",
        "- `generate_docx_report.py` — сборка готового отчёта в формате `.docx`.",
        "- `requirements.txt` — список используемых библиотек.",
        "- `outputs/data/*.csv, *.json` — вычисленные таблицы и промежуточные результаты.",
        "",
        "Для температуры, влажности и ветра функции принадлежности привязаны к сезонным квантилям, рассчитанным по историческим данным. "
        "Это позволяет учитывать различие между «нормально» для весны в Казани и, например, для лета в Санкт-Петербурге.",
        "",
        "## Сезонные нормы текущего сезона",
        "",
        norms_table,
        "",
        "## Результаты работы",
        "",
        summary_table,
        "",
        "### Графики",
        "",
        "![Сезонные профили](outputs/plots/seasonal_profiles.png)",
        "",
        "![Исторический тренд температуры](outputs/plots/historical_temperature_trend.png)",
        "",
        "![Текущее значение и норма](outputs/plots/current_vs_norms.png)",
        "",
    ]

    for membership_item in context["membership_plot_items"]:
        lines.extend(
            [
                f"![Функции принадлежности {membership_item['city_name']}]({membership_item['path']})",
                "",
            ]
        )

    lines.extend(
        [
            "## Анализ результатов",
            "",
        ]
    )

    for paragraph in context["analysis_paragraphs"]:
        lines.extend([f"- {paragraph}", ""])

    lines.extend(
        [
            "## Выводы",
            "",
            "Поставленная цель достигнута: разработана экспертная система, которая получает реальные погодные данные, "
            "сравнивает их с историческими сезонными нормами и выполняет нечеткий вывод Мамдани. "
            "Система автоматически формирует рекомендации и визуализирует результаты в виде таблиц и графиков.",
            "",
            "## Список литературы",
            "",
            "1. OpenWeather. Current weather data API. https://openweathermap.org/current",
            "2. Open-Meteo. Historical Weather API. https://open-meteo.com/en/docs/historical-weather-api",
            "3. scikit-fuzzy documentation. https://pythonhosted.org/scikit-fuzzy/",
        ]
    )

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def write_readme() -> None:
    README_FILE.write_text(
        "\n".join(
            [
                "# Лабораторная работа №3: Нечёткая экспертная система погоды",
                "",
                "В папке находятся:",
                "- `main.py` — основной сценарий лабораторной.",
                "- `generate_docx_report.py` — генерация итогового отчёта `.docx`.",
                "- `requirements.txt` — зависимости проекта.",
                "- `report.md` — сгенерированный текстовый отчёт.",
                "- `outputs/data/` — CSV и JSON с результатами анализа.",
                "- `outputs/plots/` — графики и схема архитектуры.",
                "",
                "## Быстрый запуск",
                "",
                "```bash",
                "cd lab3",
                ".venv/bin/python main.py",
                ".venv/bin/python generate_docx_report.py",
                "```",
                "",
                "## Что делает программа",
                "",
                "1. Загружает текущую погоду для Казани, Москвы и Санкт-Петербурга из OpenWeatherMap.",
                "2. Загружает исторические данные Open-Meteo за период 2021-2025.",
                "3. Вычисляет сезонные нормы и квантили.",
                "4. Строит нечеткую систему Мамдани на базе `scikit-fuzzy`.",
                "5. Определяет комфорт, аномалии и рекомендации.",
                "6. Формирует таблицы, графики, `report.md` и `lab3_report_ready.docx`.",
                "",
                "## Примечание",
                "",
                "Ключ OpenWeatherMap читается из файла `lab3/.env` или из переменной окружения `OPENWEATHER_API_KEY`.",
            ]
        ),
        encoding="utf-8",
    )


def build_context(
    results: list[dict[str, Any]],
    norms: pd.DataFrame,
    membership_plot_items: list[dict[str, str]],
    generated_at: datetime,
) -> dict[str, Any]:
    current_season = results[0]["season"]
    summary_display_rows = build_summary_display_rows(results)
    norms_display_rows = build_norms_display_rows(norms, current_season)
    analysis_paragraphs = [analysis_paragraph(result) for result in results]
    return {
        "generated_at": generated_at.isoformat(),
        "generated_at_human": generated_at.strftime("%d.%m.%Y %H:%M:%S"),
        "current_season": current_season,
        "current_season_name": SEASON_NAMES[current_season],
        "summary_display_rows": summary_display_rows,
        "norms_display_rows": norms_display_rows,
        "analysis_paragraphs": analysis_paragraphs,
        "results": results,
        "membership_plot_items": membership_plot_items,
        "sources": [
            "https://openweathermap.org/current",
            "https://open-meteo.com/en/docs/historical-weather-api",
            "https://pythonhosted.org/scikit-fuzzy/",
        ],
        "history_period": {
            "start": HISTORY_START_DATE,
            "end": HISTORY_END_DATE,
        },
    }


def save_outputs(history: pd.DataFrame, norms: pd.DataFrame, monthly: pd.DataFrame, results: list[dict[str, Any]]) -> None:
    history.to_csv(OUTPUT_DATA_DIR / "historical_daily.csv", index=False)
    norms.to_csv(OUTPUT_DATA_DIR / "seasonal_norms.csv", index=False)
    monthly.to_csv(OUTPUT_DATA_DIR / "monthly_trends.csv", index=False)
    pd.DataFrame(results).drop(columns=["recommendations", "temperature_membership", "humidity_membership", "wind_membership"]).to_csv(
        OUTPUT_DATA_DIR / "summary.csv",
        index=False,
    )
    save_json(OUTPUT_DATA_DIR / "detailed_results.json", results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Лабораторная работа 3: нечеткий анализ погоды")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Использовать сохранённые JSON/CSV при наличии.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_output_dirs()
    write_readme()

    api_key = load_openweather_api_key()
    generated_at = datetime.now(MOSCOW_TZ)

    historical_frames = [
        fetch_historical_daily(city, HISTORY_START_DATE, HISTORY_END_DATE, use_cache=args.use_cache)
        for city in CITIES
    ]
    history = pd.concat(historical_frames, ignore_index=True)
    norms = compute_seasonal_norms(history)
    monthly = compute_monthly_trends(history)

    current_measurements = [fetch_current_weather(city, api_key, use_cache=args.use_cache) for city in CITIES]

    results: list[dict[str, Any]] = []
    membership_plot_items: list[dict[str, str]] = []

    for city, current in zip(CITIES, current_measurements):
        observed_at = datetime.fromisoformat(current["observed_at"])
        season = season_from_datetime(observed_at)
        norm_row = norms[(norms["city_slug"] == city.slug) & (norms["season"] == season)].iloc[0]
        result, bundle = analyze_city(city, current, norm_row)
        results.append(result)

        plot_path = OUTPUT_PLOTS_DIR / f"membership_{city.slug}.png"
        plot_membership_functions(city.name, result["season_name"], result, bundle, plot_path)
        membership_plot_items.append(
            {
                "city_name": city.name,
                "path": str(plot_path.relative_to(ROOT)),
            }
        )

    summary = pd.DataFrame(results).sort_values("city_name").reset_index(drop=True)
    save_outputs(history, norms, monthly, results)

    plot_seasonal_profiles(norms, OUTPUT_PLOTS_DIR / "seasonal_profiles.png")
    plot_monthly_temperature_trend(monthly, OUTPUT_PLOTS_DIR / "historical_temperature_trend.png")
    plot_current_vs_norm(summary, OUTPUT_PLOTS_DIR / "current_vs_norms.png")
    plot_architecture(OUTPUT_PLOTS_DIR / "architecture.png")

    context = build_context(results, norms, membership_plot_items, generated_at)
    save_json(REPORT_CONTEXT_FILE, context)
    write_report_markdown(context)

    display_columns = [
        "city_name",
        "season_name",
        "temperature_c",
        "norm_temp_c",
        "humidity_pct",
        "wind_speed_ms",
        "comfort_score",
        "anomaly_score",
    ]
    print("\nИтоговая таблица:")
    print(summary[display_columns].to_string(index=False))
    print(f"\nОтчёт сохранён: {REPORT_FILE}")
    print(f"Контекст отчёта: {REPORT_CONTEXT_FILE}")


if __name__ == "__main__":
    main()
