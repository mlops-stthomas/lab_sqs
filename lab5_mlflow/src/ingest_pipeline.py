"""
Snowflake → Neo4j ingestion with historical and incremental strategies.
Maintains a simple watermark in-memory (can be swapped for persistent store).
"""
import os
import pandas as pd
from datetime import datetime
from typing import Any, Dict


class IngestPipeline:
    def __init__(self, neo4j: Any, snowflake: Any):
        self.neo4j = neo4j
        self.snowflake = snowflake
        self.watermark = None  # replace with persistent store in production

    def run_historical(self, start_date: str, end_date: str, batch_size: int = 5000) -> Dict[str, Any]:
        """Ingest historical data by date window."""
        query = f"""
        SELECT * FROM ORDERS
        WHERE BUSINESS_DATE >= '{start_date}' AND BUSINESS_DATE <= '{end_date}'
        ORDER BY BUSINESS_DATE
        """
        df = self.snowflake.execute_query(query)
        return self._load_to_neo4j(df, batch_size, mode="historical")

    def run_incremental(self, batch_size: int = 2000) -> Dict[str, Any]:
        """Ingest changes since last watermark (simple timestamp)."""
        watermark = self.watermark or "1970-01-01"
        query = f"""
        SELECT * FROM ORDERS
        WHERE LAST_MODIFIED_AT > '{watermark}'
        ORDER BY LAST_MODIFIED_AT
        """
        df = self.snowflake.execute_query(query)
        stats = self._load_to_neo4j(df, batch_size, mode="incremental")
        if not df.empty:
            self.watermark = df["LAST_MODIFIED_AT"].max()
        return stats

    def _load_to_neo4j(self, df: pd.DataFrame, batch_size: int, mode: str) -> Dict[str, Any]:
        if df.empty:
            return {"mode": mode, "rows": 0}

        # Example upsert for orders; extend for line items, payments, etc.
        cypher = """
        UNWIND $rows AS row
        MERGE (o:Order {guid: row.GUID})
          ON CREATE SET o.businessDate = date(row.BUSINESS_DATE),
                        o.createdAt = datetime(),
                        o.source = $mode
          ON MATCH SET o.lastModifiedAt = datetime()
        WITH o, row
        MERGE (r:Restaurant {restaurantGuid: row.RESTAURANTGUID})
        MERGE (o)-[:PLACED_AT_RESTAURANT]->(r)
        """
        # Batch in chunks
        total = 0
        for i in range(0, len(df), batch_size):
            chunk = df.iloc[i : i + batch_size].to_dict("records")
            self.neo4j.driver.session().run(cypher, rows=chunk, mode=mode)
            total += len(chunk)
        return {"mode": mode, "rows": total, "batch_size": batch_size}
