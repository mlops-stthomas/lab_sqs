#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AIRFLOW_HOME="${AIRFLOW_HOME:-"$ROOT/.airflow"}"
export AIRFLOW__CORE__LOAD_EXAMPLES=${AIRFLOW__CORE__LOAD_EXAMPLES:-False}
export AIRFLOW__CORE__DAGS_FOLDER="${AIRFLOW__CORE__DAGS_FOLDER:-"$ROOT/dags"}"

run_cmd() {
  if command -v uv >/dev/null 2>&1; then
    uv run --env-file "$ROOT/.env" airflow scheduler
  else
    source "$ROOT/.venv/bin/activate"
    airflow scheduler
  fi
}

run_cmd
