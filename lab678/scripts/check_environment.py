from __future__ import annotations

import importlib.util
import shutil
import socket
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    "dotenv",
    "requests",
    "psycopg2",
    "pgvector",
    "sentence_transformers",
    "streamlit",
    "pandas",
]


def check_package(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_port(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Project: {ROOT}")
    print()

    print("Python packages:")
    for package in PACKAGES:
        status = "OK" if check_package(package) else "MISSING"
        print(f"  {package}: {status}")

    print()
    print("Commands:")
    for command in ["docker", "psql"]:
        path = shutil.which(command)
        print(f"  {command}: {path or 'not found'}")

    print()
    print("Local ports:")
    print(f"  PostgreSQL localhost:5432: {'open' if check_port('localhost', 5432) else 'closed'}")
    print(f"  Ollama localhost:11434: {'open' if check_port('localhost', 11434) else 'closed'}")
    print(f"  LM Studio localhost:1234: {'open' if check_port('localhost', 1234) else 'closed'}")


if __name__ == "__main__":
    main()
