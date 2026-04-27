#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v brew >/dev/null 2>&1; then
  brew services start postgresql@17 >/dev/null
  brew services start ollama >/dev/null
fi

/opt/homebrew/opt/postgresql@17/bin/psql -h localhost -d postgres -v ON_ERROR_STOP=1 \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres'; ELSE ALTER ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres'; END IF; END \$\$;" >/dev/null

if ! /opt/homebrew/opt/postgresql@17/bin/psql -h localhost -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'rag_db';" | grep -q 1; then
  /opt/homebrew/opt/postgresql@17/bin/createdb -h localhost -O postgres rag_db
fi

/opt/homebrew/opt/postgresql@17/bin/psql postgresql://postgres:postgres@localhost/rag_db -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed."
  exit 1
fi

if ! ollama list | grep -q "qwen2.5:3b"; then
  ollama pull qwen2.5:3b
fi

./start_ui.sh
