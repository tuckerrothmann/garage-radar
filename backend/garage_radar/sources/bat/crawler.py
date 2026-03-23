"""
Bring a Trailer (BaT) crawler.

Fetches listing URLs from BaT search results for each vehicle in the watchlist.
BaT search pages paginate via &page=N.

Individual listing:  https://bringatrailer.com/listing/{slug}/

Rate: 1 req / 3s (0.33 req/s) with ±20% jitter.
"""
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from garage_radar.config import get_settings
from garage_radar.sources.base import BaseCrawler, RawPage
from garage_radar.sources.shared.http_client import HttpClient
from garage_radar.sources.shared.snapshot_store import get_snapshot_store

logger = logging.getLogger(__name__)

_BASE_URL = "https://bringatrailer.com"
_SEARCH_URL = "https://bringatrailer.com/listing/search/"
_RATE = 0.33  # 1 req / 3s

# BaT listing URLs match this pattern
_LISTING_URL_RE = re.compile(r"https://bringatrailer\.com/listing/[a-z0-9-]+/?$")


class BaTCrawler(BaseCrawler):
    source_name = "bat"

    def __init__(
        self,
        include_sold: bool = True,
        max_pages: int = 10,
        watched_vehicles=None,
    ):
        """
        include_sold: also crawl the completed/sold results page
        max_pages: cap on search pages to paginate (safety limit)
        watched_vehicles: list of WatchedVehicle from watchlist; if None, loaded lazily
        """
        self.include_sold = include_sold
        self.max_pages = max_pages
        self._watched_vehicles = watched_vehicles

    @property
    def watched_vehicles(self):
        if self._watched_vehicles is None:
            from garage_radar.watchlist import get_watched_vehicles
            self._watched_vehicles = get_watched_vehicles()
        return self._watched_vehicles

    async def get_listing_urls(self, limit: Optional[int] = None) -> list[str]:
        """
        Collect listing URLs from BaT search results for all watched vehicles.
        Returns a deduplicated list of listing page URLs.
        """
        if not self.watched_vehicles:
            logger.warning("BaTCrawler: no watched vehicles in watchlist — nothing to crawl.")
            return []

        urls: set[str] = set()

        async with HttpClient(
            source_name=self.source_name,
            domain="bringatrailer.com",
            rate=get_settings().bat_rate_limit,
        ) as client:
            for vehicle in self.watched_vehicles:
                query = vehicle.search_query("bat")
                await self._crawl_search(
                    client, query, sold=False, urls=urls, limit=limit
                )
                if self.include_sold:
                    await self._crawl_search(
                        client, query, sold=True, urls=urls, limit=limit
                    )

        result = list(urls)
        if limit:
            result = result[:limit]
        logger.info("BaT: collected %d listing URLs.", len(result))
        return result

    async def _crawl_search(
        self,
        client: HttpClient,
        query: str,
        sold: bool,
        urls: set[str],
        limit: Optional[int],
    ) -> None:
        """Paginate through BaT search results and collect listing URLs."""
        for page_num in range(1, self.max_pages + 1):
            if limit and len(urls) >= limit:
                break

            params = {"s": query}
            if sold:
                params["sold"] = "1"
            if page_num > 1:
                params["page"] = str(page_num)

            url = _SEARCH_URL + "?" + urlencode(params)

            raw = await client.get(url, referer=_BASE_URL)
            if raw.status_code == 0:
                logger.error("BaT search page failed permanently: %s", url)
                break
            if raw.status_code == 404:
                logger.debug("BaT: reached end of pages at page %d.", page_num)
                break

            store = get_snapshot_store()
            store.write(raw)

            new_urls = self._extract_listing_urls(raw.content)
            if not new_urls:
                logger.info(
                    "BaT: no listing URLs on page %d for %r — stopping.",
                    page_num, query,
                )
                break

            before = len(urls)
            urls.update(new_urls)
            after = len(urls)
            logger.info(
                "BaT page %d (%s, %r): found %d URLs, %d new.",
                page_num,
                "sold" if sold else "active",
                query,
                len(new_urls),
                after - before,
            )

    def _extract_listing_urls(self, html: str) -> list[str]:
        """Parse listing URLs from a BaT search results page."""
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        found = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("/listing/"):
                href = urljoin(_BASE_URL, href)
            href = href.split("?")[0].split("#")[0].rstrip("/")
            if _LISTING_URL_RE.match(href):
                found.append(href)

        # Deduplicate while preserving order
        seen = set()
        result = []
        for u in found:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    async def fetch_page(self, url: str) -> RawPage:
        """Fetch a single BaT listing page."""
        async with HttpClient(
            source_name=self.source_name,
            domain="bringatrailer.com",
            rate=get_settings().bat_rate_limit,
        ) as client:
            raw = await client.get(url, referer=_BASE_URL)
            store = get_snapshot_store()
            path = store.write(raw)
            if path:
                raw.snapshot_path = path
            return raw
