"""
Bring a Trailer (BaT) crawler.

Fetches listing URLs from BaT model/search pages.

Target URLs are derived from the configured vehicle target. BaT's global
search redirects many make/model queries to a canonical landing page such
as `/ford/bronco/` or `/bmw/m3/`, so we resolve that page first and crawl
from there.

Individual listing:  https://bringatrailer.com/listing/{slug}/

Rate: 1 req / 3s (0.33 req/s) with ±20% jitter.
"""
import logging
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseCrawler, RawPage
from garage_radar.sources.shared.http_client import HttpClient
from garage_radar.sources.shared.snapshot_store import get_snapshot_store
from garage_radar.sources.targeting import VehicleTarget, get_vehicle_target

logger = logging.getLogger(__name__)

_BASE_URL = "https://bringatrailer.com"
_RATE = 0.33  # 1 req / 3s

# BaT listing URLs match this pattern
_LISTING_URL_RE = re.compile(r"https://bringatrailer\.com/listing/[a-z0-9-]+/?$")


class BaTCrawler(BaseCrawler):
    source_name = "bat"

    def __init__(
        self,
        include_sold: bool = True,
        max_pages: int = 10,
        target: VehicleTarget | None = None,
    ):
        """
        include_sold: also crawl the completed/sold results page
        max_pages: cap on category pages to paginate (safety limit)
        """
        self.include_sold = include_sold
        self.max_pages = max_pages
        self.target = target or get_vehicle_target()

    async def get_listing_urls(self, limit: int | None = None) -> list[str]:
        """
        Collect listing URLs from BaT category pages (active + optionally sold).
        Returns a deduplicated list of listing page URLs.
        """
        urls: set[str] = set()

        async with HttpClient(
            source_name=self.source_name,
            domain="bringatrailer.com",
            rate=_RATE,
        ) as client:
            base_url = await self._resolve_search_url(client)
            # Active listings
            await self._crawl_category(
                client, base_url, sold=False, urls=urls, limit=limit
            )
            # Completed / sold results
            if self.include_sold:
                await self._crawl_category(
                    client, base_url, sold=True, urls=urls, limit=limit
                )

        result = list(urls)
        if limit:
            result = result[:limit]
        logger.info("BaT: collected %d listing URLs.", len(result))
        return result

    async def _crawl_category(
        self,
        client: HttpClient,
        base_url: str,
        sold: bool,
        urls: set[str],
        limit: int | None,
    ) -> None:
        """Paginate through a BaT category page and collect listing URLs."""
        for page_num in range(1, self.max_pages + 1):
            if limit and len(urls) >= limit:
                break

            url = self._page_url(base_url, sold=sold, page_num=page_num)

            raw = await client.get(url, referer=_BASE_URL)
            if raw.status_code == 0:
                logger.error("BaT category page failed permanently: %s", url)
                break
            if raw.status_code == 404:
                logger.debug("BaT: reached end of pages at page %d.", page_num)
                break

            # Save snapshot
            store = get_snapshot_store()
            store.write(raw)

            new_urls = self._extract_listing_urls(raw.content)
            if not new_urls:
                logger.info("BaT: no listing URLs on page %d — stopping pagination.", page_num)
                break

            before = len(urls)
            urls.update(new_urls)
            after = len(urls)
            logger.info(
                "BaT page %d (%s): found %d URLs, %d new.",
                page_num,
                "sold" if sold else "active",
                len(new_urls),
                after - before,
            )

    async def _resolve_search_url(self, client: HttpClient) -> str:
        """
        Resolve the configured search query to BaT's canonical landing page.

        Example:
          /?s=ford+bronco -> /ford/bronco/
        """
        search_url = f"{_BASE_URL}/?s={self.target.encoded_marketplace_query}"
        raw = await client.get(search_url, referer=_BASE_URL)
        if raw.status_code != 200:
            logger.warning("BaT: search resolution failed for %s", self.target.label)
            return search_url

        store = get_snapshot_store()
        store.write(raw)

        resolved = raw.url.rstrip("/")
        if "/listing/" in raw.content:
            logger.info("BaT: resolved %s to %s", self.target.label, resolved)
            return resolved

        logger.warning("BaT: resolved page for %s had no listing links; using search URL.", self.target.label)
        return search_url

    def _page_url(self, base_url: str, *, sold: bool, page_num: int) -> str:
        """Build a paginated BaT search URL from the resolved landing page."""
        parsed = urlparse(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if sold:
            query["sold"] = "1"
        else:
            query.pop("sold", None)
        if page_num > 1:
            query["page"] = str(page_num)
        else:
            query.pop("page", None)
        return urlunparse(parsed._replace(query=urlencode(query)))

    def _extract_listing_urls(self, html: str) -> list[str]:
        """
        Parse listing URLs from a BaT category page HTML.

        BaT renders listing cards as <article> elements or <li> items with
        <a href="/listing/..."> links. We collect all href values that
        match the listing URL pattern.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        found = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            # Normalize to absolute URL
            if href.startswith("/listing/"):
                href = urljoin(_BASE_URL, href)
            # Remove query strings / fragments from listing URLs
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
            rate=_RATE,
        ) as client:
            raw = await client.get(url, referer=_BASE_URL)
            store = get_snapshot_store()
            path = store.write(raw)
            if path:
                raw.snapshot_path = path
            return raw
