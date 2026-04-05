"""Tests for configurable source targeting."""

from garage_radar.config import Settings
from garage_radar.sources.bat.crawler import BaTCrawler
from garage_radar.sources.carsandbids.crawler import CarsAndBidsCrawler
from garage_radar.sources.ebay.crawler import EbayCrawler
from garage_radar.sources.pcarmarket.crawler import PcarmarketCrawler
from garage_radar.sources.targeting import (
    VehicleTarget,
    get_vehicle_targets,
    get_vehicle_targets_for_source,
)


class TestVehicleTarget:
    def test_marketplace_query_uses_make_and_model(self):
        target = VehicleTarget(make="Ford", model="Bronco")
        assert target.marketplace_query == "Ford Bronco"

    def test_ebay_keywords_include_extra_keywords(self):
        target = VehicleTarget(make="BMW", model="M3", keywords="e30 coupe")
        assert target.ebay_keywords == "BMW M3 e30 coupe"

    def test_label_falls_back_to_keywords(self):
        target = VehicleTarget(make=None, model=None, keywords="collector truck")
        assert target.label == "collector truck"

    def test_supports_source_respects_source_filter(self):
        target = VehicleTarget(make="Porsche", sources=("bat", "pcarmarket"))
        assert target.supports_source("bat") is True
        assert target.supports_source("pcarmarket") is True
        assert target.supports_source("carsandbids") is False

    def test_preset_loads_major_makes(self):
        settings = Settings(_env_file=None, vehicle_target_preset="major_makes")
        targets = get_vehicle_targets(settings)

        assert any(target.make == "Ford" for target in targets)
        assert any(target.make == "Porsche" for target in targets)
        assert any(target.make == "Tesla" for target in targets)
        assert any(target.make == "Volvo" for target in targets)

    def test_source_filter_uses_preset_sources(self):
        settings = Settings(_env_file=None, vehicle_target_preset="major_makes")
        targets = get_vehicle_targets_for_source("pcarmarket", settings)

        assert targets == (
            VehicleTarget(
                make="Porsche",
                sources=("bat", "carsandbids", "ebay", "pcarmarket"),
            ),
        )

    def test_json_targets_override_single_target_defaults(self):
        settings = Settings(
            _env_file=None,
            vehicle_target_make="Porsche",
            vehicle_target_model="911",
            vehicle_targets_json='[{"make":"Ford"},{"make":"BMW","model":"M3","sources":["bat"]}]',
        )
        targets = get_vehicle_targets(settings)

        assert targets[0] == VehicleTarget(make="Ford")
        assert targets[1] == VehicleTarget(make="BMW", model="M3", sources=("bat",))

    def test_matches_listing_uses_vehicle_fields_when_present(self):
        target = VehicleTarget(make="Ford", model="Bronco", year_min=1966, year_max=1977)

        assert target.matches_listing(
            title="1975 Ford Bronco Ranger",
            make="Ford",
            model="Bronco",
            year=1975,
        ) is True
        assert target.matches_listing(
            title="2015 Ford Bronco Concept",
            make="Ford",
            model="Bronco",
            year=2015,
        ) is False

    def test_matches_listing_can_fall_back_to_title_text(self):
        target = VehicleTarget(make="Aston Martin", model="V8 Vantage")

        assert target.matches_listing(title="2009 Aston Martin V8 Vantage Roadster") is True
        assert target.matches_listing(title="2009 Aston Martin DB9 Volante") is False


class TestCrawlerTargetUrls:
    def test_bat_page_url_adds_sold_and_page(self):
        crawler = BaTCrawler(target=VehicleTarget(make="Ford", model="Bronco"))
        assert (
            crawler._page_url(
                "https://bringatrailer.com/ford/bronco/",
                sold=True,
                page_num=2,
            )
            == "https://bringatrailer.com/ford/bronco/?sold=1&page=2"
        )

    def test_carsandbids_search_url_uses_marketplace_query(self):
        crawler = CarsAndBidsCrawler(target=VehicleTarget(make="BMW", model="M3"))
        assert (
            crawler._build_search_url(sold=False, page_num=3)
            == "https://carsandbids.com/search/?q=BMW+M3&page=3"
        )

    def test_pcarmarket_search_url_uses_query_and_model(self):
        crawler = PcarmarketCrawler(target=VehicleTarget(make="Porsche", model="356"))
        assert (
            crawler._build_section_url(sold=True, page_num=2)
            == "https://www.pcarmarket.com/results?search=Porsche+356&page=2"
        )

    def test_ebay_search_params_use_target_and_year_range(self):
        crawler = EbayCrawler(
            target=VehicleTarget(
                make="Ford",
                model="Bronco",
                keywords="restomod",
                year_min=1966,
                year_max=1977,
            )
        )
        params = crawler._build_search_params(
            operation="findCompletedItems",
            page=4,
            app_id="abc123",
        )

        assert params["keywords"] == "Ford Bronco restomod"
        assert params["paginationInput.pageNumber"] == "4"
        assert params["itemFilter(0).name"] == "MinYear"
        assert params["itemFilter(0).value"] == "1966"
        assert params["itemFilter(1).name"] == "MaxYear"
        assert params["itemFilter(1).value"] == "1977"

    def test_carsandbids_feed_filters_and_accepts_modern_url_shape(self):
        crawler = CarsAndBidsCrawler(target=VehicleTarget(make="Ford"))
        xml_text = """
        <rss>
          <channel>
            <item>
              <title>1975 Ford Bronco Ranger</title>
              <link>https://carsandbids.com/auctions/3Rn4boR1/1975-ford-bronco-ranger</link>
            </item>
            <item>
              <title>1989 BMW 325i Coupe</title>
              <link>https://carsandbids.com/auctions/3OAADbov/1989-bmw-325i-coupe</link>
            </item>
          </channel>
        </rss>
        """

        assert crawler._extract_listing_urls_from_feed(xml_text) == [
            "https://carsandbids.com/auctions/3Rn4boR1/1975-ford-bronco-ranger"
        ]

    def test_pcarmarket_payload_filters_vehicle_results(self):
        crawler = PcarmarketCrawler(target=VehicleTarget(make="Porsche", model="911"))
        payload = {
            "count": 2,
            "next": "http://www.pcarmarket.com/api/auctions/?limit=24&page=2&status=sold",
            "results": [
                {
                    "slug": "1974-porsche-911-15",
                    "title": "1974 Porsche 911",
                    "vehicle": {"make": "Porsche", "model": "911", "year": 1974},
                },
                {
                    "slug": "marketplace-porsche-sign",
                    "title": "Porsche Sign",
                    "vehicle": None,
                },
            ],
        }

        assert crawler._extract_listing_urls_from_payload(payload) == [
            "https://www.pcarmarket.com/auction/1974-porsche-911-15"
        ]
        assert (
            crawler._normalize_next_url(payload["next"])
            == "https://www.pcarmarket.com/api/auctions/?limit=24&page=2&status=sold"
        )
