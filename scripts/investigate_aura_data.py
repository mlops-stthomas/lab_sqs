#!/usr/bin/env python3
"""
Investigate what data exists in your Aura knowledge graphs.

This script connects to your Neo4j Aura instances and provides:
- Node counts by label
- Relationship counts by type
- Sample data
- Data freshness (most recent records)
- Schema overview
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multi_neo4j_connector import MultiNeo4jConnector, KnowledgeGraph

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def investigate_knowledge_graph(kg: KnowledgeGraph, connector: MultiNeo4jConnector):
    """Deep dive into a knowledge graph."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Investigating: {kg.value.upper()} Knowledge Graph")
    logger.info(f"{'='*60}")

    try:
        # Get schema
        schema = connector.get_schema(kg)

        # Print overview
        logger.info(f"\n📊 Overview:")
        logger.info(f"  Total Nodes: {schema['total_nodes']:,}")
        logger.info(f"  Total Relationships: {schema['total_relationships']:,}")
        logger.info(f"  Node Labels: {len(schema['node_labels'])}")
        logger.info(f"  Relationship Types: {len(schema['relationship_types'])}")

        # Print top 10 node labels
        logger.info(f"\n📦 Top Node Labels:")
        for label_info in schema['node_labels'][:10]:
            label = label_info['label']
            count = label_info['count']
            logger.info(f"  {label:<30} {count:>10,} nodes")

        # Print top 10 relationship types
        logger.info(f"\n🔗 Top Relationship Types:")
        for rel_info in schema['relationship_types'][:10]:
            rel_type = rel_info['type']
            count = rel_info['count']
            logger.info(f"  {rel_type:<30} {count:>10,} relationships")

        # Check for common operational data
        driver = connector.connect(kg)
        with driver.session(database=connector.configs[kg]['database']) as session:

            # Check for Orders
            try:
                result = session.run("""
                    MATCH (o:Order)
                    WITH o ORDER BY o.createdAt DESC LIMIT 1
                    RETURN o.createdAt as latest_order,
                           date() as today,
                           date(o.createdAt) as order_date
                """)
                record = result.single()
                if record:
                    logger.info(f"\n📅 Data Freshness (Orders):")
                    logger.info(f"  Latest Order: {record['latest_order']}")
                    logger.info(f"  Order Date: {record['order_date']}")
                    logger.info(f"  Today: {record['today']}")

                    # Count today's orders
                    result = session.run("""
                        MATCH (o:Order)
                        WHERE date(o.createdAt) = date()
                        RETURN count(o) as today_count
                    """)
                    today_count = result.single()['today_count']
                    logger.info(f"  Orders Today: {today_count:,}")
            except Exception as e:
                logger.debug(f"No Order data or error: {e}")

            # Check for Restaurants
            try:
                result = session.run("""
                    MATCH (r:Restaurant)
                    RETURN count(r) as restaurant_count,
                           collect(r.restaurantName)[0..5] as sample_names
                """)
                record = result.single()
                if record and record['restaurant_count'] > 0:
                    logger.info(f"\n🏪 Restaurants:")
                    logger.info(f"  Total: {record['restaurant_count']}")
                    logger.info(f"  Sample Names:")
                    for name in record['sample_names']:
                        if name:
                            logger.info(f"    - {name}")
            except Exception as e:
                logger.debug(f"No Restaurant data or error: {e}")

            # Check for Employees
            try:
                result = session.run("""
                    MATCH (e:Employee)
                    RETURN count(e) as employee_count
                """)
                record = result.single()
                if record and record['employee_count'] > 0:
                    logger.info(f"\n👥 Employees:")
                    logger.info(f"  Total: {record['employee_count']:,}")
            except Exception as e:
                logger.debug(f"No Employee data or error: {e}")

            # Check for vector embeddings (for Aura Agent readiness)
            try:
                result = session.run("""
                    CALL db.index.vector.queryNodes('excerpt_embedding', 5, [1.0, 2.0, 3.0])
                    YIELD node, score
                    RETURN count(node) as has_vector_index
                """)
                logger.info(f"\n🔍 Vector Search Ready:")
                logger.info(f"  ✓ Vector index 'excerpt_embedding' exists")
            except Exception as e:
                logger.info(f"\n🔍 Vector Search:")
                logger.info(f"  ✗ No vector indexes found")
                logger.info(f"    (Required for Aura Agent similarity search)")

            # Suggest import opportunities
            logger.info(f"\n💡 Import Opportunities:")

            # Check if data is stale
            try:
                result = session.run("""
                    MATCH (o:Order)
                    WITH o ORDER BY o.createdAt DESC LIMIT 1
                    RETURN date(o.createdAt) < date() - duration('P1D') as is_stale
                """)
                record = result.single()
                if record and record['is_stale']:
                    logger.info(f"  - Order data is >1 day old - consider daily imports")
            except:
                pass

            # Check for missing employee data
            try:
                result = session.run("""
                    MATCH (o:Order)
                    WHERE NOT EXISTS((o)-[:CREATED_BY]->(:Employee))
                    RETURN count(o) as orders_without_employee
                """)
                record = result.single()
                if record and record['orders_without_employee'] > 0:
                    logger.info(f"  - {record['orders_without_employee']:,} orders missing employee link")
            except:
                pass

    except Exception as e:
        logger.error(f"Error investigating {kg.value}: {e}")
        logger.exception("Full traceback:")


def check_import_readiness(connector: MultiNeo4jConnector):
    """Check if instances are ready for Aura Import API."""
    logger.info(f"\n{'='*60}")
    logger.info("Aura Import API Readiness Check")
    logger.info(f"{'='*60}")

    # Try to get instance IDs
    try:
        instances = connector.list_instances() if hasattr(connector, 'list_instances') else []

        if instances:
            logger.info(f"\n✓ Found {len(instances)} Aura instances")
            for inst in instances:
                logger.info(f"  - {inst.name} (ID: {inst.id})")
                logger.info(f"    Tier: {inst.tier}, Status: {inst.status}")
        else:
            logger.warning("\n⚠ Could not list Aura instances")
            logger.info("  Make sure AURA_ORGANIZATION_ID and AURA_PROJECT_ID are set")
    except Exception as e:
        logger.warning(f"\n⚠ Could not check instances: {e}")

    logger.info(f"\n📋 Next Steps for Import Setup:")
    logger.info("  1. Go to https://console.neo4j.io/tools/import")
    logger.info("  2. Create a data source (Snowflake, BigQuery, S3)")
    logger.info("  3. Build graph model with visual builder")
    logger.info("  4. Note the import model ID from the URL")
    logger.info("  5. Use scripts/setup_incremental_pipeline.py")


def main():
    parser = argparse.ArgumentParser(
        description="Investigate data in Aura knowledge graphs"
    )
    parser.add_argument(
        "--kg",
        choices=["melting-pot", "proper", "tray", "all"],
        default="all",
        help="Which knowledge graph to investigate"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export investigation results to JSON"
    )

    args = parser.parse_args()

    logger.info("\n🔍 Starting Aura Data Investigation...")

    # Initialize connector
    try:
        connector = MultiNeo4jConnector()
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j connector: {e}")
        logger.error("Make sure Neo4j credentials are set in .env")
        sys.exit(1)

    # Map KG names to enums
    kg_map = {
        "melting-pot": KnowledgeGraph.MELTING_POT,
        "proper": KnowledgeGraph.PROPER,
        "tray": KnowledgeGraph.TRAY
    }

    # Investigate knowledge graphs
    if args.kg == "all":
        for kg_name, kg_enum in kg_map.items():
            investigate_knowledge_graph(kg_enum, connector)
    else:
        investigate_knowledge_graph(kg_map[args.kg], connector)

    # Check import readiness
    check_import_readiness(connector)

    logger.info(f"\n{'='*60}")
    logger.info("Investigation Complete!")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
