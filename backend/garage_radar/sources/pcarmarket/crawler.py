"""
PCA Market (pcarmarket.com) crawler.

PCA Market is a Porsche-specialist auction site. All listings are Porsches,
so signal quality is high and noise filtering is minimal.

Target URLs:
  Active:    https://www.pcarmarket.com/auction/
  Completed: https://www.pcarmarket.com/statistics/  (sold results)

Individual listing: https://www.pcarmarket.com/auction/{slug}/

Rate: 1 req / 6s (0.17 req/s) — conservative, Porsche-community site.
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

_BASE_URL = "https://www.pcarmarket.com"
_ACTIVE_URL = "https://www.pcarmarket.com/auction/"
_SOLD_URL = "https://www.pcarmarket.com/statistics/"
_RATE = 0.17  # 1 req / 6s

_LISTING_RE = re.compile(
    r"https://www\.pcarmarket\.com/auction/[a-z0-9-]+/?$"
)

# PCA Market uses 911 as a filter keyword
_SEARCH_PARAMS_ACTIVE = "?search=911"
_SEARCH_PARAMS_SOLD = "?search=911&model=911"


class PcarmarketCrawler(BaseCrawler):
    source_name = "pcarmarket"

    def __init__(self, include_sold: bool = True, max_pages: int = 10):
        self.include_sold = include_sold
        self.max_pages = max_pages

    async def get_listing_urls(self, limit: Optional[int] = None) -> list[str]:
        urls: set[str] = set()

        async with HttpClient(
            source_name=self.source_name,
            domain="pcarmarket.com",
            rate=_RATE,
        ) as client:
            await self._crawl_section(
                client, _ACTIVE_URL + _SEARCH_PARAMS_ACTIVE,
                urls, limit, label="active"
            )
            if self.include_sold:
                await self._crawl_section(
                    client, _SOLD_URL + _SEARCH_PARAMS_SOLD,
                    urls, limit, label="sold"
                )

        result = list(urls)
        if limit:
            result = result[:limit]
        logger.info("PcarmarketCrawler: collected %d listing URLs.", len(result))
        return result

    async def _crawl_section(
        self,
        client: HttpClient,
        start_url: str,
        urls: set[str],
        limit: Optional[int],
        label: str,
    ) -> None:
        """Follow pagination on a PCA Market listing/results page."""
        url = start_url
        for page_num in range(1, self.max_pages + 1):
            if limit and len(urls) >= limit:
                break

            if page_num > 1:
                sep = "&" if "?" in url else "?"
                url = f"{start_url}{sep}page={page_num}"

            raw = await client.get(url, referer=_BASE_URL)
            if raw.status_code == 0:
                logger.error("PCA Market fetch failed permanently: %s", url)
                break
            if raw.status_code == 404:
                break

            store = get_snapshot_store()
            store.write(raw)

            new_urls = self._extract_listing_urls(raw.content)
            if not new_urls:
                logger.info(
                    "PCA Market %s page %d: no listings — stopping.", label, page_num
                )
                break

            before = len(urls)
            urls.update(new_urls)
            logger.info(
                "PCA Market %s page %d: %d new URLs (total %d).",
                label, page_num, len(urls) - before, len(urls),
            )

    def _extract_listing_urls(self, html: str) -> list[str]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        found = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("/auction/"):
                href = urljoin(_BASE_URL, href)
            href = href.split("?")[0].split("#")[0].rstrip("/")
            if _LISTING_RE.match(href):
                found.append(href)

        seen: set[str] = set()
        result = []
        for u in found:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    async def fetch_page(self, url: str) -> RawPage:
        async with HttpClient(
            source_name=self.source_name,
            domain="pcarmarket.com",
            rate=_RATE,
        ) as client:
            raw = await client.get(url, referer=_ACTIVE_URL)
            store = get_snapshot_store()
            path = store.write(raw)
            if path:
                raw.snapshot_path = path
            return raw
