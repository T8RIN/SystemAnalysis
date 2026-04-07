import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    appid: str
    base_url: str
    output_dir: Path
    log_file: Path
    timeout_seconds: int
    max_retries: int


def _resolve_path(base_dir: Path, raw_value: str) -> Path:
    # Поддерживаем и абсолютные, и относительные пути из config.json.
    path = Path(raw_value)
    if path.is_absolute():
        return path
    return base_dir / path


def load_config(config_path: Path) -> AppConfig:
    # Проверяем, что файл конфигурации существует.
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Загружаем JSON-конфигурацию.
    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # Проверяем обязательные поля.
    required_fields = ["appid", "base_url", "output_dir", "log_file", "timeout_seconds"]
    missing = [field for field in required_fields if field not in raw]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    # Валидируем AppID.
    appid = str(raw["appid"]).strip()
    if not appid:
        raise ValueError("Config field 'appid' is empty")

    # Приводим пути к абсолютным относительно папки проекта.
    base_dir = config_path.parent
    output_dir = _resolve_path(base_dir, str(raw["output_dir"]))
    log_file = _resolve_path(base_dir, str(raw["log_file"]))

    # Валидируем параметры сетевых запросов.
    timeout_seconds = int(raw["timeout_seconds"])
    if timeout_seconds <= 0:
        raise ValueError("Config field 'timeout_seconds' must be positive")
    max_retries = int(raw.get("max_retries", 2))
    if max_retries < 0:
        raise ValueError("Config field 'max_retries' must be 0 or higher")

    return AppConfig(
        appid=appid,
        base_url=str(raw["base_url"]),
        output_dir=output_dir,
        log_file=log_file,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
