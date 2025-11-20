# -------- Python --------
PY := python3.11

# -------- Venvs --------
APP_VENV := app_venv
AF_VENV  := airflow_venv

APP_PY  := $(APP_VENV)/bin/python
APP_PIP := $(APP_VENV)/bin/pip
AF_PY   := $(AF_VENV)/bin/python
AF_PIP  := $(AF_VENV)/bin/pip
AF_BIN  := $(AF_VENV)/bin/airflow

# -------- Paths --------
ABS_DB := sqlite:////$(shell pwd)/mlflow.db
ABS_AR := file://$(shell pwd)/mlruns

# -------- Airflow env (point UI/scheduler at your repo) --------
AF_ENV = AIRFLOW_HOME=$$(pwd)/.airflow \
         AIRFLOW__CORE__DAGS_FOLDER=$$(pwd)/dags \
         AIRFLOW__WEBSERVER__WEB_SERVER_HOST=0.0.0.0 \
         PYTHONPATH=$$(pwd) \
         PATH=$$(pwd)/airflow_venv/bin:$$PATH

# ===== Bootstrap targets =====
bootstrap-mlflow:
	rm -rf $(APP_VENV)
	$(PY) -m venv $(APP_VENV)
	$(APP_PY) -m pip install --upgrade pip wheel
	$(APP_PIP) install -r requirements-mlflow.txt

bootstrap-airflow:
	rm -rf $(AF_VENV)
	$(PY) -m venv $(AF_VENV)
	$(AF_PY) -m pip install --upgrade pip wheel
	$(AF_PIP) install -r requirements-airflow.txt

# (Optional) OS deps on RHEL/Amazon Linux; run this once manually if needed
install-os-deps:
	sudo dnf -y install python3.11 python3.11-devel gcc

bootstrap: bootstrap-mlflow bootstrap-airflow

# ===== MLflow UI =====
mlflow-ui:
	MLFLOW_TRACKING_URI=$(ABS_DB) \
	MLFLOW_REGISTRY_URI=$(ABS_DB) \
	$(APP_PY) -m mlflow ui \
	  --backend-store-uri $(ABS_DB) \
	  --default-artifact-root ./mlruns \
	  --host 0.0.0.0 --port 5001

# ===== FastAPI (optional) =====
api:
	$(APP_PY) -m uvicorn service.app:app --host 0.0.0.0 --port 8000 --reload

AF_BIN := $(AF_VENV)/bin/airflow

airflow-init:
	$(AF_ENV) $(AF_BIN) db init && \
	$(AF_ENV) $(AF_BIN) users create \
	  --username admin --firstname admin --lastname user \
	  --role Admin --email admin@example.com --password admin || true

airflow-webserver:
	$(AF_ENV) $(AF_BIN) webserver --port 8081

airflow-scheduler:
	$(AF_ENV) $(AF_BIN) scheduler

# ===== Debug helpers =====
airflow-list:
	$(AF_ENV) $(AF_PY) -m airflow dags list -v

airflow-import-errors:
	$(AF_ENV) $(AF_PY) -m airflow dags list-import-errors

airflow-conf:
	AIRFLOW_HOME=$$(pwd)/.airflow $(AF_PY) -m airflow config get-value core dags_folder

airflow-setvars:
	$(AF_ENV) $(AF_PY) -m airflow variables set APP_PY "$$(pwd)/app_venv/bin/python"
	$(AF_ENV) $(AF_PY) -m airflow variables set REPO_DIR "$$(pwd)"
	$(AF_ENV) $(AF_PY) -m airflow variables set ART_DIR  "$$(pwd)/.airflow/artifacts"
	$(AF_ENV) $(AF_PY) -m airflow variables set MLFLOW_TRACKING_URI "$(ABS_DB)"
	$(AF_ENV) $(AF_PY) -m airflow variables set MLFLOW_REGISTRY_URI "$(ABS_DB)"
	$(AF_ENV) $(AF_PY) -m airflow variables set MLFLOW_ARTIFACT_URI "$(ABS_AR)"
	$(AF_ENV) $(AF_PY) -m airflow variables set SERVICE_RELOAD_URL "http://0.0.0.0:8000/reload"
