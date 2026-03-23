"""
Scheduler job functions.

Two jobs are defined:

  crawl_job(source_name)
    — collect listing URLs for a source, fetch+parse+normalize+upsert each
      one, write a PipelineLog row when done.

  insights_job()
    — run rebuild_comp_clusters → run_alert_engine, writing results to the
      application log (pipeline_log integration done in runner.py).

Both functions are plain `async def` so they can be:
  - called from APScheduler's AsyncIOScheduler
  - called directly from scripts / tests

Concurrency within a crawl is limited to MAX_CONCURRENT_FETCHES per-source
(the HttpClient + rate_limiter handles per-domain pacing; the semaphore
here caps in-flight async tasks to keep memory bounded).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from garage_radar.db import get_session_factory
from garage_radar.db.models import SourceEnum
from garage_radar.db.upsert import (
    mark_listing_removed,
    upsert_comp,
    upsert_listing,
    write_pipeline_log,
)
from garage_radar.insights.runner import run_insight_pipeline
from garage_radar.normalize.pipeline import normalize
from garage_radar.sources.base import BaseCrawler, BaseParser, ParsedComp

logger = logging.getLogger(__name__)

MAX_CONCURRENT_FETCHES = 3


# ── Source registry ───────────────────────────────────────────────────────────

def _get_crawler(source_name: str, **kwargs) -> BaseCrawler:
    if source_name == "bat":
        from garage_radar.sources.bat.crawler import BaTCrawler
        return BaTCrawler(**kwargs)
    if source_name == "carsandbids":
        from garage_radar.sources.carsandbids.crawler import CarsAndBidsCrawler
        return CarsAndBidsCrawler(**kwargs)
    if source_name == "ebay":
        from garage_radar.sources.ebay.crawler import EbayCrawler
        # eBay doesn't use max_pages in the same way; pass through if provided
        return EbayCrawler(max_pages=kwargs.get("max_pages", 5))
    raise ValueError(f"Unknown source: {source_name!r}")


def _get_parser(source_name: str) -> BaseParser:
    if source_name == "bat":
        from garage_radar.sources.bat.parser import BaTParser
        return BaTParser()
    if source_name == "carsandbids":
        from garage_radar.sources.carsandbids.parser import CarsAndBidsParser
        return CarsAndBidsParser()
    if source_name == "ebay":
        from garage_radar.sources.ebay.parser import EbayParser
        return EbayParser()
    raise ValueError(f"Unknown source: {source_name!r}")


# ── Crawl job ─────────────────────────────────────────────────────────────────

async def crawl_job(
    source_name: str,
    *,
    max_pages: int = 10,
    include_sold: bool = True,
    max_urls: Optional[int] = None,
) -> dict:
    """
    Full crawl pipeline for one source: discover → fetch → parse → normalize → upsert.

    Returns a stats dict mirroring the PipelineLog columns so the caller
    can write the log (or inspect it in tests).
    """
    run_at = datetime.now(timezone.utc)
    try:
        source_enum = SourceEnum(source_name)
    except ValueError:
        logger.error("crawl_job: unknown source %r", source_name)
        return {
            "source": source_name,
            "run_at": run_at,
            "pages_fetched": 0, "records_extracted": 0,
            "records_inserted": 0, "records_updated": 0,
            "extraction_errors": 0, "normalization_errors": 0,
            "duration_s": None,
            "notes": f"Unknown source: {source_name!r}",
        }

    stats = {
        "source": source_enum,
        "run_at": run_at,
        "pages_fetched": 0,
        "records_extracted": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "extraction_errors": 0,
        "normalization_errors": 0,
        "duration_s": None,
        "notes": None,
    }

    try:
        crawler = _get_crawler(
            source_name,
            max_pages=max_pages,
            include_sold=include_sold,
        )
        parser = _get_parser(source_name)
    except ValueError as exc:
        logger.error("crawl_job: %s", exc)
        stats["notes"] = str(exc)
        return stats

    logger.info("crawl_job[%s]: discovering listing URLs...", source_name)
    try:
        urls = await crawler.get_listing_urls(limit=max_urls)
    except Exception:
        logger.exception("crawl_job[%s]: URL discovery failed.", source_name)
        stats["notes"] = "URL discovery failed"
        return stats

    logger.info("crawl_job[%s]: %d URLs found. Starting fetch+parse.", source_name, len(urls))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
    factory = get_session_factory()

    async def _process_url(url: str) -> None:
        async with semaphore:
            await _fetch_parse_upsert(url, crawler, parser, factory, stats)

    tasks = [asyncio.create_task(_process_url(url)) for url in urls]
    await asyncio.gather(*tasks, return_exceptions=True)

    stats["duration_s"] = round(
        (datetime.now(timezone.utc) - run_at).total_seconds(), 2
    )

    # Write pipeline log
    async with factory() as session:
        try:
            await write_pipeline_log(session, stats)
        except Exception:
            logger.exception("crawl_job[%s]: failed to write pipeline log.", source_name)

    logger.info(
        "crawl_job[%s]: done. inserted=%d updated=%d errors=%d (%.1fs)",
        source_name,
        stats["records_inserted"],
        stats["records_updated"],
        stats["extraction_errors"] + stats["normalization_errors"],
        stats["duration_s"] or 0,
    )
    return stats


async def _fetch_parse_upsert(
    url: str,
    crawler: BaseCrawler,
    parser: BaseParser,
    factory,
    stats: dict,
) -> None:
    """Fetch one URL, parse, normalize, and upsert. Mutates stats in-place."""
    # ── Fetch ─────────────────────────────────────────────────────────────────
    try:
        raw = await crawler.fetch_page(url)
        stats["pages_fetched"] += 1
    except Exception:
        logger.exception("crawl: fetch failed for %s", url)
        stats["extraction_errors"] += 1
        return

    # ── 404 → mark removed ───────────────────────────────────────────────────
    if raw.status_code == 404:
        async with factory() as session:
            await mark_listing_removed(session, raw.source, url)
            await session.commit()
        return

    if raw.status_code != 200:
        logger.warning("crawl: unexpected status %d for %s", raw.status_code, url)
        stats["extraction_errors"] += 1
        return

    # ── Parse ─────────────────────────────────────────────────────────────────
    try:
        # Try as a listing first to discover is_completed
        parsed = parser.parse_listing(raw)
        if parsed is None:
            logger.debug("crawl: parser returned None for %s", url)
            stats["extraction_errors"] += 1
            return
        stats["records_extracted"] += 1

        # If completed, re-parse as a comp to get sale-specific fields
        if parsed.is_completed:
            parsed_comp = parser.parse_comp(raw)
            if parsed_comp is not None:
                parsed = parsed_comp
    except Exception:
        logger.exception("crawl: parse error for %s", url)
        stats["extraction_errors"] += 1
        return

    # ── Normalize ─────────────────────────────────────────────────────────────
    try:
        normalized = normalize(parsed)
    except Exception:
        logger.exception("crawl: normalize error for %s", url)
        stats["normalization_errors"] += 1
        return

    # ── Upsert ────────────────────────────────────────────────────────────────
    async with factory() as session:
        try:
            if isinstance(parsed, ParsedComp) and normalized.get("sale_date"):
                action, _ = await upsert_comp(session, normalized)
            else:
                action, _ = await upsert_listing(session, normalized)
            await session.commit()
        except Exception:
            logger.exception("crawl: upsert failed for %s", url)
            await session.rollback()
            stats["extraction_errors"] += 1
            return

    if action == "inserted":
        stats["records_inserted"] += 1
    elif action == "updated":
        stats["records_updated"] += 1


# ── Dedup job ─────────────────────────────────────────────────────────────────

async def dedup_job() -> dict:
    """
    Run duplicate detection across all active listings.

    Returns the stats dict from run_dedup():
        {vin_pairs, fuzzy_pairs, marked}
    """
    from garage_radar.dedup.engine import run_dedup

    logger.info("dedup_job: starting...")
    factory = get_session_factory()
    async with factory() as session:
        stats = await run_dedup(session)
    logger.info(
        "dedup_job: done. vin_pairs=%d fuzzy_pairs=%d marked=%d",
        stats.get("vin_pairs", 0),
        stats.get("fuzzy_pairs", 0),
        stats.get("marked", 0),
    )
    return stats


# ── Insights job ──────────────────────────────────────────────────────────────

async def insights_job(window_days: Optional[int] = None) -> dict:
    """
    Run the insight pipeline (comp cluster rebuild + alert engine), then
    notify on any new watch/act alerts that haven't been notified yet.

    Returns the stats dict from run_insight_pipeline() plus notify stats.
    """
    logger.info("insights_job: starting...")
    try:
        result = await run_insight_pipeline(window_days=window_days)
        logger.info(
            "insights_job: done. clusters=%d alerts_created=%d errors=%d",
            result.get("clusters", {}).get("total", 0),
            result.get("alerts", {}).get("created", 0),
            result.get("errors", 0),
        )
    except Exception:
        logger.exception("insights_job: unhandled exception.")
        return {"errors": 1}

    # ── Notify on new alerts ─────────────────────────────────────────────────
    notify_stats = {"sent_email": 0, "sent_slack": 0, "skipped": 0, "errors": 0}
    try:
        from sqlalchemy import select
        from garage_radar.db import get_session_factory
        from garage_radar.db.models import Alert, AlertStatusEnum
        from garage_radar.notifications.notifier import notify_alerts, stamp_notified

        factory = get_session_factory()
        async with factory() as session:
            unnotified = (await session.execute(
                select(Alert).where(
                    Alert.notified_at.is_(None),
                    Alert.status == AlertStatusEnum.open,
                )
            )).scalars().all()

            if unnotified:
                notify_stats = await notify_alerts(unnotified)
                if notify_stats.get("sent_email") or notify_stats.get("sent_slack"):
                    await stamp_notified(session, list(unnotified))

        logger.info(
            "insights_job: notifications — email=%d slack=%d errors=%d",
            notify_stats.get("sent_email", 0),
            notify_stats.get("sent_slack", 0),
            notify_stats.get("errors", 0),
        )
    except Exception:
        logger.exception("insights_job: notification step failed (non-fatal).")

    result["notify"] = notify_stats
    return result
