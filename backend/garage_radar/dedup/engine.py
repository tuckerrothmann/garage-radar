"""
Duplicate detection engine.

Two-pass algorithm:

  Pass 1 — VIN exact match
    Group all active listings by VIN. Any group with listings from two or
    more different sources is a confirmed duplicate set. The listing with the
    highest normalization_confidence is the canonical; all others receive
    possible_duplicate_id = canonical.id.

  Pass 2 — Fuzzy match
    For listings that did not get a VIN match, group by (year, make, model).
    Within each group, compare every pair (O(n²), groups are small). A pair
    is considered a duplicate when ALL of:
      - different source
      - mileage within ±MILEAGE_TOLERANCE miles (or either is NULL)
      - asking_price within ±PRICE_TOLERANCE % (or either is NULL)
      - created_at within DATE_WINDOW_DAYS days of each other

Tie-breaking: higher normalization_confidence wins; ties go to the older
(earlier created_at) listing.

The function mutates Listing.possible_duplicate_id in-place via the
SQLAlchemy session and commits once at the end.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.db.models import Listing, ListingStatusEnum

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

MILEAGE_TOLERANCE = 1_000   # ± miles
PRICE_TOLERANCE   = 0.15    # ± 15 %
DATE_WINDOW_DAYS  = 30      # max days between created_at values


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confidence(listing: Any) -> float:
    return float(listing.normalization_confidence or 0.0)


def _pick_canonical(a: Any, b: Any) -> tuple[Any, Any]:
    """
    Return (canonical, duplicate).
    Canonical = higher normalization_confidence; tie-break = older created_at.
    """
    ca, cb = _confidence(a), _confidence(b)
    if ca > cb:
        return a, b
    if cb > ca:
        return b, a
    # Tie: older record is canonical
    if a.created_at <= b.created_at:
        return a, b
    return b, a


def _price_match(pa: float | None, pb: float | None) -> bool:
    """True when prices are within PRICE_TOLERANCE or either is unknown."""
    if pa is None or pb is None:
        return True
    hi, lo = max(pa, pb), min(pa, pb)
    return (hi - lo) / hi <= PRICE_TOLERANCE


def _mileage_match(ma: int | None, mb: int | None) -> bool:
    """True when mileages are within MILEAGE_TOLERANCE or either is unknown."""
    if ma is None or mb is None:
        return True
    return abs(ma - mb) <= MILEAGE_TOLERANCE


def _date_match(ca: datetime, cb: datetime) -> bool:
    """True when listings were created within DATE_WINDOW_DAYS of each other."""
    return abs((ca - cb).total_seconds()) <= DATE_WINDOW_DAYS * 86_400


# ── Engine ────────────────────────────────────────────────────────────────────

async def run_dedup(session: AsyncSession) -> dict:
    """
    Detect cross-source duplicates for active listings.

    Marks the weaker record of each identified pair by setting
    Listing.possible_duplicate_id = canonical.id.

    Returns:
        {
          "vin_pairs":   int,   # pairs found via VIN exact match
          "fuzzy_pairs": int,   # pairs found via fuzzy match
          "marked":      int,   # total listings marked (≥ 1 per pair)
        }
    """
    stats: dict[str, int] = {"vin_pairs": 0, "fuzzy_pairs": 0, "marked": 0}

    # ── Pass 1: VIN exact match ───────────────────────────────────────────────
    vin_rows = (await session.execute(
        select(Listing).where(
            Listing.listing_status == ListingStatusEnum.active,
            Listing.vin.isnot(None),
        )
    )).scalars().all()

    vin_groups: dict[str, list] = defaultdict(list)
    for row in vin_rows:
        vin_groups[row.vin].append(row)

    for vin, group in vin_groups.items():
        sources = {r.source for r in group}
        if len(sources) < 2:
            continue  # same source or single listing — not a cross-source dup

        # Best record first: highest confidence, then oldest
        group.sort(key=lambda r: (-_confidence(r), r.created_at))
        canonical = group[0]

        for dup in group[1:]:
            if dup.possible_duplicate_id is None:
                dup.possible_duplicate_id = canonical.id
                stats["vin_pairs"] += 1
                stats["marked"] += 1
                logger.debug(
                    "dedup VIN=%s: %s (%s) → dup of %s (%s)",
                    vin, dup.id, dup.source, canonical.id, canonical.source,
                )

    # ── Pass 2: Fuzzy match ───────────────────────────────────────────────────
    # Only consider listings not already flagged by the VIN pass.
    fuzzy_rows = (await session.execute(
        select(Listing).where(
            Listing.listing_status == ListingStatusEnum.active,
            Listing.possible_duplicate_id.is_(None),
        )
    )).scalars().all()

    # Group by (year, make, model) — keeps O(n²) inner loops tiny
    # Using make+model (not generation) avoids false positives across different
    # vehicles that share a year but happen to have the same generation code.
    fuzzy_groups: dict[tuple, list] = defaultdict(list)
    for row in fuzzy_rows:
        fuzzy_groups[(row.year, row.make, row.model)].append(row)

    for (year, make, model), group in fuzzy_groups.items():
        if len(group) < 2:
            continue

        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = group[i], group[j]

                # Skip if either already got flagged by an earlier pair in
                # this loop (possible_duplicate_id was just set in-memory).
                if a.possible_duplicate_id or b.possible_duplicate_id:
                    continue
                if a.source == b.source:
                    continue
                if not _date_match(a.created_at, b.created_at):
                    continue
                if not _mileage_match(a.mileage, b.mileage):
                    continue
                if not _price_match(a.asking_price, b.asking_price):
                    continue

                canonical, dup = _pick_canonical(a, b)
                dup.possible_duplicate_id = canonical.id
                stats["fuzzy_pairs"] += 1
                stats["marked"] += 1
                logger.debug(
                    "dedup fuzzy year=%s make=%s model=%s: %s (%s) → dup of %s (%s)",
                    year, make, model,
                    dup.id, dup.source, canonical.id, canonical.source,
                )

    await session.commit()
    logger.info(
        "dedup: vin_pairs=%d fuzzy_pairs=%d total_marked=%d",
        stats["vin_pairs"], stats["fuzzy_pairs"], stats["marked"],
    )
    return stats
