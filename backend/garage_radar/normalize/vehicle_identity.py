"""
Generic vehicle identity extraction.

The repo started as an air-cooled 911 tracker, but the broader pipeline now
needs a data-driven make/model layer so listings can normalize across marques
without waiting for every source parser to grow bespoke extraction logic.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_YEAR_RE = re.compile(r"\b(18(?:8[6-9]|9\d)|19\d{2}|20\d{2}|2100)\b")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9&+./'-]*")
_MODEL_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "data" / "vehicle_model_library.json"

_MAKE_ALIASES = {
    "acura": "Acura",
    "alfa romeo": "Alfa Romeo",
    "am general": "AM General",
    "aston martin": "Aston Martin",
    "audi": "Audi",
    "bentley": "Bentley",
    "bmw": "BMW",
    "buick": "Buick",
    "cadillac": "Cadillac",
    "chevrolet": "Chevrolet",
    "chrysler": "Chrysler",
    "de tomaso": "De Tomaso",
    "detomaso": "De Tomaso",
    "dodge": "Dodge",
    "ferrari": "Ferrari",
    "fiat": "Fiat",
    "ford": "Ford",
    "genesis": "Genesis",
    "gmc": "GMC",
    "honda": "Honda",
    "hyundai": "Hyundai",
    "infiniti": "Infiniti",
    "jaguar": "Jaguar",
    "jeep": "Jeep",
    "kia": "Kia",
    "lamborghini": "Lamborghini",
    "land rover": "Land Rover",
    "lexus": "Lexus",
    "lincoln": "Lincoln",
    "lotus": "Lotus",
    "maserati": "Maserati",
    "mazda": "Mazda",
    "mclaren": "McLaren",
    "mercedes benz": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercury": "Mercury",
    "mini": "MINI",
    "mitsubishi": "Mitsubishi",
    "nissan": "Nissan",
    "oldsmobile": "Oldsmobile",
    "packard": "Packard",
    "plymouth": "Plymouth",
    "pontiac": "Pontiac",
    "porsche": "Porsche",
    "ram": "RAM",
    "rivian": "Rivian",
    "rolls royce": "Rolls-Royce",
    "rolls-royce": "Rolls-Royce",
    "saab": "Saab",
    "saturn": "Saturn",
    "scion": "Scion",
    "shelby": "Shelby",
    "subaru": "Subaru",
    "suzuki": "Suzuki",
    "tesla": "Tesla",
    "toyota": "Toyota",
    "volkswagen": "Volkswagen",
    "volvo": "Volvo",
    "vw": "Volkswagen",
}

_STOP_WORDS = {
    "awd",
    "convertible",
    "coupe",
    "crossover",
    "cvt",
    "fwd",
    "hatchback",
    "manual",
    "rwd",
    "sedan",
    "speedster",
    "suv",
    "targa",
    "truck",
    "wagon",
}

_COMPOUND_MODELS_BY_MAKE: dict[str, tuple[tuple[str, ...], ...]] = {
    "Aston Martin": (("V8", "Vantage"),),
    "Jeep": (("Grand", "Cherokee"), ("Grand", "Wagoneer")),
    "Land Rover": (("Range", "Rover"),),
    "Mazda": (("MX-5", "Miata"),),
    "Toyota": (("FJ", "Cruiser"), ("Land", "Cruiser")),
}

_GENERIC_MODELS = {"auction", "auctions", "listing", "marketplace", "vehicle", "vehicles"}


def extract_vehicle_identity(
    title: str | None,
    *,
    make_raw: str | None = None,
    model_raw: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Return a best-effort (make, model) tuple.

    Parser-supplied values still matter, but we now compare them with
    title-derived candidates so longer, better-known model phrases like
    "Focus RS" can replace weaker raw values like "Focus".
    """
    raw_make = _normalize_make(make_raw)
    raw_model = _normalize_model(model_raw)
    title_make, title_model = _extract_from_title(title or "")

    make = _select_make(raw_make, title_make)
    model = _select_model(raw_model, title_model, title=title or "")
    return make, model


def _extract_from_title(title: str) -> tuple[str | None, str | None]:
    search_space = _title_after_year(title)
    tokens = _TOKEN_RE.findall(search_space)
    if not tokens:
        return None, None

    make, consumed = _extract_make(tokens)
    model = _extract_model(tokens[consumed:], make=make)
    return make, model


def _title_after_year(title: str) -> str:
    match = _YEAR_RE.search(title)
    if match:
        return title[match.end():].strip(" :-")
    return title


def _extract_make(tokens: list[str]) -> tuple[str | None, int]:
    if not tokens:
        return None, 0

    for token_count in (3, 2, 1):
        if len(tokens) < token_count:
            continue
        candidate = " ".join(tokens[:token_count]).lower()
        if candidate in _MAKE_ALIASES:
            return _MAKE_ALIASES[candidate], token_count

    return _normalize_make(tokens[0]), 1


def _extract_model(tokens: list[str], *, make: str | None) -> str | None:
    if not tokens:
        return None

    library_model = _match_known_model(tokens, make)
    if library_model:
        return library_model

    for phrase in _COMPOUND_MODELS_BY_MAKE.get(make or "", ()):
        if len(tokens) < len(phrase):
            continue
        candidate = tuple(tokens[: len(phrase)])
        if all(
            left.casefold() == right.casefold()
            for left, right in zip(candidate, phrase, strict=True)
        ):
            return " ".join(_normalize_model(token) or token for token in candidate)

    model = _normalize_model(tokens[0])
    if model and model.casefold() not in _STOP_WORDS:
        return model
    return None


def _normalize_make(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None

    canonical = _MAKE_ALIASES.get(cleaned.lower())
    if canonical:
        return canonical

    return " ".join(part.capitalize() for part in cleaned.split())


def _normalize_model(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip(" -_/")
    if not cleaned:
        return None

    if cleaned.isupper():
        return cleaned
    if any(char.isdigit() for char in cleaned):
        if re.match(r"^\d+[A-Za-z]$", cleaned):
            return cleaned
        if cleaned.islower():
            return cleaned.upper()
        return cleaned

    return cleaned.title()


def _select_make(raw_make: str | None, title_make: str | None) -> str | None:
    if raw_make and _is_known_make(raw_make):
        return raw_make
    return title_make or raw_make


def _select_model(
    raw_model: str | None,
    title_model: str | None,
    *,
    title: str,
) -> str | None:
    if raw_model and title_model:
        if raw_model.casefold() in _GENERIC_MODELS:
            return title_model
        raw_norm = _normalize_phrase(raw_model)
        title_norm = _normalize_phrase(title_model)
        if raw_norm == title_norm:
            return title_model
        if _compact_phrase(raw_norm) == _compact_phrase(title_norm):
            return title_model
        if _is_more_specific_model(title_model, raw_model):
            return title_model
        if _is_specialized_title_variant(raw_model, title_model, title):
            return title_model
        return raw_model
    return raw_model or title_model


def _is_known_make(make: str | None) -> bool:
    if not make:
        return False
    return make in set(_MAKE_ALIASES.values())


def _is_more_specific_model(candidate: str, baseline: str) -> bool:
    candidate_norm = _normalize_phrase(candidate)
    baseline_norm = _normalize_phrase(baseline)
    if not candidate_norm or candidate_norm == baseline_norm:
        return False
    if len(candidate_norm.split()) > len(baseline_norm.split()) and (
        candidate_norm.startswith(baseline_norm)
        or candidate_norm.endswith(baseline_norm)
    ):
        return True
    return len(candidate_norm) > len(baseline_norm) and baseline_norm in candidate_norm


def _is_specialized_title_variant(candidate_baseline: str, candidate_title: str, title: str) -> bool:
    baseline_norm = _normalize_phrase(candidate_baseline)
    title_norm = _normalize_phrase(candidate_title)
    search_space = _normalize_phrase(title)
    if not baseline_norm or not title_norm or baseline_norm == title_norm:
        return False
    if baseline_norm not in search_space or title_norm not in search_space:
        return False
    if title_norm in _STOP_WORDS or title_norm in _GENERIC_MODELS:
        return False

    looks_specific = (
        len(title_norm.split()) > 1
        or any(char.isdigit() for char in candidate_title)
        or "-" in candidate_title
        or candidate_title.isupper()
    )
    return looks_specific


def _match_known_model(tokens: list[str], make: str | None) -> str | None:
    if not make:
        return None

    phrases = _model_library().get(make, ())
    if not phrases:
        return None

    normalized_tokens = [_normalize_phrase(token) for token in tokens]
    filtered_tokens = [token for token in normalized_tokens if token and token not in _STOP_WORDS]
    filtered_title = " ".join(filtered_tokens)
    compact_filtered_title = _compact_phrase(filtered_title)

    for label, phrase_tokens, phrase_norm, compact_phrase in phrases:
        phrase_length = len(phrase_tokens)
        if len(normalized_tokens) < phrase_length:
            if phrase_norm and phrase_norm in filtered_title:
                return label
            if compact_phrase and compact_phrase in compact_filtered_title:
                return label
            continue
        for token_pool in (normalized_tokens, filtered_tokens):
            if len(token_pool) < phrase_length:
                continue
            for start in range(len(token_pool) - phrase_length + 1):
                if token_pool[start : start + phrase_length] == list(phrase_tokens):
                    return label
        if phrase_norm and phrase_norm in filtered_title:
            return label
        if compact_phrase and compact_phrase in compact_filtered_title:
            return label
    return None


@lru_cache(maxsize=1)
def _model_library() -> dict[str, tuple[tuple[str, tuple[str, ...], str, str], ...]]:
    if not _MODEL_LIBRARY_PATH.exists():
        return {}

    try:
        payload = json.loads(_MODEL_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    library: dict[str, tuple[tuple[str, tuple[str, ...], str, str], ...]] = {}
    for raw_make, raw_models in payload.items():
        make = _normalize_make(raw_make)
        if not make or not isinstance(raw_models, list):
            continue

        entries: list[tuple[str, tuple[str, ...], str, str]] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, str):
                continue
            label = " ".join(raw_model.strip().split())
            if not label:
                continue
            tokens = tuple(
                normalized
                for token in _TOKEN_RE.findall(label)
                if (normalized := _normalize_phrase(token))
            )
            if not tokens:
                continue
            phrase_norm = _normalize_phrase(label)
            compact_phrase = _compact_phrase(phrase_norm)
            entries.append((label, tokens, phrase_norm, compact_phrase))

        entries.sort(key=lambda item: (-len(item[1]), -len(item[2]), item[0]))
        library[make] = tuple(entries)
    return library


def _normalize_phrase(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _compact_phrase(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")
