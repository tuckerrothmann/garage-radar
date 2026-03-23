"""
Bring a Trailer (BaT) listing parser.

Confirmed BaT HTML structure (2024–2025, from working scrapers):
  Title:    <h1 class="post-title listing-post-title">
  Specs:    <div class="item"><ul><li>Field: Value</li>...</ul></div>
  Location: <a href="...maps/place/...">City, State</a>
  Result:   <span class="info-value noborder-tiny">$97,500</span>
            (appears in a stats strip for completed auctions)
  Bid cnt:  also in info-value spans ("47 bids")
  VIN:      <a href="/search?q=VINHERE">WP0AA2994SS300001</a>
  Desc:     <div class="post-description"> or <div class="more-info">

BaT spec list items may or may not have "Label:" prefixes.
We apply content-detection regexes to categorise each item regardless.

All extraction is best-effort — returns None on failure, never raises.
"""
import logging
import re
from datetime import datetime, date
from typing import Optional

from bs4 import BeautifulSoup

from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_SOURCE = "bat"

# ── Regex patterns ────────────────────────────────────────────────────────────

_YEAR_RE = re.compile(r"\b(19[6-9]\d|1998)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\.?)", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*([\d,]+)")
_BIDS_RE = re.compile(r"(\d+)\s+bids?", re.IGNORECASE)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_ENGINE_RE = re.compile(
    r"\b(2\.0|2\.2|2\.4|2\.7|2\.7[- ]?[Tt]urbo|3\.0|3\.0[- ]?[Tt]urbo|"
    r"3\.2|3\.3[- ]?[Tt]urbo|3\.6|3\.8|3\.5)\b",
    re.IGNORECASE,
)
_CHASSIS_LABEL_RE = re.compile(r"(?:chassis|vin|serial)[:\s]+", re.I)
_COLOR_LABEL_RE = re.compile(r"(?:exterior\s+color|color|exterior|paint)[:\s]+", re.I)
_MILEAGE_LABEL_RE = re.compile(r"(?:mileage|miles|odometer)[:\s]+", re.I)
_TRANS_LABEL_RE = re.compile(r"(?:transmission|gearbox)[:\s]+", re.I)

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


class BaTParser(BaseParser):
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
            logger.warning("BaT: no title on %s — skipping.", raw.url)
            return None
        year = self._extract_year(title)
        if not year:
            logger.warning("BaT: no year in title '%s' on %s — skipping.", title, raw.url)
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
            "vin": self._extract_vin(soup, specs),
            "asking_price": self._extract_asking_price(soup),
            "final_price": self._extract_result(soup)[0],
            "description_raw": description,
            "specs_raw": specs,
            "location": self._extract_location(soup, specs),
            "bidder_count": self._extract_bidder_count(soup),
            "listing_date": self._extract_listing_date(soup),
            "is_completed": self._check_is_completed(soup),
            "seller_type_raw": "auction_house",
        }

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        # Confirmed primary selector from working BaT scrapers
        for selector in [
            "h1.post-title.listing-post-title",
            "h1.post-title",
            "h1.listing-post-title",
            "h1",
        ]:
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
        for selector in [
            "div.post-description",
            "div.more-info",
            "div.listing-description",
            "div.post-excerpt",
        ]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator=" ", strip=True)
        return None

    def _extract_specs(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Parse the BaT listing essentials.

        Primary: <div class="item"><ul><li>Label: Value</li></ul></div>
        The li items may have explicit "Label: " prefixes or may be label-free
        (e.g. "68,200 Miles", "5-Speed G50 Manual", "Riviera Blue Metallic").
        We detect content-type by regex and store under normalized keys.
        """
        specs: dict[str, str] = {}
        items_text: list[str] = []

        # Primary: div.item ul li (confirmed from real BaT scrapers)
        for div in soup.select("div.item"):
            for li in div.select("ul li"):
                text = li.get_text(separator=" ", strip=True)
                if text:
                    items_text.append(text)

        # Fallback: ul.listing-essentials (older BaT format still seen on some pages)
        if not items_text:
            for ul in soup.select("ul.listing-essentials"):
                for li in ul.find_all("li"):
                    text = li.get_text(separator=" ", strip=True)
                    if text:
                        items_text.append(text)

        # Parse each item — detect labeled vs unlabeled
        for text in items_text:
            # Explicit "Label: Value" format
            if ":" in text:
                label, _, value = text.partition(":")
                label = label.strip().lower()
                value = value.strip()
                if label and value:
                    specs[label] = value
                    continue

            # Unlabeled — detect by content
            text_lower = text.lower()
            if _MILEAGE_RE.search(text) and "mileage" not in specs:
                specs["mileage"] = text
            elif any(kw in text_lower for kw in ("tiptronic", "speed", "manual", "g50", "915")) \
                    and "transmission" not in specs:
                specs["transmission"] = text
            elif _ENGINE_RE.search(text) and "engine" not in specs:
                specs["engine"] = text

        return specs

    def _extract_body_style(self, text: str) -> Optional[str]:
        lower = text.lower()
        for keyword, canonical in _BODY_STYLE_MAP:
            if keyword in lower:
                return canonical
        return None

    def _extract_transmission(self, specs: dict, text: str) -> Optional[str]:
        # Check labeled spec first
        for key in ("transmission", "gearbox"):
            if key in specs:
                val = specs[key]
                for pattern, canonical in _TRANSMISSION_MAP:
                    if pattern.search(val):
                        return canonical
        # Fall back to full text
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
                raw_val = specs[key]
                # BaT sometimes has "Exterior Color over Interior Color" — take exterior part
                if " over " in raw_val.lower():
                    raw_val = raw_val.split(" over ")[0].strip()
                return raw_val
        return None

    def _extract_engine_variant(self, specs: dict, text: str) -> Optional[str]:
        for key in ("engine", "engine size", "displacement"):
            if key in specs:
                m = _ENGINE_RE.search(specs[key])
                if m:
                    return m.group(1)
        m = _ENGINE_RE.search(text)
        return m.group(1) if m else None

    def _extract_vin(self, soup: BeautifulSoup, specs: dict) -> Optional[str]:
        # From specs dict (labeled "chassis" or "vin")
        for key in ("chassis", "vin", "serial", "chassis number"):
            if key in specs:
                m = _VIN_RE.search(specs[key])
                if m:
                    return m.group(1)

        # From BaT VIN search links: <a href="/search?q=VINHERE">
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "/search?q=" in href:
                candidate = href.split("/search?q=")[-1].split("&")[0]
                if _VIN_RE.match(candidate.upper()):
                    return candidate.upper()
        return None

    def _extract_location(self, soup: BeautifulSoup, specs: dict) -> Optional[str]:
        # From specs dict
        for key in ("location", "seller location", "located in"):
            if key in specs:
                return specs[key]

        # Confirmed: BaT links to Google Maps for location
        for anchor in soup.find_all("a", href=True):
            if "maps/place" in anchor["href"] or "maps.google" in anchor["href"]:
                text = anchor.get_text(strip=True)
                if text:
                    return text

        return None

    def _extract_asking_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Current bid for active auctions."""
        # BaT shows price in info-value spans or a dedicated bid element
        for selector in [
            "span.info-value.noborder-tiny",
            ".current-bid-amount",
            ".bid-price",
        ]:
            for el in soup.select(selector):
                m = _PRICE_RE.search(el.get_text())
                if m:
                    return float(m.group(1).replace(",", ""))

        # Meta tag fallback
        meta = soup.find("meta", {"property": "og:description"})
        if meta and meta.get("content"):
            m = _PRICE_RE.search(meta["content"])
            if m:
                return float(m.group(1).replace(",", ""))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[date]]:
        """Final sale price + date for completed auctions."""
        price: Optional[float] = None
        sale_date: Optional[date] = None

        # BaT result strip uses span.info-value.noborder-tiny
        # The text pattern is "Sold for $97,500 on February 20, 2025" or similar
        result_text = ""

        # Try the result/stats strip first
        for selector in [
            ".listing-available-cta",
            ".auction-ended",
            ".bid-result",
            ".listing-result",
        ]:
            el = soup.select_one(selector)
            if el:
                result_text = el.get_text(separator=" ", strip=True)
                break

        # Fall back: search the full page text
        if not result_text:
            result_text = soup.get_text(separator=" ")

        # Extract price
        sold_m = re.search(r"[Ss]old\s+for\s+\$([\d,]+)", result_text)
        if sold_m:
            price = float(sold_m.group(1).replace(",", ""))

        # If no "Sold for" pattern, look for any price in info-value spans
        if price is None:
            for el in soup.select("span.info-value.noborder-tiny"):
                m = _PRICE_RE.search(el.get_text())
                if m:
                    price = float(m.group(1).replace(",", ""))
                    break

        # Extract date
        date_m = re.search(
            r"(?:on\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
            result_text,
        )
        if date_m:
            try:
                sale_date = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
            except ValueError:
                pass

        return price, sale_date

    def _extract_bidder_count(self, soup: BeautifulSoup) -> Optional[int]:
        # Check info-value spans
        for el in soup.select("span.info-value.noborder-tiny"):
            m = _BIDS_RE.search(el.get_text())
            if m:
                return int(m.group(1))
        # Fallback: full page text
        m = _BIDS_RE.search(soup.get_text(separator=" "))
        return int(m.group(1)) if m else None

    def _extract_listing_date(self, soup: BeautifulSoup) -> Optional[str]:
        for prop in ["article:published_time", "og:article:published_time"]:
            meta = soup.find("meta", {"property": prop})
            if meta and meta.get("content"):
                return meta["content"][:10]
        time_el = soup.find("time", {"datetime": True})
        if time_el:
            return time_el["datetime"][:10]
        return None

    def _check_is_completed(self, soup: BeautifulSoup) -> bool:
        page_text = soup.get_text(separator=" ")
        if re.search(r"\bsold\s+for\b|\bauction\s+ended\b|\bno\s+sale\b", page_text, re.I):
            return True
        if soup.select_one(".auction-ended, .listing-result, .bid-result"):
            return True
        return False
