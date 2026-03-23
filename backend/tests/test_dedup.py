"""
Duplicate detection engine unit tests — no live database required.

Tests cover:
  - Helper functions: _price_match, _mileage_match, _date_match, _pick_canonical
  - run_dedup VIN pass: exact-match, same-source skip, already-marked skip
  - run_dedup fuzzy pass: match, same-source skip, mileage miss, price miss, date miss
  - dedup_job integration stub

Run: pytest backend/tests/test_dedup.py -v
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from garage_radar.dedup.engine import (
    DATE_WINDOW_DAYS,
    MILEAGE_TOLERANCE,
    PRICE_TOLERANCE,
    _date_match,
    _mileage_match,
    _pick_canonical,
    _price_match,
    run_dedup,
)
from garage_radar.db.models import ListingStatusEnum, SourceEnum


# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _listing(
    *,
    source=SourceEnum.bat,
    year=1985,
    generation="G4",
    mileage=50_000,
    asking_price=60_000.0,
    vin=None,
    normalization_confidence=0.8,
    created_at=None,
    possible_duplicate_id=None,
    listing_status=ListingStatusEnum.active,
):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.source = source
    m.year = year
    m.generation = generation
    m.mileage = mileage
    m.asking_price = asking_price
    m.vin = vin
    m.normalization_confidence = normalization_confidence
    m.created_at = created_at or _NOW
    m.possible_duplicate_id = possible_duplicate_id
    m.listing_status = listing_status
    return m


# ── _price_match ──────────────────────────────────────────────────────────────

class TestPriceMatch:
    def test_identical_prices_match(self):
        assert _price_match(60_000, 60_000)

    def test_within_tolerance_match(self):
        # 15% of 60k = 9k — so 60k vs 69k is exactly at boundary
        assert _price_match(60_000, 69_000)

    def test_just_outside_tolerance_no_match(self):
        # (72000 - 60000) / 72000 = 16.7% > 15%
        assert not _price_match(60_000, 72_000)

    def test_none_left_is_permissive(self):
        assert _price_match(None, 60_000)

    def test_none_right_is_permissive(self):
        assert _price_match(60_000, None)

    def test_both_none_is_permissive(self):
        assert _price_match(None, None)

    def test_large_difference_no_match(self):
        assert not _price_match(30_000, 80_000)


# ── _mileage_match ────────────────────────────────────────────────────────────

class TestMileageMatch:
    def test_identical_mileage_match(self):
        assert _mileage_match(50_000, 50_000)

    def test_within_tolerance_match(self):
        assert _mileage_match(50_000, 50_000 + MILEAGE_TOLERANCE)

    def test_just_outside_tolerance_no_match(self):
        assert not _mileage_match(50_000, 50_000 + MILEAGE_TOLERANCE + 1)

    def test_none_left_is_permissive(self):
        assert _mileage_match(None, 50_000)

    def test_none_right_is_permissive(self):
        assert _mileage_match(50_000, None)

    def test_both_none_is_permissive(self):
        assert _mileage_match(None, None)


# ── _date_match ───────────────────────────────────────────────────────────────

class TestDateMatch:
    def test_same_date_match(self):
        assert _date_match(_NOW, _NOW)

    def test_within_window_match(self):
        assert _date_match(_NOW, _NOW + timedelta(days=DATE_WINDOW_DAYS))

    def test_just_outside_window_no_match(self):
        assert not _date_match(_NOW, _NOW + timedelta(days=DATE_WINDOW_DAYS + 1))

    def test_earlier_date_also_works(self):
        assert _date_match(_NOW, _NOW - timedelta(days=DATE_WINDOW_DAYS))


# ── _pick_canonical ───────────────────────────────────────────────────────────

class TestPickCanonical:
    def test_higher_confidence_wins(self):
        high = _listing(normalization_confidence=0.9)
        low  = _listing(normalization_confidence=0.6)
        canon, dup = _pick_canonical(high, low)
        assert canon is high
        assert dup is low

    def test_higher_confidence_wins_reversed_args(self):
        high = _listing(normalization_confidence=0.9)
        low  = _listing(normalization_confidence=0.6)
        canon, dup = _pick_canonical(low, high)
        assert canon is high
        assert dup is low

    def test_tie_older_is_canonical(self):
        older  = _listing(created_at=_NOW - timedelta(days=5), normalization_confidence=0.8)
        newer  = _listing(created_at=_NOW,                     normalization_confidence=0.8)
        canon, dup = _pick_canonical(older, newer)
        assert canon is older
        assert dup is newer

    def test_tie_older_canonical_reversed_args(self):
        older  = _listing(created_at=_NOW - timedelta(days=5), normalization_confidence=0.8)
        newer  = _listing(created_at=_NOW,                     normalization_confidence=0.8)
        canon, dup = _pick_canonical(newer, older)
        assert canon is older
        assert dup is newer


# ── run_dedup — VIN pass ──────────────────────────────────────────────────────

def _make_session(*query_results):
    """
    Build an AsyncMock session whose .execute() calls return successive results.
    Each item in query_results is a list of ORM-like objects.
    """
    session = AsyncMock()
    session.commit = AsyncMock()

    # Each execute() call returns a result whose .scalars().all() yields the list.
    async_results = []
    for rows in query_results:
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        async_results.append(result)

    session.execute = AsyncMock(side_effect=async_results)
    return session


class TestRunDedupVIN:
    @pytest.mark.asyncio
    async def test_vin_match_cross_source_marks_duplicate(self):
        bat_listing = _listing(source=SourceEnum.bat,        vin="WP0AB0911NS123456",
                               normalization_confidence=0.9)
        cb_listing  = _listing(source=SourceEnum.carsandbids, vin="WP0AB0911NS123456",
                               normalization_confidence=0.7)
        session = _make_session([bat_listing, cb_listing], [])  # VIN rows, fuzzy rows

        stats = await run_dedup(session)

        assert stats["vin_pairs"] == 1
        assert stats["marked"] == 1
        # Lower confidence is the duplicate
        assert cb_listing.possible_duplicate_id == bat_listing.id
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vin_match_same_source_skipped(self):
        a = _listing(source=SourceEnum.bat, vin="WP0AB0911NS123456")
        b = _listing(source=SourceEnum.bat, vin="WP0AB0911NS123456")
        session = _make_session([a, b], [])

        stats = await run_dedup(session)

        assert stats["vin_pairs"] == 0
        assert a.possible_duplicate_id is None
        assert b.possible_duplicate_id is None

    @pytest.mark.asyncio
    async def test_vin_match_already_marked_skipped(self):
        canonical_id = uuid.uuid4()
        a = _listing(source=SourceEnum.bat,        vin="WP0AB0911NS123456",
                     normalization_confidence=0.9)
        b = _listing(source=SourceEnum.carsandbids, vin="WP0AB0911NS123456",
                     possible_duplicate_id=canonical_id)  # already flagged
        session = _make_session([a, b], [])

        stats = await run_dedup(session)

        # b was already marked — should not be overwritten by this run
        assert b.possible_duplicate_id == canonical_id
        assert stats["vin_pairs"] == 0

    @pytest.mark.asyncio
    async def test_unique_vins_no_duplicates(self):
        a = _listing(source=SourceEnum.bat,        vin="WP0AB0911NS000001")
        b = _listing(source=SourceEnum.carsandbids, vin="WP0AB0911NS000002")
        session = _make_session([a, b], [])

        stats = await run_dedup(session)

        assert stats["vin_pairs"] == 0
        assert a.possible_duplicate_id is None
        assert b.possible_duplicate_id is None

    @pytest.mark.asyncio
    async def test_three_vin_matches_canonical_highest_confidence(self):
        a = _listing(source=SourceEnum.bat,        vin="VIN1", normalization_confidence=0.9)
        b = _listing(source=SourceEnum.carsandbids, vin="VIN1", normalization_confidence=0.7)
        c = _listing(source=SourceEnum.ebay,        vin="VIN1", normalization_confidence=0.5)
        session = _make_session([a, b, c], [])

        stats = await run_dedup(session)

        assert stats["vin_pairs"] == 2
        assert stats["marked"] == 2
        assert b.possible_duplicate_id == a.id
        assert c.possible_duplicate_id == a.id


# ── run_dedup — fuzzy pass ────────────────────────────────────────────────────

class TestRunDedupFuzzy:
    @pytest.mark.asyncio
    async def test_fuzzy_match_detected(self):
        a = _listing(source=SourceEnum.bat,        year=1985, generation="G4",
                     mileage=50_000, asking_price=60_000, created_at=_NOW,
                     normalization_confidence=0.9)
        b = _listing(source=SourceEnum.carsandbids, year=1985, generation="G4",
                     mileage=50_500, asking_price=61_000, created_at=_NOW + timedelta(days=5),
                     normalization_confidence=0.7)
        session = _make_session([], [a, b])  # no VIN rows, fuzzy candidates

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 1
        assert stats["marked"] == 1
        assert b.possible_duplicate_id == a.id  # a has higher confidence

    @pytest.mark.asyncio
    async def test_fuzzy_same_source_skipped(self):
        a = _listing(source=SourceEnum.bat, year=1985, generation="G4",
                     mileage=50_000, asking_price=60_000, created_at=_NOW)
        b = _listing(source=SourceEnum.bat, year=1985, generation="G4",
                     mileage=50_500, asking_price=61_000, created_at=_NOW)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 0

    @pytest.mark.asyncio
    async def test_fuzzy_mileage_too_different_skipped(self):
        a = _listing(source=SourceEnum.bat,        mileage=50_000, created_at=_NOW)
        b = _listing(source=SourceEnum.carsandbids, mileage=55_000, created_at=_NOW)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 0

    @pytest.mark.asyncio
    async def test_fuzzy_price_too_different_skipped(self):
        a = _listing(source=SourceEnum.bat,        asking_price=60_000, created_at=_NOW)
        b = _listing(source=SourceEnum.carsandbids, asking_price=90_000, created_at=_NOW)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 0

    @pytest.mark.asyncio
    async def test_fuzzy_date_too_old_skipped(self):
        old_date = _NOW - timedelta(days=DATE_WINDOW_DAYS + 5)
        a = _listing(source=SourceEnum.bat,        created_at=_NOW)
        b = _listing(source=SourceEnum.carsandbids, created_at=old_date)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 0

    @pytest.mark.asyncio
    async def test_fuzzy_different_year_skipped(self):
        a = _listing(source=SourceEnum.bat,        year=1985, generation="G4", created_at=_NOW)
        b = _listing(source=SourceEnum.carsandbids, year=1987, generation="G4", created_at=_NOW)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        # Different year → different group → no match
        assert stats["fuzzy_pairs"] == 0

    @pytest.mark.asyncio
    async def test_fuzzy_null_mileage_permissive(self):
        a = _listing(source=SourceEnum.bat,        mileage=None, asking_price=60_000,
                     created_at=_NOW, normalization_confidence=0.9)
        b = _listing(source=SourceEnum.carsandbids, mileage=None, asking_price=62_000,
                     created_at=_NOW, normalization_confidence=0.7)
        session = _make_session([], [a, b])

        stats = await run_dedup(session)

        assert stats["fuzzy_pairs"] == 1

    @pytest.mark.asyncio
    async def test_empty_listings_no_error(self):
        session = _make_session([], [])
        stats = await run_dedup(session)
        assert stats == {"vin_pairs": 0, "fuzzy_pairs": 0, "marked": 0}


# ── dedup_job integration ─────────────────────────────────────────────────────

class TestDedupJob:
    @pytest.mark.asyncio
    async def test_dedup_job_calls_run_dedup(self):
        expected = {"vin_pairs": 2, "fuzzy_pairs": 1, "marked": 3}

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch(
            "garage_radar.scheduler.jobs.get_session_factory",
            return_value=mock_factory,
        ), patch(
            "garage_radar.dedup.engine.run_dedup",
            new=AsyncMock(return_value=expected),
        ):
            from garage_radar.scheduler.jobs import dedup_job
            result = await dedup_job()

        assert result == expected
