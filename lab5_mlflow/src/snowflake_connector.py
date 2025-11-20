"""
Snowflake connector for loading training data
"""
import os
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv

load_dotenv()


class SnowflakeConnector:
    """Manages connections and operations with Snowflake."""

    def __init__(self):
        self.connection = None
        self.config = {
            'account': os.getenv('SNOWFLAKE_ACCOUNT'),
            'user': os.getenv('SNOWFLAKE_USER'),
            'password': os.getenv('SNOWFLAKE_PASSWORD'),
            'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
            'database': os.getenv('SNOWFLAKE_DATABASE'),
            'schema': os.getenv('SNOWFLAKE_SCHEMA'),
            'role': os.getenv('SNOWFLAKE_ROLE', 'SYSADMIN')
        }

    def connect(self):
        """Establish connection to Snowflake."""
        if not self.connection:
            self.connection = snowflake.connector.connect(**self.config)
        return self.connection

    def close(self):
        """Close Snowflake connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame."""
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=columns)
        finally:
            cursor.close()

    def load_training_data(self, table_name: str = "IRIS_DATASET") -> pd.DataFrame:
        """
        Load training data from Snowflake.

        Args:
            table_name: Name of the table containing training data

        Returns:
            DataFrame with training data
        """
        query = f"SELECT * FROM {table_name}"
        return self.execute_query(query)

    def upload_dataframe(self, df: pd.DataFrame, table_name: str):
        """Upload a DataFrame to Snowflake."""
        conn = self.connect()
        write_pandas(
            conn=conn,
            df=df,
            table_name=table_name,
            auto_create_table=True,
            overwrite=True
        )
        print(f"✓ Uploaded {len(df)} rows to {table_name}")

    def create_iris_table(self):
        """Create and populate Iris dataset table in Snowflake (for demo)."""
        from sklearn.datasets import load_iris

        # Load Iris dataset
        iris = load_iris()
        df = pd.DataFrame(
            data=iris.data,
            columns=['SEPAL_LENGTH', 'SEPAL_WIDTH', 'PETAL_LENGTH', 'PETAL_WIDTH']
        )
        df['TARGET'] = iris.target
        df['TARGET_NAME'] = [iris.target_names[t] for t in iris.target]

        # Upload to Snowflake
        table = os.getenv("IRIS_TABLE_NAME", "IRIS_DATASET")
        self.upload_dataframe(df, table)
        return df


if __name__ == "__main__":
    # Example usage
    connector = SnowflakeConnector()
    try:
        # Create sample table
        df = connector.create_iris_table()
        print(f"Created IRIS_DATASET table with {len(df)} rows")

        # Load data back
        data = connector.load_training_data()
        print(f"Loaded {len(data)} rows from Snowflake")
        print(data.head())
    finally:
        connector.close()
