"""
Generation mapping for vintage vehicles.

Maps (make, model, year) to a generation code using per-make lookup tables.
Generation codes are free text (e.g. "G1", "C2", "First Gen") — not an enum.

Returns None when no generation table exists for a make/model, or when the
year is outside all defined ranges.  Generation is an enrichment, not required.
"""
from __future__ import annotations

from typing import Optional


def _load_table() -> dict:
    return _GENERATION_TABLE


_GENERATION_TABLE: dict = {
    "Porsche": {
        "911": {
            "year_to_generation": {
                **{str(y): "G1" for y in range(1965, 1974)},
                **{str(y): "G2" for y in range(1974, 1978)},
                **{str(y): "G3" for y in range(1978, 1984)},
                **{str(y): "G4" for y in range(1984, 1989)},
                "1989": "G4_OR_G5",   # ambiguous — 964 or 3.2 carrera
                **{str(y): "G5" for y in range(1990, 1994)},
                "1994": "G5_OR_G6",   # ambiguous — 964 or 993
                **{str(y): "G6" for y in range(1995, 1999)},
            },
            "ambiguous_years": {
                "1989": {
                    "keywords_g4": ["carrera 3.2", "speedster", "g50"],
                    "keywords_g5": ["964", "carrera 2", "carrera 4", "c4", "c4s", "tiptronic"],
                },
                "1994": {
                    "keywords_g5": ["964"],
                    "keywords_g6": ["993"],
                },
            },
        }
    },
    "Chevrolet": {
        "Corvette": {
            "year_to_generation": {
                **{str(y): "C1" for y in range(1953, 1963)},
                **{str(y): "C2" for y in range(1963, 1968)},
                **{str(y): "C3" for y in range(1968, 1983)},
                **{str(y): "C4" for y in range(1984, 1997)},
                **{str(y): "C5" for y in range(1997, 2005)},
                **{str(y): "C6" for y in range(2005, 2014)},
                **{str(y): "C7" for y in range(2014, 2020)},
                **{str(y): "C8" for y in range(2020, 2026)},
            },
            "ambiguous_years": {
                "1963": {
                    "keywords_c1": ["split window"],
                    "keywords_c2": ["sting ray", "stingray"],
                },
            },
        }
    },
    "Ford": {
        "Mustang": {
            "year_to_generation": {
                **{str(y): "Gen1" for y in range(1964, 1974)},
                **{str(y): "Gen2" for y in range(1974, 1978)},
                **{str(y): "Gen3" for y in range(1979, 1994)},
                **{str(y): "Gen4" for y in range(1994, 2005)},
                **{str(y): "Gen5" for y in range(2005, 2015)},
                **{str(y): "Gen6" for y in range(2015, 2026)},
            },
            "ambiguous_years": {},
        }
    },
}


def year_to_generation(
    year: int,
    description: str = "",
    make: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Map a model year (and optionally make/model) to a generation code.

    For makes/models with defined generation tables, uses the table to map
    year → generation, handling ambiguous years via description text hints.

    Returns None if:
      - make/model are unknown
      - year is outside all defined ranges for this make/model
    """
    table = _load_table()

    # Normalize make/model for lookup
    make_key = (make or "").strip()
    model_key = (model or "").strip()

    # Find the make-level entry (case-insensitive)
    make_data: Optional[dict] = None
    for k in table:
        if k.lower() == make_key.lower():
            make_data = table[k]
            break

    if make_data is None:
        return None

    # Find the model-level entry
    model_data: Optional[dict] = None
    for k in make_data:
        if k.lower() == model_key.lower():
            model_data = make_data[k]
            break

    if model_data is None:
        return None

    year_map = model_data.get("year_to_generation", {})
    ambiguous = model_data.get("ambiguous_years", {})

    raw = year_map.get(str(year))
    if raw is None:
        return None

    if "_OR_" not in raw:
        return raw

    # Ambiguous year — try to resolve from description text
    if str(year) in ambiguous:
        hints = ambiguous[str(year)]
        desc_lower = description.lower()

        # Check all hint keys in order of specificity (later gens first)
        hint_pairs = sorted(
            [(k, v) for k, v in hints.items() if k.startswith("keywords_")],
            key=lambda x: x[0],
            reverse=True,
        )
        for key, keywords in hint_pairs:
            if any(kw in desc_lower for kw in keywords):
                # Extract generation from key name: "keywords_g6" → "G6"
                gen_code = key.split("_", 1)[1].upper()
                return gen_code

    # Can't resolve — return the earlier generation as a conservative default
    return raw.split("_OR_")[0]
