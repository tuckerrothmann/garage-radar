"""
Year → generation mapping for air-cooled Porsche 911 (1965–1998).

Handles ambiguous model years (1989, 1994) using title/description hints.
"""
import json
from pathlib import Path
from typing import Optional

# Load lookup table from normalize/generation_table.json (relative to project root)
_TABLE_PATH = Path(__file__).parents[5] / "normalize" / "generation_table.json"


def _load_table() -> dict:
    try:
        with open(_TABLE_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback inline table if file not found
        return _FALLBACK_TABLE


_FALLBACK_TABLE = {
    "year_to_generation": {
        str(y): gen
        for gen, years in [
            ("G1", range(1965, 1974)),
            ("G2", range(1974, 1978)),
            ("G3", range(1978, 1984)),
            ("G4", range(1984, 1989)),
            ("G5", range(1990, 1994)),
            ("G6", range(1995, 1999)),
        ]
        for y in years
    },
    "ambiguous_years": {
        "1989": {
            "keywords_g4": ["carrera 3.2", "speedster", "g50"],
            "keywords_g5": ["964", "carrera 2", "carrera 4", "tiptronic"],
        },
        "1994": {
            "keywords_g5": ["964"],
            "keywords_g6": ["993"],
        },
    },
}


def year_to_generation(year: int, description: str = "") -> Optional[str]:
    """
    Map a model year to a generation code (G1–G6).

    For ambiguous years (1989, 1994), uses description text hints.
    Returns None if year is out of range (not air-cooled 911 territory).
    """
    if year < 1965 or year > 1998:
        return None

    table = _load_table()
    year_map = table.get("year_to_generation", {})
    ambiguous = table.get("ambiguous_years", {})

    raw = year_map.get(str(year))

    if raw and "_OR_" not in raw:
        return raw

    # Ambiguous year — try to resolve from description text
    if str(year) in ambiguous:
        hints = ambiguous[str(year)]
        desc_lower = description.lower()

        # Check later-generation keywords first (more specific)
        for key, gen_code in [("keywords_g6", "G6"), ("keywords_g5", "G5")]:
            if key in hints and any(kw in desc_lower for kw in hints[key]):
                return gen_code

        # Check earlier generation
        for key, gen_code in [("keywords_g5", "G5"), ("keywords_g4", "G4")]:
            if key in hints and any(kw in desc_lower for kw in hints[key]):
                return gen_code

    # Can't resolve — return the earlier generation as a conservative default
    if raw:
        gens = raw.split("_OR_")
        return gens[0]  # e.g., "G4" from "G4_OR_G5"

    return None
