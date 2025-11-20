"""
Centralized factory to build external service clients from environment/config.

Usage:
    from app.client_factory import build_clients
    clients = build_clients()
    neo4j = clients["neo4j"]
    snowflake = clients["snowflake"]
    mlflow_client = clients["mlflow"]
"""
import os
import mlflow
from typing import Dict, Any

from lab5_mlflow.src.neo4j_connector import Neo4jConnector
from lab5_mlflow.src.snowflake_connector import SnowflakeConnector


def build_clients() -> Dict[str, Any]:
    """Instantiate clients based on environment variables."""
    clients: Dict[str, Any] = {}

    # Neo4j
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if neo4j_uri and neo4j_password:
        neo4j_conn = Neo4jConnector()
        neo4j_conn.connect()
        clients["neo4j"] = neo4j_conn

    # Snowflake
    if os.getenv("SNOWFLAKE_ACCOUNT"):
        clients["snowflake"] = SnowflakeConnector()

    # MLflow
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
        clients["mlflow"] = mlflow

    return clients
