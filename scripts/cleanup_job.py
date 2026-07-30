"""
Standalone hard-forgetting background job.

Run on schedule (cron or manual):
    python scripts/cleanup_job.py
    python scripts/cleanup_job.py --dry-run

Deletes:
  - Qdrant episodic: importance < 3 AND last_accessed > 30 days
  - Neo4j semantic: status=outdated AND outdated_at > 60 days
    (+ corresponding Qdrant semantic_facts entries)

Logs every deletion to MongoDB memory_audit_log BEFORE deleting.
"""

from __future__ import annotations

import asyncio
import sys
import os
import logging

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # pyrefly: ignore

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cleanup_job")


async def main(dry_run: bool = False) -> None:
    """Run the hard-forgetting cleanup job."""
    from app.forgetting import hard_forget_episodic, hard_forget_semantic

    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info("=" * 60)
    logger.info("MemoraeAI Hard Forgetting Job (%s)", mode)
    logger.info("=" * 60)

    # Episodic cleanup
    logger.info("--- Episodic memories cleanup ---")
    episodic_count = await hard_forget_episodic(dry_run=dry_run)
    logger.info("Episodic: %d points %s.", episodic_count, "would be deleted" if dry_run else "deleted")

    # Semantic cleanup
    logger.info("--- Semantic facts cleanup ---")
    semantic_count = await hard_forget_semantic(dry_run=dry_run)
    logger.info("Semantic: %d relationships %s.", semantic_count, "would be deleted" if dry_run else "deleted")

    total = episodic_count + semantic_count
    logger.info("=" * 60)
    logger.info("Total: %d items %s.", total, "would be deleted" if dry_run else "deleted")
    logger.info("Cleanup job complete.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry))
