"""
Cars & Bids (carsandbids.com) crawler.

Fetches listing URLs from C&B search results for Porsche 911.

Target URLs:
  Active:    https://carsandbids.com/search/?q=porsche+911
  Completed: https://carsandbids.com/search/?q=porsche+911&sold=1

Individual listing: https://carsandbids.com/auctions/{slug}/

Rate: 1 req / 4s (0.25 req/s) with ±20% jitter.
"""
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseCrawler, RawPage
from garage_radar.sources.shared.http_client import HttpClient
from garage_radar.sources.shared.snapshot_store import get_snapshot_store

logger = logging.getLogger(__name__)

_BASE_URL = "https://carsandbids.com"
_SEARCH_URL = "https://carsandbids.com/search/"
_RATE = 0.25  # 1 req / 4s

_LISTING_URL_RE = re.compile(r"https://carsandbids\.com/auctions/[a-z0-9-]+/?$")


class CarsAndBidsCrawler(BaseCrawler):
    source_name = "carsandbids"

    def __init__(self, include_sold: bool = True, max_pages: int = 10):
        self.include_sold = include_sold
        self.max_pages = max_pages

    async def get_listing_urls(self, limit: Optional[int] = None) -> list[str]:
        urls: set[str] = set()

        async with HttpClient(
            source_name=self.source_name,
            domain="carsandbids.com",
            rate=_RATE,
        ) as client:
            await self._crawl_search(client, sold=False, urls=urls, limit=limit)
            if self.include_sold:
                await self._crawl_search(client, sold=True, urls=urls, limit=limit)

        result = list(urls)
        if limit:
            result = result[:limit]
        logger.info("C&B: collected %d listing URLs.", len(result))
        return result

    async def _crawl_search(
        self,
        client: HttpClient,
        sold: bool,
        urls: set[str],
        limit: Optional[int],
    ) -> None:
        """Paginate through C&B search results and collect listing URLs."""
        for page_num in range(1, self.max_pages + 1):
            if limit and len(urls) >= limit:
                break

            params = f"?q=porsche+911" + ("&sold=1" if sold else "")
            if page_num > 1:
                params += f"&page={page_num}"
            url = _SEARCH_URL + params

            raw = await client.get(url, referer=_BASE_URL)
            if raw.status_code == 0:
                logger.error("C&B search page failed permanently: %s", url)
                break
            if raw.status_code == 404:
                break

            store = get_snapshot_store()
            store.write(raw)

            new_urls = self._extract_listing_urls(raw.content)
            if not new_urls:
                logger.info("C&B: no listing URLs on page %d — stopping.", page_num)
                break

            before = len(urls)
            urls.update(new_urls)
            after = len(urls)
            logger.info(
                "C&B page %d (%s): found %d URLs, %d new.",
                page_num,
                "sold" if sold else "active",
                len(new_urls),
                after - before,
            )

    def _extract_listing_urls(self, html: str) -> list[str]:
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        found = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("/auctions/"):
                href = urljoin(_BASE_URL, href)
            href = href.split("?")[0].split("#")[0].rstrip("/")
            if _LISTING_URL_RE.match(href):
                found.append(href)

        # Deduplicate preserving order
        seen = set()
        result = []
        for u in found:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    async def fetch_page(self, url: str) -> RawPage:
        async with HttpClient(
            source_name=self.source_name,
            domain="carsandbids.com",
            rate=_RATE,
        ) as client:
            raw = await client.get(url, referer=_SEARCH_URL)
            store = get_snapshot_store()
            path = store.write(raw)
            if path:
                raw.snapshot_path = path
            return raw
