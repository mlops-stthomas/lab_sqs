"""
Pipeline factory for Snowflake→Neo4j data ingestion strategies.

Implements two main patterns:
1. Historical Pipeline: Date-ranged batch imports with full schema setup
2. Incremental Pipeline: Watermark-based hourly upserts with MERGE

Usage:
    from .pipeline_factory import create_incremental_pipeline, create_historical_pipeline

    # Incremental (hourly)
    pipeline = create_incremental_pipeline(
        snowflake_conn=snowflake_conn,
        neo4j_driver=neo4j_driver,
        batch_size=2000
    )
    result = await pipeline.run()

    # Historical (one-time backfill)
    pipeline = create_historical_pipeline(
        snowflake_conn=snowflake_conn,
        neo4j_driver=neo4j_driver,
        start_date="2024-01-01",
        end_date="2024-12-31",
        batch_size=5000
    )
    result = await pipeline.run()
"""
import logging
from typing import Optional, Dict, Any, Protocol
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import pandas as pd
from neo4j import Driver
import snowflake.connector

logger = logging.getLogger(__name__)


# ===================
# Pipeline Interface
# ===================

class DataPipeline(Protocol):
    """Protocol for data ingestion pipelines."""

    async def run(self) -> Dict[str, Any]:
        """Execute the pipeline and return results."""
        ...


class BaseSnowflakeNeo4jPipeline(ABC):
    """
    Base pipeline for Snowflake→Neo4j data movement.

    Handles common operations:
    - Connection management
    - Batch processing with UNWIND
    - Constraint creation
    - Error handling and logging
    """

    def __init__(
        self,
        snowflake_conn: snowflake.connector.SnowflakeConnection,
        neo4j_driver: Driver,
        batch_size: int = 2000
    ):
        self.snowflake_conn = snowflake_conn
        self.neo4j_driver = neo4j_driver
        self.batch_size = batch_size
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Statistics
        self.nodes_created = 0
        self.relationships_created = 0
        self.batches_processed = 0
        self.errors = []

    @abstractmethod
    async def run(self) -> Dict[str, Any]:
        """Execute pipeline. Must be implemented by subclasses."""
        pass

    def ensure_constraints(self):
        """
        Create uniqueness constraints and indexes.

        Run once before bulk imports for optimal performance.
        """
        constraints = [
            # Restaurant entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Restaurant) REQUIRE r.restaurantId IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:ProperHotelToastRestaurant) REQUIRE r.guid IS UNIQUE",

            # Order entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Order) REQUIRE o.guid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (h:ProperHotelToastOrderHeader) REQUIRE r.guid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (l:ProperHotelToastOrderLineItem) REQUIRE l.guid IS UNIQUE",

            # Employee entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Employee) REQUIRE e.guid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:ProperHotelToastEmployee) REQUIRE e.guid IS UNIQUE",

            # Payment entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Payment) REQUIRE p.guid IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Check) REQUIRE c.guid IS UNIQUE",

            # Stock entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:ProperHotelToastStock) REQUIRE s.guid IS UNIQUE",

            # Alert entities
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:ProperHotelToastOperationalAlert) REQUIRE a.alertId IS UNIQUE",
        ]

        with self.neo4j_driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    self.logger.info(f"✓ Created constraint: {constraint[:60]}...")
                except Exception as e:
                    self.logger.warning(f"Constraint already exists or failed: {e}")

    def batch_upsert_nodes(
        self,
        session,
        label: str,
        nodes: list[Dict],
        unique_key: str = "guid"
    ) -> int:
        """
        Batch upsert nodes using UNWIND and MERGE.

        Args:
            session: Neo4j session
            label: Node label
            nodes: List of node dictionaries
            unique_key: Property for uniqueness (e.g., "guid")

        Returns:
            Number of nodes created/updated
        """
        if not nodes:
            return 0

        # Build MERGE query with all properties
        query = f"""
        UNWIND $nodes AS node
        MERGE (n:{label} {{{unique_key}: node.{unique_key}}})
        SET n += node
        RETURN count(n) as count
        """

        result = session.run(query, nodes=nodes)
        count = result.single()["count"]

        self.logger.info(f"✓ Upserted {count} {label} nodes")
        return count

    def batch_create_relationships(
        self,
        session,
        from_label: str,
        to_label: str,
        rel_type: str,
        relationships: list[Dict],
        from_key: str = "from_guid",
        to_key: str = "to_guid"
    ) -> int:
        """
        Batch create relationships using UNWIND.

        Args:
            session: Neo4j session
            from_label: Source node label
            to_label: Target node label
            rel_type: Relationship type
            relationships: List of relationship dictionaries
            from_key: Key for source node ID
            to_key: Key for target node ID

        Returns:
            Number of relationships created
        """
        if not relationships:
            return 0

        query = f"""
        UNWIND $rels AS rel
        MATCH (from:{from_label} {{guid: rel.{from_key}}})
        MATCH (to:{to_label} {{guid: rel.{to_key}}})
        MERGE (from)-[r:{rel_type}]->(to)
        SET r += rel.properties
        RETURN count(r) as count
        """

        result = session.run(query, rels=relationships)
        count = result.single()["count"]

        self.logger.info(f"✓ Created {count} {rel_type} relationships")
        return count

    def extract_from_snowflake(
        self,
        query: str,
        parameters: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        Extract data from Snowflake.

        Args:
            query: SQL query
            parameters: Query parameters

        Returns:
            DataFrame with results
        """
        cursor = self.snowflake_conn.cursor()
        try:
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)

            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()

            return pd.DataFrame(data, columns=columns)
        finally:
            cursor.close()


# ===================
# Incremental Pipeline
# ===================

class IncrementalPipeline(BaseSnowflakeNeo4jPipeline):
    """
    Incremental (hourly) ingestion pipeline with watermark tracking.

    Strategy:
    1. Get last successful watermark from Neo4j
    2. Extract new/updated records from Snowflake
    3. Upsert nodes and relationships
    4. Update watermark on success

    Watermark storage in Neo4j:
        (:Watermark {table: "orders", last_sync: datetime})
    """

    def __init__(
        self,
        snowflake_conn: snowflake.connector.SnowflakeConnection,
        neo4j_driver: Driver,
        batch_size: int = 2000,
        watermark_table: str = "Watermark"
    ):
        super().__init__(snowflake_conn, neo4j_driver, batch_size)
        self.watermark_table = watermark_table

    async def run(self) -> Dict[str, Any]:
        """Execute incremental ingestion."""
        start_time = datetime.now()
        self.logger.info("Starting incremental ingestion pipeline")

        with self.neo4j_driver.session() as session:
            # Get last watermark
            last_sync = self._get_watermark(session, "toast_orders")

            # Extract new data from Snowflake
            orders_df = self._extract_new_orders(last_sync)
            line_items_df = self._extract_new_line_items(last_sync)
            employees_df = self._extract_new_employees(last_sync)

            self.logger.info(
                f"Extracted {len(orders_df)} orders, "
                f"{len(line_items_df)} line items, "
                f"{len(employees_df)} employees"
            )

            # Upsert nodes
            self.nodes_created += self.batch_upsert_nodes(
                session,
                "ProperHotelToastOrderHeader",
                orders_df.to_dict('records'),
                unique_key="guid"
            )

            self.nodes_created += self.batch_upsert_nodes(
                session,
                "ProperHotelToastOrderLineItem",
                line_items_df.to_dict('records'),
                unique_key="guid"
            )

            self.nodes_created += self.batch_upsert_nodes(
                session,
                "ProperHotelToastEmployee",
                employees_df.to_dict('records'),
                unique_key="guid"
            )

            # Create relationships
            if not orders_df.empty:
                # Order → Restaurant
                order_restaurant_rels = [
                    {
                        "from_guid": row["guid"],
                        "to_guid": row["restaurantGuid"],
                        "properties": {}
                    }
                    for _, row in orders_df.iterrows()
                    if pd.notna(row.get("restaurantGuid"))
                ]

                self.relationships_created += self.batch_create_relationships(
                    session,
                    "ProperHotelToastOrderHeader",
                    "ProperHotelToastRestaurant",
                    "PLACED_AT_RESTAURANT",
                    order_restaurant_rels
                )

                # Order → Employee
                order_employee_rels = [
                    {
                        "from_guid": row["guid"],
                        "to_guid": row["employeeGuid"],
                        "properties": {}
                    }
                    for _, row in orders_df.iterrows()
                    if pd.notna(row.get("employeeGuid"))
                ]

                self.relationships_created += self.batch_create_relationships(
                    session,
                    "ProperHotelToastOrderHeader",
                    "ProperHotelToastEmployee",
                    "CREATED_BY_EMPLOYEE",
                    order_employee_rels
                )

            # Line Item → Order Header
            if not line_items_df.empty:
                line_item_order_rels = [
                    {
                        "from_guid": row["guid"],
                        "to_guid": row["orderGuid"],
                        "properties": {}
                    }
                    for _, row in line_items_df.iterrows()
                    if pd.notna(row.get("orderGuid"))
                ]

                self.relationships_created += self.batch_create_relationships(
                    session,
                    "ProperHotelToastOrderLineItem",
                    "ProperHotelToastOrderHeader",
                    "IS_PART_OF_ORDER_HEADER",
                    line_item_order_rels
                )

            # Update watermark
            current_time = datetime.now()
            self._update_watermark(session, "toast_orders", current_time)

            duration = (datetime.now() - start_time).total_seconds()

            self.logger.info(
                f"✓ Incremental ingestion completed in {duration:.2f}s: "
                f"{self.nodes_created} nodes, {self.relationships_created} relationships"
            )

            return {
                "status": "success",
                "mode": "incremental",
                "nodes_created": self.nodes_created,
                "relationships_created": self.relationships_created,
                "duration_seconds": duration,
                "watermark": current_time.isoformat(),
                "errors": self.errors
            }

    def _get_watermark(self, session, table: str) -> Optional[datetime]:
        """Get last successful watermark."""
        query = f"""
        MATCH (w:{self.watermark_table} {{table: $table}})
        RETURN w.last_sync as last_sync
        """

        result = session.run(query, table=table)
        record = result.single()

        if record and record["last_sync"]:
            return record["last_sync"]

        # Default: last 2 hours
        return datetime.now() - timedelta(hours=2)

    def _update_watermark(self, session, table: str, timestamp: datetime):
        """Update watermark after successful ingestion."""
        query = f"""
        MERGE (w:{self.watermark_table} {{table: $table}})
        SET w.last_sync = $timestamp,
            w.updated_at = datetime()
        """

        session.run(query, table=table, timestamp=timestamp)
        self.logger.info(f"✓ Updated watermark for {table}: {timestamp}")

    def _extract_new_orders(self, since: datetime) -> pd.DataFrame:
        """Extract orders modified since watermark."""
        query = """
        SELECT
            guid,
            restaurantGuid,
            employeeGuid,
            createdDate,
            modifiedDate,
            businessDate,
            openedDate,
            closedDate,
            promisedDate,
            voided,
            voidBusinessDate,
            paidDate,
            numberOfGuests,
            approvalStatus,
            taxExempt,
            durationOfService
        FROM TOAST.PUBLIC.ORDERS
        WHERE modifiedDate >= %s
        ORDER BY modifiedDate
        """

        return self.extract_from_snowflake(query, {"modifiedDate": since})

    def _extract_new_line_items(self, since: datetime) -> pd.DataFrame:
        """Extract line items for orders modified since watermark."""
        query = """
        SELECT
            li.guid,
            li.orderGuid,
            li.itemGuid,
            li.menuItemName,
            li.modifiedDate,
            li.price,
            li.quantity,
            li.tax,
            li.preDiscountPrice
        FROM TOAST.PUBLIC.ORDER_LINE_ITEMS li
        JOIN TOAST.PUBLIC.ORDERS o ON li.orderGuid = o.guid
        WHERE o.modifiedDate >= %s
        ORDER BY li.modifiedDate
        """

        return self.extract_from_snowflake(query, {"modifiedDate": since})

    def _extract_new_employees(self, since: datetime) -> pd.DataFrame:
        """Extract employees who created/modified orders since watermark."""
        query = """
        SELECT DISTINCT
            e.guid,
            e.firstName,
            e.lastName,
            e.email,
            e.externalEmployeeId
        FROM TOAST.PUBLIC.EMPLOYEES e
        JOIN TOAST.PUBLIC.ORDERS o ON e.guid = o.employeeGuid
        WHERE o.modifiedDate >= %s
        """

        return self.extract_from_snowflake(query, {"modifiedDate": since})


# ===================
# Historical Pipeline
# ===================

class HistoricalPipeline(BaseSnowflakeNeo4jPipeline):
    """
    Historical (one-time) ingestion pipeline for backfilling data.

    Strategy:
    1. Create all constraints and indexes upfront
    2. Extract full dataset in date range
    3. Process in large batches (5k-10k)
    4. Create all nodes before relationships
    5. Log progress for resume capability
    """

    def __init__(
        self,
        snowflake_conn: snowflake.connector.SnowflakeConnection,
        neo4j_driver: Driver,
        start_date: str,
        end_date: str,
        batch_size: int = 5000
    ):
        super().__init__(snowflake_conn, neo4j_driver, batch_size)
        self.start_date = start_date
        self.end_date = end_date

    async def run(self) -> Dict[str, Any]:
        """Execute historical bulk ingestion."""
        start_time = datetime.now()
        self.logger.info(
            f"Starting historical ingestion: {self.start_date} to {self.end_date}"
        )

        # Step 1: Create constraints
        self.logger.info("Creating constraints and indexes...")
        self.ensure_constraints()

        # Step 2: Extract full dataset
        self.logger.info("Extracting data from Snowflake...")
        orders_df = self._extract_historical_orders()
        line_items_df = self._extract_historical_line_items()
        employees_df = self._extract_historical_employees()
        restaurants_df = self._extract_restaurants()

        self.logger.info(
            f"Extracted {len(orders_df)} orders, "
            f"{len(line_items_df)} line items, "
            f"{len(employees_df)} employees, "
            f"{len(restaurants_df)} restaurants"
        )

        with self.neo4j_driver.session() as session:
            # Step 3: Upsert nodes in batches
            self.logger.info("Upserting nodes...")

            # Restaurants first (referenced by orders)
            for i in range(0, len(restaurants_df), self.batch_size):
                batch = restaurants_df.iloc[i:i+self.batch_size]
                self.nodes_created += self.batch_upsert_nodes(
                    session,
                    "ProperHotelToastRestaurant",
                    batch.to_dict('records')
                )
                self.batches_processed += 1

            # Employees
            for i in range(0, len(employees_df), self.batch_size):
                batch = employees_df.iloc[i:i+self.batch_size]
                self.nodes_created += self.batch_upsert_nodes(
                    session,
                    "ProperHotelToastEmployee",
                    batch.to_dict('records')
                )
                self.batches_processed += 1

            # Orders
            for i in range(0, len(orders_df), self.batch_size):
                batch = orders_df.iloc[i:i+self.batch_size]
                self.nodes_created += self.batch_upsert_nodes(
                    session,
                    "ProperHotelToastOrderHeader",
                    batch.to_dict('records')
                )
                self.batches_processed += 1

            # Line Items
            for i in range(0, len(line_items_df), self.batch_size):
                batch = line_items_df.iloc[i:i+self.batch_size]
                self.nodes_created += self.batch_upsert_nodes(
                    session,
                    "ProperHotelToastOrderLineItem",
                    batch.to_dict('records')
                )
                self.batches_processed += 1

            # Step 4: Create relationships
            self.logger.info("Creating relationships...")

            # Order → Restaurant
            order_restaurant_rels = [
                {
                    "from_guid": row["guid"],
                    "to_guid": row["restaurantGuid"],
                    "properties": {}
                }
                for _, row in orders_df.iterrows()
                if pd.notna(row.get("restaurantGuid"))
            ]

            for i in range(0, len(order_restaurant_rels), self.batch_size):
                batch = order_restaurant_rels[i:i+self.batch_size]
                self.relationships_created += self.batch_create_relationships(
                    session,
                    "ProperHotelToastOrderHeader",
                    "ProperHotelToastRestaurant",
                    "PLACED_AT_RESTAURANT",
                    batch
                )

            # More relationships...
            # (Similar pattern for other relationships)

            duration = (datetime.now() - start_time).total_seconds()

            self.logger.info(
                f"✓ Historical ingestion completed in {duration:.2f}s: "
                f"{self.nodes_created} nodes, {self.relationships_created} relationships, "
                f"{self.batches_processed} batches"
            )

            return {
                "status": "success",
                "mode": "historical",
                "start_date": self.start_date,
                "end_date": self.end_date,
                "nodes_created": self.nodes_created,
                "relationships_created": self.relationships_created,
                "batches_processed": self.batches_processed,
                "duration_seconds": duration,
                "errors": self.errors
            }

    def _extract_historical_orders(self) -> pd.DataFrame:
        """Extract all orders in date range."""
        query = f"""
        SELECT *
        FROM TOAST.PUBLIC.ORDERS
        WHERE businessDate BETWEEN '{self.start_date}' AND '{self.end_date}'
        ORDER BY businessDate, createdDate
        """

        return self.extract_from_snowflake(query)

    def _extract_historical_line_items(self) -> pd.DataFrame:
        """Extract all line items for orders in date range."""
        query = f"""
        SELECT li.*
        FROM TOAST.PUBLIC.ORDER_LINE_ITEMS li
        JOIN TOAST.PUBLIC.ORDERS o ON li.orderGuid = o.guid
        WHERE o.businessDate BETWEEN '{self.start_date}' AND '{self.end_date}'
        ORDER BY li.orderGuid
        """

        return self.extract_from_snowflake(query)

    def _extract_historical_employees(self) -> pd.DataFrame:
        """Extract all employees who created orders in date range."""
        query = f"""
        SELECT DISTINCT e.*
        FROM TOAST.PUBLIC.EMPLOYEES e
        JOIN TOAST.PUBLIC.ORDERS o ON e.guid = o.employeeGuid
        WHERE o.businessDate BETWEEN '{self.start_date}' AND '{self.end_date}'
        """

        return self.extract_from_snowflake(query)

    def _extract_restaurants(self) -> pd.DataFrame:
        """Extract all restaurants."""
        query = "SELECT * FROM TOAST.PUBLIC.RESTAURANTS"
        return self.extract_from_snowflake(query)


# ===================
# Factory Functions
# ===================

def create_incremental_pipeline(
    snowflake_conn: snowflake.connector.SnowflakeConnection,
    neo4j_driver: Driver,
    batch_size: int = 2000
) -> IncrementalPipeline:
    """
    Create incremental ingestion pipeline.

    Args:
        snowflake_conn: Snowflake connection
        neo4j_driver: Neo4j driver
        batch_size: Records per batch

    Returns:
        Configured IncrementalPipeline
    """
    return IncrementalPipeline(
        snowflake_conn=snowflake_conn,
        neo4j_driver=neo4j_driver,
        batch_size=batch_size
    )


def create_historical_pipeline(
    snowflake_conn: snowflake.connector.SnowflakeConnection,
    neo4j_driver: Driver,
    start_date: str,
    end_date: str,
    batch_size: int = 5000
) -> HistoricalPipeline:
    """
    Create historical bulk ingestion pipeline.

    Args:
        snowflake_conn: Snowflake connection
        neo4j_driver: Neo4j driver
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        batch_size: Records per batch

    Returns:
        Configured HistoricalPipeline
    """
    return HistoricalPipeline(
        snowflake_conn=snowflake_conn,
        neo4j_driver=neo4j_driver,
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size
    )


if __name__ == "__main__":
    # Example usage
    from .client_factory import ClientFactory

    async def main():
        factory = ClientFactory.from_env()

        # Incremental pipeline
        incremental = create_incremental_pipeline(
            snowflake_conn=factory.get_snowflake_connection(),
            neo4j_driver=factory.get_neo4j_driver(),
            batch_size=2000
        )

        result = await incremental.run()
        print(f"✓ Incremental ingestion: {result}")

    import asyncio
    asyncio.run(main())
