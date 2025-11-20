"""
Build FastAPI routers with injected dependencies.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import pandas as pd
import os

from lab5_mlflow.src.ingest_pipeline import IngestPipeline
from lab5_mlflow.src.aura_graphql_api_client import AuraGraphQLAPIClient, AuthProvider, AuthProviderType


def build_mlflow_router(clients: Dict[str, Any]) -> APIRouter:
    router = APIRouter(prefix="/mlflow", tags=["mlflow"])
    mlflow = clients.get("mlflow")
    if not mlflow:
        return router

    model_name = os.getenv("MODEL_NAME", "iris-classifier")

    @router.get("/health")
    def health():
        return {"tracking_uri": mlflow.get_tracking_uri(), "model_name": model_name}

    @router.post("/predict")
    def predict(payload: dict):
        version_or_stage = payload.get("version") or os.getenv("MODEL_STAGE", "Production")
        model_uri = f"models:/{model_name}/{version_or_stage}"
        try:
            model = mlflow.pyfunc.load_model(model_uri)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        df = pd.DataFrame(payload.get("rows", []))
        preds = model.predict(df)
        return {"predictions": preds.tolist()}

    return router


def build_ingest_router(clients: Dict[str, Any]) -> APIRouter:
    router = APIRouter(prefix="/ingest", tags=["ingest"])
    neo4j = clients.get("neo4j")
    snowflake = clients.get("snowflake")
    if not neo4j or not snowflake:
        return router

    pipeline = IngestPipeline(neo4j=neo4j, snowflake=snowflake)

    @router.post("/historical")
    def historical(start_date: str, end_date: str, batch_size: int = 5000):
        stats = pipeline.run_historical(start_date, end_date, batch_size)
        return {"status": "ok", "stats": stats}

    @router.post("/incremental")
    def incremental(batch_size: int = 2000):
        stats = pipeline.run_incremental(batch_size)
        return {"status": "ok", "stats": stats}

    return router


def build_aura_router(clients: Dict[str, Any]) -> APIRouter:
    router = APIRouter(prefix="/aura", tags=["aura"])

    @router.post("/graphql-api")
    def create_graphql_api(instance_id: str, name: str, type_definitions: str, cors_origins: list[str] = None):
        client = AuraGraphQLAPIClient()
        api = client.create_graphql_api(
            instance_id=instance_id,
            name=name,
            type_definitions=type_definitions,
            auth_providers=[AuthProvider(name="default", type=AuthProviderType.API_KEY)],
            cors_origins=cors_origins,
            introspection_enabled=True,
            field_suggestions_enabled=True,
        )
        return api.__dict__

    return router
