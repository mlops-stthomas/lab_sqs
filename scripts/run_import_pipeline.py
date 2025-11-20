#!/usr/bin/env python3
"""
Execute configured import pipelines.

This script reads pipeline configurations and executes import jobs.
Designed to be called by cron, Airflow, or Cloud Workflows.

Usage:
    # Run specific pipeline
    python scripts/run_import_pipeline.py --pipeline-name snowflake_incremental_sync

    # Run all enabled pipelines
    python scripts/run_import_pipeline.py --all

    # Dry run (don't actually trigger import)
    python scripts/run_import_pipeline.py --pipeline-name test_pipeline --dry-run
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_manager import AuraManager
from src.aura_import_client import ImportJob, print_job_progress

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineExecutor:
    """Executes configured import pipelines."""

    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = config_dir
        self.config_file = config_dir / "import_pipelines.json"
        self.manager = AuraManager()

        # Initialize import client
        try:
            self.manager.setup_import_client()
        except Exception as e:
            logger.error(f"Failed to initialize Aura Import client: {e}")
            raise

    def load_pipelines(self) -> list[Dict[str, Any]]:
        """Load all pipeline configurations."""
        if not self.config_file.exists():
            logger.error(f"Configuration file not found: {self.config_file}")
            logger.info("Run setup_incremental_pipeline.py to create pipeline configs")
            return []

        with open(self.config_file) as f:
            pipelines = json.load(f)

        return pipelines

    def get_pipeline(self, name: str) -> Optional[Dict[str, Any]]:
        """Get specific pipeline configuration by name."""
        pipelines = self.load_pipelines()
        return next((p for p in pipelines if p.get("name") == name), None)

    def execute_pipeline(
        self,
        pipeline: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a single import pipeline.

        Args:
            pipeline: Pipeline configuration
            dry_run: If True, don't actually trigger import

        Returns:
            Execution result dict
        """
        name = pipeline["name"]
        import_model_id = pipeline["import_model_id"]
        instance_id = pipeline["instance_id"]
        timeout = pipeline.get("timeout_seconds", 3600)
        retry_policy = pipeline.get("retry_policy", {})

        logger.info("="*60)
        logger.info(f"Executing Pipeline: {name}")
        logger.info("="*60)
        logger.info(f"Import Model ID: {import_model_id}")
        logger.info(f"Target Instance: {instance_id}")
        logger.info(f"Timeout: {timeout}s")

        result = {
            "pipeline": name,
            "start_time": datetime.now().isoformat(),
            "status": "unknown",
            "job_id": None,
            "error": None
        }

        if dry_run:
            logger.info("✓ DRY RUN - Import job would be triggered here")
            result["status"] = "dry_run_success"
            return result

        # Execute with retries
        max_retries = retry_policy.get("max_retries", 3)
        retry_delay = retry_policy.get("retry_delay_seconds", 300)

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.warning(f"Retry attempt {attempt}/{max_retries}")
                    time.sleep(retry_delay)

                # Trigger import job
                logger.info("Creating import job...")
                job = self.manager.create_import_job(
                    import_model_id=import_model_id,
                    db_id=instance_id
                )

                result["job_id"] = job.id
                logger.info(f"✓ Import job created: {job.id}")
                logger.info(f"  Initial state: {job.state}")

                # Wait for completion
                logger.info(f"Waiting for completion (max {timeout}s)...")
                final_job = self.manager.wait_for_import_completion(
                    job.id,
                    poll_interval=30,
                    max_wait=timeout,
                    callback=print_job_progress
                )

                # Check final state
                if final_job.state == "Completed":
                    logger.info("="*60)
                    logger.info(f"✓ Pipeline '{name}' completed successfully")
                    logger.info(f"  Job ID: {final_job.id}")
                    if final_job.progress:
                        logger.info(f"  Nodes processed: {final_job.progress.nodes_processed}")
                        logger.info(f"  Relationships processed: {final_job.progress.relationships_processed}")
                    logger.info("="*60)

                    result["status"] = "success"
                    result["end_time"] = datetime.now().isoformat()
                    return result

                elif final_job.state == "Failed":
                    error_msg = final_job.progress.exit_status_message if final_job.progress else "Unknown error"
                    logger.error(f"✗ Import job failed: {error_msg}")
                    result["error"] = error_msg

                    # Don't retry on permanent failures
                    if "schema" in error_msg.lower() or "configuration" in error_msg.lower():
                        logger.error("Configuration error detected - not retrying")
                        break

                    # Retry on transient failures
                    if attempt < max_retries:
                        logger.warning(f"Retrying in {retry_delay}s...")
                        continue

                elif final_job.state == "Cancelled":
                    logger.warning("Import job was cancelled")
                    result["error"] = "Job cancelled"
                    break

            except TimeoutError as e:
                logger.error(f"✗ Import job timed out after {timeout}s")
                result["error"] = f"Timeout after {timeout}s"

                if attempt < max_retries:
                    logger.warning(f"Retrying in {retry_delay}s...")
                    continue

            except Exception as e:
                logger.exception(f"✗ Unexpected error: {e}")
                result["error"] = str(e)

                if attempt < max_retries:
                    logger.warning(f"Retrying in {retry_delay}s...")
                    continue

        # If we get here, all retries failed
        result["status"] = "failed"
        result["end_time"] = datetime.now().isoformat()

        logger.error("="*60)
        logger.error(f"✗ Pipeline '{name}' failed after {max_retries + 1} attempts")
        logger.error(f"  Error: {result['error']}")
        logger.error("="*60)

        return result

    def execute_all_pipelines(self, dry_run: bool = False) -> list[Dict[str, Any]]:
        """Execute all enabled pipelines."""
        pipelines = self.load_pipelines()
        enabled_pipelines = [p for p in pipelines if p.get("enabled", True)]

        logger.info(f"Found {len(enabled_pipelines)} enabled pipelines")

        results = []
        for pipeline in enabled_pipelines:
            result = self.execute_pipeline(pipeline, dry_run=dry_run)
            results.append(result)

        return results

    def save_execution_log(self, results: list[Dict[str, Any]]):
        """Save execution results to log file."""
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        log_file = logs_dir / f"import_execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(log_file, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Execution log saved: {log_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Execute configured import pipelines"
    )
    parser.add_argument(
        "--pipeline-name",
        help="Name of specific pipeline to run"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all enabled pipelines"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run (don't actually trigger imports)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List configured pipelines"
    )

    args = parser.parse_args()

    # Initialize executor
    try:
        executor = PipelineExecutor()
    except Exception as e:
        logger.error(f"Failed to initialize pipeline executor: {e}")
        sys.exit(1)

    # List pipelines
    if args.list:
        pipelines = executor.load_pipelines()
        if not pipelines:
            logger.info("No pipelines configured")
            sys.exit(0)

        logger.info("\nConfigured Pipelines:")
        logger.info("="*80)
        for p in pipelines:
            status = "✓ enabled" if p.get("enabled", True) else "✗ disabled"
            logger.info(f"{p['name']:<40} {status:<15} Schedule: {p.get('schedule', 'N/A')}")
        logger.info("="*80)
        sys.exit(0)

    # Execute pipelines
    results = []

    if args.all:
        logger.info("Executing all enabled pipelines...")
        results = executor.execute_all_pipelines(dry_run=args.dry_run)

    elif args.pipeline_name:
        pipeline = executor.get_pipeline(args.pipeline_name)
        if not pipeline:
            logger.error(f"Pipeline not found: {args.pipeline_name}")
            logger.info("Run with --list to see configured pipelines")
            sys.exit(1)

        if not pipeline.get("enabled", True):
            logger.warning(f"Pipeline '{args.pipeline_name}' is disabled")
            sys.exit(1)

        result = executor.execute_pipeline(pipeline, dry_run=args.dry_run)
        results = [result]

    else:
        parser.print_help()
        sys.exit(1)

    # Save execution log
    if not args.dry_run:
        executor.save_execution_log(results)

    # Print summary
    logger.info("\n" + "="*60)
    logger.info("Execution Summary")
    logger.info("="*60)

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")

    for result in results:
        status_icon = "✓" if result["status"] == "success" else "✗"
        logger.info(f"{status_icon} {result['pipeline']}: {result['status']}")
        if result.get("error"):
            logger.info(f"    Error: {result['error']}")

    logger.info("="*60)
    logger.info(f"Total: {len(results)} | Success: {success_count} | Failed: {failed_count}")

    # Exit with error code if any failures
    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
