"""
Transmission normalization for air-cooled Porsche 911 listings.

Maps raw transmission text to canonical values:
  'manual'     — 5-speed, G50, 915, most manuals
  'manual-6sp' — 993 RS specific 6-speed
  'auto'       — Tiptronic
"""
import re
from typing import Optional

_MANUAL_6SP_RE = re.compile(r"\b6[-\s]?speed\b", re.I)
_TIPTRONIC_RE = re.compile(r"\btiptronic\b", re.I)
_MANUAL_RE = re.compile(r"\b(5[-\s]?speed|g50|915|manual|stick|getrag)\b", re.I)


def normalize_transmission(raw: Optional[str]) -> Optional[str]:
    """
    Map a raw transmission string to a canonical value.
    Returns 'manual', 'manual-6sp', 'auto', or None if unknown.
    """
    if not raw or not raw.strip():
        return None

    if _TIPTRONIC_RE.search(raw):
        return "auto"
    if _MANUAL_6SP_RE.search(raw):
        return "manual-6sp"
    if _MANUAL_RE.search(raw):
        return "manual"
    return None
