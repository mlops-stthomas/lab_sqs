"""
Neo4j connector for tracking model lineage and metadata
"""
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class Neo4jConnector:
    """Manages connections and operations with Neo4j for model lineage tracking."""

    def __init__(self):
        self.uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        self.user = os.getenv('NEO4J_USER', 'neo4j')
        self.password = os.getenv('NEO4J_PASSWORD')
        self.driver = None

    def connect(self):
        """Establish connection to Neo4j."""
        if not self.driver:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        return self.driver

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None

    def create_constraints(self):
        """Create uniqueness constraints for nodes."""
        with self.driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Model) REQUIRE m.name IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (v:Version) REQUIRE v.id IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Dataset) REQUIRE d.name IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Experiment) REQUIRE e.id IS UNIQUE"
            ]
            for constraint in constraints:
                session.run(constraint)

    def log_training_run(
        self,
        model_name: str,
        version: str,
        experiment_id: str,
        run_id: str,
        parameters: Dict[str, Any],
        metrics: Dict[str, float],
        dataset_source: str = "Snowflake",
        tags: Optional[Dict[str, str]] = None
    ):
        """
        Log a complete training run to Neo4j with full lineage.

        Creates a graph structure:
        (Dataset) -[:USED_BY]-> (TrainingRun) -[:PRODUCES]-> (ModelVersion) -[:VERSION_OF]-> (Model)
        """
        with self.driver.session() as session:
            query = """
            // Create or match model
            MERGE (model:Model {name: $model_name})
            ON CREATE SET
                model.created_at = datetime(),
                model.type = 'LogisticRegression',
                model.framework = 'scikit-learn'

            // Create model version
            CREATE (version:ModelVersion {
                id: $version_id,
                version: $version,
                created_at: datetime(),
                run_id: $run_id,
                experiment_id: $experiment_id,
                stage: 'None'
            })
            SET version.parameters = $parameters,
                version.metrics = $metrics,
                version.tags = $tags

            // Link version to model
            CREATE (version)-[:VERSION_OF]->(model)

            // Create dataset node
            MERGE (dataset:Dataset {name: $dataset_name})
            ON CREATE SET
                dataset.source = $dataset_source,
                dataset.created_at = datetime()

            // Create training run node
            CREATE (run:TrainingRun {
                id: $run_id,
                started_at: datetime(),
                completed_at: datetime(),
                status: 'SUCCESS'
            })

            // Create relationships
            CREATE (dataset)-[:USED_BY]->(run)
            CREATE (run)-[:PRODUCES]->(version)

            RETURN version.id as version_id
            """

            result = session.run(
                query,
                model_name=model_name,
                version_id=f"{model_name}-v{version}",
                version=version,
                run_id=run_id,
                experiment_id=experiment_id,
                parameters=parameters,
                metrics=metrics,
                tags=tags or {},
                dataset_name="iris_dataset",
                dataset_source=dataset_source
            )

            record = result.single()
            print(f"✓ Logged training run to Neo4j: {record['version_id']}")

    def update_model_stage(self, model_name: str, version: str, stage: str):
        """Update the stage of a model version (Production, Staging, etc.)."""
        with self.driver.session() as session:
            query = """
            MATCH (v:ModelVersion {version: $version})-[:VERSION_OF]->(m:Model {name: $model_name})
            SET v.stage = $stage,
                v.stage_updated_at = datetime()
            RETURN v.version as version, v.stage as stage
            """

            result = session.run(query, model_name=model_name, version=version, stage=stage)
            record = result.single()
            if record:
                print(f"✓ Updated {model_name} v{version} to stage: {stage}")
            else:
                print(f"✗ Model version not found: {model_name} v{version}")

    def get_model_lineage(self, model_name: str, version: str) -> Dict[str, Any]:
        """Get complete lineage for a model version."""
        with self.driver.session() as session:
            query = """
            MATCH (dataset:Dataset)-[:USED_BY]->(run:TrainingRun)-[:PRODUCES]->
                  (version:ModelVersion {version: $version})-[:VERSION_OF]->
                  (model:Model {name: $model_name})
            RETURN
                model.name as model_name,
                version.version as version,
                version.stage as stage,
                version.metrics as metrics,
                version.parameters as parameters,
                dataset.name as dataset_name,
                dataset.source as dataset_source,
                run.started_at as training_started,
                run.completed_at as training_completed
            """

            result = session.run(query, model_name=model_name, version=version)
            record = result.single()

            if record:
                return dict(record)
            return {}

    def get_all_versions(self, model_name: str) -> List[Dict[str, Any]]:
        """Get all versions of a model."""
        with self.driver.session() as session:
            query = """
            MATCH (v:ModelVersion)-[:VERSION_OF]->(m:Model {name: $model_name})
            RETURN
                v.version as version,
                v.stage as stage,
                v.metrics as metrics,
                v.created_at as created_at
            ORDER BY v.created_at DESC
            """

            result = session.run(query, model_name=model_name)
            return [dict(record) for record in result]

    def visualize_lineage_cypher(self, model_name: str) -> str:
        """Return Cypher query to visualize model lineage in Neo4j Browser."""
        return f"""
        MATCH path = (dataset:Dataset)-[:USED_BY]->(run:TrainingRun)-[:PRODUCES]->
                     (version:ModelVersion)-[:VERSION_OF]->(model:Model {{name: '{model_name}'}})
        RETURN path
        """


if __name__ == "__main__":
    # Example usage
    connector = Neo4jConnector()
    connector.connect()

    try:
        # Create constraints
        connector.create_constraints()

        # Log a training run
        connector.log_training_run(
            model_name="iris-classifier",
            version="1",
            experiment_id="exp-001",
            run_id="run-12345",
            parameters={"C": 1.0, "max_iter": 200},
            metrics={"accuracy": 0.9736},
            dataset_source="Snowflake",
            tags={"env": "development"}
        )

        # Get lineage
        lineage = connector.get_model_lineage("iris-classifier", "1")
        print("\nModel Lineage:")
        for key, value in lineage.items():
            print(f"  {key}: {value}")

        # Get all versions
        versions = connector.get_all_versions("iris-classifier")
        print(f"\nAll versions: {len(versions)}")

    finally:
        connector.close()
