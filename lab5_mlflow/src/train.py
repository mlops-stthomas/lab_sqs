import mlflow
import mlflow.sklearn
import os
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from datetime import datetime
from typing import Optional

# Import connectors (if available)
try:
    from snowflake_connector import SnowflakeConnector
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False
    print("⚠️  Snowflake connector not available, using local Iris dataset")

try:
    from neo4j_connector import Neo4jConnector
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("⚠️  Neo4j connector not available, skipping lineage tracking")


def load_training_data(use_snowflake: bool = False):
    """
    Load training data from Snowflake or fall back to local dataset.

    Args:
        use_snowflake: If True and Snowflake is configured, load from Snowflake

    Returns:
        X_train, X_test, y_train, y_test
    """
    if use_snowflake and SNOWFLAKE_AVAILABLE and os.getenv('SNOWFLAKE_ACCOUNT'):
        try:
            print("Loading data from Snowflake...")
            snowflake_conn = SnowflakeConnector()
            df = snowflake_conn.load_training_data("IRIS_DATASET")
            snowflake_conn.close()

            # Extract features and target
            feature_cols = ['SEPAL_LENGTH', 'SEPAL_WIDTH', 'PETAL_LENGTH', 'PETAL_WIDTH']
            X = df[feature_cols].values
            y = df['TARGET'].values

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.25, random_state=42, stratify=y
            )

            data_source = "Snowflake"
            print(f"✓ Loaded {len(df)} samples from Snowflake")

        except Exception as e:
            print(f"Failed to load from Snowflake: {e}")
            print("Falling back to local dataset...")
            data_source = "Local (Snowflake fallback)"
            data = load_iris()
            X_train, X_test, y_train, y_test = train_test_split(
                data.data, data.target, test_size=0.25, random_state=42, stratify=data.target
            )
    else:
        # Use local Iris dataset
        data = load_iris()
        X_train, X_test, y_train, y_test = train_test_split(
            data.data, data.target, test_size=0.25, random_state=42, stratify=data.target
        )
        data_source = "Local (sklearn)"
        print(f"✓ Loaded {len(data.data)} samples from local dataset")

    return X_train, X_test, y_train, y_test, data_source


def log_to_neo4j(
    run_id: str,
    model_name: str,
    version: str,
    parameters: dict,
    metrics: dict,
    data_source: str
):
    """Log training run lineage to Neo4j."""
    if not NEO4J_AVAILABLE or not os.getenv('NEO4J_URI'):
        print("⚠️  Neo4j not configured, skipping lineage logging")
        return

    try:
        neo4j_conn = Neo4jConnector()
        neo4j_conn.connect()
        neo4j_conn.create_constraints()

        # Log complete training run
        neo4j_conn.log_training_run(
            model_name=model_name,
            version=version,
            experiment_id=os.getenv('MLFLOW_EXPERIMENT_ID', 'default'),
            run_id=run_id,
            parameters=parameters,
            metrics=metrics,
            dataset_source=data_source,
            tags={
                'framework': 'scikit-learn',
                'algorithm': 'LogisticRegression',
                'environment': os.getenv('ENVIRONMENT', 'development')
            }
        )

        neo4j_conn.close()
        print("✓ Logged lineage to Neo4j")

    except Exception as e:
        print(f"⚠️  Failed to log to Neo4j: {e}")


def main(use_snowflake: bool = False, log_lineage: bool = True):
    """
    Main training function.

    Args:
        use_snowflake: Load data from Snowflake if available
        log_lineage: Log model lineage to Neo4j if available
    """
    print("=" * 60)
    print("Starting model training...")
    print("=" * 60)

    mlflow.set_experiment("iris_model_exp")

    # Load training data
    X_train, X_test, y_train, y_test, data_source = load_training_data(use_snowflake)

    # Training parameters
    C = float(os.getenv('MODEL_C', '1.0'))
    max_iter = int(os.getenv('MODEL_MAX_ITER', '200'))

    print(f"\nTraining parameters:")
    print(f"  C: {C}")
    print(f"  max_iter: {max_iter}")
    print(f"  Data source: {data_source}")

    with mlflow.start_run(run_name=f"iris-logreg-{datetime.now().strftime('%Y%m%d-%H%M%S')}") as run:
        # Log parameters
        mlflow.log_param("C", C)
        mlflow.log_param("max_iter", max_iter)
        mlflow.log_param("data_source", data_source)
        mlflow.log_param("train_size", len(X_train))
        mlflow.log_param("test_size", len(X_test))

        # Train model
        print("\nTraining model...")
        clf = LogisticRegression(C=C, max_iter=max_iter, n_jobs=None, random_state=42)
        clf.fit(X_train, y_train)

        # Make predictions
        y_pred_train = clf.predict(X_train)
        y_pred_test = clf.predict(X_test)

        # Calculate metrics
        train_acc = accuracy_score(y_train, y_pred_train)
        test_acc = accuracy_score(y_test, y_pred_test)
        precision = precision_score(y_test, y_pred_test, average='weighted')
        recall = recall_score(y_test, y_pred_test, average='weighted')
        f1 = f1_score(y_test, y_pred_test, average='weighted')

        # Log metrics to MLFlow
        mlflow.log_metric("train_accuracy", float(train_acc))
        mlflow.log_metric("test_accuracy", float(test_acc))
        mlflow.log_metric("precision", float(precision))
        mlflow.log_metric("recall", float(recall))
        mlflow.log_metric("f1_score", float(f1))

        # Log model
        mlflow.sklearn.log_model(
            clf,
            "model",
            registered_model_name="iris-classifier"
        )

        print(f"\n{'='*60}")
        print("Training Results:")
        print(f"{'='*60}")
        print(f"  Train Accuracy: {train_acc:.4f}")
        print(f"  Test Accuracy:  {test_acc:.4f}")
        print(f"  Precision:      {precision:.4f}")
        print(f"  Recall:         {recall:.4f}")
        print(f"  F1 Score:       {f1:.4f}")
        print(f"  MLFlow Run ID:  {run.info.run_id}")
        print(f"{'='*60}")

        # Log lineage to Neo4j
        if log_lineage:
            log_to_neo4j(
                run_id=run.info.run_id,
                model_name="iris-classifier",
                version=datetime.now().strftime('%Y%m%d-%H%M%S'),
                parameters={
                    "C": C,
                    "max_iter": max_iter,
                    "data_source": data_source
                },
                metrics={
                    "train_accuracy": float(train_acc),
                    "test_accuracy": float(test_acc),
                    "precision": float(precision),
                    "recall": float(recall),
                    "f1_score": float(f1)
                },
                data_source=data_source
            )

        print("\n✓ Training completed successfully!\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Train Iris classifier')
    parser.add_argument('--snowflake', action='store_true',
                       help='Load data from Snowflake')
    parser.add_argument('--no-lineage', action='store_true',
                       help='Skip Neo4j lineage logging')

    args = parser.parse_args()

    main(
        use_snowflake=args.snowflake,
        log_lineage=not args.no_lineage
    )
