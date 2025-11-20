"""
Unified Neo4j Aura Management Interface

Combines Aura CLI (instance/GraphQL API management) with Aura Import API
for comprehensive graph database lifecycle management.

Features:
- Instance provisioning and management (via Aura CLI)
- GraphQL Data API setup (via Aura CLI)
- Import job orchestration (via Aura Import API v2beta1)
- Automated ingestion pipelines
- Schema management and monitoring
"""
import os
import json
import subprocess
import logging
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

# Import our existing Aura Import API client
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from aura_import_client import AuraImportClient, AuraCredentials, ImportJob


logger = logging.getLogger(__name__)


class InstanceType(Enum):
    """Aura instance types."""
    FREE = "free"
    PROFESSIONAL = "professional-db"
    ENTERPRISE = "enterprise-db"
    BUSINESS_CRITICAL = "business-critical-db"


class CloudProvider(Enum):
    """Cloud providers for Aura instances."""
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"


@dataclass
class AuraInstance:
    """Represents an Aura database instance."""
    id: str
    name: str
    tier: str
    status: str
    connection_url: str
    cloud_provider: Optional[str] = None
    region: Optional[str] = None


@dataclass
class GraphQLDataAPI:
    """Represents a GraphQL Data API."""
    id: str
    name: str
    instance_id: str
    url: str
    status: str


class AuraManager:
    """
    Unified manager for Neo4j Aura operations.

    Provides high-level interface for:
    1. Instance lifecycle (create, delete, pause, resume, list)
    2. GraphQL Data API setup
    3. Import job management
    4. Automated data pipelines
    """

    def __init__(
        self,
        cli_path: str = "aura-cli",
        output_format: Literal["json", "table", "default"] = "json"
    ):
        """
        Initialize Aura Manager.

        Args:
            cli_path: Path to aura-cli executable
            output_format: Output format for CLI commands
        """
        self.cli_path = cli_path
        self.output_format = output_format
        self.import_client: Optional[AuraImportClient] = None

        # Verify CLI is available
        self._verify_cli()

    def _verify_cli(self):
        """Verify Aura CLI is installed and configured."""
        try:
            result = subprocess.run(
                [self.cli_path, "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Aura CLI version: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                f"Aura CLI not found or not configured. "
                f"Install from: https://neo4j.com/labs/aura-cli/\n"
                f"Error: {e}"
            )

    def _run_cli_command(
        self,
        command: List[str],
        parse_json: bool = True
    ) -> Any:
        """
        Run Aura CLI command and parse output.

        Args:
            command: CLI command parts (e.g., ["instance", "list"])
            parse_json: Parse JSON output

        Returns:
            Parsed JSON or raw string output
        """
        full_command = [self.cli_path] + command

        # Add output format flag if not already present
        if "--output" not in command and self.output_format == "json":
            full_command.extend(["--output", "json"])

        logger.debug(f"Running: {' '.join(full_command)}")

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()

        if parse_json and self.output_format == "json":
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON output, returning raw string")
                return output

        return output

    # ==================== Instance Management ====================

    def list_instances(self) -> List[AuraInstance]:
        """
        List all Aura instances.

        Returns:
            List of AuraInstance objects
        """
        data = self._run_cli_command(["instance", "list"])

        instances = []
        for item in data.get("data", []):
            instances.append(AuraInstance(
                id=item.get("id"),
                name=item.get("name"),
                tier=item.get("tier"),
                status=item.get("status"),
                connection_url=item.get("connection_url", ""),
                cloud_provider=item.get("cloud_provider"),
                region=item.get("region")
            ))

        return instances

    def get_instance(self, instance_id: str) -> AuraInstance:
        """
        Get details of a specific instance.

        Args:
            instance_id: Instance ID

        Returns:
            AuraInstance object
        """
        data = self._run_cli_command(["instance", "get", instance_id])

        item = data.get("data", {})
        return AuraInstance(
            id=item.get("id"),
            name=item.get("name"),
            tier=item.get("tier"),
            status=item.get("status"),
            connection_url=item.get("connection_url", ""),
            cloud_provider=item.get("cloud_provider"),
            region=item.get("region")
        )

    def create_instance(
        self,
        name: str,
        instance_type: InstanceType = InstanceType.PROFESSIONAL,
        cloud_provider: CloudProvider = CloudProvider.GCP,
        region: str = "us-central1",
        memory: str = "8GB",
        wait: bool = True
    ) -> AuraInstance:
        """
        Create a new Aura instance.

        Args:
            name: Instance name
            instance_type: Instance tier
            cloud_provider: Cloud provider (gcp, aws, azure)
            region: Cloud region
            memory: Instance memory (e.g., "8GB", "16GB")
            wait: Wait for instance to be ready

        Returns:
            Created AuraInstance
        """
        command = [
            "instance", "create",
            "--name", name,
            "--type", instance_type.value,
            "--cloud-provider", cloud_provider.value,
            "--region", region,
            "--memory", memory
        ]

        if wait:
            command.append("--wait")

        data = self._run_cli_command(command)

        # Get full instance details
        instance_id = data.get("data", {}).get("id")
        return self.get_instance(instance_id)

    def delete_instance(self, instance_id: str, wait: bool = False) -> Dict[str, Any]:
        """
        Delete an Aura instance.

        Args:
            instance_id: Instance ID
            wait: Wait for deletion to complete

        Returns:
            Deletion response
        """
        command = ["instance", "delete", instance_id]
        if wait:
            command.append("--wait")

        return self._run_cli_command(command)

    def pause_instance(self, instance_id: str) -> Dict[str, Any]:
        """Pause an Aura instance."""
        return self._run_cli_command(["instance", "pause", instance_id])

    def resume_instance(self, instance_id: str) -> Dict[str, Any]:
        """Resume a paused Aura instance."""
        return self._run_cli_command(["instance", "resume", instance_id])

    # ==================== GraphQL Data API Management ====================

    def list_graphql_apis(self) -> List[GraphQLDataAPI]:
        """
        List all GraphQL Data APIs.

        Returns:
            List of GraphQLDataAPI objects
        """
        data = self._run_cli_command(["data-api", "graphql", "list"])

        apis = []
        for item in data.get("data", []):
            apis.append(GraphQLDataAPI(
                id=item.get("id"),
                name=item.get("name"),
                instance_id=item.get("instance_id"),
                url=item.get("url", ""),
                status=item.get("status")
            ))

        return apis

    def create_graphql_api(
        self,
        instance_id: str,
        name: Optional[str] = None,
        wait: bool = True
    ) -> GraphQLDataAPI:
        """
        Create a GraphQL Data API for an instance.

        Args:
            instance_id: Target instance ID
            name: API name (defaults to instance name + "-api")
            wait: Wait for API to be ready

        Returns:
            Created GraphQLDataAPI
        """
        command = ["data-api", "graphql", "create", "--instance-id", instance_id]

        if name:
            command.extend(["--name", name])

        if wait:
            command.append("--wait")

        data = self._run_cli_command(command)

        api_id = data.get("data", {}).get("id")
        return self.get_graphql_api(api_id)

    def get_graphql_api(self, api_id: str) -> GraphQLDataAPI:
        """Get details of a GraphQL Data API."""
        data = self._run_cli_command(["data-api", "graphql", "get", api_id])

        item = data.get("data", {})
        return GraphQLDataAPI(
            id=item.get("id"),
            name=item.get("name"),
            instance_id=item.get("instance_id"),
            url=item.get("url", ""),
            status=item.get("status")
        )

    def delete_graphql_api(self, api_id: str) -> Dict[str, Any]:
        """Delete a GraphQL Data API."""
        return self._run_cli_command(["data-api", "graphql", "delete", api_id])

    # ==================== Import Job Management ====================

    def setup_import_client(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        organization_id: Optional[str] = None,
        project_id: Optional[str] = None
    ):
        """
        Initialize Aura Import API client.

        Args:
            client_id: API client ID (or use AURA_API_CLIENT_ID env var)
            client_secret: API client secret
            organization_id: Organization ID
            project_id: Project ID
        """
        self.import_client = AuraImportClient(
            client_id=client_id,
            client_secret=client_secret,
            organization_id=organization_id,
            project_id=project_id
        )
        logger.info("Aura Import API client initialized")

    def create_import_job(
        self,
        import_model_id: str,
        db_id: str,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None
    ) -> ImportJob:
        """
        Create and trigger an import job.

        Args:
            import_model_id: Import model ID from Aura Console
            db_id: Target database ID
            db_user: Database user (for Free/VDC tier)
            db_password: Database password (for Free/VDC tier)

        Returns:
            ImportJob object
        """
        if not self.import_client:
            raise RuntimeError("Import client not initialized. Call setup_import_client() first.")

        creds = AuraCredentials(
            db_id=db_id,
            user=db_user,
            password=db_password
        )

        return self.import_client.create_import_job(
            import_model_id=import_model_id,
            aura_credentials=creds
        )

    def get_import_job(
        self,
        job_id: str,
        include_progress: bool = True
    ) -> ImportJob:
        """Get status of an import job."""
        if not self.import_client:
            raise RuntimeError("Import client not initialized.")

        return self.import_client.get_import_job(job_id, include_progress=include_progress)

    def wait_for_import_completion(
        self,
        job_id: str,
        poll_interval: int = 30,
        max_wait: int = 3600,
        callback: Optional[callable] = None
    ) -> ImportJob:
        """Wait for import job to complete."""
        if not self.import_client:
            raise RuntimeError("Import client not initialized.")

        return self.import_client.wait_for_completion(
            job_id,
            poll_interval=poll_interval,
            max_wait=max_wait,
            callback=callback
        )

    # ==================== Automated Pipeline Orchestration ====================

    def setup_incremental_pipeline(
        self,
        instance_id: str,
        import_model_id: str,
        schedule: str = "0 * * * *"  # Hourly by default
    ) -> Dict[str, Any]:
        """
        Set up an automated incremental import pipeline.

        Args:
            instance_id: Target instance ID (e.g., "705c1e42")
            import_model_id: Import model configured for incremental data
            schedule: Cron schedule (default: hourly)

        Returns:
            Pipeline configuration
        """
        config = {
            "instance_id": instance_id,
            "import_model_id": import_model_id,
            "schedule": schedule,
            "type": "incremental",
            "enabled": True
        }

        logger.info(
            f"Incremental pipeline configured:\n"
            f"  Instance: {instance_id}\n"
            f"  Schedule: {schedule}\n"
            f"  Import Model: {import_model_id}"
        )

        # Save configuration for scheduler
        config_path = Path("config/import_pipelines.json")
        config_path.parent.mkdir(exist_ok=True)

        if config_path.exists():
            with open(config_path) as f:
                pipelines = json.load(f)
        else:
            pipelines = []

        pipelines.append(config)

        with open(config_path, 'w') as f:
            json.dump(pipelines, f, indent=2)

        logger.info(f"Pipeline saved to {config_path}")

        return config

    def trigger_historical_import(
        self,
        import_model_id: str,
        instance_id: str,
        wait: bool = True
    ) -> ImportJob:
        """
        Trigger one-time historical data import.

        Args:
            import_model_id: Import model for historical data
            instance_id: Target instance ID
            wait: Wait for completion

        Returns:
            ImportJob (completed if wait=True)
        """
        if not self.import_client:
            raise RuntimeError("Import client not initialized.")

        logger.info(f"Starting historical import to instance {instance_id}")

        job = self.create_import_job(
            import_model_id=import_model_id,
            db_id=instance_id
        )

        logger.info(f"Historical import job created: {job.id}")

        if wait:
            from aura_import_client import print_job_progress
            job = self.wait_for_import_completion(
                job.id,
                callback=print_job_progress
            )
            logger.info(f"Historical import completed: {job.state}")

        return job

    # ==================== Monitoring and Health Checks ====================

    def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.

        Returns:
            Health status for all components
        """
        health = {
            "cli": {"status": "unknown"},
            "instances": {"status": "unknown", "count": 0},
            "graphql_apis": {"status": "unknown", "count": 0},
            "import_api": {"status": "unknown"}
        }

        # Check CLI
        try:
            self._verify_cli()
            health["cli"]["status"] = "healthy"
        except Exception as e:
            health["cli"]["status"] = "unhealthy"
            health["cli"]["error"] = str(e)

        # Check instances
        try:
            instances = self.list_instances()
            health["instances"]["status"] = "healthy"
            health["instances"]["count"] = len(instances)
            health["instances"]["details"] = [
                {"id": i.id, "name": i.name, "status": i.status}
                for i in instances
            ]
        except Exception as e:
            health["instances"]["status"] = "unhealthy"
            health["instances"]["error"] = str(e)

        # Check GraphQL APIs
        try:
            apis = self.list_graphql_apis()
            health["graphql_apis"]["status"] = "healthy"
            health["graphql_apis"]["count"] = len(apis)
        except Exception as e:
            health["graphql_apis"]["status"] = "unhealthy"
            health["graphql_apis"]["error"] = str(e)

        # Check Import API
        if self.import_client:
            try:
                # Just verify we can get access token
                self.import_client._get_access_token()
                health["import_api"]["status"] = "healthy"
                health["import_api"]["organization_id"] = self.import_client.organization_id
            except Exception as e:
                health["import_api"]["status"] = "unhealthy"
                health["import_api"]["error"] = str(e)
        else:
            health["import_api"]["status"] = "not_configured"

        return health


# ==================== CLI Helper Functions ====================

def print_instances_table(instances: List[AuraInstance]):
    """Pretty print instances in table format."""
    if not instances:
        print("No instances found.")
        return

    print(f"\n{'ID':<12} {'Name':<30} {'Tier':<20} {'Status':<15}")
    print("-" * 80)
    for i in instances:
        print(f"{i.id:<12} {i.name:<30} {i.tier:<20} {i.status:<15}")


def print_graphql_apis_table(apis: List[GraphQLDataAPI]):
    """Pretty print GraphQL APIs in table format."""
    if not apis:
        print("No GraphQL APIs found.")
        return

    print(f"\n{'ID':<12} {'Name':<30} {'Instance ID':<15} {'Status':<15}")
    print("-" * 75)
    for api in apis:
        print(f"{api.id:<12} {api.name:<30} {api.instance_id:<15} {api.status:<15}")


if __name__ == "__main__":
    """
    Example usage and testing.
    """
    logging.basicConfig(level=logging.INFO)

    # Initialize manager
    manager = AuraManager()

    # Health check
    print("\n=== Aura Health Check ===")
    health = manager.health_check()
    print(json.dumps(health, indent=2))

    # List instances
    print("\n=== Aura Instances ===")
    instances = manager.list_instances()
    print_instances_table(instances)

    # List GraphQL APIs
    print("\n=== GraphQL Data APIs ===")
    try:
        apis = manager.list_graphql_apis()
        print_graphql_apis_table(apis)
    except Exception as e:
        print(f"Error listing GraphQL APIs: {e}")

    # Setup import client (requires credentials)
    print("\n=== Aura Import API ===")
    try:
        manager.setup_import_client()
        print(f"✓ Import API configured for organization: {manager.import_client.organization_id}")
    except Exception as e:
        print(f"⚠ Import API not configured: {e}")
        print("  Set environment variables: AURA_API_CLIENT_ID, AURA_API_CLIENT_SECRET,")
        print("  AURA_ORGANIZATION_ID, AURA_PROJECT_ID")
