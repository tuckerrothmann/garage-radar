"""
Cars & Bids listing parser.

C&B HTML structure (as of 2024–2025):
  - Title: <h1 class="listing-title"> or <h1>
  - Specs: <ul class="listing-essentials"> or structured key-value sections
  - Description: <div class="listing-description">
  - Sold price: visible on completed listing pages
  - Bidder count: "X bids" in page text

C&B listings tend to have shorter descriptions than BaT. NLP extraction is less reliable
but the structured spec fields are usually sufficient.
"""
import logging
import re
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_SOURCE = "carsandbids"

_YEAR_RE = re.compile(r"\b(19[6-9]\d|1998)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\.?)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([\d,]+)")
_BIDS_RE = re.compile(r"(\d+)\s+bids?", re.IGNORECASE)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_ENGINE_RE = re.compile(
    r"\b(2\.0|2\.2|2\.4|2\.7|2\.7T|3\.0|3\.0T|3\.2|3\.3T|3\.6|3\.8|3\.5)\b",
    re.IGNORECASE,
)

_BODY_STYLE_MAP = [
    ("speedster", "speedster"),
    ("cabriolet", "cabriolet"),
    ("cabrio", "cabriolet"),
    ("convertible", "cabriolet"),
    ("targa", "targa"),
    ("coupe", "coupe"),
]

_TRANSMISSION_MAP = [
    (re.compile(r"\btiptronic\b", re.I), "auto"),
    (re.compile(r"\b6[-\s]?speed\b", re.I), "manual-6sp"),
    (re.compile(r"\b(5[-\s]?speed|g50|915|manual)\b", re.I), "manual"),
]

_DRIVETRAIN_MAP = [
    (re.compile(r"\b(carrera\s*4|c4|all[-\s]?wheel)\b", re.I), "awd"),
]


class CarsAndBidsParser(BaseParser):
    source_name = _SOURCE

    def parse_listing(self, raw: RawPage) -> Optional[ParsedListing]:
        if not raw.content or raw.status_code not in (200, 301, 302):
            return None

        soup = BeautifulSoup(raw.content, "lxml")
        data = self._extract_fields(soup, raw)
        if data is None:
            return None

        return ParsedListing(
            source=_SOURCE,
            source_url=raw.url,
            scrape_ts=raw.fetched_at,
            **data,
        )

    def parse_comp(self, raw: RawPage) -> Optional[ParsedComp]:
        if not raw.content or raw.status_code not in (200, 301, 302):
            return None

        soup = BeautifulSoup(raw.content, "lxml")
        data = self._extract_fields(soup, raw)
        if data is None:
            return None

        final_price, sale_date = self._extract_result(soup)
        is_completed = final_price is not None or data.get("is_completed", False)

        if not is_completed:
            return None

        return ParsedComp(
            source=_SOURCE,
            source_url=raw.url,
            scrape_ts=raw.fetched_at,
            sale_date=sale_date,
            price_type="auction_final",
            **{k: v for k, v in data.items() if k != "is_completed"},
            final_price=final_price,
            is_completed=True,
        )

    def _extract_fields(self, soup: BeautifulSoup, raw: RawPage) -> Optional[dict]:
        title = self._extract_title(soup)
        if not title:
            logger.warning("C&B: no title found on %s — skipping.", raw.url)
            return None

        year = self._extract_year(title)
        if not year:
            logger.warning("C&B: no year in title '%s' on %s — skipping.", title, raw.url)
            return None

        description = self._extract_description(soup)
        specs = self._extract_specs(soup)
        combined_text = f"{title} {description or ''} {' '.join(specs.values())}"

        body_style = self._extract_body_style(combined_text)
        transmission = self._extract_transmission(combined_text)
        drivetrain = self._extract_drivetrain(combined_text)
        mileage = self._extract_mileage(specs, combined_text)
        color = self._extract_color(specs)
        engine_variant = self._extract_engine_variant(combined_text)
        vin = self._extract_vin(combined_text)
        location = specs.get("location") or specs.get("seller location")
        asking_price = self._extract_asking_price(soup)
        bidder_count = self._extract_bidder_count(soup)
        listing_date = self._extract_listing_date(soup)
        is_completed = self._check_is_completed(soup)
        final_price, _ = self._extract_result(soup)

        return {
            "title_raw": title,
            "year": year,
            "trim": self._extract_trim(title),
            "engine_variant": engine_variant,
            "body_style_raw": body_style,
            "transmission_raw": transmission,
            "drivetrain_raw": drivetrain,
            "exterior_color_raw": color,
            "mileage": mileage,
            "vin": vin,
            "asking_price": asking_price,
            "final_price": final_price,
            "description_raw": description,
            "specs_raw": specs,
            "location": location,
            "bidder_count": bidder_count,
            "listing_date": listing_date,
            "is_completed": is_completed,
            "seller_type_raw": "auction_house",
        }

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in ["h1.listing-title", "h1.auction-title", "h1"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_year(self, title: str) -> Optional[int]:
        m = _YEAR_RE.search(title)
        return int(m.group(1)) if m else None

    def _extract_trim(self, title: str) -> Optional[str]:
        trimmed = _YEAR_RE.sub("", title).strip()
        trimmed = re.sub(r"\bPorsche\s+91[0-9]\b", "", trimmed, flags=re.I).strip()
        return trimmed.strip(", ") or None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in ["div.listing-description", "div.auction-description", "div.description"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)
        return None

    def _extract_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        specs: dict[str, str] = {}
        for ul in soup.select("ul.listing-essentials, ul.auction-essentials, ul.specs-list"):
            for li in ul.find_all("li"):
                text = li.get_text(separator=":", strip=True)
                if ":" in text:
                    k, _, v = text.partition(":")
                    specs[k.strip().lower()] = v.strip()
        # Try dl-based layouts
        for dl in soup.select("dl.specs, dl.listing-specs"):
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                k = dt.get_text(strip=True).lower().rstrip(":")
                v = dd.get_text(strip=True)
                if k and v:
                    specs[k] = v
        return specs

    def _extract_body_style(self, text: str) -> Optional[str]:
        lower = text.lower()
        for keyword, canonical in _BODY_STYLE_MAP:
            if keyword in lower:
                return canonical
        return None

    def _extract_transmission(self, text: str) -> Optional[str]:
        for pattern, canonical in _TRANSMISSION_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_drivetrain(self, text: str) -> Optional[str]:
        for pattern, canonical in _DRIVETRAIN_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_mileage(self, specs: dict, text: str) -> Optional[int]:
        for key in ("mileage", "miles", "odometer"):
            if key in specs:
                m = _MILEAGE_RE.search(specs[key])
                if m:
                    return int(m.group(1).replace(",", ""))
        m = _MILEAGE_RE.search(text)
        return int(m.group(1).replace(",", "")) if m else None

    def _extract_color(self, specs: dict) -> Optional[str]:
        for key in ("exterior", "color", "paint", "exterior color"):
            if key in specs:
                return specs[key]
        return None

    def _extract_engine_variant(self, text: str) -> Optional[str]:
        m = _ENGINE_RE.search(text)
        return m.group(1) if m else None

    def _extract_vin(self, text: str) -> Optional[str]:
        m = _VIN_RE.search(text)
        return m.group(1) if m else None

    def _extract_asking_price(self, soup: BeautifulSoup) -> Optional[float]:
        for selector in [".current-bid", ".bid-amount", ".auction-bid"]:
            el = soup.select_one(selector)
            if el:
                m = _PRICE_RE.search(el.get_text())
                if m:
                    return float(m.group(1).replace(",", ""))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[date]]:
        price: Optional[float] = None
        sale_date: Optional[date] = None

        page_text = soup.get_text(separator=" ")
        m = re.search(r"Sold\s+for\s+\$([\d,]+)", page_text, re.I)
        if m:
            price = float(m.group(1).replace(",", ""))

        date_m = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", page_text, re.I)
        if date_m:
            try:
                sale_date = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
            except ValueError:
                pass

        return price, sale_date

    def _extract_bidder_count(self, soup: BeautifulSoup) -> Optional[int]:
        m = _BIDS_RE.search(soup.get_text(separator=" "))
        return int(m.group(1)) if m else None

    def _extract_listing_date(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", {"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"][:10]
        time_el = soup.find("time", {"datetime": True})
        if time_el:
            return time_el["datetime"][:10]
        return None

    def _check_is_completed(self, soup: BeautifulSoup) -> bool:
        page_text = soup.get_text(separator=" ")
        return bool(re.search(r"\bsold\s+for\b|\bauction\s+ended\b|\bno\s+sale\b", page_text, re.I))
