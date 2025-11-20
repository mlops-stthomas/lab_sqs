from fastapi import FastAPI
from lab5_mlflow.app.client_factory import build_clients
from lab5_mlflow.app.router_factory import build_mlflow_router, build_ingest_router, build_aura_router


def create_app() -> FastAPI:
    clients = build_clients()
    app = FastAPI(
        title="DataOps API",
        description="MLflow model serving + Data movement + Aura GraphQL management",
        version="1.0.0",
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "services": list(clients.keys())}

    app.include_router(build_mlflow_router(clients))
    app.include_router(build_ingest_router(clients))
    app.include_router(build_aura_router(clients))
    return app


app = create_app()

    return ModelVersionResponse(
        model_name=MODEL_NAME,
        version=model_state.version,
        model_uri=model_state.model_uri,
        model_loaded=model_state.model is not None
    )
