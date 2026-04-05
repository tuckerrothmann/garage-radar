"""
Additional parser coverage for the lower-tested sources.

These tests use compact synthetic fixtures so we can lock in expected behavior
without depending on live network responses.
"""
from __future__ import annotations

import json
from datetime import datetime

from garage_radar.normalize.pipeline import normalize
from garage_radar.sources.base import RawPage
from garage_radar.sources.carsandbids.parser import CarsAndBidsParser
from garage_radar.sources.ebay.parser import EbayParser
from garage_radar.sources.pcarmarket.parser import PcarmarketParser

_SCRAPE_TS = datetime(2025, 3, 15, 12, 0, 0)


def _raw_ebay(item: dict, url: str, *, snapshot_path: str | None = None) -> RawPage:
    return RawPage(
        source="ebay",
        url=url,
        fetched_at=_SCRAPE_TS,
        content=json.dumps({"Item": item}),
        content_type="json",
        status_code=200,
        snapshot_path=snapshot_path,
    )


def _raw_pcarmarket(html: str, url: str, *, snapshot_path: str | None = None) -> RawPage:
    return RawPage(
        source="pcarmarket",
        url=url,
        fetched_at=_SCRAPE_TS,
        content=html,
        content_type="html",
        status_code=200,
        snapshot_path=snapshot_path,
    )


def _raw_carsandbids(html: str, url: str, *, snapshot_path: str | None = None) -> RawPage:
    return RawPage(
        source="carsandbids",
        url=url,
        fetched_at=_SCRAPE_TS,
        content=html,
        content_type="html",
        status_code=200,
        snapshot_path=snapshot_path,
    )


class TestEbayParser:
    def test_active_listing_uses_currency_bidcount_and_odometer_fallbacks(self):
        raw = _raw_ebay(
            {
                "Title": "1995 Porsche 911 Carrera Coupe 6-Speed",
                "CurrentPrice": {"Value": "58995.00", "CurrencyID": "EUR"},
                "SellingStatus": {
                    "ListingStatus": "Active",
                    "BidCount": "12",
                    "TimeLeft": "P3DT4H30M",
                },
                "StartTime": "2025-03-01T10:00:00.000Z",
                "EndTime": "2025-03-18T16:30:00.000Z",
                "Description": "<p>Clean coupe with 87,500 miles.</p>",
                "Seller": {"UserID": "aircooledseller"},
                "ItemSpecifics": {
                    "NameValueList": [
                        {"Name": "Year", "Value": "1995"},
                        {"Name": "Odometer", "Value": "87,500"},
                        {"Name": "Vehicle Identification Number (VIN)", "Value": "WP0AA2994SS300001"},
                        {"Name": "Exterior Color", "Value": "Midnight Blue Metallic"},
                        {"Name": "Interior Color", "Value": "Tan"},
                        {"Name": "Transmission", "Value": "Manual"},
                        {"Name": "Drive Type", "Value": "RWD"},
                        {"Name": "Body Type", "Value": "Coupe"},
                        {"Name": "Engine", "Value": "3.6L"},
                        {"Name": "Trim", "Value": "Carrera"},
                    ]
                },
            },
            "https://www.ebay.com/itm/1234567890",
            snapshot_path="data/snapshots/ebay/1234567890.json",
        )

        parsed = EbayParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.year == 1995
        assert parsed.asking_price == 58995.0
        assert parsed.current_bid == 58995.0
        assert parsed.currency == "EUR"
        assert parsed.bidder_count == 12
        assert parsed.mileage == 87500
        assert parsed.vin == "WP0AA2994SS300001"
        assert parsed.snapshot_path == "data/snapshots/ebay/1234567890.json"
        assert parsed.listing_date == "2025-03-01"
        assert parsed.auction_end_at == "2025-03-18T16:30:00.000Z"
        assert parsed.time_remaining_text == "3d 4h"
        assert parsed.is_completed is False

    def test_completed_listing_parses_comp_fields(self):
        raw = _raw_ebay(
            {
                "Title": "1991 Porsche 911 Carrera 2 Coupe",
                "SellingStatus": {
                    "ListingStatus": "Ended",
                    "ConvertedCurrentPrice": {"Value": "71500.00", "CurrencyID": "USD"},
                    "BidCount": "31",
                },
                "EndTime": "2025-02-14T18:30:00.000Z",
                "Description": "<p>Well-kept 964 with records.</p>",
                "Seller": {"UserID": "auctionfan"},
                "ItemSpecifics": {
                    "NameValueList": [
                        {"Name": "Model Year", "Value": "1991"},
                        {"Name": "Mileage", "Value": "94,500 miles"},
                        {"Name": "VIN", "Value": "WP0AA2964MS400123"},
                        {"Name": "Exterior Color", "Value": "Guards Red"},
                        {"Name": "Transmission", "Value": "Manual"},
                        {"Name": "Body Type", "Value": "Coupe"},
                    ]
                },
            },
            "https://www.ebay.com/itm/0987654321",
        )

        parsed = EbayParser().parse_comp(raw)

        assert parsed is not None
        assert parsed.year == 1991
        assert parsed.final_price == 71500.0
        assert parsed.currency == "USD"
        assert parsed.bidder_count == 31
        assert parsed.sale_date == "2025-02-14"
        assert parsed.is_completed is True

    def test_active_listing_normalizes_cleanly(self):
        raw = _raw_ebay(
            {
                "Title": "1997 Porsche 911 Carrera Coupe",
                "CurrentPrice": {"Value": "104000.00", "CurrencyID": "USD"},
                "SellingStatus": {"ListingStatus": "Active"},
                "StartTime": "2025-03-10T10:00:00.000Z",
                "Description": "<p>Numbers matching car with service records.</p>",
                "ItemSpecifics": {
                    "NameValueList": [
                        {"Name": "Year", "Value": "1997"},
                        {"Name": "Mileage", "Value": "39,800 miles"},
                        {"Name": "Exterior Color", "Value": "Arctic Silver Metallic"},
                        {"Name": "Transmission", "Value": "Manual"},
                        {"Name": "Body Type", "Value": "Coupe"},
                    ]
                },
            },
            "https://www.ebay.com/itm/1111111111",
        )

        parsed = EbayParser().parse_listing(raw)
        result = normalize(parsed)

        assert result["generation"] == "G6"
        assert result["transmission"] == "manual"
        assert result["body_style"] == "coupe"


class TestPcarmarketParser:
    def test_completed_listing_parses_sold_result(self):
        raw = _raw_pcarmarket(
            """
            <html><body>
              <h1 class="auction-title">1997 Porsche 911 Carrera Coupe</h1>
              <div class="auction-result">Sold for $104,000</div>
              <span class="bid-count">42 bids</span>
              <time datetime="2025-02-20T18:30:00Z"></time>
              <table class="auction-details">
                <tr><th>Body Style</th><td>Coupe</td></tr>
                <tr><th>Transmission</th><td>Manual</td></tr>
                <tr><th>Exterior Color</th><td>Arctic Silver Metallic</td></tr>
                <tr><th>Mileage</th><td>39,800 miles</td></tr>
                <tr><th>VIN</th><td>WP0AA2997VS300456</td></tr>
              </table>
              <div class="auction-description">Original paint and service records included.</div>
              <span class="seller-name">Aircooled Specialist</span>
            </body></html>
            """,
            "https://www.pcarmarket.com/auction/1997-porsche-911-carrera-coupe/",
            snapshot_path="data/snapshots/pcarmarket/1997-carrera.html",
        )

        parsed = PcarmarketParser().parse_comp(raw)

        assert parsed is not None
        assert parsed.year == 1997
        assert parsed.final_price == 104000.0
        assert parsed.sale_date == "2025-02-20"
        assert parsed.bidder_count == 42
        assert parsed.snapshot_path == "data/snapshots/pcarmarket/1997-carrera.html"

    def test_bid_to_page_is_not_treated_as_confirmed_comp(self):
        raw = _raw_pcarmarket(
            """
            <html><body>
              <h1 class="auction-title">1991 Porsche 911 Carrera 2 Coupe</h1>
              <div class="auction-result">Bid to $95,000</div>
              <span class="bid-amount">$95,000</span>
              <span class="bid-count">28 bids</span>
              <time datetime="2025-02-21T18:30:00Z"></time>
              <table class="auction-details">
                <tr><th>Year</th><td>1991</td></tr>
                <tr><th>Body Style</th><td>Coupe</td></tr>
                <tr><th>Transmission</th><td>Manual</td></tr>
                <tr><th>Mileage</th><td>94,000 miles</td></tr>
              </table>
              <div class="auction-description">Reserve not met.</div>
            </body></html>
            """,
            "https://www.pcarmarket.com/auction/1991-porsche-911-carrera-2-coupe/",
        )

        listing = PcarmarketParser().parse_listing(raw)
        comp = PcarmarketParser().parse_comp(raw)

        assert listing is not None
        assert listing.is_completed is False
        assert listing.current_bid == 95000.0
        assert listing.asking_price == 95000.0
        assert listing.listing_date == "2025-02-21"
        assert listing.auction_end_at == "2025-02-21T18:30:00Z"
        assert comp is None

    def test_completed_listing_normalizes_cleanly(self):
        raw = _raw_pcarmarket(
            """
            <html><body>
              <h1 class="listing-title">1995 Porsche 911 Carrera Coupe</h1>
              <div class="sold-price">$82,000</div>
              <time datetime="2025-02-14T18:30:00Z"></time>
              <table class="auction-details">
                <tr><th>Body Style</th><td>Coupe</td></tr>
                <tr><th>Transmission</th><td>Manual</td></tr>
                <tr><th>Exterior Color</th><td>Riviera Blue Metallic</td></tr>
                <tr><th>Mileage</th><td>68,200 miles</td></tr>
              </table>
              <div class="auction-description">Matching-numbers car with original paint.</div>
            </body></html>
            """,
            "https://www.pcarmarket.com/auction/1995-porsche-911-carrera-coupe/",
        )

        parsed = PcarmarketParser().parse_comp(raw)
        result = normalize(parsed)

        assert result["generation"] == "G6"
        assert result["body_style"] == "coupe"
        assert result["transmission"] == "manual"

    def test_generic_shell_title_can_fall_back_to_url_slug(self):
        raw = _raw_pcarmarket(
            """
            <html><head>
              <title>PCARMARKET | Auctions &amp; Marketplace for Collectible Vehicles</title>
              <meta property="og:title" content="PCARMARKET | Auctions &amp; Marketplace for Collectible Vehicles" />
            </head><body>
              <h1>PCARMARKET | Auctions &amp; Marketplace for Collectible Vehicles</h1>
              <div class="auction-result">Sold for $18,500</div>
              <time datetime="2025-02-20T18:30:00Z"></time>
            </body></html>
            """,
            "https://www.pcarmarket.com/auction/1985-porsche-944-11/",
        )

        parsed = PcarmarketParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.title_raw == "1985 Porsche 944"
        assert parsed.year == 1985


class TestCarsAndBidsParserMetaFallback:
    def test_meta_tags_can_seed_basic_active_listing_fields(self):
        raw = _raw_carsandbids(
            """
            <html><head>
              <title>1993 Acura Integra LS Coupe auction - Cars &amp; Bids</title>
              <meta property="og:title" content="1993 Acura Integra LS Coupe - 1 Owner Until 2022, 5-Speed Manual, Captiva Blue Pearl" />
              <meta name="description" content="This 1993 Acura Integra LS Coupe is for sale on Cars &amp; Bids! Auction ends April 2 2026." />
            </head><body><div id="root"></div></body></html>
            """,
            "https://carsandbids.com/auctions/9WLM58zv/1993-acura-integra-ls-coupe",
        )

        parsed = CarsAndBidsParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.title_raw == "1993 Acura Integra LS Coupe"
        assert parsed.year == 1993
        assert parsed.transmission_raw == "manual"
        assert parsed.body_style_raw == "coupe"
        assert parsed.listing_date == "2026-04-02"
        assert parsed.current_bid is None
        assert parsed.auction_end_at == "2026-04-02"
        assert parsed.is_completed is False

    def test_generic_shell_title_can_fall_back_to_url_slug(self):
        raw = _raw_carsandbids(
            """
            <html><head>
              <title>Cars &amp; Bids</title>
              <meta property="og:title" content="Cars &amp; Bids" />
            </head><body>
              <h1>Cars &amp; Bids</h1>
            </body></html>
            """,
            "https://carsandbids.com/auctions/0aEX8Qj6/2005-mercedes-benz-cl65-amg",
        )

        parsed = CarsAndBidsParser().parse_listing(raw)

        assert parsed is not None
        assert parsed.title_raw == "2005 Mercedes Benz CL65 AMG"
        assert parsed.year == 2005
        assert parsed.make_raw == "Mercedes-Benz"
        assert parsed.model_raw == "CL65 AMG"
