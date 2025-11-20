"""
FastAPI router factory for composable, dependency-injected API design.

Creates domain-specific routers with injected service clients:
- /mlflow - Model serving with MLflow
- /ingest - Snowflake→Neo4j data pipelines
- /aura - Aura GraphQL API management and import jobs
- /graph - Neo4j graph operations
- /health - Health checks and configuration

Usage:
    from fastapi import FastAPI
    from .router_factory import RouterFactory
    from .client_factory import ClientFactory

    factory = ClientFactory.from_env()
    router_factory = RouterFactory(client_factory=factory)

    app = FastAPI(title="Restaurant Analytics API")
    app.include_router(router_factory.create_health_router())
    app.include_router(router_factory.create_mlflow_router())
    app.include_router(router_factory.create_ingest_router())
    app.include_router(router_factory.create_aura_router())
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
import mlflow
from mlflow.pyfunc import PyFuncModel

from .client_factory import ClientFactory

logger = logging.getLogger(__name__)


# ===================
# Request/Response Models
# ===================

class PredictRequest(BaseModel):
    """Request for model prediction."""
    data: list[Dict[str, Any]]
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_stage: Optional[str] = "Production"


class PredictResponse(BaseModel):
    """Response from model prediction."""
    predictions: list[Any]
    model_name: str
    model_version: str
    model_stage: str
    timestamp: str


class ModelLoadRequest(BaseModel):
    """Request to load specific model version."""
    model_name: str
    version: Optional[str] = None
    stage: Optional[str] = "Production"


class IngestRequest(BaseModel):
    """Request to trigger data ingestion."""
    mode: str = "incremental"  # "incremental" or "historical"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    batch_size: int = 2000
    target_instance: str = "default"


class IngestResponse(BaseModel):
    """Response from ingestion job."""
    job_id: str
    mode: str
    status: str
    nodes_created: int = 0
    relationships_created: int = 0
    duration_seconds: float
    timestamp: str


class CreateGraphQLAPIRequest(BaseModel):
    """Request to create Aura GraphQL Data API."""
    instance_id: str
    name: str
    schema_file: str = "schemas/multi_tenant_restaurant_schema.graphql"
    auth0_domain: Optional[str] = None
    cors_origins: list[str] = ["*"]
    introspection_enabled: bool = False


class CreateImportJobRequest(BaseModel):
    """Request to create Aura import job."""
    import_model_id: str
    instance_id: str
    wait_for_completion: bool = False


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    services: Dict[str, str]


# ===================
# Router Factory
# ===================

class RouterFactory:
    """
    Factory for creating FastAPI routers with dependency injection.

    All routers receive configured service clients through the factory.
    """

    def __init__(self, client_factory: ClientFactory):
        """
        Initialize router factory.

        Args:
            client_factory: Configured client factory for all services
        """
        self.factory = client_factory
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # In-memory model cache (use Redis in production)
        self._loaded_models: Dict[str, PyFuncModel] = {}

    # ===================
    # Health & Config Router
    # ===================

    def create_health_router(self) -> APIRouter:
        """
        Create health check router.

        Endpoints:
            GET /health - Overall health status
            GET /health/neo4j - Neo4j connectivity
            GET /health/snowflake - Snowflake connectivity
            GET /config - Current configuration
        """
        router = APIRouter(prefix="/health", tags=["health"])

        @router.get("/", response_model=HealthResponse)
        async def health_check():
            """Overall health status."""
            services = {}

            # Check Neo4j
            try:
                driver = self.factory.get_neo4j_driver()
                driver.verify_connectivity()
                services["neo4j"] = "healthy"
            except Exception as e:
                services["neo4j"] = f"unhealthy: {str(e)}"

            # Check Snowflake if configured
            if self.factory.config.snowflake:
                try:
                    conn = self.factory.get_snowflake_connection()
                    services["snowflake"] = "healthy"
                except Exception as e:
                    services["snowflake"] = f"unhealthy: {str(e)}"

            # Check MLflow if configured
            if self.factory.config.mlflow:
                try:
                    client = self.factory.get_mlflow_client()
                    experiments = client.search_experiments()
                    services["mlflow"] = "healthy"
                except Exception as e:
                    services["mlflow"] = f"unhealthy: {str(e)}"

            # Overall status
            all_healthy = all(s == "healthy" for s in services.values())
            status = "healthy" if all_healthy else "degraded"

            return HealthResponse(
                status=status,
                timestamp=datetime.now().isoformat(),
                services=services
            )

        @router.get("/neo4j")
        async def neo4j_health(instance: str = "default"):
            """Check Neo4j connectivity for specific instance."""
            try:
                driver = self.factory.get_neo4j_driver(instance=instance)
                driver.verify_connectivity()
                return {"status": "healthy", "instance": instance}
            except Exception as e:
                raise HTTPException(status_code=503, detail=str(e))

        @router.get("/snowflake")
        async def snowflake_health():
            """Check Snowflake connectivity."""
            try:
                conn = self.factory.get_snowflake_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return {"status": "healthy"}
            except Exception as e:
                raise HTTPException(status_code=503, detail=str(e))

        return router

    # ===================
    # MLflow Serving Router
    # ===================

    def create_mlflow_router(self) -> APIRouter:
        """
        Create MLflow model serving router.

        Endpoints:
            POST /mlflow/predict - Run prediction
            POST /mlflow/model/load - Load specific model version
            GET /mlflow/model/info - Get loaded model info
            GET /mlflow/models - List available models
        """
        router = APIRouter(prefix="/mlflow", tags=["mlflow"])

        @router.post("/predict", response_model=PredictResponse)
        async def predict(request: PredictRequest):
            """
            Run prediction using loaded MLflow model.

            Example:
                POST /mlflow/predict
                {
                    "data": [
                        {"sepal_length": 5.1, "sepal_width": 3.5, ...},
                        {"sepal_length": 6.2, "sepal_width": 2.9, ...}
                    ],
                    "model_stage": "Production"
                }
            """
            model_key = f"{request.model_name or 'default'}:{request.model_stage}"

            # Load model if not cached
            if model_key not in self._loaded_models:
                model_name = request.model_name or os.getenv("MODEL_NAME", "iris-classifier")

                if request.model_version:
                    model_uri = f"models:/{model_name}/{request.model_version}"
                else:
                    model_uri = f"models:/{model_name}/{request.model_stage}"

                self._loaded_models[model_key] = mlflow.pyfunc.load_model(model_uri)

            model = self._loaded_models[model_key]

            # Run prediction
            import pandas as pd
            df = pd.DataFrame(request.data)
            predictions = model.predict(df)

            return PredictResponse(
                predictions=predictions.tolist(),
                model_name=request.model_name or "default",
                model_version=request.model_version or "latest",
                model_stage=request.model_stage,
                timestamp=datetime.now().isoformat()
            )

        @router.post("/model/load")
        async def load_model(request: ModelLoadRequest):
            """Load specific model version into memory."""
            if request.version:
                model_uri = f"models:/{request.model_name}/{request.version}"
            else:
                model_uri = f"models:/{request.model_name}/{request.stage}"

            model = mlflow.pyfunc.load_model(model_uri)
            model_key = f"{request.model_name}:{request.stage}"
            self._loaded_models[model_key] = model

            return {
                "message": "Model loaded successfully",
                "model_uri": model_uri,
                "model_key": model_key
            }

        @router.get("/model/info")
        async def model_info():
            """Get information about loaded models."""
            return {
                "loaded_models": list(self._loaded_models.keys()),
                "count": len(self._loaded_models)
            }

        @router.get("/models")
        async def list_models():
            """List all registered models."""
            client = self.factory.get_mlflow_client()
            models = client.search_registered_models()

            return {
                "models": [
                    {
                        "name": m.name,
                        "latest_versions": [
                            {
                                "version": v.version,
                                "stage": v.current_stage,
                                "run_id": v.run_id
                            }
                            for v in m.latest_versions
                        ]
                    }
                    for m in models
                ]
            }

        return router

    # ===================
    # Data Ingestion Router
    # ===================

    def create_ingest_router(self) -> APIRouter:
        """
        Create data ingestion router (Snowflake→Neo4j).

        Endpoints:
            POST /ingest/run - Trigger ingestion job
            GET /ingest/status/{job_id} - Check job status
            GET /ingest/history - List recent jobs
        """
        router = APIRouter(prefix="/ingest", tags=["ingestion"])

        # In-memory job tracker (use database in production)
        self._ingest_jobs: Dict[str, Dict] = {}

        @router.post("/run", response_model=IngestResponse)
        async def run_ingestion(
            request: IngestRequest,
            background_tasks: BackgroundTasks
        ):
            """
            Trigger Snowflake→Neo4j data ingestion.

            Modes:
                - incremental: Hourly watermark-based upsert
                - historical: Date-ranged batch import

            Example:
                POST /ingest/run
                {
                    "mode": "incremental",
                    "target_instance": "default"
                }
            """
            import uuid
            job_id = str(uuid.uuid4())

            # Create job record
            job = {
                "job_id": job_id,
                "mode": request.mode,
                "status": "running",
                "start_time": datetime.now(),
                "target_instance": request.target_instance
            }
            self._ingest_jobs[job_id] = job

            # Run in background
            if request.mode == "incremental":
                background_tasks.add_task(
                    self._run_incremental_ingest,
                    job_id,
                    request
                )
            elif request.mode == "historical":
                background_tasks.add_task(
                    self._run_historical_ingest,
                    job_id,
                    request
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid mode: {request.mode}"
                )

            return IngestResponse(
                job_id=job_id,
                mode=request.mode,
                status="running",
                duration_seconds=0.0,
                timestamp=datetime.now().isoformat()
            )

        @router.get("/status/{job_id}")
        async def job_status(job_id: str):
            """Get ingestion job status."""
            if job_id not in self._ingest_jobs:
                raise HTTPException(status_code=404, detail="Job not found")

            return self._ingest_jobs[job_id]

        @router.get("/history")
        async def job_history(limit: int = 10):
            """Get recent ingestion jobs."""
            jobs = sorted(
                self._ingest_jobs.values(),
                key=lambda x: x["start_time"],
                reverse=True
            )
            return {"jobs": jobs[:limit]}

        return router

    async def _run_incremental_ingest(self, job_id: str, request: IngestRequest):
        """Execute incremental ingestion (background task)."""
        try:
            from .pipeline_factory import create_incremental_pipeline

            pipeline = create_incremental_pipeline(
                snowflake_conn=self.factory.get_snowflake_connection(),
                neo4j_driver=self.factory.get_neo4j_driver(instance=request.target_instance),
                batch_size=request.batch_size
            )

            result = await pipeline.run()

            self._ingest_jobs[job_id].update({
                "status": "completed",
                "nodes_created": result.get("nodes_created", 0),
                "relationships_created": result.get("relationships_created", 0),
                "end_time": datetime.now(),
                "duration_seconds": (datetime.now() - self._ingest_jobs[job_id]["start_time"]).total_seconds()
            })

        except Exception as e:
            self.logger.error(f"Incremental ingest failed: {e}")
            self._ingest_jobs[job_id].update({
                "status": "failed",
                "error": str(e),
                "end_time": datetime.now()
            })

    async def _run_historical_ingest(self, job_id: str, request: IngestRequest):
        """Execute historical ingestion (background task)."""
        try:
            from .pipeline_factory import create_historical_pipeline

            pipeline = create_historical_pipeline(
                snowflake_conn=self.factory.get_snowflake_connection(),
                neo4j_driver=self.factory.get_neo4j_driver(instance=request.target_instance),
                start_date=request.start_date,
                end_date=request.end_date,
                batch_size=request.batch_size
            )

            result = await pipeline.run()

            self._ingest_jobs[job_id].update({
                "status": "completed",
                "nodes_created": result.get("nodes_created", 0),
                "relationships_created": result.get("relationships_created", 0),
                "end_time": datetime.now(),
                "duration_seconds": (datetime.now() - self._ingest_jobs[job_id]["start_time"]).total_seconds()
            })

        except Exception as e:
            self.logger.error(f"Historical ingest failed: {e}")
            self._ingest_jobs[job_id].update({
                "status": "failed",
                "error": str(e),
                "end_time": datetime.now()
            })

    # ===================
    # Aura Management Router
    # ===================

    def create_aura_router(self) -> APIRouter:
        """
        Create Aura API management router.

        Endpoints:
            POST /aura/graphql-api - Create GraphQL Data API
            GET /aura/instances - List Aura instances
            POST /aura/import-job - Trigger import job
            GET /aura/import-job/{job_id} - Check import job status
        """
        router = APIRouter(prefix="/aura", tags=["aura"])

        @router.post("/graphql-api")
        async def create_graphql_api(request: CreateGraphQLAPIRequest):
            """
            Create new GraphQL Data API on Aura instance.

            Example:
                POST /aura/graphql-api
                {
                    "instance_id": "705c1e42",
                    "name": "Multi-Tenant Restaurant API",
                    "auth0_domain": "your-tenant.auth0.com",
                    "cors_origins": ["https://app.example.com"]
                }
            """
            client = self.factory.get_aura_graphql_client()

            # Load schema file
            from pathlib import Path
            from .aura_graphql_api_client import load_type_definitions, AuthProvider, AuthProviderType

            schema_path = Path(__file__).parent.parent / request.schema_file
            type_definitions = load_type_definitions(str(schema_path))

            # Configure auth providers
            auth_providers = []
            if request.auth0_domain:
                auth_providers.append(AuthProvider(
                    name="Auth0 JWKS",
                    type=AuthProviderType.JWKS,
                    url=f"https://{request.auth0_domain}/.well-known/jwks.json"
                ))
            auth_providers.append(AuthProvider(
                name="Admin API Key",
                type=AuthProviderType.API_KEY
            ))

            # Create API
            api = client.create_graphql_api(
                instance_id=request.instance_id,
                name=request.name,
                type_definitions=type_definitions,
                auth_providers=auth_providers,
                cors_origins=request.cors_origins,
                introspection_enabled=request.introspection_enabled
            )

            return {
                "api_id": api.id,
                "endpoint": api.endpoint,
                "api_key": api.api_key,
                "message": "GraphQL API created successfully. Save the API key securely!"
            }

        @router.get("/instances")
        async def list_instances():
            """List all Aura instances."""
            manager = self.factory.get_aura_manager()
            instances = manager.list_instances()
            return {"instances": instances}

        @router.post("/import-job")
        async def create_import_job(request: CreateImportJobRequest):
            """
            Trigger Aura import job.

            Example:
                POST /aura/import-job
                {
                    "import_model_id": "e4cd23ef-c4ec-4e27-8d5d-0e890f496388",
                    "instance_id": "705c1e42",
                    "wait_for_completion": false
                }
            """
            manager = self.factory.get_aura_manager()

            job = manager.create_import_job(
                import_model_id=request.import_model_id,
                db_id=request.instance_id
            )

            if request.wait_for_completion:
                final_job = manager.wait_for_job_completion(
                    job_id=job.id,
                    timeout_seconds=3600
                )
                return {
                    "job_id": final_job.id,
                    "status": final_job.state,
                    "completed": True
                }

            return {
                "job_id": job.id,
                "status": job.state,
                "completed": False
            }

        @router.get("/import-job/{job_id}")
        async def import_job_status(job_id: str):
            """Check Aura import job status."""
            manager = self.factory.get_aura_manager()
            job = manager.get_import_job_status(job_id=job_id)

            return {
                "job_id": job.id,
                "status": job.state,
                "import_type": job.import_type,
                "data_source": job.data_source_name
            }

        return router

    # ===================
    # Graph Operations Router
    # ===================

    def create_graph_router(self) -> APIRouter:
        """
        Create graph operations router.

        Endpoints:
            POST /graph/query - Execute Cypher query
            GET /graph/schema - Get database schema
            GET /graph/stats - Get database statistics
        """
        router = APIRouter(prefix="/graph", tags=["graph"])

        @router.post("/query")
        async def execute_query(
            cypher: str,
            parameters: Dict[str, Any] = {},
            instance: str = "default"
        ):
            """
            Execute Cypher query on Neo4j instance.

            Example:
                POST /graph/query
                {
                    "cypher": "MATCH (r:Restaurant) RETURN count(r) as total",
                    "parameters": {},
                    "instance": "default"
                }
            """
            driver = self.factory.get_neo4j_driver(instance=instance)

            with driver.session() as session:
                result = session.run(cypher, parameters)
                records = [dict(record) for record in result]

            return {
                "records": records,
                "count": len(records)
            }

        @router.get("/schema")
        async def get_schema(instance: str = "default"):
            """Get Neo4j database schema."""
            driver = self.factory.get_neo4j_driver(instance=instance)

            with driver.session() as session:
                # Get node labels
                labels_result = session.run("CALL db.labels()")
                labels = [r["label"] for r in labels_result]

                # Get relationship types
                rels_result = session.run("CALL db.relationshipTypes()")
                rel_types = [r["relationshipType"] for r in rels_result]

                # Get constraints
                constraints_result = session.run("SHOW CONSTRAINTS")
                constraints = [dict(r) for r in constraints_result]

            return {
                "labels": labels,
                "relationship_types": rel_types,
                "constraints": constraints
            }

        @router.get("/stats")
        async def get_stats(instance: str = "default"):
            """Get database statistics."""
            driver = self.factory.get_neo4j_driver(instance=instance)

            with driver.session() as session:
                # Node counts by label
                labels_result = session.run("CALL db.labels()")
                labels = [r["label"] for r in labels_result]

                node_counts = {}
                for label in labels:
                    count_result = session.run(
                        f"MATCH (n:{label}) RETURN count(n) as count"
                    )
                    node_counts[label] = count_result.single()["count"]

                # Relationship counts by type
                rels_result = session.run("CALL db.relationshipTypes()")
                rel_types = [r["relationshipType"] for r in rels_result]

                rel_counts = {}
                for rel_type in rel_types:
                    count_result = session.run(
                        f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count"
                    )
                    rel_counts[rel_type] = count_result.single()["count"]

            return {
                "node_counts": node_counts,
                "relationship_counts": rel_counts,
                "total_nodes": sum(node_counts.values()),
                "total_relationships": sum(rel_counts.values())
            }

        return router


if __name__ == "__main__":
    # Example usage
    from fastapi import FastAPI

    factory = ClientFactory.from_env()
    router_factory = RouterFactory(client_factory=factory)

    app = FastAPI(title="Restaurant Analytics API", version="1.0.0")

    # Include all routers
    app.include_router(router_factory.create_health_router())
    app.include_router(router_factory.create_mlflow_router())
    app.include_router(router_factory.create_ingest_router())
    app.include_router(router_factory.create_aura_router())
    app.include_router(router_factory.create_graph_router())

    print("✓ API routers created successfully")
    print("  - /health")
    print("  - /mlflow")
    print("  - /ingest")
    print("  - /aura")
    print("  - /graph")
