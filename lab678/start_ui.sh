#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/streamlit" ]; then
  echo "Streamlit is missing. Run ./setup.sh first."
  exit 1
fi

./.venv/bin/streamlit run app.py
