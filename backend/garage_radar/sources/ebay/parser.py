"""
eBay listing parser.

Parses the JSON response from the eBay Shopping API GetSingleItem call.
Returns a ParsedComp for ended/completed items or ParsedListing for active.

eBay item data structure (GetSingleItem JSON):
  Item.Title            "1995 Porsche 911 Carrera Coupe 5-Speed"
  Item.CurrentPrice     {"Value": 42500.0, "CurrencyID": "USD"}
  Item.SellingStatus    {"ConvertedCurrentPrice": {...}, "ListingStatus": "Ended"}
  Item.EndTime          "2025-02-14T18:30:00.000Z"
  Item.ItemSpecifics    {"NameValueList": [{"Name": "Mileage", "Value": "87000"}, ...]}
  Item.VIN              "WP0AA2994SS300001"
  Item.Description      HTML string
  Item.PrimaryCategory  {"CategoryID": "6001", "CategoryName": "Cars & Trucks"}
  Item.Seller           {"UserID": "seller123"}
  Item.HitCount         42

All field extraction is best-effort; None on any failure, never raises.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\b(196[5-9]|19[7-9]\d|1998)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\.?)", re.IGNORECASE)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_PRICE_CLEAN_RE = re.compile(r"[^\d.]")


class EbayParser(BaseParser):
    source_name = "ebay"

    def parse_listing(self, raw: RawPage) -> Optional[ParsedListing]:
        item = self._load_item(raw)
        if not item:
            return None

        is_completed = self._is_ended(item)
        parsed = ParsedListing(
            source="ebay",
            source_url=raw.url,
            scrape_ts=raw.fetched_at,
            title_raw=item.get("Title"),
            year=self._extract_year(item),
            asking_price=self._extract_price(item),
            currency=self._extract_currency(item),
            mileage=self._extract_mileage(item),
            vin=item.get("VIN") or self._extract_vin_from_specifics(item),
            exterior_color_raw=self._spec_value(item, "Exterior Color"),
            interior_color_raw=self._spec_value(item, "Interior Color"),
            transmission_raw=self._spec_value(item, "Transmission"),
            drivetrain_raw=self._spec_value(item, "Drive Type"),
            body_style_raw=self._spec_value(item, "Body Type"),
            engine_variant=self._spec_value(item, "Engine"),
            trim=self._spec_value(item, "Trim"),
            description_raw=self._strip_html(item.get("Description") or ""),
            seller_name=item.get("Seller", {}).get("UserID"),
            seller_type_raw="private",  # eBay default
            is_completed=is_completed,
            listing_date=self._extract_listing_date(item),
        )
        return parsed

    def parse_comp(self, raw: RawPage) -> Optional[ParsedComp]:
        item = self._load_item(raw)
        if not item:
            return None
        if not self._is_ended(item):
            return None

        comp = ParsedComp(
            source="ebay",
            source_url=raw.url,
            scrape_ts=raw.fetched_at,
            title_raw=item.get("Title"),
            year=self._extract_year(item),
            final_price=self._extract_price(item),
            currency=self._extract_currency(item),
            mileage=self._extract_mileage(item),
            vin=item.get("VIN") or self._extract_vin_from_specifics(item),
            exterior_color_raw=self._spec_value(item, "Exterior Color"),
            interior_color_raw=self._spec_value(item, "Interior Color"),
            transmission_raw=self._spec_value(item, "Transmission"),
            drivetrain_raw=self._spec_value(item, "Drive Type"),
            body_style_raw=self._spec_value(item, "Body Type"),
            engine_variant=self._spec_value(item, "Engine"),
            trim=self._spec_value(item, "Trim"),
            description_raw=self._strip_html(item.get("Description") or ""),
            seller_name=item.get("Seller", {}).get("UserID"),
            seller_type_raw="private",
            is_completed=True,
            sale_date=self._extract_end_date(item),
            price_type="auction_final",
        )
        return comp

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _load_item(self, raw: RawPage) -> Optional[dict]:
        if not raw.content:
            return None
        try:
            data = json.loads(raw.content)
            return data.get("Item") or data.get("item")
        except (json.JSONDecodeError, TypeError):
            logger.debug("EbayParser: could not parse JSON for %s", raw.url)
            return None

    def _is_ended(self, item: dict) -> bool:
        status = (
            item.get("SellingStatus", {}).get("ListingStatus", "") or
            item.get("ListingStatus", "")
        )
        return str(status).lower() in ("ended", "completed", "sold")

    def _extract_year(self, item: dict) -> Optional[int]:
        # Try item specifics first
        year_str = self._spec_value(item, "Year")
        if year_str:
            try:
                return int(year_str)
            except ValueError:
                pass
        # Fall back to regex on title
        title = item.get("Title") or ""
        m = _YEAR_RE.search(title)
        return int(m.group(1)) if m else None

    def _extract_price(self, item: dict) -> Optional[float]:
        # Prefer ConvertedCurrentPrice for currency-normalised value
        for path in [
            ("SellingStatus", "ConvertedCurrentPrice", "Value"),
            ("SellingStatus", "CurrentPrice", "Value"),
            ("CurrentPrice", "Value"),
        ]:
            val = item
            for key in path:
                val = val.get(key) if isinstance(val, dict) else None
            if val is not None:
                try:
                    return float(_PRICE_CLEAN_RE.sub("", str(val)))
                except ValueError:
                    pass
        return None

    def _extract_currency(self, item: dict) -> str:
        return (
            item.get("SellingStatus", {}).get("ConvertedCurrentPrice", {}).get("CurrencyID")
            or "USD"
        )

    def _extract_mileage(self, item: dict) -> Optional[int]:
        mileage_str = self._spec_value(item, "Mileage")
        if mileage_str:
            clean = _PRICE_CLEAN_RE.sub("", mileage_str.split()[0])
            try:
                return int(clean)
            except ValueError:
                pass
        # Try description
        desc = item.get("Description") or ""
        m = _MILEAGE_RE.search(desc)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _extract_vin_from_specifics(self, item: dict) -> Optional[str]:
        vin = self._spec_value(item, "VIN")
        if vin and _VIN_RE.match(vin.upper()):
            return vin.upper()
        return None

    def _spec_value(self, item: dict, name: str) -> Optional[str]:
        """Extract a value from ItemSpecifics NameValueList by field name."""
        specifics = item.get("ItemSpecifics", {})
        nvlist = specifics.get("NameValueList", [])
        if isinstance(nvlist, dict):
            nvlist = [nvlist]
        for entry in nvlist:
            if isinstance(entry, dict) and entry.get("Name", "").lower() == name.lower():
                val = entry.get("Value")
                if isinstance(val, list):
                    return val[0] if val else None
                return val
        return None

    def _extract_listing_date(self, item: dict) -> Optional[str]:
        start = item.get("StartTime") or item.get("ListingDetails", {}).get("StartTime")
        if start:
            return start[:10]
        return None

    def _extract_end_date(self, item: dict) -> Optional[str]:
        end = item.get("EndTime")
        if end:
            return end[:10]
        return None

    def _strip_html(self, html: str) -> str:
        if not html:
            return ""
        clean = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", clean).strip()[:2000]
