"""
Type-safe configuration models using Pydantic.

Provides validated configuration dataclasses for all external services:
- Neo4j (Aura instances)
- Snowflake
- AWS (SQS, Secrets Manager)
- Aura API
- MLflow

Usage:
    config = Neo4jConfig.from_env()
    driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
"""
import os
from typing import Optional, Literal
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Neo4jConfig:
    """Neo4j database configuration with validation."""
    uri: str
    user: str
    password: str
    database: str = "neo4j"
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: int = 60

    @classmethod
    def from_env(cls, prefix: str = "NEO4J") -> "Neo4jConfig":
        """
        Load Neo4j configuration from environment variables.

        Args:
            prefix: Environment variable prefix (default: NEO4J)
                    Use PROPER_NEO4J, TRAY_NEO4J for multi-instance setups

        Example:
            # Load default instance
            config = Neo4jConfig.from_env()

            # Load specific instance
            proper_config = Neo4jConfig.from_env(prefix="PROPER_NEO4J")
        """
        uri = os.getenv(f"{prefix}_URI")
        user = os.getenv(f"{prefix}_USERNAME", os.getenv(f"{prefix}_USER", "neo4j"))
        password = os.getenv(f"{prefix}_PASSWORD")
        database = os.getenv(f"{prefix}_DATABASE", "neo4j")

        if not uri or not password:
            raise ValueError(f"Missing required {prefix} configuration: URI={uri}, PASSWORD={'***' if password else None}")

        return cls(
            uri=uri,
            user=user,
            password=password,
            database=database
        )

    def to_driver_config(self) -> dict:
        """Convert to neo4j.GraphDatabase.driver() config."""
        return {
            "max_connection_lifetime": self.max_connection_lifetime,
            "max_connection_pool_size": self.max_connection_pool_size,
            "connection_acquisition_timeout": self.connection_acquisition_timeout
        }


@dataclass
class SnowflakeConfig:
    """Snowflake data warehouse configuration."""
    account: str
    user: str
    password: str
    warehouse: str
    database: str
    schema: str
    role: str = "SYSADMIN"
    authenticator: str = "snowflake"

    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        """Load Snowflake configuration from environment variables."""
        account = os.getenv("SNOWFLAKE_ACCOUNT")
        user = os.getenv("SNOWFLAKE_USER")
        password = os.getenv("SNOWFLAKE_PASSWORD")
        warehouse = os.getenv("SNOWFLAKE_WAREHOUSE")
        database = os.getenv("SNOWFLAKE_DATABASE")
        schema = os.getenv("SNOWFLAKE_SCHEMA")
        role = os.getenv("SNOWFLAKE_ROLE", "SYSADMIN")

        if not all([account, user, password, warehouse, database, schema]):
            raise ValueError("Missing required Snowflake configuration")

        return cls(
            account=account,
            user=user,
            password=password,
            warehouse=warehouse,
            database=database,
            schema=schema,
            role=role
        )

    def to_connection_params(self) -> dict:
        """Convert to snowflake.connector.connect() params."""
        return {
            "account": self.account,
            "user": self.user,
            "password": self.password,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
            "role": self.role,
            "authenticator": self.authenticator
        }


@dataclass
class AWSConfig:
    """AWS services configuration (SQS, Secrets Manager, etc.)."""
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-2"

    @classmethod
    def from_env(cls) -> "AWSConfig":
        """Load AWS configuration from environment variables."""
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        region = os.getenv("AWS_REGION", "us-east-2")

        if not access_key or not secret_key:
            raise ValueError("Missing required AWS credentials")

        return cls(
            access_key_id=access_key,
            secret_access_key=secret_key,
            region=region
        )

    def to_boto3_config(self) -> dict:
        """Convert to boto3.client() config."""
        return {
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "region_name": self.region
        }


@dataclass
class SQSConfig:
    """SQS queue configuration."""
    queue_url: str
    dlq_url: Optional[str] = None
    max_messages: int = 10
    visibility_timeout: int = 30
    wait_time: int = 20

    @classmethod
    def from_env(cls) -> "SQSConfig":
        """Load SQS configuration from environment variables."""
        queue_url = os.getenv("QUEUE_URL")
        dlq_url = os.getenv("DLQ_URL")
        max_messages = int(os.getenv("MAX_MESSAGES", "10"))
        visibility_timeout = int(os.getenv("VISIBILITY_TIMEOUT", "30"))
        wait_time = int(os.getenv("WAIT_TIME", "20"))

        if not queue_url:
            raise ValueError("QUEUE_URL must be set")

        return cls(
            queue_url=queue_url,
            dlq_url=dlq_url,
            max_messages=max_messages,
            visibility_timeout=visibility_timeout,
            wait_time=wait_time
        )


@dataclass
class AuraAPIConfig:
    """Neo4j Aura API configuration (OAuth 2.0)."""
    client_id: str
    client_secret: str
    organization_id: str
    project_id: str
    oauth_url: str = "https://api.neo4j.io/oauth/token"
    api_base: str = "https://api.neo4j.io/v2beta1"
    client_name: Optional[str] = None

    @classmethod
    def from_env(cls) -> "AuraAPIConfig":
        """Load Aura API configuration from environment variables."""
        client_id = os.getenv("AURA_API_CLIENT_ID")
        client_secret = os.getenv("AURA_API_CLIENT_SECRET")
        org_id = os.getenv("AURA_ORGANIZATION_ID")
        project_id = os.getenv("AURA_PROJECT_ID")

        if not all([client_id, client_secret, org_id, project_id]):
            raise ValueError("Missing required Aura API configuration")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            organization_id=org_id,
            project_id=project_id,
            oauth_url=os.getenv("AURA_OAUTH_URL", "https://api.neo4j.io/oauth/token"),
            api_base=os.getenv("AURA_API_BASE", "https://api.neo4j.io/v2beta1"),
            client_name=os.getenv("AURA_CLIENT_NAME")
        )


@dataclass
class MLflowConfig:
    """MLflow tracking server configuration."""
    tracking_uri: str
    experiment_name: str = "default"
    artifact_location: Optional[str] = None

    @classmethod
    def from_env(cls) -> "MLflowConfig":
        """Load MLflow configuration from environment variables."""
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "default")
        artifact_location = os.getenv("MLFLOW_ARTIFACT_LOCATION")

        return cls(
            tracking_uri=tracking_uri,
            experiment_name=experiment_name,
            artifact_location=artifact_location
        )


@dataclass
class ImportPipelineConfig:
    """Configuration for Aura import pipelines."""
    import_model_id: str
    target_instance_id: str
    schedule: Literal["hourly", "daily", "manual"] = "hourly"
    incremental: bool = True
    batch_size: int = 10000
    max_retries: int = 3
    timeout_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: dict) -> "ImportPipelineConfig":
        """Create from dictionary (e.g., from JSON config file)."""
        return cls(**data)


@dataclass
class AppConfig:
    """Complete application configuration with all services."""
    neo4j: Neo4jConfig
    snowflake: Optional[SnowflakeConfig] = None
    aws: Optional[AWSConfig] = None
    sqs: Optional[SQSConfig] = None
    aura_api: Optional[AuraAPIConfig] = None
    mlflow: Optional[MLflowConfig] = None

    # Multi-instance Neo4j configs
    proper_neo4j: Optional[Neo4jConfig] = None
    tray_neo4j: Optional[Neo4jConfig] = None

    @classmethod
    def from_env(cls, include_optional: bool = True) -> "AppConfig":
        """
        Load complete application configuration from environment.

        Args:
            include_optional: If True, load optional configs (AWS, Snowflake, etc.)
                            If False, only load required Neo4j config
        """
        # Required: Primary Neo4j instance
        neo4j_config = Neo4jConfig.from_env()

        if not include_optional:
            return cls(neo4j=neo4j_config)

        # Optional services
        snowflake_config = None
        aws_config = None
        sqs_config = None
        aura_api_config = None
        mlflow_config = None
        proper_neo4j_config = None
        tray_neo4j_config = None

        try:
            snowflake_config = SnowflakeConfig.from_env()
        except (ValueError, TypeError):
            pass

        try:
            aws_config = AWSConfig.from_env()
        except (ValueError, TypeError):
            pass

        try:
            sqs_config = SQSConfig.from_env()
        except (ValueError, TypeError):
            pass

        try:
            aura_api_config = AuraAPIConfig.from_env()
        except (ValueError, TypeError):
            pass

        try:
            mlflow_config = MLflowConfig.from_env()
        except (ValueError, TypeError):
            pass

        # Multi-instance Neo4j configs
        try:
            proper_neo4j_config = Neo4jConfig.from_env(prefix="PROPER_NEO4J")
        except (ValueError, TypeError):
            pass

        try:
            tray_neo4j_config = Neo4jConfig.from_env(prefix="TRAY_NEO4J")
        except (ValueError, TypeError):
            pass

        return cls(
            neo4j=neo4j_config,
            snowflake=snowflake_config,
            aws=aws_config,
            sqs=sqs_config,
            aura_api=aura_api_config,
            mlflow=mlflow_config,
            proper_neo4j=proper_neo4j_config,
            tray_neo4j=tray_neo4j_config
        )


if __name__ == "__main__":
    # Example usage and validation
    try:
        config = AppConfig.from_env()
        print("✓ Application configuration loaded successfully")
        print(f"  Neo4j URI: {config.neo4j.uri}")
        if config.aura_api:
            print(f"  Aura API: Configured (Org: {config.aura_api.organization_id})")
        if config.snowflake:
            print(f"  Snowflake: {config.snowflake.database}.{config.snowflake.schema}")
        if config.sqs:
            print(f"  SQS: {config.sqs.queue_url}")
    except Exception as e:
        print(f"✗ Configuration error: {e}")
