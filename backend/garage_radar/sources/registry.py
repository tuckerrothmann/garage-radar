"""Shared source registry for crawlers and parsers."""

from garage_radar.sources.base import BaseCrawler, BaseParser

VALID_SOURCES = ("bat", "carsandbids", "ebay", "pcarmarket")


def get_crawler(source_name: str, **kwargs) -> BaseCrawler:
    if source_name == "bat":
        from garage_radar.sources.bat.crawler import BaTCrawler

        return BaTCrawler(**kwargs)
    if source_name == "carsandbids":
        from garage_radar.sources.carsandbids.crawler import CarsAndBidsCrawler

        return CarsAndBidsCrawler(**kwargs)
    if source_name == "ebay":
        from garage_radar.sources.ebay.crawler import EbayCrawler

        return EbayCrawler(
            max_pages=kwargs.get("max_pages", 5),
            include_active=kwargs.get("include_active", False),
            target=kwargs.get("target"),
        )
    if source_name == "pcarmarket":
        from garage_radar.sources.pcarmarket.crawler import PcarmarketCrawler

        return PcarmarketCrawler(**kwargs)
    raise ValueError(f"Unknown source: {source_name!r}. Valid: {', '.join(VALID_SOURCES)}")


def get_parser(source_name: str) -> BaseParser:
    if source_name == "bat":
        from garage_radar.sources.bat.parser import BaTParser

        return BaTParser()
    if source_name == "carsandbids":
        from garage_radar.sources.carsandbids.parser import CarsAndBidsParser

        return CarsAndBidsParser()
    if source_name == "ebay":
        from garage_radar.sources.ebay.parser import EbayParser

        return EbayParser()
    if source_name == "pcarmarket":
        from garage_radar.sources.pcarmarket.parser import PcarmarketParser

        return PcarmarketParser()
    raise ValueError(f"Unknown source: {source_name!r}. Valid: {', '.join(VALID_SOURCES)}")
