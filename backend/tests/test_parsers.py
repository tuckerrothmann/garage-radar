"""
Parser tests — validates BaT and C&B parsers against realistic HTML fixtures.

Fixtures are in data/fixtures/ and represent the confirmed HTML structures
from working scrapers (2024–2025). Tests assert specific field values, not just
"not None", so parser regressions are immediately visible.

Run: pytest backend/tests/test_parsers.py -v
"""
from datetime import date, datetime
from pathlib import Path

import pytest

from garage_radar.sources.base import RawPage
from garage_radar.sources.bat.parser import BaTParser
from garage_radar.sources.carsandbids.parser import CarsAndBidsParser

FIXTURE_DIR = Path(__file__).parents[2] / "data" / "fixtures"

_SCRAPE_TS = datetime(2025, 3, 15, 12, 0, 0)


def _make_raw(filename: str, url: str) -> RawPage:
    """Load an HTML fixture file as a RawPage."""
    path = FIXTURE_DIR / filename
    content = path.read_text(encoding="utf-8")
    return RawPage(
        source="bat" if "bat" in filename else "carsandbids",
        url=url,
        fetched_at=_SCRAPE_TS,
        content=content,
        content_type="html",
        status_code=200,
    )


# ── BaT parser tests ──────────────────────────────────────────────────────────

class TestBaTParserActiveListing:
    """BaT active listing: 1995 993 Carrera Coupe."""

    @pytest.fixture(autouse=True)
    def setup(self):
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        self.parsed = BaTParser().parse_listing(raw)

    def test_parse_returns_result(self):
        assert self.parsed is not None, "Parser returned None — check title extraction"

    def test_year(self):
        assert self.parsed.year == 1995

    def test_title_contains_year(self):
        assert "1995" in self.parsed.title_raw

    def test_body_style_coupe(self):
        assert self.parsed.body_style_raw == "coupe"

    def test_transmission_manual(self):
        assert self.parsed.transmission_raw == "manual"

    def test_mileage(self):
        assert self.parsed.mileage == 68200

    def test_exterior_color(self):
        assert self.parsed.exterior_color_raw is not None
        assert "Riviera Blue" in self.parsed.exterior_color_raw

    def test_vin(self):
        assert self.parsed.vin == "WP0AA2994SS300001"

    def test_location(self):
        assert self.parsed.location is not None
        assert "Los Angeles" in self.parsed.location

    def test_asking_price(self):
        assert self.parsed.asking_price == 82000.0

    def test_current_bid(self):
        assert self.parsed.current_bid == 82000.0

    def test_time_remaining(self):
        assert self.parsed.time_remaining_text == "3 days"

    def test_description_not_empty(self):
        assert self.parsed.description_raw
        assert len(self.parsed.description_raw) > 50

    def test_engine_variant(self):
        assert self.parsed.engine_variant == "3.6"

    def test_not_completed(self):
        assert not self.parsed.is_completed

    def test_seller_type(self):
        assert self.parsed.seller_type_raw == "auction_house"

    def test_listing_date(self):
        assert self.parsed.listing_date == "2025-02-14"

    def test_mileage_prefixed_modern_title_still_extracts_year(self):
        raw = RawPage(
            source="bat",
            url="https://bringatrailer.com/listing/2018-porsche-911-gt3-180/",
            fetched_at=_SCRAPE_TS,
            content="""
            <html>
              <body>
                <h1 class="post-title listing-post-title">15k-Mile 2018 Porsche 911 GT3</h1>
              </body>
            </html>
            """,
            content_type="html",
            status_code=200,
        )

        parsed = BaTParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.year == 2018
        assert parsed.title_raw == "15k-Mile 2018 Porsche 911 GT3"

    def test_hidden_year_title_can_fall_back_to_url_slug(self):
        raw = RawPage(
            source="bat",
            url="https://bringatrailer.com/listing/1971-austin-mini-van-2/",
            fetched_at=_SCRAPE_TS,
            content="""
            <html>
              <body>
                <h1 class="post-title listing-post-title">33-Years-Owned 1,275cc-Powered Mini Van</h1>
              </body>
            </html>
            """,
            content_type="html",
            status_code=200,
        )

        parsed = BaTParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.title_raw == "1971 Austin Mini Van"
        assert parsed.year == 1971
        assert parsed.make_raw == "Austin"
        assert parsed.model_raw == "Mini"


class TestBaTParserCompletedListing:
    """BaT completed auction: 1991 964 Carrera 2."""

    @pytest.fixture(autouse=True)
    def setup(self):
        raw = _make_raw(
            "bat_completed_listing.html",
            "https://bringatrailer.com/listing/1991-porsche-911-carrera-2-coupe/",
        )
        self.parsed = BaTParser().parse_comp(raw)

    def test_parse_returns_result(self):
        assert self.parsed is not None, "Parser returned None — check is_completed detection"

    def test_year(self):
        assert self.parsed.year == 1991

    def test_final_price(self):
        assert self.parsed.final_price == 71500.0

    def test_sale_date(self):
        assert self.parsed.sale_date == date(2025, 2, 20)

    def test_bidder_count(self):
        assert self.parsed.bidder_count == 47

    def test_is_completed(self):
        assert self.parsed.is_completed

    def test_vin(self):
        assert self.parsed.vin == "WP0AA2964MS400123"

    def test_mileage(self):
        assert self.parsed.mileage == 94500

    def test_exterior_color(self):
        assert self.parsed.exterior_color_raw is not None
        assert "Guards Red" in self.parsed.exterior_color_raw

    def test_transmission_manual(self):
        assert self.parsed.transmission_raw == "manual"

    def test_location(self):
        assert self.parsed.location is not None
        assert "Denver" in self.parsed.location


# ── C&B parser tests ──────────────────────────────────────────────────────────

class TestCarsAndBidsParserActiveListing:
    """C&B active listing: 1991 964 Carrera 2."""

    @pytest.fixture(autouse=True)
    def setup(self):
        raw = _make_raw(
            "carsandbids_active_listing.html",
            "https://carsandbids.com/auctions/1991-porsche-911-carrera-2-coupe/",
        )
        self.parsed = CarsAndBidsParser().parse_listing(raw)

    def test_parse_returns_result(self):
        assert self.parsed is not None, "Parser returned None — check title extraction"

    def test_year(self):
        assert self.parsed.year == 1991

    def test_body_style_coupe(self):
        assert self.parsed.body_style_raw == "coupe"

    def test_transmission_manual(self):
        assert self.parsed.transmission_raw == "manual"

    def test_mileage(self):
        assert self.parsed.mileage == 94000

    def test_exterior_color(self):
        assert self.parsed.exterior_color_raw == "Guards Red"

    def test_vin(self):
        assert self.parsed.vin == "WP0AA2964MS400123"

    def test_location(self):
        assert self.parsed.location == "Denver, CO"

    def test_asking_price(self):
        assert self.parsed.asking_price == 61000.0

    def test_current_bid(self):
        assert self.parsed.current_bid == 61000.0

    def test_bidder_count(self):
        assert self.parsed.bidder_count == 23

    def test_description_not_empty(self):
        assert self.parsed.description_raw
        assert len(self.parsed.description_raw) > 50

    def test_engine_variant(self):
        assert self.parsed.engine_variant == "3.6"

    def test_listing_date(self):
        assert self.parsed.listing_date == "2025-02-12"

    def test_not_completed(self):
        assert not self.parsed.is_completed


class TestCarsAndBidsParserCompletedListing:
    """C&B completed auction: 1997 993 Carrera."""

    @pytest.fixture(autouse=True)
    def setup(self):
        raw = _make_raw(
            "carsandbids_completed_listing.html",
            "https://carsandbids.com/auctions/1997-porsche-911-carrera-coupe/",
        )
        self.parsed = CarsAndBidsParser().parse_comp(raw)

    def test_parse_returns_result(self):
        assert self.parsed is not None, "Parser returned None — check is_completed detection"

    def test_year(self):
        assert self.parsed.year == 1997

    def test_final_price(self):
        assert self.parsed.final_price == 104000.0

    def test_bidder_count(self):
        assert self.parsed.bidder_count == 62

    def test_is_completed(self):
        assert self.parsed.is_completed

    def test_vin(self):
        assert self.parsed.vin == "WP0AA2997VS300456"

    def test_mileage(self):
        assert self.parsed.mileage == 39800

    def test_exterior_color(self):
        assert self.parsed.exterior_color_raw == "Arctic Silver Metallic"

    def test_location(self):
        assert self.parsed.location == "Scottsdale, AZ"

    def test_transmission_manual_6sp(self):
        # 1997 993 C2S had a 6-speed option but most had 6-speed
        assert self.parsed.transmission_raw in ("manual", "manual-6sp")


# ── Normalization pipeline integration tests ──────────────────────────────────

class TestNormalizationPipeline:
    """
    Run the full parse → normalize pipeline on fixtures.
    Validates that field-level normalization produces expected canonical values.
    """

    def test_bat_active_generation_g6(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        parsed = BaTParser().parse_listing(raw)
        assert parsed is not None
        result = normalize(parsed)
        assert result["generation"] == "G6"

    def test_bat_active_color_canonical(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        parsed = BaTParser().parse_listing(raw)
        result = normalize(parsed)
        assert result["exterior_color_canonical"] == "blue-metallic"

    def test_bat_active_transmission_canonical(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        parsed = BaTParser().parse_listing(raw)
        result = normalize(parsed)
        assert result["transmission"] == "manual"

    def test_bat_active_nlp_flags_from_description(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        parsed = BaTParser().parse_listing(raw)
        result = normalize(parsed)
        assert result["matching_numbers"] is True
        assert result["original_paint"] is True
        assert result["service_history"] is True

    def test_cb_completed_generation_g6(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "carsandbids_completed_listing.html",
            "https://carsandbids.com/auctions/1997-porsche-911-carrera-coupe/",
        )
        parsed = CarsAndBidsParser().parse_comp(raw)
        assert parsed is not None
        result = normalize(parsed)
        assert result["generation"] == "G6"

    def test_cb_active_mods_detected(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "carsandbids_active_listing.html",
            "https://carsandbids.com/auctions/1991-porsche-911-carrera-2-coupe/",
        )
        parsed = CarsAndBidsParser().parse_listing(raw)
        result = normalize(parsed)
        assert "aftermarket_wheels" in result["modification_flags"]

    def test_cb_active_original_paint_false(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "carsandbids_active_listing.html",
            "https://carsandbids.com/auctions/1991-porsche-911-carrera-2-coupe/",
        )
        parsed = CarsAndBidsParser().parse_listing(raw)
        result = normalize(parsed)
        # Description says "was repainted" → should be False
        assert result["original_paint"] is False

    def test_confidence_score_reasonable(self):
        from garage_radar.normalize.pipeline import normalize
        raw = _make_raw(
            "bat_active_listing.html",
            "https://bringatrailer.com/listing/1995-porsche-911-carrera-coupe-5-speed/",
        )
        parsed = BaTParser().parse_listing(raw)
        result = normalize(parsed)
        assert result["normalization_confidence"] is not None
        assert result["normalization_confidence"] >= 0.5, (
            f"Confidence too low: {result['normalization_confidence']}. "
            "Check which fields are failing to extract."
        )
