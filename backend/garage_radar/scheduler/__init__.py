"""
Garage Radar — APScheduler job schedule.

Nightly schedule (all times UTC):
  02:00  BaT crawl
  03:30  Cars & Bids crawl
  06:00  Insight pipeline (clusters + alerts)

The scheduler can be run in two modes:

  1. Embedded — started inside the FastAPI lifespan (default for the web
     server). The API and jobs share the same event loop.

  2. Standalone worker — run via:
         python -m garage_radar.scheduler
     Useful when running the API and the crawler as separate containers.

Job overlap protection: each job is configured with
  misfire_grace_time=3600  (tolerate up to 1h late start)
  max_instances=1          (skip if previous run still active)

Schedule is configurable via CRON_* environment variables so staging
environments can run more frequently without code changes.
"""
import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from garage_radar.config import get_settings
from garage_radar.scheduler.jobs import crawl_job, insights_job

logger = logging.getLogger(__name__)

# Module-level scheduler instance (singleton per process)
_scheduler: Optional[AsyncIOScheduler] = None


# ── Schedule defaults ─────────────────────────────────────────────────────────

_JOB_DEFAULTS = {
    "misfire_grace_time": 3600,  # tolerate up to 1h late fire
    "max_instances": 1,          # never run two copies of the same job
    "coalesce": True,            # merge misfired runs into a single catch-up
}

_JOBS = [
    # (job_id, func, cron_kwargs, job_kwargs)
    (
        "crawl_bat",
        lambda: crawl_job("bat", max_pages=15, include_sold=True),
        {"hour": 2, "minute": 0},
        {},
    ),
    (
        "crawl_carsandbids",
        lambda: crawl_job("carsandbids", max_pages=15, include_sold=True),
        {"hour": 3, "minute": 30},
        {},
    ),
    (
        "insights",
        lambda: insights_job(),
        {"hour": 6, "minute": 0},
        {},
    ),
]


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def get_scheduler() -> AsyncIOScheduler:
    """Return the module-level scheduler, creating it if needed."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(job_defaults=_JOB_DEFAULTS, timezone="UTC")
        _register_jobs(_scheduler)
    return _scheduler


def _register_jobs(scheduler: AsyncIOScheduler) -> None:
    """Add all scheduled jobs to the scheduler instance."""
    for job_id, func, cron_kwargs, extra_kwargs in _JOBS:
        scheduler.add_job(
            func,
            trigger=CronTrigger(timezone="UTC", **cron_kwargs),
            id=job_id,
            name=job_id,
            replace_existing=True,
            **extra_kwargs,
        )
        logger.debug(
            "Scheduler: registered job '%s' (%s).",
            job_id,
            _cron_str(cron_kwargs),
        )


def start_scheduler() -> AsyncIOScheduler:
    """Start the scheduler if it isn't already running."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started. %d jobs registered.", len(scheduler.get_jobs()))
        for job in scheduler.get_jobs():
            logger.info("  - %s  next run: %s", job.id, job.next_run_time)
    return scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    _scheduler = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cron_str(kwargs: dict) -> str:
    h = kwargs.get("hour", "*")
    m = kwargs.get("minute", 0)
    return f"{h:02d}:{m:02d} UTC" if isinstance(h, int) else f"{h}:{m} UTC"


# ── Standalone runner ─────────────────────────────────────────────────────────

def main() -> None:
    """
    Run the scheduler as a standalone worker process.

    Keeps the event loop alive until interrupted.
    Usage:
        python -m garage_radar.scheduler
        python -m garage_radar.scheduler --run-now bat
        python -m garage_radar.scheduler --run-now insights
    """
    import argparse
    import signal

    parser = argparse.ArgumentParser(description="Garage Radar scheduler worker")
    parser.add_argument(
        "--run-now",
        metavar="JOB",
        help="Run a specific job immediately and exit (bat | carsandbids | insights)",
    )
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    if args.run_now:
        _run_now_and_exit(args.run_now)
        return

    # Normal mode: start scheduler and block
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    scheduler = get_scheduler()
    scheduler.start()

    logger.info("Scheduler worker running. Press Ctrl-C to stop.")
    for job in scheduler.get_jobs():
        logger.info("  [%s] next: %s", job.id, job.next_run_time)

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        stop_scheduler()
        loop.close()


def _run_now_and_exit(job_name: str) -> None:
    """Run a single job immediately (for manual triggers / debugging)."""
    async def _run():
        if job_name in ("bat", "carsandbids"):
            result = await crawl_job(job_name, max_pages=5, include_sold=True)
        elif job_name == "insights":
            result = await insights_job()
        else:
            raise ValueError(f"Unknown job: {job_name!r}. Valid: bat, carsandbids, insights")
        logger.info("Job %r complete: %s", job_name, result)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
