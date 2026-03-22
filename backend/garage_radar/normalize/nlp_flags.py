"""
NLP signal extraction from listing description text.
Regex + keyword matching. No ML — fast and transparent.

Returns boolean flags (True/False/None):
  True  = keyword found → flag likely applies
  False = negation found OR keywords explicitly absent
  None  = not mentioned — unknown (don't assume False)
"""
import re
from typing import Optional


# ── Keyword dictionaries ─────────────────────────────────────────────────────

MATCHING_NUMBERS_KEYWORDS = [
    r"\bmatching[- ]numbers?\b",
    r"\bnumbers?[- ]matching\b",
    r"\boriginal[- ]engine\b",
    r"\boriginal[- ]motor\b",
    r"\bfactory[- ]engine\b",
]
MATCHING_NUMBERS_NEGATIONS = [
    r"\bnon[- ]matching\b",
    r"\bengine[- ](swap|replacement|rebuild|replaced)\b",
    r"\b(replacement|rebuilt|swapped)[- ]engine\b",
]

ORIGINAL_PAINT_KEYWORDS = [
    r"\boriginal[- ]paint\b",
    r"\bunrestored\b",
    r"\bbarn[- ]find\b",
    r"\bfactory[- ](?:original[- ])?paint\b",
    r"\boriginal[- ](?:factory[- ])?finish\b",
    r"\bpaint[- ]meter\b",          # paint meter readings = originality check
]
ORIGINAL_PAINT_NEGATIONS = [
    r"\brepaint(?:ed)?\b",
    r"\bre[- ]paint(?:ed)?\b",
    r"\bnew[- ]paint\b",
    r"\bcolor[- ]change\b",
    r"\brefin(?:ish|ished)\b",
]

SERVICE_HISTORY_KEYWORDS = [
    r"\bservice[- ]record[s]?\b",
    r"\bservice[- ]histor(?:y|ies)\b",
    r"\bdealer[- ]maintained\b",
    r"\bdocumented[- ](?:service[- ])?histor(?:y|ies)\b",
    r"\bmaintenance[- ]record[s]?\b",
    r"\brecords[- ]present\b",
    r"\brecords[- ]available\b",
    r"\brecords[- ]on[- ]file\b",
    r"\boriginal[- ]books?\b",
]
SERVICE_HISTORY_NEGATIONS = [
    r"\bno[- ]service[- ]record[s]?\b",
    r"\bno[- ]records?\b",
    r"\brecords?[- ](not[- ]available|unavailable|unknown|missing)\b",
]

MODIFICATION_KEYWORDS = {
    "widebody": [r"\bwidebody\b", r"\bwide[- ]body\b", r"\bflared?\b"],
    "engine_swap": [r"\bengine[- ](swap|replaced|conversion)\b", r"\b(993|964|3\.8|3\.6|3\.2)[- ]swap\b"],
    "turbo_conversion": [r"\bturbo[- ]conversion\b", r"\bturbo[- ]kit\b"],
    "aftermarket_exhaust": [r"\baftermarket[- ]exhaust\b", r"\bsport[- ]exhaust\b", r"\b(borla|akrapovic|dansk)\b"],
    "aftermarket_wheels": [r"\baftermarket[- ]wheels?\b", r"\bnon[- ]factory[- ]wheels?\b"],
    "suspension_mods": [r"\blowered\b", r"\bcoilover[s]?\b", r"\bsuspension[- ](kit|upgrade)\b"],
    "roll_cage": [r"\broll[- ]cage\b", r"\brollcage\b"],
    "stripped_interior": [r"\bstripped[- ]interior\b", r"\bcage[d]?\b", r"\btrack[- ]prep\b"],
}


# ── Extraction helpers ───────────────────────────────────────────────────────

def _has_keyword(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_matching_numbers(description: Optional[str]) -> Optional[bool]:
    if not description:
        return None
    if _has_keyword(description, MATCHING_NUMBERS_NEGATIONS):
        return False
    if _has_keyword(description, MATCHING_NUMBERS_KEYWORDS):
        return True
    return None


def extract_original_paint(description: Optional[str]) -> Optional[bool]:
    if not description:
        return None
    if _has_keyword(description, ORIGINAL_PAINT_NEGATIONS):
        return False
    if _has_keyword(description, ORIGINAL_PAINT_KEYWORDS):
        return True
    return None


def extract_service_history(description: Optional[str]) -> Optional[bool]:
    if not description:
        return None
    if _has_keyword(description, SERVICE_HISTORY_NEGATIONS):
        return False
    if _has_keyword(description, SERVICE_HISTORY_KEYWORDS):
        return True
    return None


def extract_modification_flags(description: Optional[str]) -> list[str]:
    """Return list of detected modification flag keys (e.g., ['widebody', 'aftermarket_wheels'])."""
    if not description:
        return []
    found = []
    for flag_name, patterns in MODIFICATION_KEYWORDS.items():
        if _has_keyword(description, patterns):
            found.append(flag_name)
    return found


def extract_all_flags(description: Optional[str]) -> dict:
    """Extract all NLP flags from description text. Returns a dict of all signals."""
    return {
        "matching_numbers": extract_matching_numbers(description),
        "original_paint": extract_original_paint(description),
        "service_history": extract_service_history(description),
        "modification_flags": extract_modification_flags(description),
    }
