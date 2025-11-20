# ML single server homework - Implementation documentation

**Student**: John Affolter
**Repository**: https://github.com/johnaffolter/lab5_mlflow

## Overview

This project implements a complete ML single server system with Airflow for orchestration, MLFlow for model tracking and registry, and FastAPI for model serving. The system demonstrates the full MLOps lifecycle: Train → Track → Register → Serve.

## System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ML Single Server                          │
│                                                                   │
│  ┌────────────────┐       ┌──────────────────┐                  │
│  │   Airflow      │       │    MLFlow        │                  │
│  │   Scheduler    │       │   Tracking       │                  │
│  │                │       │    Server        │                  │
│  │  ┌──────────┐  │       │                  │                  │
│  │  │ DAG:     │  │       │  ┌────────────┐  │                  │
│  │  │ train_   │──┼──────▶│  │ Experiment │  │                  │
│  │  │ model    │  │ train │  │  Tracking  │  │                  │
│  │  └──────────┘  │       │  └────────────┘  │                  │
│  │                │       │                  │                  │
│  │  Triggers:     │       │  ┌────────────┐  │                  │
│  │  - Manual      │       │  │   Model    │  │                  │
│  │  - Scheduled   │       │  │  Registry  │  │                  │
│  └────────────────┘       │  │            │  │                  │
│         │                 │  │ Versions:  │  │                  │
│         │                 │  │  - v1      │  │                  │
│         ▼                 │  │  - v2      │◀─┼──────┐           │
│  ┌────────────────┐       │  │  - v3...   │  │      │           │
│  │  src/train.py  │       │  └────────────┘  │      │           │
│  │                │       │                  │      │           │
│  │  - Load Iris   │       │  Storage:        │      │           │
│  │  - Train Model │       │  ./mlruns        │      │  Load     │
│  │  - Log Metrics │──────▶│  ./mlartifacts   │      │  Model    │
│  │  - Save Model  │       │                  │      │           │
│  └────────────────┘       └──────────────────┘      │           │
│                                                      │           │
│                           ┌──────────────────┐      │           │
│                           │   FastAPI        │      │           │
│                           │   Server         │      │           │
│                           │                  │      │           │
│                           │  Endpoints:      │      │           │
│                           │                  │      │           │
│                           │  POST /predict ──┼──────┘           │
│                           │  (uses loaded    │                  │
│                           │   model)         │                  │
│                           │                  │                  │
│                           │  GET  /model/    │                  │
│                           │       version    │                  │
│                           │  (view current)  │                  │
│                           │                  │                  │
│                           │  POST /model/    │                  │
│                           │       version    │                  │
│                           │  (switch ver.)   │                  │
│                           │                  │                  │
│                           │  GET  /health    │                  │
│                           └──────────────────┘                  │
│                                     ▲                            │
│                                     │                            │
│                                     │ HTTP Requests              │
└─────────────────────────────────────┼────────────────────────────┘
                                      │
                                      │
                              ┌───────┴────────┐
                              │   External     │
                              │   Clients      │
                              └────────────────┘
```

## Component details

### 1. Airflow (Orchestration)
- **Port**: 8080
- **Purpose**: Orchestrate model training workflows
- **DAG**: `train_model` - Manually triggered training pipeline
- **Location**: `dags/train_model.py`
- **Functionality**:
  - Executes training script (`src/train.py`)
  - Sets MLFlow tracking URI
  - Manages Python environment
  - Logs output for debugging

### 2. MLFlow (Model tracking & registry)
- **Port**: 5000
- **Purpose**: Track experiments and manage model registry
- **Storage**:
  - Runs: `./mlruns`
  - Artifacts: `./mlartifacts`
- **Features**:
  - Experiment tracking (parameters, metrics)
  - Model versioning
  - Model staging (Production, Staging, etc.)
  - Artifact storage
- **Access**: Web UI at http://localhost:5000

### 3. Training script
- **Location**: `src/train.py`
- **Model**: Logistic Regression on Iris dataset
- **Process**:
  1. Load Iris dataset
  2. Split data (75% train, 25% test)
  3. Train LogisticRegression model
  4. Log parameters (C, max_iter)
  5. Log metrics (accuracy)
  6. Save model to MLFlow as `iris-classifier`

### 4. FastAPI server (Model serving)
- **Port**: 8000
- **Purpose**: Serve model predictions via REST API
- **Location**: `app/server.py`

#### API endpoints

##### 1. POST /predict
Predict Iris species from measurements.

**Request**:
```json
{
  "samples": [
    {
      "sepal_length": 5.1,
      "sepal_width": 3.5,
      "petal_length": 1.4,
      "petal_width": 0.2
    }
  ]
}
```

**Response**:
```json
{
  "class_id": [0],
  "class_label": ["setosa"]
}
```

##### 2. GET /model/version
Get currently loaded model version.

**Response**:
```json
{
  "model_name": "iris-classifier",
  "version": "1",
  "model_uri": "models:/iris-classifier/1",
  "model_loaded": true
}
```

##### 3. POST /model/version
Switch to a different model version.

**Request**:
```json
{
  "version": "2"
}
```

**Response**:
```json
{
  "model_name": "iris-classifier",
  "version": "2",
  "model_uri": "models:/iris-classifier/2",
  "model_loaded": true
}
```

**Supported version formats**:
- Numeric: `"1"`, `"2"`, `"3"`
- Stage names: `"Production"`, `"Staging"`, `"Archived"`

##### 4. GET /health
Health check endpoint.

**Response**:
```json
{
  "status": "ok",
  "model_uri": "models:/iris-classifier/1",
  "model_version": "1",
  "model_loaded": true
}
```

## Implementation highlights

### Dynamic model loading
The FastAPI server maintains a global `ModelState` object that:
- Stores the currently loaded model
- Tracks the active version
- Provides `load_model(version)` method for hot-swapping models
- Handles errors gracefully (404 for invalid versions)

### Model version management
Models can be switched at runtime without restarting the server:
1. Client sends POST request to `/model/version` with desired version
2. Server loads new model from MLFlow registry
3. Subsequent `/predict` requests use the new model
4. `/model/version` GET shows current version

### Error handling
- Returns 503 if no model is loaded
- Returns 404 if requested version doesn't exist
- Validates input data with Pydantic
- Provides clear error messages

## Setup and usage

### 1. Environment setup
```bash
bash setup.sh
source .venv/bin/activate
```

### 2. Initialize Airflow
```bash
bash scripts/airflow_init.sh
```

### 3. Start all services

**Terminal 1 - Airflow Webserver**:
```bash
bash scripts/airflow_webserver.sh
```

**Terminal 2 - Airflow Scheduler**:
```bash
bash scripts/airflow_scheduler.sh
```

**Terminal 3 - MLFlow Server**:
```bash
bash scripts/mlflow_ui.sh
```

**Terminal 4 - FastAPI Server**:
```bash
bash scripts/fast_api.sh
```

### 4. Train models via Airflow
1. Go to http://localhost:8080
2. Login: admin / admin
3. Enable `train_model` DAG
4. Click "Trigger DAG" multiple times to create multiple versions

### 5. Register models in MLFlow
1. Go to http://localhost:5000
2. Navigate to "Models" → Create model "iris-classifier"
3. Register runs as versions
4. Optionally set stages (Production, Staging)

### 6. Test API
Go to http://localhost:8000/docs

**Test prediction**:
```bash
curl -X POST "http://localhost:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}
    ]
  }'
```

**Check version**:
```bash
curl http://localhost:8000/model/version
```

**Switch version**:
```bash
curl -X POST "http://localhost:8000/model/version" \
  -H "Content-Type: application/json" \
  -d '{"version": "2"}'
```

## Learning outcomes

This implementation demonstrates:

1. **Model training orchestration** - Airflow DAGs trigger training jobs
2. **Experiment tracking** - MLFlow logs parameters, metrics, and models
3. **Model registry** - Centralized versioning and staging
4. **Model serving** - REST API for real-time predictions
5. **Version management** - Runtime model switching without downtime
6. **Complete MLOps pipeline** - End-to-end automation from training to serving

## Extensions and improvements

Possible enhancements:
- Add monitoring/logging (Prometheus, Grafana)
- Implement model performance tracking
- Add A/B testing between versions
- Implement model rollback on poor performance
- Add authentication/authorization
- Deploy with Docker/Kubernetes
- Add data validation and drift detection
- Implement batch prediction endpoint
