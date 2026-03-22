"""
Cars & Bids listing parser.

Confirmed C&B HTML structure (2024–2025, from working scrapers):
  Title:       .auction-title h1
  Specs:       dl within .quick-facts  (dt/dd pairs)
               Fields include: Mileage, Transmission, VIN, Location,
               Exterior Color, Interior Color, Engine
  Sold price:  .bid-value within .current-bid.ended
  Bid count:   ul.stats — look for "Bids" label + value
  Description: .detail-body p within .detail-section.detail-highlights
  Current bid: .bid-value within .current-bid (not .ended)

All extraction is best-effort — returns None on failure, never raises.
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
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_ENGINE_RE = re.compile(
    r"\b(2\.0|2\.2|2\.4|2\.7|2\.7[- ]?[Tt]urbo|3\.0|3\.0[- ]?[Tt]urbo|"
    r"3\.2|3\.3[- ]?[Tt]urbo|3\.6|3\.8|3\.5)\b",
    re.IGNORECASE,
)

_BODY_STYLE_MAP = [
    ("speedster", "speedster"),
    ("cabriolet", "cabriolet"),
    ("cabrio", "cabriolet"),
    ("convertible", "cabriolet"),
    ("targa", "targa"),
    ("coupe", "coupe"),
    ("coupé", "coupe"),
]

_TRANSMISSION_MAP = [
    (re.compile(r"\btiptronic\b", re.I), "auto"),
    (re.compile(r"\b6[-\s]?speed\b", re.I), "manual-6sp"),
    (re.compile(r"\b(5[-\s]?speed|g50|915|manual)\b", re.I), "manual"),
]

_DRIVETRAIN_MAP = [
    (re.compile(r"\b(carrera\s*4|c4|all[-\s]?wheel|awd)\b", re.I), "awd"),
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
        return ParsedListing(source=_SOURCE, source_url=raw.url, scrape_ts=raw.fetched_at, **data)

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
            **{k: v for k, v in data.items() if k not in ("is_completed", "final_price")},
            final_price=final_price,
            is_completed=True,
        )

    # ── Internal extraction ───────────────────────────────────────────────────

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

        return {
            "title_raw": title,
            "year": year,
            "trim": self._extract_trim(title),
            "engine_variant": self._extract_engine_variant(specs, combined_text),
            "body_style_raw": self._extract_body_style(combined_text),
            "transmission_raw": self._extract_transmission(specs, combined_text),
            "drivetrain_raw": self._extract_drivetrain(combined_text),
            "exterior_color_raw": self._extract_color(specs),
            "mileage": self._extract_mileage(specs),
            "vin": self._extract_vin(specs, combined_text),
            "asking_price": self._extract_asking_price(soup),
            "final_price": self._extract_result(soup)[0],
            "description_raw": description,
            "specs_raw": specs,
            "location": specs.get("location") or specs.get("seller location"),
            "bidder_count": self._extract_bidder_count(soup),
            "listing_date": self._extract_listing_date(soup),
            "is_completed": self._check_is_completed(soup),
            "seller_type_raw": "auction_house",
        }

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # Confirmed primary selector from working C&B scrapers
        for selector in [".auction-title h1", "h1.auction-title", "h1.listing-title", "h1"]:
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
        # Confirmed selector from working C&B scrapers
        el = soup.select_one(".detail-section.detail-highlights .detail-body")
        if el:
            return " ".join(p.get_text(strip=True) for p in el.find_all("p") if p.get_text(strip=True))

        # Fallbacks
        for selector in [
            ".listing-description",
            ".auction-description",
            ".detail-body",
            ".description",
        ]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)
        return None

    def _extract_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Parse the C&B quick-facts section.

        Confirmed structure: dl elements within .quick-facts, with dt/dd pairs.
        dt contains the field label; dd contains the value.
        """
        specs: dict[str, str] = {}

        # Primary: .quick-facts dl (confirmed from working scrapers)
        quick_facts = soup.select_one(".quick-facts")
        if quick_facts:
            for dl in quick_facts.find_all("dl"):
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                for dt, dd in zip(dts, dds):
                    k = dt.get_text(strip=True).lower().rstrip(":")
                    v = dd.get_text(strip=True)
                    if k and v:
                        specs[k] = v

        # Fallback: any visible dl on the page
        if not specs:
            for dl in soup.find_all("dl"):
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                for dt, dd in zip(dts, dds):
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

    def _extract_transmission(self, specs: dict, text: str) -> Optional[str]:
        for key in ("transmission", "gearbox"):
            if key in specs:
                for pattern, canonical in _TRANSMISSION_MAP:
                    if pattern.search(specs[key]):
                        return canonical
        for pattern, canonical in _TRANSMISSION_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_drivetrain(self, text: str) -> Optional[str]:
        for pattern, canonical in _DRIVETRAIN_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_mileage(self, specs: dict) -> Optional[int]:
        for key in ("mileage", "miles", "odometer"):
            if key in specs:
                m = _MILEAGE_RE.search(specs[key])
                if m:
                    return int(m.group(1).replace(",", ""))
        return None

    def _extract_color(self, specs: dict) -> Optional[str]:
        for key in ("exterior color", "exterior", "color", "paint"):
            if key in specs:
                return specs[key]
        return None

    def _extract_engine_variant(self, specs: dict, text: str) -> Optional[str]:
        for key in ("engine", "engine size", "displacement"):
            if key in specs:
                m = _ENGINE_RE.search(specs[key])
                if m:
                    return m.group(1)
        m = _ENGINE_RE.search(text)
        return m.group(1) if m else None

    def _extract_vin(self, specs: dict, text: str) -> Optional[str]:
        for key in ("vin", "chassis", "serial"):
            if key in specs:
                m = _VIN_RE.search(specs[key])
                if m:
                    return m.group(1)
        m = _VIN_RE.search(text)
        return m.group(1) if m else None

    def _extract_asking_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Current bid for active auctions — .bid-value NOT inside .ended."""
        bid_section = soup.select_one(".current-bid:not(.ended)")
        if bid_section:
            el = bid_section.select_one(".bid-value")
            if el:
                m = _PRICE_RE.search(el.get_text())
                if m:
                    return float(m.group(1).replace(",", ""))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[date]]:
        """Final sold price + date from a completed C&B auction."""
        price: Optional[float] = None
        sale_date: Optional[date] = None

        # Confirmed: .bid-value within .current-bid.ended
        ended = soup.select_one(".current-bid.ended")
        if ended:
            bid_val = ended.select_one(".bid-value")
            if bid_val:
                m = _PRICE_RE.search(bid_val.get_text())
                if m:
                    price = float(m.group(1).replace(",", ""))

        # Fallback: "Sold for $X" in page text
        if price is None:
            m = re.search(r"[Ss]old\s+for\s+\$([\d,]+)", soup.get_text(separator=" "))
            if m:
                price = float(m.group(1).replace(",", ""))

        # Date extraction from page text
        page_text = soup.get_text(separator=" ")
        date_m = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", page_text)
        if date_m:
            try:
                sale_date = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
            except ValueError:
                pass

        return price, sale_date

    def _extract_bidder_count(self, soup: BeautifulSoup) -> Optional[int]:
        """
        Confirmed: bid count in ul.stats — find the element with "Bids" label.
        Structure: <ul class="stats"><li><span class="label">Bids</span><span class="value">47</span></li>
        """
        stats = soup.select_one("ul.stats")
        if stats:
            for li in stats.find_all("li"):
                text = li.get_text(separator="|", strip=True)
                if "bids" in text.lower():
                    # Extract the numeric part
                    m = re.search(r"(\d+)", text)
                    if m:
                        return int(m.group(1))

        # Fallback: regex on page text
        m = re.search(r"(\d+)\s+bids?", soup.get_text(separator=" "), re.I)
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
        if soup.select_one(".current-bid.ended"):
            return True
        page_text = soup.get_text(separator=" ")
        return bool(re.search(r"\bsold\s+for\b|\bauction\s+ended\b|\bno\s+sale\b", page_text, re.I))
