#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PID=""

cleanup() {
  if [ -n "$API_PID" ]; then
    kill "$API_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

"$ROOT/.venv/bin/uvicorn" backend.app.main:app \
  --app-dir "$ROOT" \
  --host 127.0.0.1 \
  --port 8000 \
  --reload &
API_PID=$!

npm --prefix "$ROOT/frontend" run dev
