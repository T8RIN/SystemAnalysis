from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return float(raw_value)


@dataclass(frozen=True)
class AppConfig:
    db_name: str = os.getenv("DB_NAME", "rag_db")
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "postgres")
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = _get_int("DB_PORT", 5432)
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    vector_dimension: int = _get_int("VECTOR_DIM", 384)
    lm_studio_url: str = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1").rstrip("/")
    llm_model: str | None = os.getenv("LLM_MODEL") or None
    llm_timeout: int = _get_int("LLM_TIMEOUT", 120)
    llm_max_tokens: int = _get_int("LLM_MAX_TOKENS", 350)
    llm_temperature: float = _get_float("LLM_TEMPERATURE", 0.0)
    default_top_k: int = _get_int("DEFAULT_TOP_K", 3)


def get_config() -> AppConfig:
    return AppConfig()
