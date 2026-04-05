#!/usr/bin/env python3
"""
Garage Radar source ingestion script.

Runs crawl -> parse -> normalize -> upsert for one or more sources.
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add backend to path so we can import garage_radar
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from garage_radar.db import ensure_schema_ready, get_session_factory
from garage_radar.db.upsert import upsert_comp, upsert_listing, write_pipeline_log
from garage_radar.normalize.pipeline import normalize
from garage_radar.sources.base import RawPage
from garage_radar.sources.registry import VALID_SOURCES, get_crawler, get_parser
from garage_radar.sources.targeting import get_vehicle_targets_for_source


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_source_components(source: str, **kwargs):
    """Return (crawler, parser) instances for the given source name."""
    return get_crawler(source, **kwargs), get_parser(source)


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

    parsed = parser.parse_comp(raw)
    is_comp = parsed is not None
    if parsed is None:
        parsed = parser.parse_listing(raw)
    if parsed is None:
        return {"status": "parse_failed", "url": url}

    normalized = normalize(parsed)

    if dry_run:
        import json

        print(
            json.dumps(
                {
                    key: str(value)
                    if not isinstance(value, (str, int, float, bool, list, type(None)))
                    else value
                    for key, value in normalized.items()
                },
                indent=2,
            )
        )
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
    limit: int | None,
    dry_run: bool = False,
) -> dict:
    """
    Full ingestion run for a source across all configured vehicle targets.

    Returns a stats dict for pipeline_log.
    """
    logger = logging.getLogger(f"ingest.{source}")
    start_time = time.monotonic()
    targets = get_vehicle_targets_for_source(source)

    if not targets:
        logger.warning("No configured vehicle targets for %s.", source)
        return {
            "source": source,
            "pages_fetched": 0,
            "records_extracted": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "extraction_errors": 0,
            "normalization_errors": 0,
            "duration_s": time.monotonic() - start_time,
        }

    stats = {
        "pages_fetched": 0,
        "records_extracted": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "extraction_errors": 0,
        "normalization_errors": 0,
    }

    logger.info(
        "Configured %d target(s) for %s: %s",
        len(targets),
        source,
        ", ".join(target.label for target in targets),
    )

    seen_urls: set[str] = set()
    session_factory = get_session_factory()

    for target in targets:
        crawler, parser = get_source_components(source, target=target)
        logger.info(
            "Collecting listing URLs from %s for %s (limit=%s per target)...",
            source,
            target.label,
            limit or "none",
        )
        urls = await crawler.get_listing_urls(limit=limit)
        urls = [url for url in urls if url not in seen_urls]
        seen_urls.update(urls)
        stats["pages_fetched"] += len(urls)

        logger.info("Found %d new listing URLs for %s.", len(urls), target.label)
        if not urls:
            logger.warning("No URLs collected from %s for %s.", source, target.label)
            continue

        for index, url in enumerate(urls, 1):
            logger.info("[%s %d/%d] Processing: %s", target.label, index, len(urls), url)
            try:
                raw: RawPage = await crawler.fetch_page(url)
                if not raw.content or raw.status_code == 0:
                    logger.warning("Fetch failed for %s (status=%s)", url, raw.status_code)
                    stats["extraction_errors"] += 1
                    continue

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
                        "DRY RUN - would %s: year=%s gen=%s trans=%s color=%s mileage=%s price=%s",
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
        "%s ingestion complete in %.1fs: %d fetched, %d extracted, %d inserted, %d updated, %d errors.",
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

    if args.url:
        if len(args.source) != 1:
            logger.error("--url requires exactly one --source.")
            sys.exit(1)
        result = await ingest_url(
            args.source[0],
            args.url,
            get_session_factory(),
            dry_run=args.dry_run,
        )
        logger.info("Result: %s", result)
        return

    if not args.dry_run:
        logger.info("Checking that the migrated database schema is ready...")
        try:
            await ensure_schema_ready()
        except Exception as exc:
            logger.error("Schema readiness check failed: %s", exc)
            logger.error("Is Postgres running, and did you run `python scripts/dev.py migrate`?")
            sys.exit(1)

    all_stats = []
    for source in args.source:
        stats = await ingest_source(source, limit=args.limit, dry_run=args.dry_run)
        all_stats.append(stats)

    if not args.dry_run:
        session_factory = get_session_factory()
        async with session_factory() as session:
            for stats in all_stats:
                await write_pipeline_log(session, stats)

    total_inserted = sum(stats.get("records_inserted", 0) for stats in all_stats)
    total_updated = sum(stats.get("records_updated", 0) for stats in all_stats)
    total_errors = sum(
        stats.get("extraction_errors", 0) + stats.get("normalization_errors", 0)
        for stats in all_stats
    )
    logger.info(
        "All done. Total: %d inserted, %d updated, %d errors.",
        total_inserted,
        total_updated,
        total_errors,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garage Radar ingestion script")
    parser.add_argument(
        "--source",
        nargs="+",
        required=True,
        choices=list(VALID_SOURCES),
        help="Source(s) to ingest from",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max listing URLs to process per target within each source",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Fetch and parse a single specific URL (overrides normal crawl)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and normalize but do not write to database",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity",
    )
    asyncio.run(main(parser.parse_args()))
