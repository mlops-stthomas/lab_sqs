#!/usr/bin/env python3
"""
Test a specific import model by triggering a job.

Usage:
    python scripts/test_import_model.py \
        --import-model-id e4cd23ef-c4ec-4e27-8d5d-0e890f496388 \
        --instance-id 705c1e42
"""
import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_manager import AuraManager
from src.aura_import_client import print_job_progress

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_import_model(import_model_id: str, instance_id: str, wait: bool = True):
    """Test an import model by triggering a job."""

    logger.info("="*60)
    logger.info("Testing Import Model")
    logger.info("="*60)
    logger.info(f"Import Model ID: {import_model_id}")
    logger.info(f"Target Instance: {instance_id}")

    # Initialize manager
    try:
        manager = AuraManager()
        manager.setup_import_client()
        logger.info("✓ Aura Manager initialized")
    except Exception as e:
        logger.error(f"✗ Failed to initialize Aura Manager: {e}")
        logger.error("Make sure AURA_API_CLIENT_ID, AURA_API_CLIENT_SECRET,")
        logger.error("AURA_ORGANIZATION_ID, and AURA_PROJECT_ID are set in .env")
        sys.exit(1)

    # Trigger import job
    try:
        logger.info("\nTriggering import job...")
        job = manager.create_import_job(
            import_model_id=import_model_id,
            db_id=instance_id
        )

        logger.info("="*60)
        logger.info("✓ Import Job Created Successfully!")
        logger.info("="*60)
        logger.info(f"Job ID: {job.id}")
        logger.info(f"State: {job.state}")
        logger.info(f"Type: {job.import_type}")

        if job.data_source_name:
            logger.info(f"Data Source: {job.data_source_name}")

        if not wait:
            logger.info("\nTo monitor this job:")
            logger.info(f"  python scripts/check_import_status.py --job-id {job.id} --watch")
            return job

        # Wait for completion
        logger.info("\nMonitoring job progress...")
        logger.info("(This may take a few minutes depending on data volume)")

        final_job = manager.wait_for_import_completion(
            job.id,
            poll_interval=30,
            max_wait=1800,  # 30 minutes
            callback=print_job_progress
        )

        # Check final state
        logger.info("\n" + "="*60)
        if final_job.state == "Completed":
            logger.info("✓ Import Completed Successfully!")
            logger.info("="*60)

            if final_job.progress:
                logger.info(f"Progress: {final_job.progress.percentage_complete}%")
                logger.info(f"Exit Status: {final_job.progress.exit_status_state}")

                if final_job.progress.nodes_processed:
                    logger.info("\nNodes Processed:")
                    for node_info in final_job.progress.nodes_processed[:5]:
                        labels = node_info.get('labels', [])
                        processed = node_info.get('processed_rows', 0)
                        total = node_info.get('total_rows', 0)
                        created = node_info.get('created_nodes', 0)
                        logger.info(f"  {labels}: {processed:,}/{total:,} rows ({created:,} created)")

            logger.info("\nNext Steps:")
            logger.info("  1. Verify data in Neo4j Browser")
            logger.info("  2. Set up automated pipeline:")
            logger.info(f"     python scripts/setup_incremental_pipeline.py \\")
            logger.info(f"       --import-model-id {import_model_id} \\")
            logger.info(f"       --instance-id {instance_id} \\")
            logger.info(f"       --schedule '0 * * * *'")

        elif final_job.state == "Failed":
            logger.error("✗ Import Failed")
            logger.error("="*60)
            if final_job.progress:
                logger.error(f"Error: {final_job.progress.exit_status_message}")

            logger.error("\nTroubleshooting:")
            logger.error("  1. Check import model configuration in Aura Console")
            logger.error("  2. Verify data source connection")
            logger.error("  3. Test with sample data first")

        return final_job

    except Exception as e:
        logger.exception(f"\n✗ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Test an import model by triggering a job"
    )
    parser.add_argument(
        "--import-model-id",
        required=True,
        help="Import model ID from Aura Console URL"
    )
    parser.add_argument(
        "--instance-id",
        required=True,
        help="Target Neo4j Aura instance ID"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for job completion"
    )

    args = parser.parse_args()

    test_import_model(
        import_model_id=args.import_model_id,
        instance_id=args.instance_id,
        wait=not args.no_wait
    )


if __name__ == "__main__":
    main()
