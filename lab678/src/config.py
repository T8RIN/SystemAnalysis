from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH, override=True)


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
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    embedding_model: str
    vector_dimension: int
    lm_studio_url: str
    llm_model: str | None
    llm_timeout: int
    llm_max_tokens: int
    llm_temperature: float
    default_top_k: int


def get_config() -> AppConfig:
    load_dotenv(ENV_PATH, override=True)
    return AppConfig(
        db_name=os.getenv("DB_NAME", "rag_db"),
        db_user=os.getenv("DB_USER", "postgres"),
        db_password=os.getenv("DB_PASSWORD", "postgres"),
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=_get_int("DB_PORT", 5432),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        vector_dimension=_get_int("VECTOR_DIM", 384),
        lm_studio_url=os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1").rstrip("/"),
        llm_model=os.getenv("LLM_MODEL") or None,
        llm_timeout=_get_int("LLM_TIMEOUT", 120),
        llm_max_tokens=_get_int("LLM_MAX_TOKENS", 350),
        llm_temperature=_get_float("LLM_TEMPERATURE", 0.0),
        default_top_k=_get_int("DEFAULT_TOP_K", 3),
    )
