#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Virtual environment is missing. Run ./setup.sh first."
  exit 1
fi

./.venv/bin/python rag_postgres.py "$@"
