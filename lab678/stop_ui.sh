#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ "$#" -gt 0 ]; then
  PORTS=("$@")
else
  PORTS=(8501 8502 8503 8504 8505 8506 8507 8508 8509 8510)
fi

killed=0
failed=0

stop_pid() {
  local pid="$1"
  local port="$2"

  echo "Stopping Streamlit listener on port $port (PID $pid)"
  kill "$pid" 2>/dev/null || true
  killed=1

  for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "Force stopping remaining listener on port $port (PID $pid)"
  kill -9 "$pid" 2>/dev/null || true

  for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "PID $pid is still running; close it manually or rerun this script."
  failed=1
}

for port in "${PORTS[@]}"; do
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    continue
  fi

  while IFS= read -r pid; do
    if [ -z "$pid" ]; then
      continue
    fi
    stop_pid "$pid" "$port"
  done <<< "$pids"
done

if [ "$killed" -eq 0 ]; then
  echo "No Streamlit listeners found on ports: ${PORTS[*]}"
elif [ "$failed" -eq 1 ]; then
  exit 1
else
  echo "Done."
fi
