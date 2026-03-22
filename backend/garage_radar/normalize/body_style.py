"""
Body style normalization for air-cooled Porsche 911 listings.

Maps raw body style text to canonical values:
  'coupe', 'targa', 'cabriolet', 'speedster'
"""
import re
from typing import Optional

_BODY_STYLE_MAP = [
    (re.compile(r"\bspeedster\b", re.I), "speedster"),
    (re.compile(r"\b(cabriolet|cabrio|convertible|roadster)\b", re.I), "cabriolet"),
    (re.compile(r"\btarga\b", re.I), "targa"),
    (re.compile(r"\b(coupe|coupé)\b", re.I), "coupe"),
]


def normalize_body_style(raw: Optional[str]) -> Optional[str]:
    """
    Map a raw body style string to a canonical value.
    Returns 'coupe', 'targa', 'cabriolet', 'speedster', or None.
    """
    if not raw or not raw.strip():
        return None

    for pattern, canonical in _BODY_STYLE_MAP:
        if pattern.search(raw):
            return canonical
    return None
