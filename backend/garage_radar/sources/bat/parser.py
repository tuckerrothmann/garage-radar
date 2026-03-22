"""
Bring a Trailer (BaT) listing parser.

Extracts structured fields from BaT listing HTML pages.

BaT HTML structure (as of 2024–2025):
  - Title: <h1 class="post-title listing-title">
  - Specs table: <div class="listing-specs"> or <ul class="listing-essentials">
  - Description: <div class="post-description listing-description">
  - Final price: <div class="listing-available-cta"> or .auction-ended price elements
  - Bidder count: "X bids" text near the auction result
  - End date: <div class="listing-stats"> or page metadata
  - Location: listed in essentials or description

HTML is subject to change — all extraction is best-effort with graceful None fallback.
"""
import logging
import re
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup, Tag

from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_SOURCE = "bat"

# ── Regex patterns ────────────────────────────────────────────────────────────

# Title: "1991 Porsche 911 Carrera 2 Coupe" or "1973 Porsche 911 RS Touring"
_YEAR_RE = re.compile(r"\b(19[6-9]\d|1998)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\.?|Miles?)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([\d,]+)")
_BIDS_RE = re.compile(r"(\d+)\s+bids?", re.IGNORECASE)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_ENGINE_RE = re.compile(
    r"\b(2\.0|2\.2|2\.4|2\.7|2\.7T|3\.0|3\.0T|3\.2|3\.3T|3\.6|3\.8|3\.5|3\.6T)\b",
    re.IGNORECASE,
)

# Body style keyword mapping (order matters — check most specific first)
_BODY_STYLE_MAP = [
    ("speedster", "speedster"),
    ("cabriolet", "cabriolet"),
    ("cabrio", "cabriolet"),
    ("convertible", "cabriolet"),
    ("targa", "targa"),
    ("coupe", "coupe"),
    ("coupé", "coupe"),
]

# Transmission keyword mapping
_TRANSMISSION_MAP = [
    (re.compile(r"\btiptronic\b", re.I), "auto"),
    (re.compile(r"\b6[-\s]?speed\b", re.I), "manual-6sp"),
    (re.compile(r"\b(5[-\s]?speed|g50|915|manual)\b", re.I), "manual"),
]

# Drivetrain
_DRIVETRAIN_MAP = [
    (re.compile(r"\b(carrera\s*4|c4|all[-\s]?wheel)\b", re.I), "awd"),
]


class BaTParser(BaseParser):
    source_name = _SOURCE

    def parse_listing(self, raw: RawPage) -> Optional[ParsedListing]:
        """Parse an active BaT listing page."""
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
        """Parse a completed BaT auction page."""
        if not raw.content or raw.status_code not in (200, 301, 302):
            return None

        soup = BeautifulSoup(raw.content, "lxml")
        data = self._extract_fields(soup, raw)
        if data is None:
            return None

        # Extract final price from completed auction
        final_price, sale_date = self._extract_result(soup)

        is_completed = final_price is not None or data.get("is_completed", False)

        if not is_completed:
            # Auction hasn't ended — return as active listing instead
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

    # ── Internal extraction ───────────────────────────────────────────────────

    def _extract_fields(self, soup: BeautifulSoup, raw: RawPage) -> Optional[dict]:
        """Extract all fields common to both listings and comps."""
        # Title is required — if we can't find it, skip this page
        title = self._extract_title(soup)
        if not title:
            logger.warning("BaT: no title found on %s — skipping.", raw.url)
            return None

        year = self._extract_year(title)
        if not year:
            logger.warning("BaT: no year in title '%s' on %s — skipping.", title, raw.url)
            return None

        description = self._extract_description(soup)
        specs = self._extract_specs(soup)
        combined_text = f"{title} {description or ''} {' '.join(specs.values())}"

        body_style = self._extract_body_style(combined_text)
        transmission = self._extract_transmission(combined_text)
        drivetrain = self._extract_drivetrain(combined_text)
        mileage = self._extract_mileage(specs, combined_text)
        color = self._extract_color(specs, combined_text)
        engine_variant = self._extract_engine_variant(combined_text)
        vin = self._extract_vin(combined_text)
        location = self._extract_location(soup, specs)
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
        # BaT uses h1.post-title or h1.listing-title
        for selector in ["h1.post-title", "h1.listing-title", "h1"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_year(self, title: str) -> Optional[int]:
        m = _YEAR_RE.search(title)
        return int(m.group(1)) if m else None

    def _extract_trim(self, title: str) -> Optional[str]:
        """
        Extract trim level from title.
        E.g. "1991 Porsche 911 Carrera 2 Coupe" → "Carrera 2"
        We strip year, make, and model prefix, leaving trim + body.
        """
        # Remove year
        trimmed = _YEAR_RE.sub("", title).strip()
        # Remove "Porsche 911" or "Porsche 912" prefix
        trimmed = re.sub(r"\bPorsche\s+91[0-9]\b", "", trimmed, flags=re.I).strip()
        # Remove leading/trailing commas/spaces
        trimmed = trimmed.strip(", ")
        return trimmed if trimmed else None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in [
            "div.post-description",
            "div.listing-description",
            "div.more-info",
            ".bids-list + div",
        ]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)
        return None

    def _extract_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Extract key-value pairs from the BaT specs/essentials table.
        BaT renders these as <ul class="listing-essentials"> with <li> items
        or as a structured table in the listing body.
        """
        specs: dict[str, str] = {}

        # Try listing essentials list
        for ul in soup.select("ul.listing-essentials, ul.specs"):
            for li in ul.find_all("li"):
                text = li.get_text(separator=":", strip=True)
                if ":" in text:
                    k, _, v = text.partition(":")
                    specs[k.strip().lower()] = v.strip()

        # Try spec table rows (key: value in adjacent cells or dl/dt/dd)
        for dl in soup.select("dl.listing-essentials, div.listing-specs dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                k = dt.get_text(strip=True).lower().rstrip(":")
                v = dd.get_text(strip=True)
                if k and v:
                    specs[k] = v

        # Fallback: scrape any labeled rows in the listing body
        for row in soup.select("div.listing-essentials div, div.essentials-item"):
            label_el = row.find(class_=re.compile(r"label|key|name"))
            value_el = row.find(class_=re.compile(r"value|val|detail"))
            if label_el and value_el:
                k = label_el.get_text(strip=True).lower().rstrip(":")
                v = value_el.get_text(strip=True)
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
        # Check specs dict first
        for key in ("mileage", "miles", "odometer"):
            if key in specs:
                m = _MILEAGE_RE.search(specs[key])
                if m:
                    return int(m.group(1).replace(",", ""))

        # Fall back to full text
        m = _MILEAGE_RE.search(text)
        if m:
            return int(m.group(1).replace(",", ""))
        return None

    def _extract_color(self, specs: dict, text: str) -> Optional[str]:
        for key in ("exterior", "color", "paint", "exterior color"):
            if key in specs:
                return specs[key]

        # Try to find "Color: X" pattern in text
        m = re.search(r"(?:exterior|color|paint)[\s:]+([A-Za-z\s]+?)(?:\s*,|\s*\.|$)", text, re.I)
        if m:
            return m.group(1).strip()
        return None

    def _extract_engine_variant(self, text: str) -> Optional[str]:
        m = _ENGINE_RE.search(text)
        return m.group(1) if m else None

    def _extract_vin(self, text: str) -> Optional[str]:
        m = _VIN_RE.search(text)
        return m.group(1) if m else None

    def _extract_location(self, soup: BeautifulSoup, specs: dict) -> Optional[str]:
        # Check specs dict
        for key in ("location", "seller location"):
            if key in specs:
                return specs[key]

        # BaT sometimes puts location in a specific element
        el = soup.select_one(".listing-location, .seller-location, .location-display")
        if el:
            return el.get_text(strip=True)
        return None

    def _extract_asking_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract current bid / asking price from an active listing."""
        # BaT shows "Current Bid: $XX,XXX" for active auctions
        for selector in [
            ".current-bid-amount",
            ".bid-price",
            ".auction-bid-amount",
        ]:
            el = soup.select_one(selector)
            if el:
                m = _PRICE_RE.search(el.get_text())
                if m:
                    return float(m.group(1).replace(",", ""))

        # Try meta tags
        meta = soup.find("meta", {"property": "og:description"})
        if meta and meta.get("content"):
            m = _PRICE_RE.search(meta["content"])
            if m:
                return float(m.group(1).replace(",", ""))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[date]]:
        """Extract final sale price and date from a completed auction page."""
        price: Optional[float] = None
        sale_date: Optional[date] = None

        # BaT completed pages show "Sold for $XX,XXX on [date]"
        result_text = ""
        for selector in [
            ".listing-available-cta",
            ".auction-ended",
            ".listing-result",
            ".sold-price",
        ]:
            el = soup.select_one(selector)
            if el:
                result_text = el.get_text(separator=" ", strip=True)
                break

        if not result_text:
            # Try the full page text for "Sold for" pattern
            page_text = soup.get_text(separator=" ")
            m = re.search(r"Sold\s+for\s+\$([\d,]+)", page_text, re.I)
            if m:
                result_text = m.group(0)

        if result_text:
            m = _PRICE_RE.search(result_text)
            if m:
                price = float(m.group(1).replace(",", ""))

            # Date: "on Month DD, YYYY" or "Month DD, YYYY"
            date_m = re.search(
                r"(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
                result_text,
                re.I,
            )
            if date_m:
                try:
                    sale_date = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
                except ValueError:
                    pass

        return price, sale_date

    def _extract_bidder_count(self, soup: BeautifulSoup) -> Optional[int]:
        page_text = soup.get_text(separator=" ")
        m = _BIDS_RE.search(page_text)
        return int(m.group(1)) if m else None

    def _extract_listing_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract listing/auction start date. Returns ISO date string."""
        # Try meta tags
        for prop in ["article:published_time", "og:article:published_time"]:
            meta = soup.find("meta", {"property": prop})
            if meta and meta.get("content"):
                try:
                    return meta["content"][:10]  # Just YYYY-MM-DD
                except (IndexError, TypeError):
                    pass

        # Try time elements
        time_el = soup.find("time", {"datetime": True})
        if time_el:
            return time_el["datetime"][:10]

        return None

    def _check_is_completed(self, soup: BeautifulSoup) -> bool:
        """Determine if this auction/listing is completed."""
        page_text = soup.get_text(separator=" ")
        if re.search(r"\bsold\s+for\b|\bauction\s+ended\b|\bno\s+sale\b", page_text, re.I):
            return True
        # Check for specific completed indicators
        if soup.select_one(".listing-available-cta .sold-badge, .auction-ended"):
            return True
        return False
