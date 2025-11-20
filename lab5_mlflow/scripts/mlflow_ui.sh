#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URI="${BACKEND_URI:-sqlite:///$ROOT/mlflow.db}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-$ROOT/mlruns}"

run_cmd() {
  if command -v uv >/dev/null 2>&1; then
    uv run --env-file "$ROOT/.env" mlflow server \
      --backend-store-uri "$BACKEND_URI" \
      --artifacts-destination "$ARTIFACT_ROOT" \
      --serve-artifacts \
      --host 0.0.0.0 --port 5000
  else
    source "$ROOT/.venv/bin/activate"
    mlflow server \
      --backend-store-uri "$BACKEND_URI" \
      --artifacts-destination "$ARTIFACT_ROOT" \
      --serve-artifacts \
      --host 0.0.0.0 --port 5000
  fi
}

run_cmd
