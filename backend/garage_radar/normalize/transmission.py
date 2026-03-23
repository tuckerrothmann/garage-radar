"""
Transmission normalization for vintage vehicle listings.

Maps raw transmission text to canonical values:
  'manual'     — any manual gearbox (3-, 4-, 5-, or generic manual)
  'manual-6sp' — 6-speed manual
  'auto'       — any automatic (Tiptronic, Turbo-Hydramatic, PowerGlide, etc.)
"""
import re
from typing import Optional

_MANUAL_6SP_RE = re.compile(r"\b6[-\s]?speed\b", re.I)
_AUTO_RE = re.compile(
    r"\b(automatic|auto(?:matic)?|tiptronic|powerglide|turbo[- ]?hydramatic|"
    r"th350|th400|4l60|4l80|slushbox|slush[- ]?box|cvt|dct|pdk)\b",
    re.I,
)
_MANUAL_RE = re.compile(
    r"\b(manual|stick|stick[- ]?shift|3[-\s]?speed|4[-\s]?speed|5[-\s]?speed|"
    r"close[- ]?ratio|wide[- ]?ratio|synchro|muncie|saginaw|toploader|"
    r"t[- ]?10|borg[- ]?warner|getrag|g50|915)\b",
    re.I,
)


def normalize_transmission(raw: Optional[str]) -> Optional[str]:
    """
    Map a raw transmission string to a canonical value.
    Returns 'manual', 'manual-6sp', 'auto', or None if unknown.
    """
    if not raw or not raw.strip():
        return None

    if _AUTO_RE.search(raw):
        return "auto"
    if _MANUAL_6SP_RE.search(raw):
        return "manual-6sp"
    if _MANUAL_RE.search(raw):
        return "manual"
    return None
