"""
Body style normalization for collector vehicle listings.

Maps raw body style text to a compact canonical set that works across
sports cars, sedans, SUVs, and trucks.
"""
import re
from typing import Optional

_BODY_STYLE_MAP = [
    (re.compile(r"\bspeedster\b", re.I), "speedster"),
    (re.compile(r"\btarga\b", re.I), "targa"),
    (
        re.compile(r"\b(cabriolet|cabrio|convertible|roadster|spyder|spider|drophead)\b", re.I),
        "cabriolet",
    ),
    (re.compile(r"\b(wagon|estate|touring|shooting brake)\b", re.I), "wagon"),
    (re.compile(r"\b(hatchback|liftback|fastback)\b", re.I), "hatchback"),
    (re.compile(r"\b(suv|crossover|sport[-\s]?utility)\b", re.I), "suv"),
    (re.compile(r"\b(pickup|truck|ute)\b", re.I), "truck"),
    (re.compile(r"\b(van|minivan|mpv)\b", re.I), "van"),
    (re.compile(r"\b(sedan|saloon)\b", re.I), "sedan"),
    (re.compile(r"\b(coupe|coupé)\b", re.I), "coupe"),
]


def normalize_body_style(raw: Optional[str]) -> Optional[str]:
    """
    Map a raw body style string to a canonical value.
    Returns a canonical body style value or None.
    """
    if not raw or not raw.strip():
        return None

    for pattern, canonical in _BODY_STYLE_MAP:
        if pattern.search(raw):
            return canonical
    return None
