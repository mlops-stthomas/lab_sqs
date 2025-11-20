from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


def upload_iris():
    """Create and upload the Iris dataset to Snowflake via the SnowflakeConnector."""
    import pathlib
    import os
    import sys

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))

    from snowflake_connector import SnowflakeConnector

    connector = SnowflakeConnector()
    try:
        table = os.getenv("IRIS_TABLE_NAME", "IRIS_DATASET")
        df = connector.create_iris_table()
        print(f"✓ Uploaded Iris dataset to Snowflake table {table} ({len(df)} rows)")
    finally:
        connector.close()


default_args = {
    "owner": "mlops",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="load_iris_to_snowflake",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    description="Upload Iris dataset into Snowflake (via SnowflakeConnector.create_iris_table)",
) as dag:
    upload = PythonOperator(
        task_id="upload_iris",
        python_callable=upload_iris,
    )

    upload
