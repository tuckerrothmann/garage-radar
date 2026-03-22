"""
Color normalization for air-cooled Porsche 911 listings.

Maps raw exterior color strings (free text) to canonical color values
using exact alias match → fuzzy match → fallback to 'other'.
"""
import json
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

_ALIASES_PATH = Path(__file__).parents[3] / "normalize" / "color_aliases.json"

CANONICAL_VALUES = [
    "white", "silver", "grey", "grey-metallic", "black",
    "red", "blue", "blue-metallic", "green", "green-metallic",
    "yellow", "orange", "brown", "beige", "gold-metallic",
    "purple", "turquoise", "burgundy", "bronze-metallic", "other",
]

_FUZZY_THRESHOLD = 70  # 0–100; lower = more permissive


def _load_aliases() -> dict[str, str]:
    """Build a flat dict: alias_string -> canonical_color."""
    try:
        with open(_ALIASES_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}

    result = {}
    for canonical, aliases in data.get("aliases", {}).items():
        for alias in aliases:
            result[alias.lower().strip()] = canonical
    return result


_ALIAS_MAP: dict[str, str] = {}


def _get_alias_map() -> dict[str, str]:
    global _ALIAS_MAP
    if not _ALIAS_MAP:
        _ALIAS_MAP = _load_aliases()
    return _ALIAS_MAP


def normalize_color(raw: Optional[str]) -> tuple[Optional[str], float]:
    """
    Normalize a raw color string to a canonical color.

    Returns: (canonical_color, confidence)
    - confidence 1.0 = exact alias match
    - confidence 0.7–0.99 = fuzzy match
    - confidence 0.0 = 'other' fallback
    """
    if not raw or not raw.strip():
        return None, 0.0

    normalized = raw.lower().strip()
    alias_map = _get_alias_map()

    # 1. Exact alias match
    if normalized in alias_map:
        return alias_map[normalized], 1.0

    # 2. Check if it's already a canonical value
    if normalized in CANONICAL_VALUES:
        return normalized, 1.0

    # 3. Fuzzy match against all known aliases
    all_aliases = list(alias_map.keys())
    if all_aliases:
        match, score, _ = process.extractOne(
            normalized,
            all_aliases,
            scorer=fuzz.token_sort_ratio,
        )
        if score >= _FUZZY_THRESHOLD:
            canonical = alias_map[match]
            confidence = round(score / 100, 2)
            return canonical, confidence

    # 4. Fuzzy match against canonical values directly
    match, score, _ = process.extractOne(
        normalized,
        CANONICAL_VALUES,
        scorer=fuzz.token_sort_ratio,
    )
    if score >= _FUZZY_THRESHOLD:
        return match, round(score / 100, 2)

    # 5. Fallback
    return "other", 0.0
