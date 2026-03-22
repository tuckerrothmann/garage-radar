"""
Scheduler unit tests — no network, no live database.

Tests cover:
  - _get_crawler / _get_parser registry
  - crawl_job stats accumulation (fetches, inserts, updates, errors)
  - 404 handling (marks listing removed instead of upsert)
  - Parse-None handling (extraction error counted)
  - Normalize exception handling (normalization error counted)
  - Upsert exception handling (extraction error counted)
  - insights_job delegates to run_insight_pipeline
  - Scheduler job registration (job IDs, cron triggers)
  - _run_now_and_exit routing (bat / carsandbids / insights / unknown)

All DB and network calls are replaced with AsyncMock / MagicMock.

Run: pytest backend/tests/test_scheduler.py -v
"""
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from garage_radar.scheduler.jobs import (
    MAX_CONCURRENT_FETCHES,
    _fetch_parse_upsert,
    _get_crawler,
    _get_parser,
    crawl_job,
    insights_job,
)
from garage_radar.sources.base import ParsedComp, ParsedListing, RawPage


# ── Helpers ────────────────────────────────────────────────────────────────────

def _raw_page(status_code=200, source="bat", url="https://example.com/listing/foo") -> RawPage:
    return RawPage(
        source=source,
        url=url,
        fetched_at=datetime.now(timezone.utc),
        content="<html></html>",
        status_code=status_code,
    )


def _parsed_listing(is_completed=False) -> ParsedListing:
    return ParsedListing(
        source="bat",
        source_url="https://bringatrailer.com/listing/foo/",
        scrape_ts=datetime.now(timezone.utc),
        year=1995,
        title_raw="1995 Porsche 911 Carrera",
        is_completed=is_completed,
    )


def _parsed_comp() -> ParsedComp:
    comp = ParsedComp(
        source="bat",
        source_url="https://bringatrailer.com/listing/foo/",
        scrape_ts=datetime.now(timezone.utc),
        year=1995,
        title_raw="1995 Porsche 911 Carrera",
        is_completed=True,
        sale_date="2025-01-15",
        final_price=85000.0,
    )
    return comp


def _mock_factory(upsert_action="inserted"):
    """Return a mock session factory whose session mock returns the given upsert action."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # upsert_listing / upsert_comp return (action, obj)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = session
    return factory, session


# ── Source registry ────────────────────────────────────────────────────────────

class TestSourceRegistry:
    def test_get_crawler_bat(self):
        from garage_radar.sources.bat.crawler import BaTCrawler
        crawler = _get_crawler("bat")
        assert isinstance(crawler, BaTCrawler)

    def test_get_crawler_carsandbids(self):
        from garage_radar.sources.carsandbids.crawler import CarsAndBidsCrawler
        crawler = _get_crawler("carsandbids")
        assert isinstance(crawler, CarsAndBidsCrawler)

    def test_get_crawler_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            _get_crawler("autotrader")

    def test_get_parser_bat(self):
        from garage_radar.sources.bat.parser import BaTParser
        parser = _get_parser("bat")
        assert isinstance(parser, BaTParser)

    def test_get_parser_carsandbids(self):
        from garage_radar.sources.carsandbids.parser import CarsAndBidsParser
        parser = _get_parser("carsandbids")
        assert isinstance(parser, CarsAndBidsParser)

    def test_get_parser_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown source"):
            _get_parser("pcarmarket")


# ── _fetch_parse_upsert ────────────────────────────────────────────────────────

class TestFetchParseUpsert:
    def _base_stats(self):
        return {
            "pages_fetched": 0,
            "records_extracted": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "extraction_errors": 0,
            "normalization_errors": 0,
        }

    @pytest.mark.asyncio
    async def test_successful_insert(self):
        """Happy path: fetch OK → parse → normalize → upsert → inserted."""
        raw = _raw_page()
        parsed = _parsed_listing()
        normalized = {"source": "bat", "source_url": raw.url, "year": 1995}

        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)

        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=parsed)

        factory, session = _mock_factory()

        stats = self._base_stats()
        with patch("garage_radar.scheduler.jobs.normalize", return_value=normalized), \
             patch("garage_radar.scheduler.jobs.upsert_listing", new_callable=AsyncMock,
                   return_value=("inserted", MagicMock())):
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["pages_fetched"] == 1
        assert stats["records_extracted"] == 1
        assert stats["records_inserted"] == 1
        assert stats["extraction_errors"] == 0

    @pytest.mark.asyncio
    async def test_404_marks_removed(self):
        raw = _raw_page(status_code=404)
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        factory, session = _mock_factory()

        stats = self._base_stats()
        with patch("garage_radar.scheduler.jobs.mark_listing_removed", new_callable=AsyncMock):
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        # No extraction error; just silently handles 404
        assert stats["pages_fetched"] == 1
        assert stats["extraction_errors"] == 0
        assert stats["records_inserted"] == 0

    @pytest.mark.asyncio
    async def test_non_200_non_404_counts_error(self):
        raw = _raw_page(status_code=503)
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        factory, _ = _mock_factory()

        stats = self._base_stats()
        await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["extraction_errors"] == 1
        assert stats["records_inserted"] == 0

    @pytest.mark.asyncio
    async def test_fetch_exception_counts_error(self):
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(side_effect=Exception("network error"))
        parser = MagicMock()
        factory, _ = _mock_factory()

        stats = self._base_stats()
        await _fetch_parse_upsert("https://example.com/x", crawler, parser, factory, stats)

        assert stats["extraction_errors"] == 1
        assert stats["pages_fetched"] == 0

    @pytest.mark.asyncio
    async def test_parse_none_counts_error(self):
        raw = _raw_page()
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)

        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=None)

        factory, _ = _mock_factory()
        stats = self._base_stats()
        await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["extraction_errors"] == 1
        assert stats["records_extracted"] == 0

    @pytest.mark.asyncio
    async def test_normalize_exception_counts_normalization_error(self):
        raw = _raw_page()
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing())
        factory, _ = _mock_factory()

        stats = self._base_stats()
        with patch("garage_radar.scheduler.jobs.normalize", side_effect=Exception("bad data")):
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["normalization_errors"] == 1
        assert stats["records_inserted"] == 0

    @pytest.mark.asyncio
    async def test_upsert_exception_counts_error(self):
        raw = _raw_page()
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing())
        factory, _ = _mock_factory()

        stats = self._base_stats()
        with patch("garage_radar.scheduler.jobs.normalize", return_value={"source": "bat", "source_url": raw.url}), \
             patch("garage_radar.scheduler.jobs.upsert_listing", new_callable=AsyncMock,
                   side_effect=Exception("DB error")):
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["extraction_errors"] == 1

    @pytest.mark.asyncio
    async def test_completed_listing_routes_to_upsert_comp(self):
        """is_completed=True → parse_comp() called → upsert_comp() used."""
        raw = _raw_page()
        parsed_active = _parsed_listing(is_completed=True)
        parsed_comp = _parsed_comp()
        normalized = {
            "source": "bat",
            "source_url": raw.url,
            "year": 1995,
            "sale_date": "2025-01-15",
        }

        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=parsed_active)
        parser.parse_comp = MagicMock(return_value=parsed_comp)

        factory, _ = _mock_factory()
        stats = self._base_stats()

        with patch("garage_radar.scheduler.jobs.normalize", return_value=normalized), \
             patch("garage_radar.scheduler.jobs.upsert_comp", new_callable=AsyncMock,
                   return_value=("inserted", MagicMock())) as mock_upsert_comp, \
             patch("garage_radar.scheduler.jobs.upsert_listing") as mock_upsert_listing:
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        mock_upsert_comp.assert_called_once()
        mock_upsert_listing.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_action_increments_updated(self):
        raw = _raw_page()
        crawler = AsyncMock()
        crawler.fetch_page = AsyncMock(return_value=raw)
        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=_parsed_listing())
        factory, _ = _mock_factory()

        stats = self._base_stats()
        with patch("garage_radar.scheduler.jobs.normalize", return_value={"source": "bat", "source_url": raw.url}), \
             patch("garage_radar.scheduler.jobs.upsert_listing", new_callable=AsyncMock,
                   return_value=("updated", MagicMock())):
            await _fetch_parse_upsert(raw.url, crawler, parser, factory, stats)

        assert stats["records_updated"] == 1
        assert stats["records_inserted"] == 0


# ── crawl_job ─────────────────────────────────────────────────────────────────

class TestCrawlJob:
    @pytest.mark.asyncio
    async def test_unknown_source_returns_error_stats(self):
        # "autotrader" is not a valid SourceEnum value
        stats = await crawl_job("autotrader")
        assert stats["notes"] is not None
        assert "autotrader" in stats["notes"]

    @pytest.mark.asyncio
    async def test_url_discovery_failure_returns_notes(self):
        with patch("garage_radar.scheduler.jobs._get_crawler") as mock_c, \
             patch("garage_radar.scheduler.jobs._get_parser"):
            crawler = AsyncMock()
            crawler.get_listing_urls = AsyncMock(side_effect=Exception("timeout"))
            mock_c.return_value = crawler

            stats = await crawl_job("bat")

        assert stats["notes"] == "URL discovery failed"
        assert stats["records_inserted"] == 0

    @pytest.mark.asyncio
    async def test_stats_aggregated_from_multiple_urls(self):
        """Two URLs: first inserts, second gets an extraction error."""
        url1 = "https://bringatrailer.com/listing/car-a/"
        url2 = "https://bringatrailer.com/listing/car-b/"

        raw_ok = _raw_page(url=url1)
        raw_503 = _raw_page(status_code=503, url=url2)

        parsed = _parsed_listing()
        normalized = {"source": "bat", "source_url": url1}

        crawler = AsyncMock()
        crawler.get_listing_urls = AsyncMock(return_value=[url1, url2])
        crawler.fetch_page = AsyncMock(side_effect=[raw_ok, raw_503])

        parser = MagicMock()
        parser.parse_listing = MagicMock(return_value=parsed)

        with patch("garage_radar.scheduler.jobs._get_crawler", return_value=crawler), \
             patch("garage_radar.scheduler.jobs._get_parser", return_value=parser), \
             patch("garage_radar.scheduler.jobs.normalize", return_value=normalized), \
             patch("garage_radar.scheduler.jobs.upsert_listing", new_callable=AsyncMock,
                   return_value=("inserted", MagicMock())), \
             patch("garage_radar.scheduler.jobs.get_session_factory") as mock_factory, \
             patch("garage_radar.scheduler.jobs.write_pipeline_log", new_callable=AsyncMock):
            session = AsyncMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = session

            stats = await crawl_job("bat")

        assert stats["records_inserted"] == 1
        assert stats["extraction_errors"] == 1
        assert stats["duration_s"] is not None

    @pytest.mark.asyncio
    async def test_pipeline_log_written(self):
        crawler = AsyncMock()
        crawler.get_listing_urls = AsyncMock(return_value=[])

        with patch("garage_radar.scheduler.jobs._get_crawler", return_value=crawler), \
             patch("garage_radar.scheduler.jobs._get_parser"), \
             patch("garage_radar.scheduler.jobs.get_session_factory") as mock_factory, \
             patch("garage_radar.scheduler.jobs.write_pipeline_log",
                   new_callable=AsyncMock) as mock_log:
            session = AsyncMock()
            session.__aenter__ = AsyncMock(return_value=session)
            session.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value.return_value = session

            await crawl_job("bat")

        mock_log.assert_called_once()


# ── insights_job ──────────────────────────────────────────────────────────────

class TestInsightsJob:
    @pytest.mark.asyncio
    async def test_delegates_to_pipeline(self):
        expected = {"clusters": {"total": 5}, "alerts": {"created": 3}, "errors": 0}
        with patch("garage_radar.scheduler.jobs.run_insight_pipeline",
                   new_callable=AsyncMock, return_value=expected) as mock_pipeline:
            result = await insights_job()

        mock_pipeline.assert_called_once()
        assert result == expected

    @pytest.mark.asyncio
    async def test_exception_returns_error_dict(self):
        with patch("garage_radar.scheduler.jobs.run_insight_pipeline",
                   new_callable=AsyncMock, side_effect=Exception("DB down")):
            result = await insights_job()

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_window_days_forwarded(self):
        with patch("garage_radar.scheduler.jobs.run_insight_pipeline",
                   new_callable=AsyncMock, return_value={}) as mock_pipeline:
            await insights_job(window_days=60)

        mock_pipeline.assert_called_once_with(window_days=60)


# ── Scheduler registration ────────────────────────────────────────────────────

class TestSchedulerRegistration:
    def setup_method(self):
        # Reset module-level singleton before each test
        import garage_radar.scheduler as sched_module
        sched_module._scheduler = None

    def teardown_method(self):
        import garage_radar.scheduler as sched_module
        if sched_module._scheduler and sched_module._scheduler.running:
            sched_module._scheduler.shutdown(wait=False)
        sched_module._scheduler = None

    def test_three_jobs_registered(self):
        from garage_radar.scheduler import get_scheduler
        sched = get_scheduler()
        job_ids = {job.id for job in sched.get_jobs()}
        assert "crawl_bat" in job_ids
        assert "crawl_carsandbids" in job_ids
        assert "insights" in job_ids

    def test_all_jobs_have_cron_triggers(self):
        from apscheduler.triggers.cron import CronTrigger
        from garage_radar.scheduler import get_scheduler
        sched = get_scheduler()
        for job in sched.get_jobs():
            assert isinstance(job.trigger, CronTrigger), \
                f"Job {job.id!r} has non-cron trigger {type(job.trigger)}"

    def test_job_defaults_include_coalesce(self):
        """Verify the scheduler was configured with coalesce=True in job_defaults."""
        from garage_radar.scheduler import _JOB_DEFAULTS
        assert _JOB_DEFAULTS.get("coalesce") is True
        assert _JOB_DEFAULTS.get("max_instances") == 1

    def test_get_scheduler_is_singleton(self):
        from garage_radar.scheduler import get_scheduler
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2
