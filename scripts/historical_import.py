#!/usr/bin/env python3
"""
One-time historical data import from Snowflake to Neo4j.

This script handles bulk imports of historical data, with support for:
- Large dataset imports with progress monitoring
- Verification of import results
- Rollback capabilities (via Neo4j snapshots)

Usage:
    # Basic historical import
    python scripts/historical_import.py \
        --import-model-id fc371c86-7966-40b5-82b3-93f196d0b928 \
        --instance-id 705c1e42

    # With verification
    python scripts/historical_import.py \
        --import-model-id fc371c86-7966-40b5-82b3-93f196d0b928 \
        --instance-id 705c1e42 \
        --verify

    # Create snapshot before import (for rollback)
    python scripts/historical_import.py \
        --import-model-id fc371c86-7966-40b5-82b3-93f196d0b928 \
        --instance-id 705c1e42 \
        --create-snapshot
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_manager import AuraManager
from src.aura_import_client import ImportJob, print_job_progress
from src.multi_neo4j_connector import MultiNeo4jConnector, KnowledgeGraph

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalImporter:
    """Manages one-time historical data imports."""

    def __init__(self):
        self.manager = AuraManager()
        self.neo4j_connector: Optional[MultiNeo4jConnector] = None

        # Initialize Aura Import client
        try:
            self.manager.setup_import_client()
            logger.info("✓ Aura Import API initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Aura Import client: {e}")
            raise

    def create_pre_import_snapshot(self, instance_id: str) -> Optional[str]:
        """
        Create snapshot before import for rollback capability.

        Args:
            instance_id: Aura instance ID

        Returns:
            Snapshot ID or None if failed
        """
        logger.info("Creating pre-import snapshot...")
        logger.info("Note: Snapshots are only available on paid Aura tiers")

        try:
            # TODO: Implement via Aura CLI when snapshot commands are available
            # For now, log instructions for manual snapshot
            logger.info("\nTo create a snapshot manually:")
            logger.info("1. Go to https://console.neo4j.io")
            logger.info(f"2. Navigate to instance {instance_id}")
            logger.info("3. Go to Snapshots tab")
            logger.info("4. Click 'Create Snapshot'")
            logger.info("5. Name it: pre_historical_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

            input("\nPress Enter when snapshot is created (or Ctrl+C to continue without snapshot)...")

            return f"manual_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        except KeyboardInterrupt:
            logger.warning("\nContinuing without snapshot...")
            return None
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return None

    def get_pre_import_stats(self, instance_id: str, kg: KnowledgeGraph) -> Dict[str, Any]:
        """
        Get database statistics before import for verification.

        Args:
            instance_id: Aura instance ID
            kg: Knowledge graph enum

        Returns:
            Pre-import statistics
        """
        logger.info("Collecting pre-import statistics...")

        try:
            if not self.neo4j_connector:
                self.neo4j_connector = MultiNeo4jConnector()

            schema = self.neo4j_connector.get_schema(kg)

            stats = {
                "timestamp": datetime.now().isoformat(),
                "instance_id": instance_id,
                "total_nodes": schema["total_nodes"],
                "total_relationships": schema["total_relationships"],
                "node_labels": schema["node_labels"],
                "relationship_types": schema["relationship_types"]
            }

            logger.info(f"Pre-import stats:")
            logger.info(f"  Total nodes: {stats['total_nodes']:,}")
            logger.info(f"  Total relationships: {stats['total_relationships']:,}")
            logger.info(f"  Node labels: {len(stats['node_labels'])}")
            logger.info(f"  Relationship types: {len(stats['relationship_types'])}")

            return stats

        except Exception as e:
            logger.warning(f"Could not collect pre-import stats: {e}")
            return {}

    def execute_historical_import(
        self,
        import_model_id: str,
        instance_id: str,
        timeout: int = 7200  # 2 hours default
    ) -> ImportJob:
        """
        Execute historical data import.

        Args:
            import_model_id: Aura Import model ID for historical data
            instance_id: Target Aura instance ID
            timeout: Maximum wait time in seconds

        Returns:
            Final ImportJob state
        """
        logger.info("="*60)
        logger.info("Starting Historical Data Import")
        logger.info("="*60)
        logger.info(f"Import Model ID: {import_model_id}")
        logger.info(f"Target Instance: {instance_id}")
        logger.info(f"Timeout: {timeout}s ({timeout // 60} minutes)")

        # Trigger import job
        logger.info("\nTriggering import job...")
        job = self.manager.create_import_job(
            import_model_id=import_model_id,
            db_id=instance_id
        )

        logger.info(f"✓ Import job created: {job.id}")
        logger.info(f"  Initial state: {job.state}")
        logger.info(f"  Type: {job.import_type}")

        # Wait for completion with progress tracking
        logger.info(f"\nMonitoring import progress (checking every 30s)...")
        logger.info("This may take a while for large datasets...")

        try:
            final_job = self.manager.wait_for_import_completion(
                job.id,
                poll_interval=30,
                max_wait=timeout,
                callback=print_job_progress
            )

            return final_job

        except TimeoutError:
            logger.error(f"\n✗ Import timed out after {timeout}s")
            logger.error(f"  Job ID: {job.id}")
            logger.error("  You can check status later with:")
            logger.error(f"  python scripts/check_import_status.py --job-id {job.id}")
            raise

    def verify_import(
        self,
        instance_id: str,
        kg: KnowledgeGraph,
        pre_import_stats: Dict[str, Any]
    ) -> bool:
        """
        Verify import completed successfully.

        Args:
            instance_id: Aura instance ID
            kg: Knowledge graph enum
            pre_import_stats: Statistics collected before import

        Returns:
            True if verification passed
        """
        logger.info("\n" + "="*60)
        logger.info("Verifying Import Results")
        logger.info("="*60)

        try:
            if not self.neo4j_connector:
                self.neo4j_connector = MultiNeo4jConnector()

            post_schema = self.neo4j_connector.get_schema(kg)

            post_nodes = post_schema["total_nodes"]
            post_rels = post_schema["total_relationships"]

            pre_nodes = pre_import_stats.get("total_nodes", 0)
            pre_rels = pre_import_stats.get("total_relationships", 0)

            nodes_added = post_nodes - pre_nodes
            rels_added = post_rels - pre_rels

            logger.info("Post-import stats:")
            logger.info(f"  Total nodes: {post_nodes:,} (+{nodes_added:,})")
            logger.info(f"  Total relationships: {post_rels:,} (+{rels_added:,})")

            # Basic sanity checks
            if nodes_added == 0 and rels_added == 0:
                logger.warning("⚠ No new nodes or relationships added!")
                logger.warning("  This might indicate:")
                logger.warning("  - Import model has no data to import")
                logger.warning("  - All data already exists (idempotent import)")
                logger.warning("  - Import failed silently")
                return False

            if nodes_added < 0 or rels_added < 0:
                logger.error("✗ Data was deleted during import!")
                logger.error("  This should never happen - check for errors")
                return False

            # Check node label distribution
            logger.info("\nNode label changes:")
            for label_info in post_schema["node_labels"][:10]:  # Top 10
                label = label_info["label"]
                post_count = label_info["count"]

                pre_count = next(
                    (l["count"] for l in pre_import_stats.get("node_labels", [])
                     if l["label"] == label),
                    0
                )

                delta = post_count - pre_count
                if delta > 0:
                    logger.info(f"  {label}: {post_count:,} (+{delta:,})")

            logger.info("\n✓ Import verification passed")
            return True

        except Exception as e:
            logger.error(f"✗ Verification failed: {e}")
            return False

    def save_import_report(
        self,
        import_model_id: str,
        instance_id: str,
        job: ImportJob,
        pre_stats: Dict[str, Any],
        snapshot_id: Optional[str] = None
    ):
        """Save detailed import report."""
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        report = {
            "timestamp": datetime.now().isoformat(),
            "import_type": "historical",
            "import_model_id": import_model_id,
            "instance_id": instance_id,
            "snapshot_id": snapshot_id,
            "pre_import_stats": pre_stats,
            "job": {
                "id": job.id,
                "state": job.state,
                "import_type": job.import_type,
                "data_source_name": job.data_source_name
            }
        }

        if job.progress:
            report["job"]["progress"] = {
                "percentage_complete": job.progress.percentage_complete,
                "exit_status": job.progress.exit_status_state,
                "exit_message": job.progress.exit_status_message
            }

        report_file = reports_dir / f"historical_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"\n✓ Import report saved: {report_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Execute one-time historical data import"
    )
    parser.add_argument(
        "--import-model-id",
        required=True,
        help="Aura Import model ID for historical data"
    )
    parser.add_argument(
        "--instance-id",
        required=True,
        help="Target Neo4j Aura instance ID"
    )
    parser.add_argument(
        "--knowledge-graph",
        default="melting-pot",
        choices=["melting-pot", "proper", "tray"],
        help="Knowledge graph name for verification"
    )
    parser.add_argument(
        "--create-snapshot",
        action="store_true",
        help="Create snapshot before import (for rollback)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify import results after completion"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Import timeout in seconds (default: 7200 = 2 hours)"
    )

    args = parser.parse_args()

    # Map KG name to enum
    kg_map = {
        "melting-pot": KnowledgeGraph.MELTING_POT,
        "proper": KnowledgeGraph.PROPER,
        "tray": KnowledgeGraph.TRAY
    }
    kg = kg_map[args.knowledge_graph]

    # Initialize importer
    try:
        importer = HistoricalImporter()
    except Exception as e:
        logger.error(f"Failed to initialize importer: {e}")
        sys.exit(1)

    # Create snapshot if requested
    snapshot_id = None
    if args.create_snapshot:
        snapshot_id = importer.create_pre_import_snapshot(args.instance_id)

    # Collect pre-import stats
    pre_stats = {}
    if args.verify:
        pre_stats = importer.get_pre_import_stats(args.instance_id, kg)

    # Execute import
    try:
        final_job = importer.execute_historical_import(
            import_model_id=args.import_model_id,
            instance_id=args.instance_id,
            timeout=args.timeout
        )

        # Check final state
        if final_job.state == "Completed":
            logger.info("\n" + "="*60)
            logger.info("✓ Historical Import Completed Successfully")
            logger.info("="*60)
            logger.info(f"Job ID: {final_job.id}")

            if final_job.progress:
                logger.info(f"Progress: {final_job.progress.percentage_complete}%")
                logger.info(f"Exit status: {final_job.progress.exit_status_state}")

            # Verify if requested
            if args.verify:
                verification_passed = importer.verify_import(
                    args.instance_id,
                    kg,
                    pre_stats
                )

                if not verification_passed:
                    logger.warning("\n⚠ Verification failed - review import carefully")
                    if snapshot_id:
                        logger.info(f"Rollback snapshot available: {snapshot_id}")

            # Save report
            importer.save_import_report(
                args.import_model_id,
                args.instance_id,
                final_job,
                pre_stats,
                snapshot_id
            )

        elif final_job.state == "Failed":
            logger.error("\n" + "="*60)
            logger.error("✗ Historical Import Failed")
            logger.error("="*60)
            logger.error(f"Job ID: {final_job.id}")
            if final_job.progress:
                logger.error(f"Error: {final_job.progress.exit_status_message}")

            if snapshot_id:
                logger.info(f"\nRollback snapshot available: {snapshot_id}")

            sys.exit(1)

        elif final_job.state == "Cancelled":
            logger.warning("\n⚠ Import was cancelled")
            sys.exit(1)

    except TimeoutError:
        logger.error("\n✗ Import timed out")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
