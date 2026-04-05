#!/usr/bin/env python3
"""Refresh live auction-state fields for stored active auction rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from garage_radar.db import get_session_factory
from garage_radar.maintenance.auction_refresh import refresh_active_auctions
from garage_radar.sources.registry import VALID_SOURCES


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main(args: argparse.Namespace) -> None:
    setup_logging(args.log_level)
    stats = await refresh_active_auctions(
        get_session_factory(),
        sources=args.source,
        limit=args.limit,
        only_missing=not args.include_complete_rows,
        dry_run=args.dry_run,
    )
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Refresh stored active auction URLs to backfill bid/countdown fields"
    )
    parser.add_argument(
        "--source",
        nargs="+",
        choices=list(VALID_SOURCES),
        help="Optional source filter",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of stored active rows to refresh",
    )
    parser.add_argument(
        "--include-complete-rows",
        action="store_true",
        help="Refresh all active/relist rows, not just ones missing auction-state fields",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse pages but do not write updates",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity",
    )
    asyncio.run(main(parser.parse_args()))
