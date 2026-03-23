"""
PCA Market (pcarmarket.com) listing parser.

Confirmed PCA Market HTML structure:
  Title:        <h1 class="listing-title"> or <h1 class="auction-title">
  Price/Result: <div class="auction-result"> or <span class="bid-amount">
  Specs table:  <table class="auction-details"> or <ul class="auction-specs">
  Description:  <div class="auction-description"> or <div class="listing-description">
  Bidder count: <span class="bid-count">
  End date:     <span class="auction-end-date"> or <time datetime="...">

PCA Market listings are all Porsches, often with detailed spec tables.
All extraction is best-effort; None on failure, never raises.
"""
import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\b(196[5-9]|19[7-9]\d|1998)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\.?)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_BIDS_RE = re.compile(r"(\d+)\s*bids?", re.IGNORECASE)


class PcarmarketParser(BaseParser):
    source_name = "pcarmarket"

    def parse_listing(self, raw: RawPage) -> Optional[ParsedListing]:
        if not raw.content or raw.status_code != 200:
            return None
        try:
            return self._parse(raw, as_comp=False)
        except Exception:
            logger.exception("PcarmarketParser.parse_listing failed for %s", raw.url)
            return None

    def parse_comp(self, raw: RawPage) -> Optional[ParsedComp]:
        if not raw.content or raw.status_code != 200:
            return None
        try:
            result = self._parse(raw, as_comp=True)
            if result and result.is_completed:
                return ParsedComp(
                    source=result.source,
                    source_url=result.source_url,
                    scrape_ts=result.scrape_ts,
                    title_raw=result.title_raw,
                    year=result.year,
                    trim=result.trim,
                    engine_variant=result.engine_variant,
                    body_style_raw=result.body_style_raw,
                    transmission_raw=result.transmission_raw,
                    drivetrain_raw=result.drivetrain_raw,
                    exterior_color_raw=result.exterior_color_raw,
                    interior_color_raw=result.interior_color_raw,
                    mileage=result.mileage,
                    vin=result.vin,
                    final_price=result.final_price,
                    currency=result.currency,
                    bidder_count=result.bidder_count,
                    description_raw=result.description_raw,
                    seller_name=result.seller_name,
                    is_completed=True,
                    sale_date=result.listing_date,
                    price_type="auction_final",
                )
        except Exception:
            logger.exception("PcarmarketParser.parse_comp failed for %s", raw.url)
        return None

    def _parse(self, raw: RawPage, as_comp: bool) -> Optional[ParsedListing]:
        soup = BeautifulSoup(raw.content, "lxml")

        title = self._extract_title(soup)
        if not title:
            logger.debug("PcarmarketParser: no title found for %s", raw.url)
            return None

        year = self._extract_year(title, soup)
        is_completed, final_price, sale_date = self._extract_result(soup)
        asking_price = self._extract_asking_price(soup) if not is_completed else None

        return ParsedListing(
            source="pcarmarket",
            source_url=raw.url,
            scrape_ts=raw.fetched_at,
            title_raw=title,
            year=year,
            trim=self._spec(soup, ["trim", "model"]),
            engine_variant=self._spec(soup, ["engine", "displacement"]),
            body_style_raw=self._spec(soup, ["body", "body style", "body type"]),
            transmission_raw=self._spec(soup, ["transmission", "gearbox"]),
            drivetrain_raw=self._spec(soup, ["drivetrain", "drive"]),
            exterior_color_raw=self._spec(soup, ["exterior color", "color", "exterior"]),
            interior_color_raw=self._spec(soup, ["interior color", "interior"]),
            mileage=self._extract_mileage(soup),
            vin=self._extract_vin(soup),
            asking_price=asking_price,
            final_price=final_price,
            currency="USD",
            bidder_count=self._extract_bidder_count(soup),
            description_raw=self._extract_description(soup),
            seller_name=self._extract_seller(soup),
            seller_type_raw="auction_house",
            is_completed=is_completed,
            listing_date=sale_date if is_completed else self._extract_end_date(soup),
        )

    # ── Field extractors ──────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.listing-title", "h1.auction-title", "h1.vehicle-title", "h1"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(strip=True)
        return None

    def _extract_year(self, title: str, soup: BeautifulSoup) -> Optional[int]:
        m = _YEAR_RE.search(title)
        if m:
            return int(m.group(1))
        # Try spec table
        year_str = self._spec(soup, ["year"])
        if year_str:
            m = _YEAR_RE.search(year_str)
            if m:
                return int(m.group(1))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[bool, Optional[float], Optional[str]]:
        """Returns (is_completed, final_price, sale_date_str)."""
        # Sold result indicators
        for sel in [".auction-result", ".sold-price", ".final-price", ".hammer-price"]:
            el = soup.select_one(sel)
            if el:
                price = _extract_price_from_text(el.get_text())
                date = self._extract_end_date(soup)
                return True, price, date

        # Check for "sold" text in result badge
        for sel in [".auction-status", ".listing-status", ".badge"]:
            el = soup.select_one(sel)
            if el and "sold" in el.get_text(strip=True).lower():
                # Try to find price nearby
                price_el = el.find_next(string=_PRICE_RE.search)
                price = _extract_price_from_text(price_el) if price_el else None
                return True, price, self._extract_end_date(soup)

        return False, None, None

    def _extract_asking_price(self, soup: BeautifulSoup) -> Optional[float]:
        for sel in [".current-bid", ".bid-amount", ".reserve-price", ".buy-now-price"]:
            el = soup.select_one(sel)
            if el:
                return _extract_price_from_text(el.get_text())
        return None

    def _extract_mileage(self, soup: BeautifulSoup) -> Optional[int]:
        # Spec table first
        mileage_str = self._spec(soup, ["mileage", "miles", "odometer"])
        if mileage_str:
            m = _MILEAGE_RE.search(mileage_str)
            if m:
                try:
                    return int(m.group(1).replace(",", ""))
                except ValueError:
                    pass
            # Bare number (e.g. "87,500")
            clean = re.sub(r"[^\d]", "", mileage_str.split()[0])
            if clean:
                try:
                    return int(clean)
                except ValueError:
                    pass
        return None

    def _extract_vin(self, soup: BeautifulSoup) -> Optional[str]:
        vin_str = self._spec(soup, ["vin", "vin number"])
        if vin_str:
            m = _VIN_RE.search(vin_str.upper())
            if m:
                return m.group(1)
        # Search full page for VIN pattern
        text = soup.get_text()
        m = _VIN_RE.search(text)
        return m.group(1) if m else None

    def _extract_bidder_count(self, soup: BeautifulSoup) -> Optional[int]:
        for sel in [".bid-count", ".bids", ".num-bids"]:
            el = soup.select_one(sel)
            if el:
                m = _BIDS_RE.search(el.get_text())
                if m:
                    return int(m.group(1))
        return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [".auction-description", ".listing-description", ".vehicle-description",
                    "#description", ".description"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator=" ", strip=True)[:3000]
        return None

    def _extract_seller(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [".seller-name", ".auction-seller", ".consignor"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_end_date(self, soup: BeautifulSoup) -> Optional[str]:
        # <time datetime="2025-02-14T18:30:00Z">
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el:
            return str(time_el["datetime"])[:10]
        for sel in [".auction-end-date", ".end-date", ".sale-date"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                # Try common date formats
                for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
        return None

    def _spec(self, soup: BeautifulSoup, names: list[str]) -> Optional[str]:
        """
        Look up a spec value from a key-value table or list.
        Tries <dt>/<dd> pairs, <th>/<td> pairs, and <li> "Label: Value" patterns.
        """
        # <dl> definition lists
        for dt in soup.find_all("dt"):
            label = dt.get_text(strip=True).lower().rstrip(":")
            if label in names:
                dd = dt.find_next_sibling("dd")
                if dd:
                    return dd.get_text(strip=True)

        # <table> rows
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower().rstrip(":")
                if label in names:
                    return cells[1].get_text(strip=True)

        # <li> items with "Label: Value" format
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            if ":" in text:
                parts = text.split(":", 1)
                if parts[0].strip().lower() in names:
                    return parts[1].strip()

        return None


def _extract_price_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    m = _PRICE_RE.search(str(text))
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None
