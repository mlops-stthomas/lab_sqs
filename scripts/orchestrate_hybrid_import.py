#!/usr/bin/env python3
"""
Hybrid import orchestration: Combines Snowflake procedures with Aura Import API.

Strategy:
1. Use Aura Import API for simple, high-volume incremental loads
2. Use Snowflake procedures for complex transformations
3. Coordinate both for complete data pipeline

Usage:
    python scripts/orchestrate_hybrid_import.py --mode daily
    python scripts/orchestrate_hybrid_import.py --mode historical
"""
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_manager import AuraManager
from src.aura_import_client import print_job_progress

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridImportOrchestrator:
    """Orchestrates both Aura Import API and Snowflake procedures."""

    def __init__(self):
        self.aura_manager = AuraManager()
        self.aura_manager.setup_import_client()

    def daily_incremental_sync(self) -> Dict[str, Any]:
        """
        Daily incremental sync using Aura Import API (optimized for speed).

        This handles:
        - Orders from last 24 hours
        - Checks from last 24 hours
        - Simple node/relationship creation
        """
        logger.info("="*60)
        logger.info("Daily Incremental Sync (Aura Import API)")
        logger.info("="*60)

        results = {
            "start_time": datetime.now().isoformat(),
            "jobs": [],
            "status": "unknown"
        }

        # Define import models for incremental data
        incremental_models = [
            {
                "name": "daily_orders",
                "import_model_id": "e4cd23ef-c4ec-4e27-8d5d-0e890f496388",  # Your model
                "instance_id": "705c1e42",
                "description": "Orders from last 24 hours"
            }
            # Add more models for Checks, Selections, etc.
        ]

        for model_config in incremental_models:
            try:
                logger.info(f"\nImporting: {model_config['name']}")
                logger.info(f"  Description: {model_config['description']}")

                # Trigger import job
                job = self.aura_manager.create_import_job(
                    import_model_id=model_config['import_model_id'],
                    db_id=model_config['instance_id']
                )

                logger.info(f"  ✓ Job created: {job.id}")

                # Wait for completion (with timeout)
                final_job = self.aura_manager.wait_for_import_completion(
                    job.id,
                    poll_interval=30,
                    max_wait=1800,  # 30 min timeout
                    callback=print_job_progress
                )

                job_result = {
                    "name": model_config['name'],
                    "job_id": final_job.id,
                    "state": final_job.state,
                    "percentage_complete": final_job.progress.percentage_complete if final_job.progress else 0
                }

                if final_job.state == "Completed":
                    logger.info(f"  ✓ Import completed: {model_config['name']}")
                    job_result["status"] = "success"
                else:
                    logger.error(f"  ✗ Import failed: {model_config['name']}")
                    job_result["status"] = "failed"
                    job_result["error"] = final_job.progress.exit_status_message if final_job.progress else "Unknown error"

                results["jobs"].append(job_result)

            except Exception as e:
                logger.exception(f"Error importing {model_config['name']}: {e}")
                results["jobs"].append({
                    "name": model_config['name'],
                    "status": "error",
                    "error": str(e)
                })

        # Determine overall status
        all_success = all(j.get("status") == "success" for j in results["jobs"])
        results["status"] = "success" if all_success else "partial_failure"
        results["end_time"] = datetime.now().isoformat()

        return results

    def historical_onboarding(self, use_snowflake_proc: bool = True) -> Dict[str, Any]:
        """
        Historical onboarding with optional Snowflake procedure fallback.

        Strategy:
        1. Try Aura Import API first (faster, optimized)
        2. Fall back to Snowflake procedure if needed (complex transformations)
        """
        logger.info("="*60)
        logger.info("Historical Onboarding")
        logger.info("="*60)

        results = {
            "start_time": datetime.now().isoformat(),
            "method": "unknown",
            "status": "unknown"
        }

        if use_snowflake_proc:
            logger.info("\nUsing Snowflake procedure for historical load")
            logger.info("  (Recommended for complex transformations)")

            # Call Snowflake procedure
            # Note: This would require snowflake-connector-python
            try:
                results["method"] = "snowflake_procedure"
                results["procedure"] = "SP_NEO4J_SYNC_HISTORICAL_FULL"

                logger.info("\n  To run the Snowflake procedure:")
                logger.info("  1. Connect to Snowflake")
                logger.info("  2. Execute:")
                logger.info("     CALL FLORAOS.MELTING.SP_NEO4J_SYNC_HISTORICAL_FULL();")
                logger.info("\n  Or use Python:")
                logger.info("     from src.snowflake_connector import SnowflakeConnector")
                logger.info("     conn = SnowflakeConnector()")
                logger.info("     results = conn.execute('CALL FLORAOS.MELTING.SP_NEO4J_SYNC_HISTORICAL_FULL()')")

                results["status"] = "manual_execution_required"

            except Exception as e:
                logger.exception(f"Error with Snowflake procedure: {e}")
                results["status"] = "error"
                results["error"] = str(e)

        else:
            logger.info("\nUsing Aura Import API for historical load")
            logger.info("  (Recommended for simple, high-volume loads)")

            # Use Aura Import API with historical import model
            try:
                from src.aura_manager import AuraManager

                # Trigger historical import
                # This would use a different import model configured for ALL data
                historical_model_id = "your-historical-model-id"  # Need to create this

                logger.info(f"\n  Import Model ID: {historical_model_id}")
                logger.info("  Note: Create historical import model in Aura Console first")
                logger.info("        (Include ALL data, not just last 24 hours)")

                results["method"] = "aura_import_api"
                results["status"] = "pending_model_creation"

            except Exception as e:
                logger.exception(f"Error with Aura Import: {e}")
                results["status"] = "error"
                results["error"] = str(e)

        results["end_time"] = datetime.now().isoformat()
        return results

    def validate_data_sync(self) -> Dict[str, Any]:
        """
        Validate that data is properly synced between Snowflake and Neo4j.

        Checks:
        - Node counts match
        - Relationship counts match
        - Data freshness (latest records)
        """
        logger.info("="*60)
        logger.info("Data Sync Validation")
        logger.info("="*60)

        # This would query both Snowflake and Neo4j to compare counts
        logger.info("\nValidation checks:")
        logger.info("  1. Count orders in Snowflake vs Neo4j")
        logger.info("  2. Count checks in Snowflake vs Neo4j")
        logger.info("  3. Verify latest record timestamps match")
        logger.info("  4. Check for orphaned relationships")

        # Placeholder - would implement actual validation
        return {
            "status": "not_implemented",
            "message": "Run validation queries manually for now"
        }


def main():
    parser = argparse.ArgumentParser(
        description="Hybrid import orchestration"
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "historical", "validate"],
        required=True,
        help="Import mode"
    )
    parser.add_argument(
        "--snowflake-proc",
        action="store_true",
        help="Use Snowflake procedure for historical (default: Aura Import API)"
    )

    args = parser.parse_args()

    # Initialize orchestrator
    try:
        orchestrator = HybridImportOrchestrator()
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}")
        sys.exit(1)

    # Execute based on mode
    if args.mode == "daily":
        results = orchestrator.daily_incremental_sync()

    elif args.mode == "historical":
        results = orchestrator.historical_onboarding(
            use_snowflake_proc=args.snowflake_proc
        )

    elif args.mode == "validate":
        results = orchestrator.validate_data_sync()

    # Print summary
    logger.info("\n" + "="*60)
    logger.info("Execution Summary")
    logger.info("="*60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Status: {results.get('status')}")

    if results.get("status") == "success":
        logger.info("\n✓ All imports completed successfully!")
    elif results.get("status") == "partial_failure":
        logger.warning("\n⚠ Some imports failed - check logs")
    else:
        logger.error(f"\n✗ Import failed: {results.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
