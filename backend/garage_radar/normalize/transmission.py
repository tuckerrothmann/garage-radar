"""
Transmission normalization for collector vehicle listings.

The current cluster model only distinguishes between manual, 6-speed
manual, and automatic-style gearboxes. This keeps pricing buckets stable
while still preserving the special 6-speed manual split that matters for
some Porsche comps.
"""
import re
from typing import Optional

_AUTO_RE = re.compile(
    r"\b("
    r"automatic|auto|tiptronic|steptronic|"
    r"pdk|dct|dsg|cvt|s[\s-]?tronic|smg|powershift|powerglide|torqueflite|"
    r"dual[-\s]?clutch"
    r")\b",
    re.I,
)
_MANUAL_6SP_RE = re.compile(
    r"\b("
    r"6[-\s]?(speed|spd)\s+manual|"
    r"manual\s+6[-\s]?(speed|spd)|"
    r"6mt"
    r")\b",
    re.I,
)
_MANUAL_RE = re.compile(
    r"\b("
    r"manual|stick|three[-\s]?pedal|"
    r"g50|915|getrag|dogleg|"
    r"[4-7](mt)|"
    r"[4-7][-\s]?(speed|spd)\s+manual|"
    r"manual\s+[4-7][-\s]?(speed|spd)"
    r")\b",
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
