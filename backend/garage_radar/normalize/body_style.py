"""
Body style normalization for vintage vehicle listings.

Maps raw body style text to canonical BodyStyleEnum values.
Patterns are ordered by specificity (most specific first).
"""
import re
from typing import Optional

# Order matters: more specific patterns first
_BODY_STYLE_MAP = [
    (re.compile(r"\bspeedster\b", re.I), "speedster"),
    (re.compile(r"\btarga\b", re.I), "targa"),
    (re.compile(r"\b(cabriolet|cabrio)\b", re.I), "cabriolet"),
    (re.compile(r"\bfastback\b", re.I), "fastback"),
    (re.compile(r"\b(roadster)\b", re.I), "roadster"),
    (re.compile(r"\b(convertible|drop[- ]?top|droptop)\b", re.I), "convertible"),
    (re.compile(r"\b(coupe|coupé)\b", re.I), "coupe"),
    (re.compile(r"\bhardtop\b", re.I), "hardtop"),
    (re.compile(r"\bsedan\b", re.I), "sedan"),
    (re.compile(r"\b(station[- ]?wagon|estate)\b", re.I), "wagon"),
    (re.compile(r"\b(pickup|pick[- ]?up|truck)\b", re.I), "pickup"),
]


def normalize_body_style(raw: Optional[str]) -> Optional[str]:
    """
    Map a raw body style string to a canonical value.
    Returns one of the BodyStyleEnum values or None if unrecognized.
    """
    if not raw or not raw.strip():
        return None

    for pattern, canonical in _BODY_STYLE_MAP:
        if pattern.search(raw):
            return canonical
    return None
