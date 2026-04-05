"""Refresh active auction rows directly from their stored source URLs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from garage_radar.db.models import Listing, ListingStatusEnum, SourceEnum
from garage_radar.db.upsert import mark_listing_removed, upsert_comp, upsert_listing
from garage_radar.normalize.pipeline import normalize
from garage_radar.sources.base import BaseCrawler, BaseParser, ParsedComp, ParsedListing
from garage_radar.sources.registry import VALID_SOURCES, get_crawler, get_parser

logger = logging.getLogger(__name__)

ACTIVE_AUCTION_STATUSES = (
    ListingStatusEnum.active,
    ListingStatusEnum.relist,
)


@dataclass(frozen=True, slots=True)
class RefreshCandidate:
    """A stored listing row eligible for an auction-state refresh."""

    source: str
    source_url: str
    listing_status: ListingStatusEnum


def normalize_sources(sources: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Validate and normalize source names for refresh runs."""
    if not sources:
        return tuple(VALID_SOURCES)

    normalized: list[str] = []
    for source in sources:
        if source not in VALID_SOURCES:
            valid = ", ".join(VALID_SOURCES)
            raise ValueError(f"Unknown source: {source!r}. Valid: {valid}")
        if source not in normalized:
            normalized.append(source)
    return tuple(normalized)


async def get_refresh_candidates(
    session_factory: async_sessionmaker,
    *,
    sources: list[str] | tuple[str, ...] | None = None,
    limit: int | None = None,
    only_missing: bool = True,
) -> list[RefreshCandidate]:
    """Load active/relist auction rows that should be re-fetched."""
    source_enums = [SourceEnum(source) for source in normalize_sources(sources)]

    async with session_factory() as session:
        stmt = select(
            Listing.source,
            Listing.source_url,
            Listing.listing_status,
        ).where(
            Listing.source.in_(source_enums),
            Listing.listing_status.in_(ACTIVE_AUCTION_STATUSES),
        )
        if only_missing:
            stmt = stmt.where(
                or_(
                    Listing.current_bid.is_(None),
                    Listing.auction_end_at.is_(None),
                    Listing.time_remaining_text.is_(None),
                )
            )
        stmt = stmt.order_by(Listing.updated_at.asc(), Listing.scrape_ts.asc())
        if limit:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        return [
            RefreshCandidate(
                source=row.source.value if isinstance(row.source, SourceEnum) else str(row.source),
                source_url=row.source_url,
                listing_status=row.listing_status,
            )
            for row in result
        ]


async def refresh_active_auctions(
    session_factory: async_sessionmaker,
    *,
    sources: list[str] | tuple[str, ...] | None = None,
    limit: int | None = None,
    only_missing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Re-fetch stored active auction URLs to backfill live bid/countdown fields.

    Returns a compact stats dict describing what happened.
    """
    normalized_sources = normalize_sources(sources)
    candidates = await get_refresh_candidates(
        session_factory,
        sources=normalized_sources,
        limit=limit,
        only_missing=only_missing,
    )

    stats: dict[str, Any] = {
        "sources": list(normalized_sources),
        "candidates": len(candidates),
        "pages_fetched": 0,
        "listings_inserted": 0,
        "listings_updated": 0,
        "comps_inserted": 0,
        "comps_updated": 0,
        "removed": 0,
        "ended": 0,
        "sold": 0,
        "promoted_to_comp": 0,
        "fetch_errors": 0,
        "parse_errors": 0,
        "normalization_errors": 0,
        "dry_run_updates": 0,
    }

    crawlers: dict[str, BaseCrawler] = {}
    parsers: dict[str, BaseParser] = {}

    for candidate in candidates:
        crawler = crawlers.setdefault(candidate.source, get_crawler(candidate.source))
        parser = parsers.setdefault(candidate.source, get_parser(candidate.source))
        result = await refresh_candidate(
            candidate,
            crawler,
            parser,
            session_factory,
            dry_run=dry_run,
        )
        stats["pages_fetched"] += int(result.get("fetched", False))

        outcome = result.get("status")
        if outcome == "removed":
            stats["removed"] += 1
        elif outcome == "fetch_error":
            stats["fetch_errors"] += 1
        elif outcome == "parse_error":
            stats["parse_errors"] += 1
        elif outcome == "normalize_error":
            stats["normalization_errors"] += 1
        elif outcome == "dry_run":
            stats["dry_run_updates"] += 1
        elif outcome == "updated":
            if result.get("listing_action") == "inserted":
                stats["listings_inserted"] += 1
            elif result.get("listing_action") == "updated":
                stats["listings_updated"] += 1

            if result.get("comp_action") == "inserted":
                stats["comps_inserted"] += 1
            elif result.get("comp_action") == "updated":
                stats["comps_updated"] += 1

            if result.get("promoted_to_comp"):
                stats["promoted_to_comp"] += 1

            completed_status = result.get("completed_status")
            if completed_status == ListingStatusEnum.ended.value:
                stats["ended"] += 1
            elif completed_status == ListingStatusEnum.sold.value:
                stats["sold"] += 1

    return stats


async def refresh_candidate(
    candidate: RefreshCandidate,
    crawler: BaseCrawler,
    parser: BaseParser,
    session_factory: async_sessionmaker,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Refresh one stored active auction row from its source URL."""
    try:
        raw = await crawler.fetch_page(candidate.source_url)
    except Exception:
        logger.exception("auction_refresh: fetch failed for %s", candidate.source_url)
        return {"status": "fetch_error", "fetched": False}

    if raw.status_code == 404:
        if not dry_run:
            async with session_factory() as session:
                await mark_listing_removed(session, raw.source, candidate.source_url)
                await session.commit()
        return {"status": "removed", "fetched": True}

    if raw.status_code != 200 or not raw.content:
        logger.warning(
            "auction_refresh: unexpected status %s for %s",
            raw.status_code,
            candidate.source_url,
        )
        return {"status": "fetch_error", "fetched": True}

    try:
        parsed = _parse_listing_or_comp(raw, parser)
    except Exception:
        logger.exception("auction_refresh: parse error for %s", candidate.source_url)
        return {"status": "parse_error", "fetched": True}

    if parsed is None:
        logger.warning("auction_refresh: parser returned None for %s", candidate.source_url)
        return {"status": "parse_error", "fetched": True}

    try:
        normalized = normalize(parsed)
    except Exception:
        logger.exception("auction_refresh: normalize error for %s", candidate.source_url)
        return {"status": "normalize_error", "fetched": True}

    completed_status = _completed_status(normalized)
    should_promote = _should_promote_to_comp(parsed, normalized)

    if dry_run:
        return {
            "status": "dry_run",
            "fetched": True,
            "completed_status": completed_status.value if completed_status else None,
            "promoted_to_comp": should_promote,
        }

    async with session_factory() as session:
        listing_action, listing = await upsert_listing(session, normalized)
        if listing is not None:
            _apply_listing_state(listing, normalized, completed_status)
            session.add(listing)

        comp_action = None
        if should_promote:
            comp_action, _ = await upsert_comp(session, normalized)

        await session.commit()

    return {
        "status": "updated",
        "fetched": True,
        "listing_action": listing_action,
        "comp_action": comp_action,
        "completed_status": completed_status.value if completed_status else None,
        "promoted_to_comp": should_promote,
    }


def _parse_listing_or_comp(raw, parser: BaseParser) -> ParsedListing | ParsedComp | None:
    parsed_listing = parser.parse_listing(raw)
    if parsed_listing is None:
        return parser.parse_comp(raw)
    if parsed_listing.is_completed:
        parsed_comp = parser.parse_comp(raw)
        if parsed_comp is not None:
            return parsed_comp
    return parsed_listing


def _should_promote_to_comp(parsed: ParsedListing, normalized: dict[str, Any]) -> bool:
    return isinstance(parsed, ParsedComp) and _has_comp_signal(normalized)


def _has_comp_signal(normalized: dict[str, Any]) -> bool:
    return normalized.get("sale_price") is not None or normalized.get("sale_date") is not None


def _completed_status(normalized: dict[str, Any]) -> ListingStatusEnum | None:
    if not normalized.get("is_completed"):
        return None
    if normalized.get("final_price") is not None or normalized.get("sale_date") is not None:
        return ListingStatusEnum.sold
    return ListingStatusEnum.ended


def _apply_listing_state(
    listing: Listing,
    normalized: dict[str, Any],
    completed_status: ListingStatusEnum | None,
) -> None:
    if completed_status is not None:
        listing.listing_status = completed_status
        listing.time_remaining_text = None

    if normalized.get("current_bid") is not None:
        listing.current_bid = normalized["current_bid"]
    if normalized.get("auction_end_at") is not None:
        listing.auction_end_at = normalized["auction_end_at"]
    if normalized.get("asking_price") is not None:
        listing.asking_price = normalized["asking_price"]
    if normalized.get("final_price") is not None:
        listing.final_price = normalized["final_price"]

    listing.updated_at = datetime.now(UTC)
