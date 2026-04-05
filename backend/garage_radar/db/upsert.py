"""
Garage Radar — Database upsert logic.

Upsert pattern: INSERT ... ON CONFLICT (source, source_url) DO UPDATE.
Never deletes records — marks removed listings with listing_status='removed'.
Tracks price changes in price_history JSONB field.
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.db.models import (
    Comp,
    Listing,
    ListingStatusEnum,
    PipelineLog,
)

logger = logging.getLogger(__name__)


async def upsert_listing(session: AsyncSession, normalized: dict) -> tuple[str, Listing | None]:
    """
    Upsert a normalized listing dict into the listings table.

    Returns (action, listing) where action is 'inserted', 'updated', or 'skipped'.
    """
    source = normalized.get("source")
    source_url = normalized.get("source_url")

    if not source or not source_url:
        logger.warning("upsert_listing: missing source or source_url — skipping.")
        return "skipped", None

    # Check for existing record to handle price history
    existing = await session.scalar(
        select(Listing).where(
            Listing.source == source,
            Listing.source_url == source_url,
        )
    )

    if existing:
        action = "updated"
        prior_vehicle = (existing.make, existing.model)
        # Track price changes
        new_price = normalized.get("asking_price")
        price_history = existing.price_history or []
        if new_price and new_price != existing.asking_price:
            price_history = list(price_history) + [
                {"price": float(existing.asking_price) if existing.asking_price else None,
                 "ts": existing.updated_at.isoformat() if existing.updated_at else None}
            ]
            normalized["price_history"] = price_history

        # Update fields
        for k, v in normalized.items():
            if k not in ("source", "source_url", "created_at") and hasattr(existing, k):
                setattr(existing, k, v)
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        _invalidate_vehicle_profile_caches(
            prior_vehicle,
            (existing.make, existing.model),
        )
        return action, existing
    else:
        action = "inserted"
        # Build Listing model fields (filter to only valid columns)
        listing_fields = _filter_listing_fields(normalized)
        listing = Listing(**listing_fields)
        session.add(listing)
        _invalidate_vehicle_profile_caches((listing.make, listing.model))
        return action, listing


async def upsert_comp(session: AsyncSession, normalized: dict) -> tuple[str, Comp | None]:
    """
    Upsert a normalized comp dict into the comps table.

    Returns (action, comp) where action is 'inserted', 'updated', or 'skipped'.
    """
    source = normalized.get("source")
    source_url = normalized.get("source_url")

    if not source or not source_url:
        logger.warning("upsert_comp: missing source or source_url — skipping.")
        return "skipped", None

    existing = await session.scalar(
        select(Comp).where(
            Comp.source == source,
            Comp.source_url == source_url,
        )
    )

    if existing:
        prior_vehicle = (existing.make, existing.model)
        # Re-ingest should heal stale comp rows after parser or normalization changes.
        for key, value in normalized.items():
            if key not in ("source", "source_url", "created_at") and hasattr(existing, key):
                setattr(existing, key, value)
        session.add(existing)
        _invalidate_vehicle_profile_caches(
            prior_vehicle,
            (existing.make, existing.model),
        )
        return "updated", existing
    else:
        comp_fields = _filter_comp_fields(normalized)
        comp = Comp(**comp_fields)
        session.add(comp)
        _invalidate_vehicle_profile_caches((comp.make, comp.model))
        return "inserted", comp


async def mark_listing_removed(session: AsyncSession, source: str, source_url: str) -> None:
    """Mark a listing as removed (404) without deleting it."""
    existing = await session.scalar(
        select(Listing).where(
            Listing.source == source,
            Listing.source_url == source_url,
        )
    )
    if existing:
        existing.listing_status = ListingStatusEnum.removed
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        _invalidate_vehicle_profile_caches((existing.make, existing.model))


async def write_pipeline_log(session: AsyncSession, log_data: dict) -> None:
    log = PipelineLog(**log_data)
    session.add(log)
    await session.commit()


# ── Field filtering ──────────────────────────────────────────────────────────

# Valid Listing column names (excludes relationship props and methods)
_LISTING_COLUMNS = {c.key for c in Listing.__table__.columns}
_COMP_COLUMNS = {c.key for c in Comp.__table__.columns}


def _filter_listing_fields(data: dict) -> dict:
    """Keep only fields that are valid Listing columns."""
    return {k: v for k, v in data.items() if k in _LISTING_COLUMNS}


def _filter_comp_fields(data: dict) -> dict:
    """Keep only fields that are valid Comp columns."""
    return {k: v for k, v in data.items() if k in _COMP_COLUMNS}


def _invalidate_vehicle_profile_caches(*vehicle_pairs: tuple[str | None, str | None]) -> None:
    """Best-effort cache eviction for affected vehicle profiles."""
    try:
        from garage_radar.vehicle_profiles import invalidate_vehicle_profile_cache

        seen: set[tuple[str, str]] = set()
        for make, model in vehicle_pairs:
            if not make or not model:
                continue
            normalized_pair = (" ".join(make.strip().split()), " ".join(model.strip().split()))
            if normalized_pair in seen:
                continue
            invalidate_vehicle_profile_cache(*normalized_pair)
            seen.add(normalized_pair)
    except Exception:
        logger.warning(
            "Failed to invalidate vehicle profile cache for %s",
            vehicle_pairs,
            exc_info=True,
        )
