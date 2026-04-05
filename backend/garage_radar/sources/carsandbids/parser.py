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
from contextlib import suppress
from datetime import date, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from garage_radar.normalize.vehicle_identity import extract_vehicle_identity
from garage_radar.sources.base import BaseParser, ParsedComp, ParsedListing, RawPage

logger = logging.getLogger(__name__)

_SOURCE = "carsandbids"

_YEAR_RE = re.compile(r"\b(18(?:8[6-9]|9\d)|19\d{2}|20\d{2}|2100)\b")
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

_UPPERCASE_SLUG_TOKENS = {
    "amg",
    "gt",
    "gt2",
    "gt3",
    "gt4",
    "gti",
    "gto",
    "gts",
    "rs",
    "si",
    "srt",
    "ss",
    "st",
    "svt",
    "v8",
    "v10",
    "v12",
    "z06",
    "zr1",
}


class CarsAndBidsParser(BaseParser):
    source_name = _SOURCE

    def parse_listing(self, raw: RawPage) -> ParsedListing | None:
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
            snapshot_path=raw.snapshot_path,
            **data,
        )

    def parse_comp(self, raw: RawPage) -> ParsedComp | None:
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
            snapshot_path=raw.snapshot_path,
            sale_date=sale_date,
            price_type="auction_final",
            **{k: v for k, v in data.items() if k not in ("is_completed", "final_price")},
            final_price=final_price,
            is_completed=True,
        )

    # ── Internal extraction ───────────────────────────────────────────────────

    def _extract_fields(self, soup: BeautifulSoup, raw: RawPage) -> dict | None:
        title = self._extract_title(soup, raw.url)
        if not title:
            logger.warning("C&B: no title found on %s — skipping.", raw.url)
            return None
        year = self._extract_year(title, raw.url)
        if not year:
            logger.warning("C&B: no year in title '%s' on %s — skipping.", title, raw.url)
            return None

        description = self._extract_description(soup)
        specs = self._extract_specs(soup)
        meta_summary = self._extract_meta_summary_text(soup)
        combined_text = " ".join(
            part for part in [title, description or "", meta_summary, *specs.values()] if part
        )
        make_raw, model_raw = self._extract_identity_from_url(raw.url)

        current_bid = self._extract_asking_price(soup)

        return {
            "title_raw": title,
            "year": year,
            "make_raw": make_raw,
            "model_raw": model_raw,
            "trim": self._extract_trim(title),
            "engine_variant": self._extract_engine_variant(specs, combined_text),
            "body_style_raw": self._extract_body_style(combined_text),
            "transmission_raw": self._extract_transmission(specs, combined_text),
            "drivetrain_raw": self._extract_drivetrain(combined_text),
            "exterior_color_raw": self._extract_color(specs),
            "mileage": self._extract_mileage(specs),
            "vin": self._extract_vin(specs, combined_text),
            "current_bid": current_bid,
            "asking_price": current_bid,
            "final_price": self._extract_result(soup)[0],
            "description_raw": description,
            "specs_raw": specs,
            "location": specs.get("location") or specs.get("seller location"),
            "bidder_count": self._extract_bidder_count(soup),
            "listing_date": self._extract_listing_date(soup),
            "auction_end_at": self._extract_auction_end_at(soup),
            "time_remaining_text": self._extract_time_remaining_text(soup),
            "is_completed": self._check_is_completed(soup),
            "seller_type_raw": "auction_house",
        }

    def _extract_title(self, soup: BeautifulSoup, url: str | None = None) -> str | None:
        # Confirmed primary selector from working C&B scrapers
        for selector in [".auction-title h1", "h1.auction-title", "h1.listing-title", "h1"]:
            el = soup.select_one(selector)
            if el:
                title = el.get_text(strip=True)
                if title and not self._is_generic_title(title):
                    return title

        title_el = soup.select_one("title")
        if title_el and title_el.get_text(strip=True):
            title = re.sub(
                r"\s+auction\s*-\s*Cars\s*&\s*Bids$",
                "",
                title_el.get_text(strip=True),
                flags=re.I,
            ).strip()
            if title and not self._is_generic_title(title):
                return title

        for value in (
            self._meta_content(soup, "property", "og:title"),
            self._meta_content(soup, "name", "twitter:title"),
        ):
            if value:
                title = value.split(" - ", 1)[0].strip()
                if title and not self._is_generic_title(title):
                    return title
        if url:
            return self._title_from_url(url)
        return None

    def _extract_year(self, title: str, url: str | None = None) -> int | None:
        m = _YEAR_RE.search(title)
        if m:
            return int(m.group(1))
        if url:
            m = _YEAR_RE.search(urlparse(url).path.replace("-", " "))
            if m:
                return int(m.group(1))
        return None

    def _extract_trim(self, title: str) -> str | None:
        trimmed = _YEAR_RE.sub("", title).strip()
        trimmed = re.sub(r"\bPorsche\s+91[0-9]\b", "", trimmed, flags=re.I).strip()
        return trimmed.strip(", ") or None

    def _extract_description(self, soup: BeautifulSoup) -> str | None:
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
        return self._meta_content(soup, "name", "description") or self._meta_content(
            soup, "property", "og:description"
        )

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
                for dt, dd in zip(dts, dds, strict=True):
                    k = dt.get_text(strip=True).lower().rstrip(":")
                    v = dd.get_text(strip=True)
                    if k and v:
                        specs[k] = v

        # Fallback: any visible dl on the page
        if not specs:
            for dl in soup.find_all("dl"):
                dts = dl.find_all("dt")
                dds = dl.find_all("dd")
                for dt, dd in zip(dts, dds, strict=True):
                    k = dt.get_text(strip=True).lower().rstrip(":")
                    v = dd.get_text(strip=True)
                    if k and v:
                        specs[k] = v

        return specs

    def _extract_body_style(self, text: str) -> str | None:
        lower = text.lower()
        for keyword, canonical in _BODY_STYLE_MAP:
            if keyword in lower:
                return canonical
        return None

    def _extract_transmission(self, specs: dict, text: str) -> str | None:
        for key in ("transmission", "gearbox"):
            if key in specs:
                for pattern, canonical in _TRANSMISSION_MAP:
                    if pattern.search(specs[key]):
                        return canonical
        for pattern, canonical in _TRANSMISSION_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_drivetrain(self, text: str) -> str | None:
        for pattern, canonical in _DRIVETRAIN_MAP:
            if pattern.search(text):
                return canonical
        return None

    def _extract_mileage(self, specs: dict) -> int | None:
        for key in ("mileage", "miles", "odometer"):
            if key in specs:
                m = _MILEAGE_RE.search(specs[key])
                if m:
                    return int(m.group(1).replace(",", ""))
        return None

    def _extract_color(self, specs: dict) -> str | None:
        for key in ("exterior color", "exterior", "color", "paint"):
            if key in specs:
                return specs[key]
        return None

    def _extract_engine_variant(self, specs: dict, text: str) -> str | None:
        for key in ("engine", "engine size", "displacement"):
            if key in specs:
                m = _ENGINE_RE.search(specs[key])
                if m:
                    return m.group(1)
        m = _ENGINE_RE.search(text)
        return m.group(1) if m else None

    def _extract_vin(self, specs: dict, text: str) -> str | None:
        for key in ("vin", "chassis", "serial"):
            if key in specs:
                m = _VIN_RE.search(specs[key])
                if m:
                    return m.group(1)
        m = _VIN_RE.search(text)
        return m.group(1) if m else None

    def _extract_asking_price(self, soup: BeautifulSoup) -> float | None:
        """Current bid for active auctions — .bid-value NOT inside .ended."""
        bid_section = soup.select_one(".current-bid:not(.ended)")
        if bid_section:
            el = bid_section.select_one(".bid-value")
            if el:
                m = _PRICE_RE.search(el.get_text())
                if m:
                    return float(m.group(1).replace(",", ""))
        return None

    def _extract_result(self, soup: BeautifulSoup) -> tuple[float | None, date | None]:
        """Final sold price + date from a completed C&B auction."""
        price: float | None = None
        sale_date: date | None = None

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
            with suppress(ValueError):
                sale_date = datetime.strptime(date_m.group(1), "%B %d, %Y").date()

        return price, sale_date

    def _extract_bidder_count(self, soup: BeautifulSoup) -> int | None:
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

    def _extract_listing_date(self, soup: BeautifulSoup) -> str | None:
        meta = soup.find("meta", {"property": "article:published_time"})
        if meta and meta.get("content"):
            return meta["content"][:10]
        time_el = soup.find("time", {"datetime": True})
        if time_el:
            return time_el["datetime"][:10]
        text = self._extract_meta_summary_text(soup)
        match = re.search(r"Auction end(?:s|ed)\s+([A-Z][a-z]+\s+\d{1,2}\s+\d{4})", text, re.I)
        if match:
            with suppress(ValueError):
                return datetime.strptime(match.group(1), "%B %d %Y").date().isoformat()
        return None

    def _extract_auction_end_at(self, soup: BeautifulSoup) -> str | None:
        for selector in (".countdown", ".time-left", ".auction-countdown", "[data-end-time]"):
            el = soup.select_one(selector)
            if not el:
                continue
            data_end = el.get("data-end-time")
            if isinstance(data_end, str) and data_end.strip():
                return data_end.strip()
            text = el.get_text(" ", strip=True)
            parsed = self._parse_auction_end_text(text)
            if parsed:
                return parsed

        text = self._extract_meta_summary_text(soup)
        return self._parse_auction_end_text(text)

    def _extract_time_remaining_text(self, soup: BeautifulSoup) -> str | None:
        for selector in (".countdown", ".time-left", ".auction-countdown"):
            el = soup.select_one(selector)
            if not el:
                continue
            text = " ".join(el.get_text(" ", strip=True).split())
            if text:
                return text
        return None

    def _check_is_completed(self, soup: BeautifulSoup) -> bool:
        if soup.select_one(".current-bid.ended"):
            return True
        page_text = f"{soup.get_text(separator=' ')} {self._extract_meta_summary_text(soup)}"
        return bool(re.search(r"\bsold\s+for\b|\bauction\s+ended\b|\bno\s+sale\b", page_text, re.I))

    def _extract_meta_summary_text(self, soup: BeautifulSoup) -> str:
        return " ".join(
            part
            for part in [
                self._meta_content(soup, "property", "og:title"),
                self._meta_content(soup, "name", "twitter:title"),
                self._meta_content(soup, "name", "description"),
                self._meta_content(soup, "property", "og:description"),
            ]
            if part
        )

    def _meta_content(self, soup: BeautifulSoup, attr: str, value: str) -> str | None:
        el = soup.find("meta", {attr: value})
        if not el:
            return None
        content = el.get("content")
        if not isinstance(content, str):
            return None
        cleaned = content.strip()
        return cleaned or None

    def _is_generic_title(self, title: str) -> bool:
        lowered = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
        return lowered in {"", "auction", "cars bids", "cars and bids"}

    def _parse_auction_end_text(self, text: str | None) -> str | None:
        if not text:
            return None
        match = re.search(r"Auction end(?:s|ed)\s+([A-Z][a-z]+\s+\d{1,2}\s+\d{4})", text, re.I)
        if not match:
            return None
        with suppress(ValueError):
            return datetime.strptime(match.group(1), "%B %d %Y").date().isoformat()
        return None

    def _title_from_url(self, url: str) -> str | None:
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        if not slug:
            return None
        slug = re.sub(r"-\d+$", "", slug)
        words = []
        for token in slug.split("-"):
            if not token:
                continue
            if token.isdigit():
                words.append(token)
            elif any(char.isdigit() for char in token):
                words.append(token.upper())
            else:
                words.append(token.upper() if token.casefold() in _UPPERCASE_SLUG_TOKENS else token.title())
        title = " ".join(words).strip()
        return title or None

    def _extract_identity_from_url(self, url: str) -> tuple[str | None, str | None]:
        title = self._title_from_url(url)
        if not title:
            return None, None
        return extract_vehicle_identity(title)
