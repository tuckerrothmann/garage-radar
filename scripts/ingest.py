#!/usr/bin/env python3
"""
Garage Radar — Source ingestion script.

Runs crawl → parse → normalize → upsert for one or more sources.

Usage:
    python scripts/ingest.py --source bat --limit 20
    python scripts/ingest.py --source carsandbids --limit 20
    python scripts/ingest.py --source bat carsandbids
    python scripts/ingest.py --source bat --url https://bringatrailer.com/listing/some-slug/

Examples:
    # Quick test: grab 5 BaT listings
    python scripts/ingest.py --source bat --limit 5

    # Full BaT run (active + sold, up to 10 pages per type)
    python scripts/ingest.py --source bat

    # Both sources, capped at 50 listings each
    python scripts/ingest.py --source bat carsandbids --limit 50
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add backend to path so we can import garage_radar
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from garage_radar.config import get_settings
from garage_radar.db import create_all_tables, get_session_factory
from garage_radar.db.upsert import upsert_comp, upsert_listing, write_pipeline_log
from garage_radar.normalize.pipeline import normalize
from garage_radar.sources.base import ParsedComp, RawPage


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy httpx logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_source_components(source: str):
    """Return (crawler, parser) instances for the given source name."""
    if source == "bat":
        from garage_radar.sources.bat import BaTCrawler, BaTParser
        return BaTCrawler(), BaTParser()
    elif source == "carsandbids":
        from garage_radar.sources.carsandbids import CarsAndBidsCrawler, CarsAndBidsParser
        return CarsAndBidsCrawler(), CarsAndBidsParser()
    else:
        raise ValueError(f"Unknown source: {source!r}. Valid: bat, carsandbids")


async def ingest_url(
    source: str,
    url: str,
    session_factory,
    dry_run: bool = False,
) -> dict:
    """Fetch, parse, normalize, and upsert a single listing URL."""
    crawler, parser = get_source_components(source)

    raw: RawPage = await crawler.fetch_page(url)
    if not raw.content:
        return {"status": "fetch_failed", "url": url}

    # Try comp first (completed auction), fall back to active listing
    parsed = parser.parse_comp(raw)
    is_comp = parsed is not None

    if parsed is None:
        parsed = parser.parse_listing(raw)

    if parsed is None:
        return {"status": "parse_failed", "url": url}

    normalized = normalize(parsed)

    if dry_run:
        import json
        print(json.dumps(
            {k: str(v) if not isinstance(v, (str, int, float, bool, list, type(None))) else v
             for k, v in normalized.items()},
            indent=2
        ))
        return {"status": "dry_run", "url": url, "is_comp": is_comp}

    async with session_factory() as session:
        if is_comp:
            action, _ = await upsert_comp(session, normalized)
        else:
            action, _ = await upsert_listing(session, normalized)
        await session.commit()

    return {"status": action, "url": url, "is_comp": is_comp}


async def ingest_source(
    source: str,
    limit: int,
    dry_run: bool = False,
) -> dict:
    """
    Full ingestion run for a source: collect URLs → fetch → parse → normalize → upsert.
    Returns a stats dict for pipeline_log.
    """
    logger = logging.getLogger(f"ingest.{source}")
    start_time = time.monotonic()
    settings = get_settings()

    crawler, parser = get_source_components(source)

    # Phase 1: Collect listing URLs
    logger.info("Collecting listing URLs from %s (limit=%s)...", source, limit or "none")
    urls = await crawler.get_listing_urls(limit=limit)
    logger.info("Found %d listing URLs.", len(urls))

    if not urls:
        logger.warning("No URLs collected from %s. Check network and source availability.", source)
        return {"source": source, "pages_fetched": 0, "records_extracted": 0,
                "records_inserted": 0, "records_updated": 0,
                "extraction_errors": 0, "normalization_errors": 0,
                "duration_s": time.monotonic() - start_time}

    # Phase 2: Fetch, parse, normalize, upsert each listing
    stats = {
        "pages_fetched": len(urls),
        "records_extracted": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "extraction_errors": 0,
        "normalization_errors": 0,
    }

    session_factory = get_session_factory()

    for i, url in enumerate(urls, 1):
        logger.info("[%d/%d] Processing: %s", i, len(urls), url)
        try:
            raw: RawPage = await crawler.fetch_page(url)

            if not raw.content or raw.status_code == 0:
                logger.warning("Fetch failed for %s (status=%s)", url, raw.status_code)
                stats["extraction_errors"] += 1
                continue

            # Try comp first, fall back to listing
            parsed = parser.parse_comp(raw)
            is_comp = parsed is not None

            if parsed is None:
                parsed = parser.parse_listing(raw)

            if parsed is None:
                logger.warning("Parse returned None for %s", url)
                stats["extraction_errors"] += 1
                continue

            stats["records_extracted"] += 1

            try:
                normalized = normalize(parsed)
            except Exception as exc:
                logger.warning("Normalization failed for %s: %s", url, exc)
                stats["normalization_errors"] += 1
                continue

            if dry_run:
                logger.info(
                    "DRY RUN — would %s: year=%s gen=%s trans=%s color=%s mileage=%s price=%s",
                    "upsert_comp" if is_comp else "upsert_listing",
                    normalized.get("year"),
                    normalized.get("generation"),
                    normalized.get("transmission"),
                    normalized.get("exterior_color_canonical"),
                    normalized.get("mileage"),
                    normalized.get("final_price") or normalized.get("asking_price"),
                )
                continue

            async with session_factory() as session:
                if is_comp:
                    action, _ = await upsert_comp(session, normalized)
                else:
                    action, _ = await upsert_listing(session, normalized)
                await session.commit()

            if action == "inserted":
                stats["records_inserted"] += 1
            elif action == "updated":
                stats["records_updated"] += 1

        except Exception as exc:
            logger.error("Unexpected error processing %s: %s", url, exc, exc_info=True)
            stats["extraction_errors"] += 1

    duration = time.monotonic() - start_time
    stats["duration_s"] = round(duration, 1)
    stats["source"] = source

    logger.info(
        "%s ingestion complete in %.1fs: %d fetched, %d extracted, "
        "%d inserted, %d updated, %d errors.",
        source,
        duration,
        stats["pages_fetched"],
        stats["records_extracted"],
        stats["records_inserted"],
        stats["records_updated"],
        stats["extraction_errors"] + stats["normalization_errors"],
    )

    return stats


async def main(args: argparse.Namespace) -> None:
    setup_logging(args.log_level)
    logger = logging.getLogger("ingest")

    # Single URL mode
    if args.url:
        if len(args.source) != 1:
            logger.error("--url requires exactly one --source.")
            sys.exit(1)
        result = await ingest_url(args.source[0], args.url, get_session_factory(), dry_run=args.dry_run)
        logger.info("Result: %s", result)
        return

    # Ensure DB tables exist (dev convenience)
    if not args.dry_run:
        logger.info("Ensuring database tables exist...")
        try:
            await create_all_tables()
        except Exception as exc:
            logger.error("DB init failed: %s", exc)
            logger.error("Is Postgres running? Check DATABASE_URL in .env")
            sys.exit(1)

    # Multi-source run
    all_stats = []
    for source in args.source:
        stats = await ingest_source(source, limit=args.limit, dry_run=args.dry_run)
        all_stats.append(stats)

    # Write pipeline logs
    if not args.dry_run:
        session_factory = get_session_factory()
        async with session_factory() as session:
            for stats in all_stats:
                await write_pipeline_log(session, stats)

    # Summary
    total_inserted = sum(s.get("records_inserted", 0) for s in all_stats)
    total_updated = sum(s.get("records_updated", 0) for s in all_stats)
    total_errors = sum(
        s.get("extraction_errors", 0) + s.get("normalization_errors", 0) for s in all_stats
    )
    logger.info(
        "All done. Total: %d inserted, %d updated, %d errors.",
        total_inserted, total_updated, total_errors,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garage Radar ingestion script")
    parser.add_argument(
        "--source", nargs="+", required=True,
        choices=["bat", "carsandbids"],
        help="Source(s) to ingest from",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max listing URLs to process per source (default: no limit)",
    )
    parser.add_argument(
        "--url", type=str, default=None,
        help="Fetch and parse a single specific URL (overrides normal crawl)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and normalize but do not write to database",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity",
    )
    args = parser.parse_args()
    asyncio.run(main(args))
