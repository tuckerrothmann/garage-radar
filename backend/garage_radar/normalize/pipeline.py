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
import contextlib
import logging
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from typing import Optional

from garage_radar.normalize.body_style import normalize_body_style
from garage_radar.normalize.color import normalize_color
from garage_radar.normalize.generation import year_to_generation
from garage_radar.normalize.nlp_flags import extract_all_flags
from garage_radar.normalize.transmission import normalize_transmission
from garage_radar.normalize.vehicle_identity import extract_vehicle_identity
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
    make, model = extract_vehicle_identity(
        title,
        make_raw=raw.get("make_raw"),
        model_raw=raw.get("model_raw"),
    )

    # 1. Generation
    generation: Optional[str] = None
    if year and _should_infer_porsche_generation(make, model, combined_text):
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
        "make": make,
        "model": model,
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
        "current_bid": raw.get("current_bid"),
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
        "auction_end_at": _parse_datetime(raw.get("auction_end_at")),
        "time_remaining_text": raw.get("time_remaining_text"),
        "seller_type": _normalize_seller_type(raw.get("seller_type_raw")),
        "seller_name": raw.get("seller_name"),
        "location": raw.get("location"),
        "bidder_count": raw.get("bidder_count"),
        "snapshot_path": raw.get("snapshot_path"),
        "is_completed": raw.get("is_completed", False),
    }

    # For comps, include sale-specific fields
    if isinstance(parsed, ParsedComp):
        result["sale_price"] = raw.get("final_price")
        result["sale_date"] = _parse_date(raw.get("sale_date"))
        result["price_type"] = raw.get("price_type", "auction_final")

    return result


def _should_infer_porsche_generation(
    make: Optional[str],
    model: Optional[str],
    text: str,
) -> bool:
    """
    Keep Porsche generation logic from leaking onto unrelated cars.

    The legacy G1-G6 mapping is only meaningful for the air-cooled 911 family.
    """
    lowered = text.lower()
    if make == "Porsche" and model:
        model_upper = model.upper()
        if model_upper.startswith(("911", "912", "930", "964", "993")):
            return True

    return any(
        cue in lowered
        for cue in (
            "porsche 911",
            "porsche 912",
            "964",
            "993",
            "930",
            "carrera 2",
            "carrera 4",
            "air-cooled",
        )
    )


def _parse_date(value) -> Optional[date]:
    """Convert string or date to date object. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%B %d, %Y"):
            try:
                return datetime.strptime(value[:len(fmt) + 4], fmt).date()
            except ValueError:
                continue
    return None


def _parse_datetime(value) -> Optional[datetime]:
    """Convert a string/date/datetime into a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        candidates = [
            text.replace("Z", "+00:00"),
            text,
        ]
        for candidate in candidates:
            with contextlib.suppress(ValueError):
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        parsed_date = _parse_date(text)
        if parsed_date is not None:
            return datetime.combine(parsed_date, time.min, tzinfo=UTC)
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
