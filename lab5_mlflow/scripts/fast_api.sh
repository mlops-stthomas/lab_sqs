#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://127.0.0.1:5000}"
export MODEL_NAME="${MODEL_NAME:-iris-classifier}"
export MODEL_STAGE="${MODEL_STAGE:-Production}"

run_cmd() {
  if command -v uv >/dev/null 2>&1; then
    uv run --env-file "$ROOT/.env" uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
  else
    source "$ROOT/.venv/bin/activate"
    uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
  fi
}

run_cmd
