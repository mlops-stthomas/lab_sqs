"""
Neo4j MLOps connector that integrates with existing restaurant operations database.
Tracks ML model lineage while coexisting with operational data.
"""
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class Neo4jMLOpsConnector:
    """
    Manages ML model lineage in Neo4j alongside existing operational data.

    Creates a separate namespace for ML models using:
    - MLModel (instead of conflicting with operational models)
    - MLModelVersion
    - MLTrainingRun
    - MLDataset
    - MLExperiment
    - MLPrediction (links to operational data like Orders, Restaurants)
    """

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

    def create_ml_constraints(self):
        """Create uniqueness constraints for ML nodes."""
        with self.driver.session() as session:
            constraints = [
                "CREATE CONSTRAINT ml_model_name IF NOT EXISTS FOR (m:MLModel) REQUIRE m.name IS UNIQUE",
                "CREATE CONSTRAINT ml_version_id IF NOT EXISTS FOR (v:MLModelVersion) REQUIRE v.id IS UNIQUE",
                "CREATE CONSTRAINT ml_run_id IF NOT EXISTS FOR (r:MLTrainingRun) REQUIRE r.run_id IS UNIQUE",
                "CREATE CONSTRAINT ml_experiment_id IF NOT EXISTS FOR (e:MLExperiment) REQUIRE e.experiment_id IS UNIQUE"
            ]
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    print(f"Constraint creation note: {e}")

    def log_ml_training_run(
        self,
        model_name: str,
        version: str,
        experiment_id: str,
        run_id: str,
        parameters: Dict[str, Any],
        metrics: Dict[str, float],
        dataset_info: Dict[str, Any],
        model_type: str = "LogisticRegression",
        framework: str = "scikit-learn",
        tags: Optional[Dict[str, str]] = None
    ):
        """
        Log a complete ML training run with lineage tracking.

        Graph structure:
        (MLDataset) -[:USED_IN_TRAINING]-> (MLTrainingRun) -[:PRODUCED]->
        (MLModelVersion) -[:VERSION_OF]-> (MLModel)

        This coexists with operational data without conflicts.
        """
        with self.driver.session() as session:
            query = """
            // Create or match ML model
            MERGE (model:MLModel {name: $model_name})
            ON CREATE SET
                model.created_at = datetime(),
                model.type = $model_type,
                model.framework = $framework,
                model.purpose = $purpose

            // Create ML experiment
            MERGE (exp:MLExperiment {experiment_id: $experiment_id})
            ON CREATE SET exp.created_at = datetime()

            // Create model version
            CREATE (version:MLModelVersion {
                id: $version_id,
                version: $version,
                created_at = datetime(),
                run_id: $run_id,
                stage: 'None',
                mlflow_uri: $mlflow_uri
            })
            SET version.parameters = $parameters,
                version.metrics = $metrics,
                version.tags = $tags

            // Create training run
            CREATE (run:MLTrainingRun {
                run_id: $run_id,
                started_at: datetime(),
                completed_at: datetime(),
                status: 'SUCCESS',
                training_duration_seconds: $duration
            })

            // Create dataset node with metadata
            MERGE (dataset:MLDataset {name: $dataset_name})
            ON CREATE SET
                dataset.source = $dataset_source,
                dataset.created_at = datetime()
            SET dataset.row_count = $row_count,
                dataset.features = $features

            // Create relationships
            CREATE (version)-[:VERSION_OF]->(model)
            CREATE (run)-[:PART_OF_EXPERIMENT]->(exp)
            CREATE (run)-[:PRODUCED]->(version)
            CREATE (dataset)-[:USED_IN_TRAINING]->(run)

            // Link to operational restaurant if available
            WITH model
            OPTIONAL MATCH (restaurant:Restaurant)
            WHERE restaurant.guid IS NOT NULL
            CREATE (model)-[:SERVES_RESTAURANT]->(restaurant)

            RETURN version.id as version_id
            """

            mlflow_uri = f"models:/{model_name}/{version}"

            result = session.run(
                query,
                model_name=model_name,
                model_type=model_type,
                framework=framework,
                purpose=dataset_info.get('purpose', 'prediction'),
                version_id=f"{model_name}-v{version}",
                version=version,
                run_id=run_id,
                experiment_id=experiment_id,
                parameters=parameters,
                metrics=metrics,
                tags=tags or {},
                mlflow_uri=mlflow_uri,
                dataset_name=dataset_info.get('name', 'unknown'),
                dataset_source=dataset_info.get('source', 'unknown'),
                row_count=dataset_info.get('row_count', 0),
                features=dataset_info.get('features', []),
                duration=dataset_info.get('duration_seconds', 0)
            )

            record = result.single()
            print(f"✓ Logged ML training run to Neo4j: {record['version_id']}")
            return record['version_id']

    def log_prediction_to_order(
        self,
        model_name: str,
        version: str,
        order_guid: str,
        prediction: Any,
        confidence: float,
        features: Dict[str, Any]
    ):
        """
        Link an ML prediction to an operational Order node.

        This shows how ML models enhance operational data:
        (MLModelVersion) -[:PREDICTED]-> (MLPrediction) -[:FOR_ORDER]-> (Order)
        """
        with self.driver.session() as session:
            query = """
            MATCH (version:MLModelVersion {version: $version})-[:VERSION_OF]->(model:MLModel {name: $model_name})
            MATCH (order:Order {guid: $order_guid})

            CREATE (pred:MLPrediction {
                id: randomUUID(),
                predicted_at: datetime(),
                prediction_value: $prediction,
                confidence: $confidence,
                model_version: $version
            })
            SET pred.features = $features

            CREATE (version)-[:PREDICTED]->(pred)
            CREATE (pred)-[:FOR_ORDER]->(order)

            RETURN pred.id as prediction_id
            """

            result = session.run(
                query,
                model_name=model_name,
                version=version,
                order_guid=order_guid,
                prediction=str(prediction),
                confidence=confidence,
                features=features
            )

            record = result.single()
            if record:
                print(f"✓ Logged prediction for order {order_guid}")
                return record['prediction_id']
            else:
                print(f"✗ Order not found: {order_guid}")
                return None

    def update_model_stage(self, model_name: str, version: str, stage: str):
        """
        Update the deployment stage of an ML model version.

        Stages: Development, Staging, Production, Archived
        """
        with self.driver.session() as session:
            query = """
            MATCH (v:MLModelVersion {version: $version})-[:VERSION_OF]->(m:MLModel {name: $model_name})
            SET v.stage = $stage,
                v.stage_updated_at = datetime()
            RETURN v.version as version, v.stage as stage
            """

            result = session.run(query, model_name=model_name, version=version, stage=stage)
            record = result.single()
            if record:
                print(f"✓ Updated {model_name} v{version} to stage: {stage}")
                return True
            else:
                print(f"✗ Model version not found: {model_name} v{version}")
                return False

    def get_model_lineage(self, model_name: str, version: str) -> Dict[str, Any]:
        """Get complete lineage for an ML model version."""
        with self.driver.session() as session:
            query = """
            MATCH (dataset:MLDataset)-[:USED_IN_TRAINING]->(run:MLTrainingRun)-[:PRODUCED]->
                  (version:MLModelVersion {version: $version})-[:VERSION_OF]->
                  (model:MLModel {name: $model_name})
            OPTIONAL MATCH (run)-[:PART_OF_EXPERIMENT]->(exp:MLExperiment)
            RETURN
                model.name as model_name,
                model.type as model_type,
                model.framework as framework,
                version.version as version,
                version.stage as stage,
                version.metrics as metrics,
                version.parameters as parameters,
                version.mlflow_uri as mlflow_uri,
                dataset.name as dataset_name,
                dataset.source as dataset_source,
                dataset.row_count as dataset_rows,
                run.started_at as training_started,
                run.completed_at as training_completed,
                run.training_duration_seconds as duration,
                exp.experiment_id as experiment_id
            """

            result = session.run(query, model_name=model_name, version=version)
            record = result.single()

            if record:
                return dict(record)
            return {}

    def get_all_model_versions(self, model_name: str) -> List[Dict[str, Any]]:
        """Get all versions of an ML model with metrics."""
        with self.driver.session() as session:
            query = """
            MATCH (v:MLModelVersion)-[:VERSION_OF]->(m:MLModel {name: $model_name})
            OPTIONAL MATCH (v)<-[:PRODUCED]-(run:MLTrainingRun)
            RETURN
                v.version as version,
                v.stage as stage,
                v.metrics as metrics,
                v.parameters as parameters,
                v.created_at as created_at,
                run.training_duration_seconds as training_duration
            ORDER BY v.created_at DESC
            """

            result = session.run(query, model_name=model_name)
            return [dict(record) for record in result]

    def get_model_performance_by_restaurant(self, model_name: str) -> List[Dict[str, Any]]:
        """
        Analyze ML model predictions grouped by restaurant.

        Shows how many predictions were made for each restaurant's orders.
        """
        with self.driver.session() as session:
            query = """
            MATCH (model:MLModel {name: $model_name})<-[:VERSION_OF]-(version:MLModelVersion)
            MATCH (version)-[:PREDICTED]->(pred:MLPrediction)-[:FOR_ORDER]->(order:Order)
            MATCH (order)-[:PLACED_AT_RESTAURANT]->(restaurant:Restaurant)

            RETURN
                restaurant.name as restaurant_name,
                restaurant.guid as restaurant_guid,
                count(pred) as prediction_count,
                avg(pred.confidence) as avg_confidence,
                collect(DISTINCT version.version) as versions_used
            ORDER BY prediction_count DESC
            """

            result = session.run(query, model_name=model_name)
            return [dict(record) for record in result]

    def create_ml_lineage_visualization_query(self, model_name: str) -> str:
        """
        Return Cypher query to visualize complete ML lineage in Neo4j Browser.

        Shows: Dataset -> TrainingRun -> ModelVersion -> Model -> Predictions -> Orders
        """
        return f"""
        MATCH path1 = (dataset:MLDataset)-[:USED_IN_TRAINING]->(run:MLTrainingRun)-[:PRODUCED]->
                     (version:MLModelVersion)-[:VERSION_OF]->(model:MLModel {{name: '{model_name}'}})
        OPTIONAL MATCH path2 = (version)-[:PREDICTED]->(pred:MLPrediction)-[:FOR_ORDER]->(order:Order)
        OPTIONAL MATCH path3 = (order)-[:PLACED_AT_RESTAURANT]->(restaurant:Restaurant)
        RETURN path1, path2, path3
        LIMIT 100
        """


if __name__ == "__main__":
    # Example usage
    connector = Neo4jMLOpsConnector()
    connector.connect()

    try:
        # Create ML-specific constraints
        connector.create_ml_constraints()

        # Log a training run
        version_id = connector.log_ml_training_run(
            model_name="order-demand-predictor",
            version="1",
            experiment_id="demand-forecast-exp-001",
            run_id="mlflow-run-12345",
            parameters={"C": 1.0, "max_iter": 200, "solver": "lbfgs"},
            metrics={"accuracy": 0.9736, "f1_score": 0.9650, "precision": 0.9800},
            dataset_info={
                "name": "toast_orders_last_30_days",
                "source": "Snowflake",
                "row_count": 101460,
                "features": ["hour_of_day", "day_of_week", "employee_count", "avg_check_size"],
                "purpose": "demand_forecasting",
                "duration_seconds": 45.2
            },
            model_type="LogisticRegression",
            framework="scikit-learn",
            tags={"environment": "production", "restaurant": "proper_hotel"}
        )

        print(f"\nCreated model version: {version_id}")

        # Get lineage
        lineage = connector.get_model_lineage("order-demand-predictor", "1")
        print("\nModel Lineage:")
        for key, value in lineage.items():
            print(f"  {key}: {value}")

        # Get all versions
        versions = connector.get_all_model_versions("order-demand-predictor")
        print(f"\nAll versions: {len(versions)}")

        # Print visualization query
        print("\n" + "="*60)
        print("Visualization Query (paste into Neo4j Browser):")
        print("="*60)
        print(connector.create_ml_lineage_visualization_query("order-demand-predictor"))

    finally:
        connector.close()
