"""
Garage Radar — Normalization pipeline.

Takes a ParsedListing or ParsedComp (raw extracted fields from a source parser)
and produces a fully normalized record ready for database insertion.

Normalization steps:
  1. Generation mapping (year → G1–G6, using description hints)
  2. Body style canonicalization
  3. Transmission canonicalization
  4. Color canonicalization (raw text → canonical palette)
  5. NLP flag extraction (matching numbers, original paint, service history, mods)
  6. Confidence scoring

The pipeline never raises — it logs warnings and continues with None for failed fields.
"""
import logging
from dataclasses import asdict
from typing import Optional

from garage_radar.normalize.body_style import normalize_body_style
from garage_radar.normalize.color import normalize_color
from garage_radar.normalize.generation import year_to_generation
from garage_radar.normalize.nlp_flags import extract_all_flags
from garage_radar.normalize.transmission import normalize_transmission
from garage_radar.sources.base import ParsedComp, ParsedListing

logger = logging.getLogger(__name__)

# Fields that contribute to the confidence score
_CONFIDENCE_FIELDS = [
    "year", "generation", "body_style_raw", "transmission_raw",
    "exterior_color_raw", "mileage",
]


def normalize(parsed: ParsedListing) -> dict:
    """
    Run the full normalization pipeline on a parsed listing.

    Returns a dict of normalized fields ready for ORM model instantiation.
    Keys map directly to Listing / Comp model column names.
    """
    raw = asdict(parsed)

    year: Optional[int] = raw.get("year")
    description: str = raw.get("description_raw") or ""
    title: str = raw.get("title_raw") or ""
    combined_text = f"{title} {description}"

    # 1. Generation
    generation: Optional[str] = None
    if year:
        generation = year_to_generation(year, combined_text)
        if not generation:
            logger.warning("normalize: could not map year %s to generation.", year)

    # 2. Body style
    body_style_raw = raw.get("body_style_raw") or ""
    # BaT parsers return canonical body style values directly; try title as fallback
    body_style = normalize_body_style(body_style_raw or combined_text)

    # 3. Transmission
    transmission_raw = raw.get("transmission_raw") or ""
    transmission = normalize_transmission(transmission_raw or combined_text)

    # 4. Drivetrain
    drivetrain_raw = raw.get("drivetrain_raw") or "rwd"
    drivetrain = "awd" if drivetrain_raw == "awd" else "rwd"

    # 5. Color
    color_raw = raw.get("exterior_color_raw")
    color_canonical: Optional[str] = None
    color_confidence: float = 0.0
    if color_raw:
        color_canonical, color_confidence = normalize_color(color_raw)

    # 6. NLP flags
    flags = extract_all_flags(description)

    # 7. Confidence score — fraction of key fields successfully extracted
    extracted_count = sum([
        1 if year else 0,
        1 if generation else 0,
        1 if body_style else 0,
        1 if transmission else 0,
        1 if color_raw else 0,
        1 if raw.get("mileage") else 0,
    ])
    field_confidence = extracted_count / len(_CONFIDENCE_FIELDS)

    # Blend field confidence with color confidence (color matters a lot for comps)
    if color_canonical and color_canonical != "other":
        overall_confidence = round((field_confidence * 0.7) + (color_confidence * 0.3), 2)
    else:
        overall_confidence = round(field_confidence * 0.7, 2)

    # 8. Build normalized output dict
    result = {
        # Identity
        "source": raw["source"],
        "source_url": raw["source_url"],
        "scrape_ts": raw["scrape_ts"],

        # Vehicle
        "title_raw": raw.get("title_raw"),
        "year": year,
        "generation": generation,
        "body_style": body_style,
        "trim": raw.get("trim"),
        "engine_variant": raw.get("engine_variant"),
        "transmission": transmission,
        "drivetrain": drivetrain,
        "exterior_color_raw": color_raw,
        "exterior_color_canonical": color_canonical,
        "interior_color_raw": raw.get("interior_color_raw"),
        "mileage": raw.get("mileage"),
        "vin": raw.get("vin"),

        # Price
        "asking_price": raw.get("asking_price"),
        "currency": raw.get("currency", "USD"),
        "final_price": raw.get("final_price"),

        # NLP flags
        "matching_numbers": flags["matching_numbers"],
        "original_paint": flags["original_paint"],
        "service_history": flags["service_history"],
        "modification_flags": flags["modification_flags"] or None,
        "normalization_confidence": overall_confidence,

        # Meta
        "description_raw": description or None,
        "listing_date": _parse_date(raw.get("listing_date")),
        "seller_type": _normalize_seller_type(raw.get("seller_type_raw")),
        "seller_name": raw.get("seller_name"),
        "location": raw.get("location"),
        "bidder_count": raw.get("bidder_count"),
        "snapshot_path": raw.get("snapshot_path"),
        "is_completed": raw.get("is_completed", False),
    }

    # For comps, include sale-specific fields
    if isinstance(parsed, ParsedComp):
        result["sale_date"] = _parse_date(raw.get("sale_date"))
        result["price_type"] = raw.get("price_type", "auction_final")

    return result


def _parse_date(value) -> Optional[object]:
    """Convert string or date to date object. Returns None on failure."""
    if value is None:
        return None
    if hasattr(value, "year"):  # already a date/datetime
        return value
    if isinstance(value, str):
        from datetime import datetime
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%B %d, %Y"):
            try:
                return datetime.strptime(value[:len(fmt) + 4], fmt).date()
            except ValueError:
                continue
    return None


def _normalize_seller_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    lower = raw.lower()
    if "auction" in lower:
        return "auction_house"
    if "dealer" in lower:
        return "dealer"
    if "private" in lower:
        return "private"
    return None
