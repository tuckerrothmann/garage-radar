"""Shared source targeting helpers."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from garage_radar.config import Settings, get_settings

logger = logging.getLogger(__name__)
_PRESET_PATH = Path(__file__).resolve().parents[1] / "data" / "vehicle_target_presets.json"
_YEAR_RE = re.compile(r"\b(18(?:8[6-9]|9\d)|19\d{2}|20\d{2}|2100)\b")


@dataclass(frozen=True)
class VehicleTarget:
    make: str | None = None
    model: str | None = None
    keywords: str = ""
    year_min: int | None = None
    year_max: int | None = None
    sources: tuple[str, ...] = ()

    @property
    def marketplace_query(self) -> str:
        parts = [self.make, self.model]
        return " ".join(part.strip() for part in parts if part and part.strip())

    @property
    def encoded_marketplace_query(self) -> str:
        query = self.marketplace_query or self.discovery_keywords or "collector cars"
        return quote_plus(query)

    @property
    def discovery_keywords(self) -> str:
        return " ".join(self.keywords.split())

    @property
    def ebay_keywords(self) -> str:
        parts = [self.marketplace_query, self.discovery_keywords]
        return " ".join(part for part in parts if part)

    @property
    def model_term(self) -> str | None:
        if not self.model:
            return None
        term = self.model.strip()
        return term or None

    @property
    def label(self) -> str:
        return self.marketplace_query or self.discovery_keywords or "collector cars"

    def supports_source(self, source_name: str) -> bool:
        return not self.sources or source_name.strip().lower() in self.sources

    def matches_listing(
        self,
        *,
        title: str = "",
        make: str | None = None,
        model: str | None = None,
        year: int | None = None,
    ) -> bool:
        if self.make:
            if make:
                if _normalize_match_text(make) != _normalize_match_text(self.make):
                    return False
            elif not _match_phrase(title, self.make):
                return False

        if self.model:
            if model:
                if _normalize_match_text(model) != _normalize_match_text(self.model):
                    return False
            elif not _match_phrase(title, self.model):
                return False

        if self.discovery_keywords:
            normalized_title = _normalize_match_text(title)
            for token in self.discovery_keywords.split():
                if _normalize_match_text(token) not in normalized_title:
                    return False

        actual_year = year
        if actual_year is None:
            actual_year = _extract_year(title)
        if self.year_min is not None and actual_year is not None and actual_year < self.year_min:
            return False
        return not (
            self.year_max is not None and actual_year is not None and actual_year > self.year_max
        )

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> VehicleTarget:
        raw_sources = payload.get("sources") or []
        if not isinstance(raw_sources, list):
            raw_sources = []

        return cls(
            make=_clean_str(payload.get("make")),
            model=_clean_str(payload.get("model")),
            keywords=_clean_str(payload.get("keywords")) or "",
            year_min=_to_int(payload.get("year_min")),
            year_max=_to_int(payload.get("year_max")),
            sources=tuple(
                source.strip().lower()
                for source in raw_sources
                if isinstance(source, str) and source.strip()
            ),
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> VehicleTarget:
        cfg = settings or get_settings()
        return cls(
            make=cfg.vehicle_target_make,
            model=cfg.vehicle_target_model,
            keywords=cfg.vehicle_target_keywords,
            year_min=cfg.vehicle_target_year_min,
            year_max=cfg.vehicle_target_year_max,
        )


def get_vehicle_targets(settings: Settings | None = None) -> tuple[VehicleTarget, ...]:
    if settings is not None:
        return _resolve_vehicle_targets(settings)
    return _cached_vehicle_targets()


def get_vehicle_targets_for_source(
    source_name: str,
    settings: Settings | None = None,
) -> tuple[VehicleTarget, ...]:
    targets = get_vehicle_targets(settings)
    return tuple(target for target in targets if target.supports_source(source_name))


def get_vehicle_target() -> VehicleTarget:
    return get_vehicle_targets()[0]


@lru_cache(maxsize=1)
def _cached_vehicle_targets() -> tuple[VehicleTarget, ...]:
    return _resolve_vehicle_targets(get_settings())


def _resolve_vehicle_targets(settings: Settings) -> tuple[VehicleTarget, ...]:
    if settings.vehicle_targets_json.strip():
        targets = _targets_from_json(settings.vehicle_targets_json)
    elif settings.vehicle_target_preset.strip():
        targets = _targets_from_preset(settings.vehicle_target_preset)
    else:
        targets = (VehicleTarget.from_settings(settings),)

    deduped = _dedupe_targets(targets)
    if deduped:
        return deduped
    return (VehicleTarget.from_settings(settings),)


def _targets_from_json(raw_json: str) -> tuple[VehicleTarget, ...]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid VEHICLE_TARGETS_JSON payload: %s", exc)
        return ()

    if isinstance(payload, dict):
        payload = payload.get("targets", [])
    if not isinstance(payload, list):
        logger.warning("VEHICLE_TARGETS_JSON must decode to a list of target objects.")
        return ()

    return tuple(
        VehicleTarget.from_payload(item)
        for item in payload
        if isinstance(item, dict)
    )


def _targets_from_preset(preset_name: str) -> tuple[VehicleTarget, ...]:
    if not _PRESET_PATH.exists():
        logger.warning("Vehicle target preset file missing: %s", _PRESET_PATH)
        return ()

    try:
        payload = json.loads(_PRESET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read vehicle target presets: %s", exc)
        return ()

    preset = payload.get(preset_name, [])
    if not isinstance(preset, list):
        logger.warning("Vehicle target preset %r is not a list.", preset_name)
        return ()

    return tuple(
        VehicleTarget.from_payload(item)
        for item in preset
        if isinstance(item, dict)
    )


def _dedupe_targets(targets: tuple[VehicleTarget, ...]) -> tuple[VehicleTarget, ...]:
    deduped: list[VehicleTarget] = []
    seen: set[tuple[object, ...]] = set()
    for target in targets:
        key = (
            target.make.casefold() if target.make else None,
            target.model.casefold() if target.model else None,
            target.keywords.casefold(),
            target.year_min,
            target.year_max,
            target.sources,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return tuple(deduped)


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _to_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_year(text: str) -> int | None:
    match = _YEAR_RE.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def _match_phrase(text: str, phrase: str) -> bool:
    normalized_text = _normalize_match_text(text)
    normalized_phrase = _normalize_match_text(phrase)
    if not normalized_phrase:
        return True
    return normalized_phrase in normalized_text


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    collapsed = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return f" {collapsed} " if collapsed else ""
