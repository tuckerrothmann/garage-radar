"""
Cars & Bids (carsandbids.com) crawler.

Cars & Bids now sits behind Cloudflare for search pages, but its RSS feed remains
available with a browser-impersonating client. We use the feed for discovery and
the detail pages for parsing.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from garage_radar.sources.base import BaseCrawler, RawPage
from garage_radar.sources.shared.impersonated_http_client import ImpersonatedHttpClient
from garage_radar.sources.shared.snapshot_store import get_snapshot_store
from garage_radar.sources.targeting import VehicleTarget, get_vehicle_target

logger = logging.getLogger(__name__)

_BASE_URL = "https://carsandbids.com"
_SEARCH_URL = "https://carsandbids.com/search/"
_RSS_URL = "https://carsandbids.com/rss.xml"
_RATE = 0.25  # 1 req / 4s

_LISTING_URL_RE = re.compile(
    r"https://carsandbids\.com/auctions/[A-Za-z0-9-]+/[a-z0-9-]+/?$"
)


class CarsAndBidsCrawler(BaseCrawler):
    source_name = "carsandbids"

    def __init__(
        self,
        include_sold: bool = True,
        max_pages: int = 10,
        target: VehicleTarget | None = None,
    ) -> None:
        self.include_sold = include_sold
        self.max_pages = max_pages
        self.target = target or get_vehicle_target()

    async def get_listing_urls(self, limit: int | None = None) -> list[str]:
        async with ImpersonatedHttpClient(
            source_name=self.source_name,
            domain="carsandbids.com",
            rate=_RATE,
        ) as client:
            raw = await client.get(_RSS_URL, referer=_BASE_URL)

        if raw.status_code == 0 or not raw.content:
            logger.error("C&B RSS fetch failed permanently.")
            return []

        store = get_snapshot_store()
        store.write(raw)

        urls = self._extract_listing_urls_from_feed(raw.content)
        if limit:
            urls = urls[:limit]

        if self.include_sold:
            logger.info("C&B: RSS-backed discovery currently covers active/recent feed items only.")

        logger.info("C&B: collected %d listing URLs.", len(urls))
        return urls

    def _build_search_url(self, *, sold: bool, page_num: int) -> str:
        params = f"?q={quote_plus(self.target.marketplace_query or self.target.label)}"
        if sold:
            params += "&sold=1"
        if page_num > 1:
            params += f"&page={page_num}"
        return _SEARCH_URL + params

    def _extract_listing_urls_from_feed(self, xml_text: str) -> list[str]:
        if not xml_text:
            return []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("C&B: RSS feed was not valid XML.")
            return []

        found: list[str] = []
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip().split("?")[0].split("#")[0].rstrip("/")
            if not title or not link:
                continue
            if not _LISTING_URL_RE.match(link):
                continue
            if not self.target.matches_listing(title=title):
                continue
            found.append(link)

        seen: set[str] = set()
        result: list[str] = []
        for url in found:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    async def fetch_page(self, url: str) -> RawPage:
        async with ImpersonatedHttpClient(
            source_name=self.source_name,
            domain="carsandbids.com",
            rate=_RATE,
        ) as client:
            raw = await client.get(url, referer=_RSS_URL)

        store = get_snapshot_store()
        path = store.write(raw)
        if path:
            raw.snapshot_path = path
        return raw
