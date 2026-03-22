"""
Garage Radar — Abstract base classes for crawlers and parsers.
Each source must implement these interfaces.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawPage:
    """A raw fetched page before any parsing."""
    source: str
    url: str
    fetched_at: datetime
    content: str           # HTML or JSON string
    content_type: str = "html"
    status_code: int = 200
    snapshot_path: Optional[str] = None


@dataclass
class ParsedListing:
    """
    Structured listing data after source-specific parsing.
    All fields are optional — downstream normalization will validate and fill gaps.
    Fields that can't be extracted are left None (not default/guessed).
    """
    source: str
    source_url: str
    scrape_ts: datetime

    # Vehicle
    title_raw: Optional[str] = None
    year: Optional[int] = None
    trim: Optional[str] = None
    engine_variant: Optional[str] = None
    body_style_raw: Optional[str] = None
    transmission_raw: Optional[str] = None
    drivetrain_raw: Optional[str] = None
    exterior_color_raw: Optional[str] = None
    interior_color_raw: Optional[str] = None
    mileage: Optional[int] = None
    vin: Optional[str] = None

    # Price
    asking_price: Optional[float] = None
    currency: str = "USD"
    final_price: Optional[float] = None   # Set if auction is completed

    # Meta
    listing_date: Optional[str] = None    # ISO date string
    seller_type_raw: Optional[str] = None
    seller_name: Optional[str] = None
    location: Optional[str] = None
    bidder_count: Optional[int] = None
    is_completed: bool = False

    # Raw text for NLP
    description_raw: Optional[str] = None
    specs_raw: dict = field(default_factory=dict)   # Key-value pairs from spec table


@dataclass
class ParsedComp(ParsedListing):
    """A completed sale — extends ParsedListing with sale date and price type."""
    sale_date: Optional[str] = None
    price_type: str = "auction_final"


class BaseCrawler(ABC):
    """Fetches page URLs for a given source. Stores raw HTML before returning."""

    source_name: str = ""

    @abstractmethod
    async def get_listing_urls(self, limit: Optional[int] = None) -> list[str]:
        """Return a list of listing page URLs (active + recent completed)."""
        ...

    @abstractmethod
    async def fetch_page(self, url: str) -> RawPage:
        """Fetch a single URL, store snapshot, return RawPage."""
        ...


class BaseParser(ABC):
    """Parses RawPage content into structured ParsedListing or ParsedComp."""

    source_name: str = ""

    @abstractmethod
    def parse_listing(self, raw: RawPage) -> Optional[ParsedListing]:
        """
        Extract structured fields from listing HTML.
        Return None if page is not a valid listing (e.g., 404, wrong type).
        Log warnings on extraction failures — never raise.
        """
        ...

    @abstractmethod
    def parse_comp(self, raw: RawPage) -> Optional[ParsedComp]:
        """
        Extract structured fields from a completed auction/sale page.
        Return None if sale is not confirmed.
        """
        ...
