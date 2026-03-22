"""
Insight pipeline runner.

Orchestrates: comp cluster rebuild → alert engine scan.

Called from:
  - The nightly scheduler (APScheduler job)
  - CLI: python -m garage_radar.insights.runner
  - scripts/ingest.py after crawl completion (optional, via --run-insights flag)

A single DB session is used for both steps so they share a transaction;
commit happens inside each step to avoid holding locks across the full run.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.db import get_session_factory
from garage_radar.insights.alert_engine import run_alert_engine
from garage_radar.insights.comp_clusters import rebuild_comp_clusters

logger = logging.getLogger(__name__)


async def run_insight_pipeline(
    session: Optional[AsyncSession] = None,
    window_days: Optional[int] = None,
) -> dict:
    """
    Run the full insight pipeline.

    If session is not provided, creates its own from the session factory.
    Returns a combined stats dict for logging / pipeline_log.

    Stats shape:
      {
        "started_at":   ISO timestamp,
        "finished_at":  ISO timestamp,
        "clusters":     { total, updated, insufficient_data },
        "alerts":       { checked, created, skipped_dedup },
        "errors":       int,
      }
    """
    started_at = datetime.now(timezone.utc)
    errors = 0

    own_session = session is None
    if own_session:
        factory = get_session_factory()
        session = factory()

    cluster_stats: dict = {}
    alert_stats: dict = {}

    try:
        # ── Step 1: rebuild comp clusters ────────────────────────────────────
        logger.info("Insight pipeline: rebuilding comp clusters...")
        try:
            cluster_stats = await rebuild_comp_clusters(session, window_days=window_days)
        except Exception:
            logger.exception("Insight pipeline: comp cluster rebuild failed.")
            errors += 1
            cluster_stats = {"total": 0, "updated": 0, "insufficient_data": 0, "error": True}

        # ── Step 2: alert engine ─────────────────────────────────────────────
        logger.info("Insight pipeline: running alert engine...")
        try:
            alert_stats = await run_alert_engine(session)
            await session.commit()
        except Exception:
            logger.exception("Insight pipeline: alert engine failed.")
            errors += 1
            await session.rollback()
            alert_stats = {"checked": 0, "created": 0, "skipped_dedup": 0, "error": True}

    finally:
        if own_session:
            await session.close()

    finished_at = datetime.now(timezone.utc)
    result = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": (finished_at - started_at).total_seconds(),
        "clusters": cluster_stats,
        "alerts": alert_stats,
        "errors": errors,
    }
    logger.info(
        "Insight pipeline complete: %d clusters, %d alerts created, %d errors (%.1fs).",
        cluster_stats.get("total", 0),
        alert_stats.get("created", 0),
        errors,
        result["duration_s"],
    )
    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """Run insight pipeline from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Garage Radar insight pipeline")
    parser.add_argument("--window-days", type=int, default=None,
                        help="Comp window in days (default: from settings)")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    result = asyncio.run(run_insight_pipeline(window_days=args.window_days))
    print(f"Done: {result}")


if __name__ == "__main__":
    main()
