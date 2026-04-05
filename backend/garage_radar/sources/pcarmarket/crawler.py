"""
PCA Market (pcarmarket.com) crawler.

PCARMARKET now serves auction collections from `/auctions` and `/results`, with the
first page embedded as JSON inside the HTML and subsequent pages available from the
linked API URLs in that payload. We fetch with a browser-impersonating client and
filter locally for the configured target.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseCrawler, RawPage
from garage_radar.sources.shared.impersonated_http_client import ImpersonatedHttpClient
from garage_radar.sources.shared.snapshot_store import get_snapshot_store
from garage_radar.sources.targeting import VehicleTarget, get_vehicle_target

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.pcarmarket.com"
_ACTIVE_URL = "https://www.pcarmarket.com/auctions"
_SOLD_URL = "https://www.pcarmarket.com/results"
_RATE = 0.17  # 1 req / 6s

_LISTING_RE = re.compile(r"https://www\.pcarmarket\.com/auction/[a-z0-9-]+/?$")
_ACTIVE_SCRIPT_ID = "__PRELOADED_AUCTIONS_LIST__"
_SOLD_SCRIPT_ID = "__PRELOADED_RESULTS_LIST__"


class PcarmarketCrawler(BaseCrawler):
    source_name = "pcarmarket"

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
        urls: set[str] = set()

        async with ImpersonatedHttpClient(
            source_name=self.source_name,
            domain="pcarmarket.com",
            rate=_RATE,
        ) as client:
            await self._crawl_section(client, urls, limit, sold=False)
            if self.include_sold:
                await self._crawl_section(client, urls, limit, sold=True)

        result = list(urls)
        if limit:
            result = result[:limit]
        logger.info("PcarmarketCrawler: collected %d listing URLs.", len(result))
        return result

    async def _crawl_section(
        self,
        client: ImpersonatedHttpClient,
        urls: set[str],
        limit: int | None,
        *,
        sold: bool,
    ) -> None:
        label = "sold" if sold else "active"
        next_url = self._build_section_url(sold=sold, page_num=1)

        for page_num in range(1, self.max_pages + 1):
            if limit and len(urls) >= limit:
                break
            if not next_url:
                break

            raw = await client.get(next_url, referer=_BASE_URL)
            if raw.status_code == 0:
                logger.error("PCA Market %s fetch failed permanently: %s", label, next_url)
                break
            if raw.status_code == 404:
                break

            store = get_snapshot_store()
            store.write(raw)

            payload = self._extract_payload(raw.content, sold=sold)
            if not payload:
                logger.info("PCA Market %s page %d: no payload found.", label, page_num)
                break

            new_urls = self._extract_listing_urls_from_payload(payload)
            if not new_urls:
                logger.info("PCA Market %s page %d: no listings, stopping.", label, page_num)
                break

            before = len(urls)
            urls.update(new_urls)
            logger.info(
                "PCA Market %s page %d: %d new URLs (total %d).",
                label,
                page_num,
                len(urls) - before,
                len(urls),
            )

            next_url = self._normalize_next_url(payload.get("next"))

    def _build_section_url(self, *, sold: bool, page_num: int) -> str:
        base_url = _SOLD_URL if sold else _ACTIVE_URL
        params = [f"search={quote_plus(self.target.marketplace_query or self.target.label)}"]
        if page_num > 1:
            params.append(f"page={page_num}")
        return f"{base_url}?{'&'.join(params)}"

    def _extract_payload(self, content: str, *, sold: bool) -> dict | None:
        stripped = content.lstrip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return None

        soup = BeautifulSoup(content, "lxml")
        script_id = _SOLD_SCRIPT_ID if sold else _ACTIVE_SCRIPT_ID
        script = soup.find("script", id=script_id, attrs={"type": "application/json"})
        if not script or not script.string:
            return None
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            logger.warning("PCA Market %s payload was not valid JSON.", "sold" if sold else "active")
            return None

    def _extract_listing_urls_from_payload(self, payload: dict) -> list[str]:
        found: list[str] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue

            vehicle = item.get("vehicle")
            if not isinstance(vehicle, dict):
                continue

            title = str(item.get("title") or "").strip()
            slug = str(item.get("slug") or "").strip().strip("/")
            if not title or not slug:
                continue

            if not self.target.matches_listing(
                title=title,
                make=str(vehicle.get("make") or "").strip() or None,
                model=str(vehicle.get("model") or "").strip() or None,
                year=_coerce_int(vehicle.get("year")),
            ):
                continue

            url = urljoin(_BASE_URL, f"/auction/{slug}/").rstrip("/")
            if _LISTING_RE.match(url):
                found.append(url)

        seen: set[str] = set()
        result: list[str] = []
        for url in found:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    def _normalize_next_url(self, url: object) -> str | None:
        if not isinstance(url, str) or not url.strip():
            return None
        normalized = url.strip()
        if normalized.startswith("http://"):
            normalized = "https://" + normalized[len("http://"):]
        return normalized

    async def fetch_page(self, url: str) -> RawPage:
        async with ImpersonatedHttpClient(
            source_name=self.source_name,
            domain="pcarmarket.com",
            rate=_RATE,
        ) as client:
            raw = await client.get(
                url,
                referer=self._build_section_url(sold=False, page_num=1),
            )

        store = get_snapshot_store()
        path = store.write(raw)
        if path:
            raw.snapshot_path = path
        return raw


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
