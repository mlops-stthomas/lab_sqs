#!/usr/bin/env python3
"""
Check status of Aura Import jobs.

Utility script for monitoring import job progress and debugging issues.

Usage:
    # Check specific job
    python scripts/check_import_status.py --job-id 667a9266-07bc-48a0-ae5f-3d1e8e73fac4

    # Check with detailed progress
    python scripts/check_import_status.py --job-id 667a9266... --progress

    # Monitor job until completion
    python scripts/check_import_status.py --job-id 667a9266... --watch
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aura_manager import AuraManager
from src.aura_import_client import ImportJob

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_job_details(job: ImportJob, show_progress: bool = False):
    """Pretty print job details."""
    print("\n" + "="*60)
    print("Import Job Status")
    print("="*60)
    print(f"Job ID: {job.id}")
    print(f"State: {job.state}")
    print(f"Type: {job.import_type}")

    if job.data_source_name:
        print(f"Data Source: {job.data_source_name}")

    if job.progress:
        print(f"\nProgress: {job.progress.percentage_complete}%")

        if job.progress.exit_status_state:
            print(f"Exit Status: {job.progress.exit_status_state}")

        if job.progress.exit_status_message:
            print(f"Message: {job.progress.exit_status_message}")

        if show_progress and job.progress.nodes_processed:
            print("\nNodes Processed:")
            for node_info in job.progress.nodes_processed[:10]:  # Show first 10
                labels = node_info.get('labels', [])
                processed = node_info.get('processed_rows', 0)
                total = node_info.get('total_rows', 0)
                created = node_info.get('created_nodes', 0)
                print(f"  {labels}: {processed:,}/{total:,} rows ({created:,} created)")

        if show_progress and job.progress.relationships_processed:
            print("\nRelationships Processed:")
            for rel_info in job.progress.relationships_processed[:10]:
                rel_type = rel_info.get('type', 'Unknown')
                processed = rel_info.get('processed_rows', 0)
                total = rel_info.get('total_rows', 0)
                created = rel_info.get('created_relationships', 0)
                print(f"  {rel_type}: {processed:,}/{total:,} rows ({created:,} created)")

    print("="*60)


def watch_job(manager: AuraManager, job_id: str, poll_interval: int = 30):
    """Monitor job until completion."""
    logger.info(f"Watching job {job_id} (polling every {poll_interval}s)")
    logger.info("Press Ctrl+C to stop watching\n")

    try:
        while True:
            job = manager.get_import_job(job_id, include_progress=True)

            # Clear screen (optional - comment out if you want scrolling output)
            # print("\033[2J\033[H", end="")

            print_job_details(job, show_progress=True)

            if job.state in ["Completed", "Failed", "Cancelled"]:
                logger.info(f"\nJob finished with state: {job.state}")
                break

            print(f"\nNext check in {poll_interval}s... (Ctrl+C to stop)")
            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("\n\nStopped watching. Job is still running.")
        logger.info(f"Check status later with: python scripts/check_import_status.py --job-id {job_id}")


def save_job_snapshot(job: ImportJob):
    """Save job details to file."""
    snapshots_dir = Path("logs/job_snapshots")
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "job_id": job.id,
        "state": job.state,
        "import_type": job.import_type,
        "data_source_name": job.data_source_name
    }

    if job.progress:
        snapshot["progress"] = {
            "state": job.progress.state,
            "percentage_complete": job.progress.percentage_complete,
            "exit_status_state": job.progress.exit_status_state,
            "exit_status_message": job.progress.exit_status_message,
            "nodes_processed": job.progress.nodes_processed,
            "relationships_processed": job.progress.relationships_processed
        }

    snapshot_file = snapshots_dir / f"{job.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(snapshot_file, 'w') as f:
        json.dump(snapshot, f, indent=2)

    logger.info(f"Job snapshot saved: {snapshot_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Check status of Aura Import jobs"
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="Import job ID to check"
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show detailed progress information"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Monitor job until completion"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval for --watch (default: 30s)"
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        help="Save job details to file"
    )

    args = parser.parse_args()

    # Initialize manager
    try:
        manager = AuraManager()
        manager.setup_import_client()
    except Exception as e:
        logger.error(f"Failed to initialize Aura Manager: {e}")
        logger.error("Ensure AURA_API_CLIENT_ID, AURA_API_CLIENT_SECRET, "
                    "AURA_ORGANIZATION_ID, and AURA_PROJECT_ID are set")
        sys.exit(1)

    # Watch mode
    if args.watch:
        watch_job(manager, args.job_id, args.poll_interval)
        sys.exit(0)

    # One-time check
    try:
        job = manager.get_import_job(args.job_id, include_progress=args.progress)

        print_job_details(job, show_progress=args.progress)

        # Save snapshot if requested
        if args.save_snapshot:
            save_job_snapshot(job)

        # Provide guidance based on state
        if job.state == "Running":
            logger.info("\nJob is still running. Options:")
            logger.info(f"  - Monitor: python scripts/check_import_status.py --job-id {args.job_id} --watch")
            logger.info(f"  - Cancel: Use Aura Console or API to cancel")

        elif job.state == "Failed":
            logger.error("\nJob failed. Check the error message above.")
            logger.info("Common issues:")
            logger.info("  - Schema validation errors (check your import model)")
            logger.info("  - Data source connection issues")
            logger.info("  - Malformed data in source tables")

        elif job.state == "Completed":
            logger.info("\n✓ Job completed successfully!")

    except Exception as e:
        logger.exception(f"Error checking job status: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
