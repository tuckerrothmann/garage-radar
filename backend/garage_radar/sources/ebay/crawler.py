"""
eBay Motors crawler — uses the eBay Finding API (JSON).

Searches for completed vehicle sales in eBay Motors > Cars & Trucks
(categoryId=6001) for each vehicle in the watchlist.

API: eBay Finding API v1.0.3
Rate: 0.5 req/s (1 per 2s) — conservative vs. the default 5 req/s quota.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from garage_radar.config import get_settings
from garage_radar.sources.base import BaseCrawler, RawPage

logger = logging.getLogger(__name__)

_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
_CATEGORY_ID = "6001"   # eBay Motors > Cars & Trucks
_PAGE_SIZE = 100        # Max items per page (API limit)
_RATE = 0.5             # req/s — conservative


class EbayCrawler(BaseCrawler):
    source_name = "ebay"

    def __init__(
        self,
        max_pages: int = 5,
        include_active: bool = False,
        watched_vehicles=None,
    ):
        """
        max_pages: number of paginated API calls per vehicle (100 items each)
        include_active: also fetch active (not yet ended) listings
        watched_vehicles: list of WatchedVehicle from watchlist
        """
        self.max_pages = max_pages
        self.include_active = include_active
        self._watched_vehicles = watched_vehicles

    @property
    def watched_vehicles(self):
        if self._watched_vehicles is None:
            from garage_radar.watchlist import get_watched_vehicles
            self._watched_vehicles = get_watched_vehicles()
        return self._watched_vehicles

    async def get_listing_urls(self, limit: Optional[int] = None) -> list[str]:
        """
        For eBay we return item IDs formatted as pseudo-URLs.
        The real data is fetched in fetch_page() via the Shopping API.
        """
        settings = get_settings()
        if not settings.ebay_app_id:
            logger.warning("EbayCrawler: ebay_app_id not configured — skipping.")
            return []

        if not self.watched_vehicles:
            logger.warning("EbayCrawler: no watched vehicles in watchlist — nothing to crawl.")
            return []

        item_ids: list[str] = []
        operations = ["findCompletedItems"]
        if self.include_active:
            operations.append("findItemsAdvanced")

        async with httpx.AsyncClient(timeout=20) as client:
            for vehicle in self.watched_vehicles:
                keywords = vehicle.search_query("ebay")
                for operation in operations:
                    ids = await self._search(
                        client, operation, settings.ebay_app_id, keywords,
                        vehicle.year_min, vehicle.year_max, limit,
                    )
                    item_ids.extend(ids)

        if limit:
            item_ids = item_ids[:limit]

        # Deduplicate
        seen: set[str] = set()
        unique_ids = [i for i in item_ids if not (i in seen or seen.add(i))]

        logger.info("EbayCrawler: found %d item IDs.", len(unique_ids))
        return [f"https://www.ebay.com/itm/{item_id}" for item_id in unique_ids]

    async def _search(
        self,
        client: httpx.AsyncClient,
        operation: str,
        app_id: str,
        keywords: str,
        year_min: int,
        year_max: int,
        limit: Optional[int],
    ) -> list[str]:
        item_ids: list[str] = []

        for page in range(1, self.max_pages + 1):
            if limit and len(item_ids) >= limit:
                break

            params = {
                "OPERATION-NAME": operation,
                "SERVICE-NAME": "FindingService",
                "SERVICE-VERSION": "1.0.3",
                "SECURITY-APPNAME": app_id,
                "RESPONSE-DATA-FORMAT": "JSON",
                "categoryId": _CATEGORY_ID,
                "keywords": keywords,
                "paginationInput.pageNumber": str(page),
                "paginationInput.entriesPerPage": str(_PAGE_SIZE),
                "sortOrder": "EndTimeSoonest",
                "itemFilter(0).name": "MinYear",
                "itemFilter(0).value": str(year_min),
                "itemFilter(1).name": "MaxYear",
                "itemFilter(1).value": str(year_max),
            }

            try:
                resp = await client.get(_FINDING_API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.exception("EbayCrawler: API call failed (page %d, %r).", page, keywords)
                break

            items = _extract_items(data, operation)
            if not items:
                logger.info("EbayCrawler: no items on page %d for %r — stopping.", page, keywords)
                break

            for item in items:
                item_id = item.get("itemId", [None])[0]
                if item_id:
                    item_ids.append(item_id)

            logger.info(
                "EbayCrawler: page %d (%r) → %d items total.", page, keywords, len(item_ids)
            )

            total_pages = int(
                data.get(f"{_op_key(operation)}Response", [{}])[0]
                    .get("paginationOutput", [{}])[0]
                    .get("totalPages", [1])[0]
            )
            if page >= total_pages:
                break

        return item_ids

    async def fetch_page(self, url: str) -> RawPage:
        """Fetch individual listing data via the eBay Shopping API GetSingleItem."""
        settings = get_settings()
        item_id = url.rstrip("/").split("/")[-1]

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    "https://open.api.ebay.com/shopping",
                    params={
                        "callname": "GetSingleItem",
                        "responseencoding": "JSON",
                        "appid": settings.ebay_app_id,
                        "siteid": "0",
                        "version": "967",
                        "ItemID": item_id,
                        "IncludeSelector": "Details,ItemSpecifics,Description",
                    },
                )
            content = resp.text
            status_code = resp.status_code
        except Exception:
            logger.exception("EbayCrawler.fetch_page: failed for %s", url)
            content = ""
            status_code = 0

        return RawPage(
            source="ebay",
            url=url,
            fetched_at=datetime.now(timezone.utc),
            content=content,
            content_type="json",
            status_code=status_code,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_items(data: dict, operation: str) -> list[dict]:
    key = _op_key(operation)
    try:
        return (
            data.get(f"{key}Response", [{}])[0]
                .get("searchResult", [{}])[0]
                .get("item", [])
        )
    except (IndexError, KeyError, TypeError):
        return []


def _op_key(operation: str) -> str:
    return {
        "findCompletedItems": "findCompletedItems",
        "findItemsAdvanced": "findItemsAdvanced",
    }.get(operation, operation)
