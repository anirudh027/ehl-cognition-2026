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

if [ -f "$ROOT/.env.devin" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.devin"
  set +a
fi

"$ROOT/.venv/bin/uvicorn" backend.app.main:app \
  --app-dir "$ROOT" \
  --host 127.0.0.1 \
  --port 8000 \
  --reload &
API_PID=$!

API_READY=false
for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null; then
    API_READY=true
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    wait "$API_PID"
  fi
  sleep 1
done

if [ "$API_READY" != true ]; then
  echo "FastAPI did not become ready on http://127.0.0.1:8000" >&2
  exit 1
fi

npm --prefix "$ROOT/frontend" run dev
