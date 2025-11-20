"""
Client factory for dependency injection and service locator pattern.

Provides centralized creation and management of all external service clients:
- Neo4j drivers (multi-instance support)
- Snowflake connections
- AWS services (SQS, Secrets Manager)
- Aura API clients (Import API, GraphQL API)
- MLflow tracking

Usage:
    # Create factory from environment
    factory = ClientFactory.from_env()

    # Get configured clients
    neo4j_driver = factory.get_neo4j_driver()
    snowflake_conn = factory.get_snowflake_connection()
    aura_manager = factory.get_aura_manager()

    # Use with FastAPI dependency injection
    @app.get("/restaurants")
    def get_restaurants(neo4j=Depends(factory.get_neo4j_driver)):
        # Use neo4j driver
        pass

    # Cleanup
    await factory.close_all()
"""
import os
import logging
from typing import Optional, Dict, Any, Callable
from contextlib import asynccontextmanager, contextmanager
import boto3
from neo4j import GraphDatabase, AsyncGraphDatabase, Driver, AsyncDriver

from .config_models import (
    AppConfig,
    Neo4jConfig,
    SnowflakeConfig,
    AWSConfig,
    SQSConfig,
    AuraAPIConfig,
    MLflowConfig
)

logger = logging.getLogger(__name__)


class ClientFactory:
    """
    Centralized factory for creating and managing service clients.

    Implements service locator pattern with lazy initialization,
    connection pooling, and proper cleanup.
    """

    def __init__(self, config: AppConfig):
        """
        Initialize factory with configuration.

        Args:
            config: Complete application configuration
        """
        self.config = config
        self._clients: Dict[str, Any] = {}
        self._cleanup_handlers: Dict[str, Callable] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @classmethod
    def from_env(cls, include_optional: bool = True) -> "ClientFactory":
        """
        Create factory from environment variables.

        Args:
            include_optional: If True, load optional services

        Example:
            factory = ClientFactory.from_env()
        """
        config = AppConfig.from_env(include_optional=include_optional)
        return cls(config)

    # ===================
    # Neo4j Clients
    # ===================

    def get_neo4j_driver(
        self,
        instance: str = "default",
        async_driver: bool = False
    ) -> Driver | AsyncDriver:
        """
        Get Neo4j driver for specified instance.

        Args:
            instance: Instance identifier ("default", "proper", "tray")
            async_driver: If True, return AsyncDriver instead of sync Driver

        Returns:
            Neo4j driver (sync or async)

        Example:
            # Get default instance
            driver = factory.get_neo4j_driver()

            # Get specific instance
            proper_driver = factory.get_neo4j_driver(instance="proper")

            # Get async driver
            async_driver = factory.get_neo4j_driver(async_driver=True)
        """
        cache_key = f"neo4j_{instance}_{'async' if async_driver else 'sync'}"

        if cache_key in self._clients:
            return self._clients[cache_key]

        # Get config for instance
        if instance == "default":
            neo4j_config = self.config.neo4j
        elif instance == "proper":
            if not self.config.proper_neo4j:
                raise ValueError("PROPER_NEO4J configuration not found")
            neo4j_config = self.config.proper_neo4j
        elif instance == "tray":
            if not self.config.tray_neo4j:
                raise ValueError("TRAY_NEO4J configuration not found")
            neo4j_config = self.config.tray_neo4j
        else:
            raise ValueError(f"Unknown Neo4j instance: {instance}")

        # Create driver
        if async_driver:
            driver = AsyncGraphDatabase.driver(
                neo4j_config.uri,
                auth=(neo4j_config.user, neo4j_config.password),
                **neo4j_config.to_driver_config()
            )
        else:
            driver = GraphDatabase.driver(
                neo4j_config.uri,
                auth=(neo4j_config.user, neo4j_config.password),
                **neo4j_config.to_driver_config()
            )

        # Cache and register cleanup
        self._clients[cache_key] = driver
        self._cleanup_handlers[cache_key] = driver.close

        self.logger.info(f"Created Neo4j driver for instance: {instance}")
        return driver

    @asynccontextmanager
    async def neo4j_session(self, instance: str = "default", **kwargs):
        """
        Context manager for Neo4j session.

        Example:
            async with factory.neo4j_session() as session:
                result = await session.run("MATCH (n) RETURN count(n)")
        """
        driver = self.get_neo4j_driver(instance=instance, async_driver=True)
        async with driver.session(**kwargs) as session:
            yield session

    # ===================
    # Snowflake Clients
    # ===================

    def get_snowflake_connection(self):
        """
        Get Snowflake database connection.

        Returns:
            snowflake.connector.Connection

        Example:
            conn = factory.get_snowflake_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders LIMIT 10")
        """
        if "snowflake" in self._clients:
            return self._clients["snowflake"]

        if not self.config.snowflake:
            raise ValueError("Snowflake configuration not found")

        import snowflake.connector

        conn = snowflake.connector.connect(
            **self.config.snowflake.to_connection_params()
        )

        self._clients["snowflake"] = conn
        self._cleanup_handlers["snowflake"] = conn.close

        self.logger.info(f"Created Snowflake connection: {self.config.snowflake.database}")
        return conn

    def get_snowflake_connector(self):
        """
        Get configured SnowflakeConnector instance.

        Returns:
            SnowflakeConnector with active connection

        Example:
            connector = factory.get_snowflake_connector()
            df = connector.execute_query("SELECT * FROM orders")
        """
        if "snowflake_connector" in self._clients:
            return self._clients["snowflake_connector"]

        # Import here to avoid circular dependencies
        import sys
        from pathlib import Path

        # Add lab5_mlflow to path if needed
        lab5_path = Path(__file__).parent.parent / "lab5_mlflow" / "src"
        if str(lab5_path) not in sys.path:
            sys.path.insert(0, str(lab5_path))

        from snowflake_connector import SnowflakeConnector

        connector = SnowflakeConnector()
        connector.connect()

        self._clients["snowflake_connector"] = connector
        self._cleanup_handlers["snowflake_connector"] = connector.close

        return connector

    # ===================
    # AWS Clients
    # ===================

    def get_sqs_client(self):
        """
        Get boto3 SQS client.

        Returns:
            boto3.client('sqs')

        Example:
            sqs = factory.get_sqs_client()
            response = sqs.receive_message(QueueUrl=queue_url)
        """
        if "sqs" in self._clients:
            return self._clients["sqs"]

        if not self.config.aws:
            raise ValueError("AWS configuration not found")

        client = boto3.client('sqs', **self.config.aws.to_boto3_config())

        self._clients["sqs"] = client
        # boto3 clients don't need explicit cleanup

        self.logger.info("Created SQS client")
        return client

    def get_s3_client(self):
        """Get boto3 S3 client."""
        if "s3" in self._clients:
            return self._clients["s3"]

        if not self.config.aws:
            raise ValueError("AWS configuration not found")

        client = boto3.client('s3', **self.config.aws.to_boto3_config())
        self._clients["s3"] = client

        self.logger.info("Created S3 client")
        return client

    def get_secrets_manager_client(self):
        """Get boto3 Secrets Manager client."""
        if "secretsmanager" in self._clients:
            return self._clients["secretsmanager"]

        if not self.config.aws:
            raise ValueError("AWS configuration not found")

        client = boto3.client('secretsmanager', **self.config.aws.to_boto3_config())
        self._clients["secretsmanager"] = client

        self.logger.info("Created Secrets Manager client")
        return client

    # ===================
    # Aura API Clients
    # ===================

    def get_aura_import_client(self):
        """
        Get Aura Import API client.

        Returns:
            AuraImportClient configured with OAuth 2.0

        Example:
            client = factory.get_aura_import_client()
            job = client.create_import_job(
                import_model_id="...",
                aura_credentials=...
            )
        """
        if "aura_import" in self._clients:
            return self._clients["aura_import"]

        if not self.config.aura_api:
            raise ValueError("Aura API configuration not found")

        # Import symlinked module
        from .aura_import_client import AuraImportClient

        client = AuraImportClient(
            client_id=self.config.aura_api.client_id,
            client_secret=self.config.aura_api.client_secret,
            organization_id=self.config.aura_api.organization_id,
            project_id=self.config.aura_api.project_id
        )

        self._clients["aura_import"] = client
        self.logger.info("Created Aura Import API client")
        return client

    def get_aura_graphql_client(self):
        """
        Get Aura GraphQL API management client.

        Returns:
            AuraGraphQLAPIClient for creating/managing GraphQL Data APIs

        Example:
            client = factory.get_aura_graphql_client()
            api = client.create_graphql_api(
                instance_id="...",
                name="My API",
                type_definitions="..."
            )
        """
        if "aura_graphql" in self._clients:
            return self._clients["aura_graphql"]

        if not self.config.aura_api:
            raise ValueError("Aura API configuration not found")

        from .aura_graphql_api_client import AuraGraphQLAPIClient

        client = AuraGraphQLAPIClient(
            client_id=self.config.aura_api.client_id,
            client_secret=self.config.aura_api.client_secret
        )

        self._clients["aura_graphql"] = client
        self.logger.info("Created Aura GraphQL API client")
        return client

    def get_aura_manager(self, cli_path: str = "aura-cli"):
        """
        Get unified Aura manager (CLI + Import API).

        Returns:
            AuraManager with both CLI and Import API capabilities

        Example:
            manager = factory.get_aura_manager()
            instances = manager.list_instances()
            job = manager.create_import_job(...)
        """
        if "aura_manager" in self._clients:
            return self._clients["aura_manager"]

        from .aura_manager import AuraManager

        manager = AuraManager(cli_path=cli_path)

        # Setup import client if Aura API config available
        if self.config.aura_api:
            manager.setup_import_client(
                client_id=self.config.aura_api.client_id,
                client_secret=self.config.aura_api.client_secret,
                organization_id=self.config.aura_api.organization_id,
                project_id=self.config.aura_api.project_id
            )

        self._clients["aura_manager"] = manager
        self.logger.info("Created Aura Manager")
        return manager

    # ===================
    # MLflow Clients
    # ===================

    def get_mlflow_client(self):
        """
        Get MLflow tracking client.

        Returns:
            mlflow.tracking.MlflowClient

        Example:
            client = factory.get_mlflow_client()
            experiments = client.list_experiments()
        """
        if "mlflow" in self._clients:
            return self._clients["mlflow"]

        if not self.config.mlflow:
            raise ValueError("MLflow configuration not found")

        import mlflow
        from mlflow.tracking import MlflowClient

        # Set tracking URI
        mlflow.set_tracking_uri(self.config.mlflow.tracking_uri)

        client = MlflowClient()

        self._clients["mlflow"] = client
        self.logger.info(f"Created MLflow client: {self.config.mlflow.tracking_uri}")
        return client

    # ===================
    # Multi-instance support
    # ===================

    def get_multi_neo4j_connector(self):
        """
        Get multi-instance Neo4j connector.

        Returns:
            MultiNeo4jConnector with all configured instances

        Example:
            connector = factory.get_multi_neo4j_connector()
            results = await connector.execute_on_all(
                "MATCH (n:Restaurant) RETURN count(n)"
            )
        """
        if "multi_neo4j" in self._clients:
            return self._clients["multi_neo4j"]

        from .multi_neo4j_connector import MultiNeo4jConnector

        # Build instance configs
        instances = {"default": self.config.neo4j}

        if self.config.proper_neo4j:
            instances["proper"] = self.config.proper_neo4j

        if self.config.tray_neo4j:
            instances["tray"] = self.config.tray_neo4j

        # Create drivers
        drivers = {}
        for name, config in instances.items():
            drivers[name] = GraphDatabase.driver(
                config.uri,
                auth=(config.user, config.password),
                **config.to_driver_config()
            )

        connector = MultiNeo4jConnector(drivers)

        self._clients["multi_neo4j"] = connector
        self._cleanup_handlers["multi_neo4j"] = connector.close_all

        self.logger.info(f"Created Multi-Neo4j connector with {len(drivers)} instances")
        return connector

    # ===================
    # Cleanup
    # ===================

    async def close_all(self):
        """Close all active clients and connections."""
        for name, handler in self._cleanup_handlers.items():
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
                self.logger.info(f"Closed client: {name}")
            except Exception as e:
                self.logger.error(f"Error closing {name}: {e}")

        self._clients.clear()
        self._cleanup_handlers.clear()

    def close_all_sync(self):
        """Synchronous version of close_all."""
        for name, handler in self._cleanup_handlers.items():
            try:
                handler()
                self.logger.info(f"Closed client: {name}")
            except Exception as e:
                self.logger.error(f"Error closing {name}: {e}")

        self._clients.clear()
        self._cleanup_handlers.clear()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit."""
        self.close_all_sync()

    async def __aenter__(self):
        """Async context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async cleanup on context exit."""
        await self.close_all()


# ===================
# Dependency Injection Helpers
# ===================

# Global factory instance for FastAPI dependencies
_global_factory: Optional[ClientFactory] = None


def init_global_factory(config: Optional[AppConfig] = None):
    """
    Initialize global factory for dependency injection.

    Args:
        config: Optional explicit configuration. If None, loads from environment.

    Example:
        # In your FastAPI startup
        @app.on_event("startup")
        async def startup():
            init_global_factory()

        @app.on_event("shutdown")
        async def shutdown():
            await get_factory().close_all()
    """
    global _global_factory

    if config:
        _global_factory = ClientFactory(config)
    else:
        _global_factory = ClientFactory.from_env()

    logger.info("Initialized global client factory")


def get_factory() -> ClientFactory:
    """
    Get global factory instance.

    Returns:
        Global ClientFactory

    Raises:
        RuntimeError: If factory not initialized

    Example:
        # In FastAPI route
        @app.get("/restaurants")
        def get_restaurants(factory: ClientFactory = Depends(get_factory)):
            driver = factory.get_neo4j_driver()
            # Use driver...
    """
    if _global_factory is None:
        raise RuntimeError(
            "Client factory not initialized. Call init_global_factory() first."
        )
    return _global_factory


# FastAPI dependency helpers
def get_neo4j_driver(instance: str = "default"):
    """FastAPI dependency for Neo4j driver."""
    def _get_driver():
        return get_factory().get_neo4j_driver(instance=instance)
    return _get_driver


def get_snowflake_connection():
    """FastAPI dependency for Snowflake connection."""
    return get_factory().get_snowflake_connection()


def get_aura_manager():
    """FastAPI dependency for Aura manager."""
    return get_factory().get_aura_manager()


if __name__ == "__main__":
    # Example usage
    import asyncio

    async def main():
        # Create factory from environment
        async with ClientFactory.from_env() as factory:
            # Get various clients
            neo4j_driver = factory.get_neo4j_driver()
            print(f"✓ Neo4j driver created: {neo4j_driver._uri}")

            if factory.config.aura_api:
                aura_manager = factory.get_aura_manager()
                print(f"✓ Aura manager created")

            # Use async Neo4j session
            async with factory.neo4j_session() as session:
                result = await session.run("RETURN 1 as num")
                record = await result.single()
                print(f"✓ Neo4j test query: {record['num']}")

    asyncio.run(main())
