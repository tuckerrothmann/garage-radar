from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from garage_radar.db.models import ListingStatusEnum
from garage_radar.maintenance.auction_refresh import (
    RefreshCandidate,
    get_refresh_candidates,
    normalize_sources,
    refresh_active_auctions,
    refresh_candidate,
)
from garage_radar.sources.base import ParsedComp, ParsedListing, RawPage


def _raw_page(status_code=200, source="bat", url="https://bringatrailer.com/listing/foo") -> RawPage:
    return RawPage(
        source=source,
        url=url,
        fetched_at=datetime.now(UTC),
        content="<html></html>",
        status_code=status_code,
    )


def _parsed_listing(is_completed: bool = False) -> ParsedListing:
    return ParsedListing(
        source="bat",
        source_url="https://bringatrailer.com/listing/foo",
        scrape_ts=datetime.now(UTC),
        year=1995,
        title_raw="1995 Porsche 911 Carrera",
        current_bid=72000.0,
        auction_end_at="2026-04-02T17:00:00Z",
        time_remaining_text="2 days",
        is_completed=is_completed,
    )


def _parsed_comp() -> ParsedComp:
    return ParsedComp(
        source="bat",
        source_url="https://bringatrailer.com/listing/foo",
        scrape_ts=datetime.now(UTC),
        year=1995,
        title_raw="1995 Porsche 911 Carrera",
        final_price=85000.0,
        sale_date="2026-03-28",
        is_completed=True,
    )


def _factory_with_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = session
    return factory, session


class TestNormalizeSources:
    def test_defaults_to_all_sources(self):
        assert normalize_sources(None) == ("bat", "carsandbids", "ebay", "pcarmarket")

    def test_rejects_unknown_source(self):
        with pytest.raises(ValueError, match="Unknown source"):
            normalize_sources(["autotrader"])


class TestGetRefreshCandidates:
    @pytest.mark.asyncio
    async def test_only_missing_filter_is_optional(self):
        factory, session = _factory_with_session()
        row = MagicMock(
            source="bat",
            source_url="https://bringatrailer.com/listing/foo",
            listing_status=ListingStatusEnum.active,
        )
        execute_result = MagicMock()
        execute_result.__iter__.return_value = iter([row])
        session.execute = AsyncMock(return_value=execute_result)

        await get_refresh_candidates(
            factory,
            sources=["bat"],
            limit=5,
            only_missing=False,
        )

        statement = session.execute.await_args.args[0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "current_bid IS NULL" not in compiled
        assert "LIMIT 5" in compiled


class TestRefreshCandidate:
    @pytest.mark.asyncio
    async def test_updates_listing_for_active_page(self):
        candidate = RefreshCandidate(
            source="bat",
            source_url="https://bringatrailer.com/listing/foo",
            listing_status=ListingStatusEnum.active,
        )
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=_raw_page())
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing())

        listing = MagicMock()
        factory, session = _factory_with_session()

        with patch(
            "garage_radar.maintenance.auction_refresh.normalize",
            return_value={
                "source": "bat",
                "source_url": candidate.source_url,
                "year": 1995,
                "current_bid": 72000.0,
                "auction_end_at": datetime(2026, 4, 2, 17, 0, tzinfo=UTC),
                "time_remaining_text": "2 days",
                "is_completed": False,
            },
        ), patch(
            "garage_radar.maintenance.auction_refresh.upsert_listing",
            new_callable=AsyncMock,
            return_value=("updated", listing),
        ) as mock_upsert_listing, patch(
            "garage_radar.maintenance.auction_refresh.upsert_comp",
            new_callable=AsyncMock,
        ) as mock_upsert_comp:
            result = await refresh_candidate(candidate, crawler, parser, factory)

        assert result["status"] == "updated"
        assert result["listing_action"] == "updated"
        assert result["promoted_to_comp"] is False
        mock_upsert_listing.assert_awaited_once()
        mock_upsert_comp.assert_not_awaited()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_promotes_completed_page_to_comp_and_marks_listing_sold(self):
        candidate = RefreshCandidate(
            source="bat",
            source_url="https://bringatrailer.com/listing/foo",
            listing_status=ListingStatusEnum.active,
        )
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=_raw_page())
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing(is_completed=True))
        parser.parse_comp = MagicMock(return_value=_parsed_comp())

        listing = MagicMock()
        listing.listing_status = ListingStatusEnum.active
        factory, session = _factory_with_session()

        with patch(
            "garage_radar.maintenance.auction_refresh.normalize",
            return_value={
                "source": "bat",
                "source_url": candidate.source_url,
                "year": 1995,
                "final_price": 85000.0,
                "sale_date": datetime(2026, 3, 28, tzinfo=UTC).date(),
                "is_completed": True,
            },
        ), patch(
            "garage_radar.maintenance.auction_refresh.upsert_listing",
            new_callable=AsyncMock,
            return_value=("updated", listing),
        ), patch(
            "garage_radar.maintenance.auction_refresh.upsert_comp",
            new_callable=AsyncMock,
            return_value=("inserted", MagicMock()),
        ) as mock_upsert_comp:
            result = await refresh_candidate(candidate, crawler, parser, factory)

        assert result["promoted_to_comp"] is True
        assert result["comp_action"] == "inserted"
        assert result["completed_status"] == ListingStatusEnum.sold.value
        assert listing.listing_status == ListingStatusEnum.sold
        mock_upsert_comp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_promotes_completed_page_when_sale_price_exists_but_sale_date_missing(self):
        candidate = RefreshCandidate(
            source="bat",
            source_url="https://bringatrailer.com/listing/foo",
            listing_status=ListingStatusEnum.active,
        )
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=_raw_page())
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing(is_completed=True))
        parser.parse_comp = MagicMock(return_value=_parsed_comp())

        listing = MagicMock()
        listing.listing_status = ListingStatusEnum.active
        factory, session = _factory_with_session()

        with patch(
            "garage_radar.maintenance.auction_refresh.normalize",
            return_value={
                "source": "bat",
                "source_url": candidate.source_url,
                "year": 1995,
                "sale_price": 85000.0,
                "sale_date": None,
                "final_price": 85000.0,
                "is_completed": True,
            },
        ), patch(
            "garage_radar.maintenance.auction_refresh.upsert_listing",
            new_callable=AsyncMock,
            return_value=("updated", listing),
        ), patch(
            "garage_radar.maintenance.auction_refresh.upsert_comp",
            new_callable=AsyncMock,
            return_value=("inserted", MagicMock()),
        ) as mock_upsert_comp:
            result = await refresh_candidate(candidate, crawler, parser, factory)

        assert result["promoted_to_comp"] is True
        assert result["completed_status"] == ListingStatusEnum.sold.value
        mock_upsert_comp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_404_marks_listing_removed(self):
        candidate = RefreshCandidate(
            source="bat",
            source_url="https://bringatrailer.com/listing/foo",
            listing_status=ListingStatusEnum.active,
        )
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=_raw_page(status_code=404))
        parser = MagicMock()
        factory, session = _factory_with_session()

        with patch(
            "garage_radar.maintenance.auction_refresh.mark_listing_removed",
            new_callable=AsyncMock,
        ) as mock_removed:
            result = await refresh_candidate(candidate, crawler, parser, factory)

        assert result == {"status": "removed", "fetched": True}
        mock_removed.assert_awaited_once_with(session, "bat", candidate.source_url)
        session.commit.assert_awaited_once()


class TestRefreshActiveAuctions:
    @pytest.mark.asyncio
    async def test_rolls_up_refresh_stats(self):
        factory, _ = _factory_with_session()
        candidates = [
            RefreshCandidate(
                source="bat",
                source_url="https://bringatrailer.com/listing/foo",
                listing_status=ListingStatusEnum.active,
            ),
            RefreshCandidate(
                source="carsandbids",
                source_url="https://carsandbids.com/auctions/bar",
                listing_status=ListingStatusEnum.relist,
            ),
        ]
        results = [
            {
                "status": "updated",
                "fetched": True,
                "listing_action": "updated",
                "comp_action": "inserted",
                "completed_status": ListingStatusEnum.sold.value,
                "promoted_to_comp": True,
            },
            {
                "status": "fetch_error",
                "fetched": True,
            },
        ]

        with patch(
            "garage_radar.maintenance.auction_refresh.get_refresh_candidates",
            new_callable=AsyncMock,
            return_value=candidates,
        ), patch(
            "garage_radar.maintenance.auction_refresh.get_crawler",
            side_effect=[MagicMock(), MagicMock()],
        ), patch(
            "garage_radar.maintenance.auction_refresh.get_parser",
            side_effect=[MagicMock(), MagicMock()],
        ), patch(
            "garage_radar.maintenance.auction_refresh.refresh_candidate",
            new_callable=AsyncMock,
            side_effect=results,
        ):
            stats = await refresh_active_auctions(factory, sources=["bat", "carsandbids"])

        assert stats["candidates"] == 2
        assert stats["pages_fetched"] == 2
        assert stats["listings_updated"] == 1
        assert stats["comps_inserted"] == 1
        assert stats["sold"] == 1
        assert stats["promoted_to_comp"] == 1
        assert stats["fetch_errors"] == 1
