"""
Curated plus inferred vehicle profile builder.

This gives the frontend a single profile payload for a make/model even before
the repo has a full encyclopedia behind it. Curated copy is merged with live
market coverage from the local database.
"""
from __future__ import annotations

import asyncio
import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garage_radar.config import get_settings
from garage_radar.db.models import Comp, Listing, ListingStatusEnum
from garage_radar.reference_sources import WikimediaVehicleProfileProvider

_PROFILE_PATH = Path(__file__).resolve().parent / "data" / "vehicle_profiles.json"
_GENERIC_RELATED_MODEL_SCOPES = {"model", "series", "type"}
_PROFILE_RESPONSE_CACHE: dict[tuple[str, str, int | None, str | None], tuple[float, dict[str, Any]]] = {}
_PROFILE_FAMILY_ALIASES: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "Audi": (
        (re.compile(r"^A8L\b", re.I), "A8"),
    ),
    "BMW": (
        (re.compile(r"^(?:3\d{2}|M3)", re.I), "3-Series"),
        (re.compile(r"^(?:4\d{2}|M4)", re.I), "4-Series"),
        (re.compile(r"^(?:5\d{2}|M5)", re.I), "5-Series"),
        (re.compile(r"^(?:8\d{2}|M8)", re.I), "8-Series"),
        (re.compile(r"^X1\b", re.I), "X1"),
        (re.compile(r"^X5\b", re.I), "X5"),
        (re.compile(r"^Z4\b", re.I), "Z4"),
    ),
    "Ford": (
        (re.compile(r"^Shelby\s+GT\d+", re.I), "Mustang"),
        (re.compile(r"^Shelby\s+F-150$", re.I), "F-150"),
        (re.compile(r"^GT\d+(?:SR)?$", re.I), "Mustang"),
    ),
    "FIAT": (
        (re.compile(r"^500[a-z]$", re.I), "500"),
    ),
    "Mercedes-Benz": (
        (re.compile(r"^c\d", re.I), "C-Class"),
        (re.compile(r"^cl\d", re.I), "CL-Class"),
        (re.compile(r"^e\d", re.I), "E-Class"),
        (re.compile(r"^g\d", re.I), "G-Class"),
        (re.compile(r"^s\d", re.I), "S-Class"),
        (re.compile(r"^sl\d", re.I), "SL-Class"),
        (re.compile(r"^\d{3}\s*sl\b", re.I), "SL-Class"),
    ),
    "Volvo": (
        (re.compile(r"^v(\d{2,3})r$", re.I), r"V\1"),
    ),
}
_PROFILE_CROSS_MAKE_ALIASES: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {
    ("Ford", "Pantera"): (("De Tomaso", "Pantera"),),
}


@lru_cache
def _profile_catalog() -> dict[str, dict[str, Any]]:
    if not _PROFILE_PATH.exists():
        return {}
    return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))


def profile_key(make: str, model: str) -> str:
    return f"{_slug(make)}:{_slug(model)}"


def _profile_family_aliases(make: str, model: str) -> list[str]:
    normalized_model = " ".join(model.strip().split())
    first_token = next((token for token in model.strip().split() if token), "")
    aliases: list[str] = []
    for pattern, alias_template in _PROFILE_FAMILY_ALIASES.get(make, ()):
        match = pattern.match(first_token) or pattern.match(normalized_model)
        if not match:
            continue
        alias = match.expand(alias_template)
        if alias not in aliases:
            aliases.append(alias)
    return aliases


def _profile_model_candidates(model: str, *, make: str | None = None) -> list[str]:
    tokens = [token for token in model.strip().split() if token]
    if not tokens:
        return [model]

    candidates: list[str] = []
    seen: set[str] = set()

    def _append(candidate: str) -> None:
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    for end in range(len(tokens), 0, -1):
        _append(" ".join(tokens[:end]))
    if len(tokens) == 1 and "-" in tokens[0]:
        hyphen_parts = [part for part in tokens[0].split("-") if part]
        for end in range(len(hyphen_parts) - 1, 0, -1):
            _append("-".join(hyphen_parts[:end]))
    if make:
        for alias in _profile_family_aliases(make, model):
            _append(alias)
    return candidates


def _profile_lookup_candidates(make: str, model: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _append(candidate_make: str, candidate_model: str) -> None:
        pair = (candidate_make, candidate_model)
        if pair in seen:
            return
        seen.add(pair)
        candidates.append(pair)

    for candidate_model in _profile_model_candidates(model, make=make):
        _append(make, candidate_model)

    for alias_make, alias_model in _PROFILE_CROSS_MAKE_ALIASES.get((make, model), ()):
        for candidate_model in _profile_model_candidates(alias_model, make=alias_make):
            _append(alias_make, candidate_model)

    return candidates


def _related_model_scope(model: str, *, make: str | None = None) -> str | None:
    candidates = _profile_model_candidates(model, make=make)[1:]
    for candidate in reversed(candidates):
        if candidate.casefold() in _GENERIC_RELATED_MODEL_SCOPES:
            continue
        return candidate
    return None


def _resolve_curated_profile(make: str, model: str) -> tuple[str | None, dict[str, Any]]:
    catalog = _profile_catalog()
    for candidate_make, candidate_model in _profile_lookup_candidates(make, model):
        curated = catalog.get(profile_key(candidate_make, candidate_model))
        if curated:
            return candidate_model, curated
    return None, {}


def clear_vehicle_profile_cache() -> None:
    """Clear the in-process vehicle profile response cache."""
    _PROFILE_RESPONSE_CACHE.clear()


def invalidate_vehicle_profile_cache(make: str | None, model: str | None) -> None:
    """Invalidate cached profile payloads for a make/model across all years."""
    if not make or not model:
        return

    normalized_make = " ".join(make.strip().split())
    normalized_model = " ".join(model.strip().split())
    doomed = [
        key
        for key in _PROFILE_RESPONSE_CACHE
        if key[0] == normalized_make and key[1] == normalized_model
    ]
    for key in doomed:
        _PROFILE_RESPONSE_CACHE.pop(key, None)


def _vehicle_profile_cache_key(
    make: str,
    model: str,
    year: int | None,
    currency: str | None,
) -> tuple[str, str, int | None, str | None]:
    return make, model, year, currency


def _vehicle_profile_cache_ttl_s() -> float:
    return max(float(get_settings().vehicle_profile_cache_ttl_s), 0.0)


def _get_cached_vehicle_profile(
    make: str,
    model: str,
    year: int | None,
    currency: str | None,
) -> dict[str, Any] | None:
    ttl_s = _vehicle_profile_cache_ttl_s()
    if ttl_s <= 0:
        return None

    key = _vehicle_profile_cache_key(make, model, year, currency)
    cached = _PROFILE_RESPONSE_CACHE.get(key)
    if cached is None:
        return None

    expires_at, payload = cached
    if expires_at <= monotonic():
        _PROFILE_RESPONSE_CACHE.pop(key, None)
        return None
    return copy.deepcopy(payload)


def _set_cached_vehicle_profile(
    make: str,
    model: str,
    year: int | None,
    currency: str | None,
    payload: dict[str, Any],
) -> None:
    ttl_s = _vehicle_profile_cache_ttl_s()
    if ttl_s <= 0:
        return

    key = _vehicle_profile_cache_key(make, model, year, currency)
    _PROFILE_RESPONSE_CACHE[key] = (monotonic() + ttl_s, copy.deepcopy(payload))


async def _resolve_external_profile(
    provider: WikimediaVehicleProfileProvider,
    make: str,
    model: str,
    *,
    year: int | None,
) -> tuple[str | None, Any]:
    try:
        async with asyncio.timeout(get_settings().reference_profile_budget_s):
            for candidate_make, candidate_model in _profile_lookup_candidates(make, model):
                profile = await provider.fetch_profile(candidate_make, candidate_model, year=year)
                if profile:
                    return candidate_model, profile
    except TimeoutError:
        return None, None
    return None, None


async def build_vehicle_profile(
    session: AsyncSession,
    make: str,
    model: str,
    *,
    year: int | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    normalized_make = " ".join(make.strip().split())
    normalized_model = " ".join(model.strip().split())
    normalized_currency = currency.strip().upper() if currency else None
    cached = _get_cached_vehicle_profile(normalized_make, normalized_model, year, normalized_currency)
    if cached is not None:
        return cached

    related_scope_model = _related_model_scope(normalized_model, make=normalized_make)
    curated_scope_model, curated = _resolve_curated_profile(normalized_make, normalized_model)
    external_task = asyncio.create_task(
        _resolve_external_profile(
            WikimediaVehicleProfileProvider(),
            normalized_make,
            normalized_model,
            year=year,
        )
    )

    family_listing_filters = [
        func.lower(Listing.make) == normalized_make.lower(),
        func.lower(Listing.model) == normalized_model.lower(),
    ]
    active_listing_filters = [
        *family_listing_filters,
        Listing.listing_status.in_([ListingStatusEnum.active, ListingStatusEnum.relist]),
    ]
    family_comp_filters = [
        func.lower(Comp.make) == normalized_make.lower(),
        func.lower(Comp.model) == normalized_model.lower(),
    ]
    listing_currency_breakdown = await _count_breakdown(
        session,
        select(Listing.currency, func.count(Listing.id).label("count"))
        .where(*active_listing_filters)
        .group_by(Listing.currency)
        .order_by(func.count(Listing.id).desc(), Listing.currency),
    )
    comp_currency_breakdown = await _count_breakdown(
        session,
        select(Comp.currency, func.count(Comp.id).label("count"))
        .where(*family_comp_filters)
        .group_by(Comp.currency)
        .order_by(func.count(Comp.id).desc(), Comp.currency),
    )
    currencies = _merge_breakdown_labels(listing_currency_breakdown, comp_currency_breakdown)
    primary_currency = normalized_currency or _choose_primary_currency(
        listing_currency_breakdown,
        comp_currency_breakdown,
    )

    listing_metric_filters = list(active_listing_filters)
    comp_metric_filters = list(family_comp_filters)
    if primary_currency:
        listing_metric_filters.append(Listing.currency == primary_currency)
        comp_metric_filters.append(Comp.currency == primary_currency)

    listing_summary = await session.execute(
        select(
            func.count(Listing.id).label("count"),
            func.min(Listing.year).label("year_min"),
            func.max(Listing.year).label("year_max"),
            func.max(Listing.created_at).label("latest_listing_at"),
            _distinct_array(Listing.body_style).label("body_styles"),
            _distinct_array(Listing.transmission).label("transmissions"),
            _distinct_array(Listing.source).label("sources"),
            _distinct_array(Listing.trim).label("trims"),
        ).where(*active_listing_filters)
    )
    listing_price_summary = await session.execute(
        select(
            func.avg(Listing.asking_price).label("avg_ask"),
            func.min(Listing.asking_price).label("min_ask"),
            func.max(Listing.asking_price).label("max_ask"),
        ).where(*listing_metric_filters, Listing.asking_price.is_not(None))
    )
    comp_summary = await session.execute(
        select(
            func.count(Comp.id).label("count"),
        ).where(*family_comp_filters)
    )
    comp_price_summary = await session.execute(
        select(
            func.count(Comp.id).label("priced_count"),
            func.avg(Comp.sale_price).label("avg_sale"),
            func.min(Comp.sale_price).label("min_sale"),
            func.max(Comp.sale_price).label("max_sale"),
            func.max(Comp.sale_date).label("latest_sale_date"),
        ).where(*comp_metric_filters, Comp.sale_price.is_not(None))
    )

    listing_row = listing_summary.mappings().one()
    listing_price_row = listing_price_summary.mappings().one()
    comp_row = comp_summary.mappings().one()
    comp_price_row = comp_price_summary.mappings().one()

    body_styles = _array_values(listing_row["body_styles"])
    transmissions = _array_values(listing_row["transmissions"])
    sources = _array_values(listing_row["sources"])
    trims = _array_values(listing_row["trims"])[:8]
    body_style_breakdown = await _count_breakdown(
        session,
        select(Listing.body_style, func.count(Listing.id).label("count"))
        .where(*active_listing_filters, Listing.body_style.is_not(None))
        .group_by(Listing.body_style)
        .order_by(func.count(Listing.id).desc(), Listing.body_style),
    )
    transmission_breakdown = await _count_breakdown(
        session,
        select(Listing.transmission, func.count(Listing.id).label("count"))
        .where(*active_listing_filters, Listing.transmission.is_not(None))
        .group_by(Listing.transmission)
        .order_by(func.count(Listing.id).desc(), Listing.transmission),
    )
    trim_breakdown = await _count_breakdown(
        session,
        select(Listing.trim, func.count(Listing.id).label("count"))
        .where(*active_listing_filters, Listing.trim.is_not(None))
        .group_by(Listing.trim)
        .order_by(func.count(Listing.id).desc(), Listing.trim)
        .limit(8),
    )
    source_breakdown = await _count_breakdown(
        session,
        select(Listing.source, func.count(Listing.id).label("count"))
        .where(*active_listing_filters)
        .group_by(Listing.source)
        .order_by(func.count(Listing.id).desc(), Listing.source),
    )
    year_breakdown = await _count_breakdown(
        session,
        select(Listing.year, func.count(Listing.id).label("count"))
        .where(*active_listing_filters)
        .group_by(Listing.year)
        .order_by(Listing.year.desc())
        .limit(10),
    )
    recent_listing_result = await session.execute(
        select(Listing)
        .where(*listing_metric_filters)
        .order_by(Listing.listing_date.desc().nullslast(), Listing.created_at.desc())
        .limit(6)
    )
    recent_listings = [
        _serialize_recent_listing(listing)
        for listing in recent_listing_result.scalars().all()
    ]
    related_model_breakdown: list[dict[str, int]] = []
    if related_scope_model:
        related_model_breakdown = await _count_breakdown(
            session,
            select(Listing.model, func.count(Listing.id).label("count"))
            .where(
                func.lower(Listing.make) == normalized_make.lower(),
                Listing.listing_status.in_([ListingStatusEnum.active, ListingStatusEnum.relist]),
                Listing.model.is_not(None),
                func.lower(Listing.model).like(f"{related_scope_model.lower()}%"),
                func.lower(Listing.model) != normalized_model.lower(),
            )
            .group_by(Listing.model)
            .order_by(func.count(Listing.id).desc(), Listing.model)
            .limit(8),
        )

    recent_sales_scope: str | None = None
    recent_sales_stmt = (
        select(Comp)
        .where(*comp_metric_filters)
        .order_by(Comp.sale_date.desc().nullslast(), Comp.created_at.desc())
        .limit(6)
    )
    if int(comp_price_row["priced_count"] or 0) == 0 and related_scope_model:
        recent_sales_scope = f"{normalized_make} {related_scope_model}"
        related_comp_filters = [
            func.lower(Comp.make) == normalized_make.lower(),
            Comp.model.is_not(None),
            func.lower(Comp.model).like(f"{related_scope_model.lower()}%"),
        ]
        if primary_currency:
            related_comp_filters.append(Comp.currency == primary_currency)
        recent_sales_stmt = (
            select(Comp)
            .where(*related_comp_filters)
            .order_by(Comp.sale_date.desc().nullslast(), Comp.created_at.desc())
            .limit(6)
        )
    recent_sales_result = await session.execute(recent_sales_stmt)
    recent_sales = [
        _serialize_recent_comp(comp)
        for comp in recent_sales_result.scalars().all()
    ]
    external_scope_model, external = await external_task
    focus_context = (
        await _focus_year_context(
            session,
            active_listing_filters,
            family_comp_filters,
            year,
            primary_currency,
        )
        if year is not None
        else {}
    )

    if curated and external:
        profile_source = "curated+external"
    elif external:
        profile_source = "external"
    elif curated:
        profile_source = "hybrid"
    else:
        profile_source = "inferred"

    stats = {
        "listing_count": int(listing_row["count"] or 0),
        "comp_count": int(comp_row["count"] or 0),
        "primary_currency": primary_currency,
        "currencies": currencies,
        "year_min": _to_int(listing_row["year_min"]),
        "year_max": _to_int(listing_row["year_max"]),
        "avg_asking_price": _to_float(listing_price_row["avg_ask"]),
        "min_asking_price": _to_float(listing_price_row["min_ask"]),
        "max_asking_price": _to_float(listing_price_row["max_ask"]),
        "avg_sale_price": _to_float(comp_price_row["avg_sale"]),
        "min_sale_price": _to_float(comp_price_row["min_sale"]),
        "max_sale_price": _to_float(comp_price_row["max_sale"]),
        "latest_listing_at": listing_row["latest_listing_at"],
        "latest_sale_date": comp_price_row["latest_sale_date"],
        "sources": sources,
    }

    observed_body_styles = curated.get("body_styles") or body_styles
    observed_transmissions = curated.get("transmissions") or transmissions
    notable_trims = curated.get("notable_trims") or [item["label"] for item in trim_breakdown] or trims

    encyclopedia_facts = {
        **(external.facts if external else {}),
        **curated.get("quick_facts", {}),
    }
    market_facts = {
        "Profile scope": f"Family-level {normalized_make} {normalized_model} market view",
        "Observed years": _format_year_range(stats["year_min"], stats["year_max"]) or "No local data yet",
        "Observed body styles": ", ".join(observed_body_styles) or "Unknown",
        "Observed transmissions": ", ".join(observed_transmissions) or "Unknown",
        "Garage Radar coverage": _coverage_label(stats["listing_count"], stats["comp_count"]),
    }
    if primary_currency:
        market_facts["Pricing stats currency"] = primary_currency
    if currencies:
        market_facts["Tracked currencies"] = ", ".join(currencies)
    if year is not None:
        market_facts["Focused year"] = str(year)
    if focus_context:
        market_facts["Focus-year coverage"] = (
            f"{focus_context['listing_count']} active listing(s), "
            f"{focus_context['comp_count']} sale(s)"
        )
        if focus_context["generations"]:
            market_facts["Focus-year generation"] = ", ".join(focus_context["generations"])
        if focus_context["engines"]:
            market_facts["Focus-year engines"] = ", ".join(focus_context["engines"])
        if focus_context["trims"]:
            market_facts["Focus-year trims"] = ", ".join(focus_context["trims"])
    if body_style_breakdown:
        market_facts.setdefault("Most common body style", body_style_breakdown[0]["label"])
    if transmission_breakdown:
        market_facts.setdefault("Dominant transmission", transmission_breakdown[0]["label"])
    if trim_breakdown:
        market_facts.setdefault("Top tracked trim", trim_breakdown[0]["label"])
    if recent_sales_scope and recent_sales:
        market_facts.setdefault("Recent sales scope", recent_sales_scope)
    scope_models = []
    for scope_model in (curated_scope_model, external_scope_model):
        if scope_model and scope_model != normalized_model and scope_model not in scope_models:
            scope_models.append(scope_model)
    if scope_models:
        market_facts.setdefault(
            "Reference scope",
            ", ".join(f"{normalized_make} {scope_model}" for scope_model in scope_models),
        )
    quick_facts = {
        **encyclopedia_facts,
        **market_facts,
    }

    overview = (
        curated.get("overview")
        or (external.summary if external else None)
        or _fallback_overview(normalized_make, normalized_model, stats)
    )
    market_summary = _market_summary(normalized_make, normalized_model, year, stats, focus_context)
    market_signals = _market_signals(
        normalized_make,
        normalized_model,
        stats,
        recent_sales,
        related_model_breakdown,
        recent_sales_scope,
    )
    highlights = curated.get("highlights") or _fallback_highlights(stats, notable_trims)
    common_questions = _merge_unique_strings(
        _focus_year_questions(normalized_make, normalized_model, year),
        curated.get("common_questions") or _fallback_questions(normalized_make, normalized_model),
    )
    buying_tips = curated.get("buying_tips") or _fallback_buying_tips(observed_body_styles, observed_transmissions)
    coverage_gaps = _coverage_gaps(stats, source_breakdown, recent_listings)
    local_observations = _merge_unique_strings(
        _focus_year_observations(year, focus_context, curated),
        _local_observations(
            normalized_make,
            normalized_model,
            stats,
            source_breakdown,
            year_breakdown,
            body_style_breakdown,
            transmission_breakdown,
            trim_breakdown,
        ),
    )

    payload = {
        "make": normalized_make,
        "model": normalized_model,
        "year": year,
        "slug": profile_key(normalized_make, normalized_model),
        "display_name": f"{normalized_make} {normalized_model}",
        "profile_source": profile_source,
        "overview": overview,
        "canonical_url": external.canonical_url if external else None,
        "hero_image_url": external.image_url if external else None,
        "production_years": curated.get("production_years") or _format_year_range(
            stats["year_min"],
            stats["year_max"],
        ),
        "body_styles": observed_body_styles,
        "transmissions": observed_transmissions,
        "notable_trims": notable_trims,
        "encyclopedia_facts": encyclopedia_facts,
        "market_facts": market_facts,
        "quick_facts": quick_facts,
        "highlights": highlights,
        "common_questions": common_questions,
        "buying_tips": buying_tips,
        "market_summary": market_summary,
        "market_signals": market_signals,
        "recent_sales_scope": recent_sales_scope,
        "reference_links": [source.__dict__ for source in (external.sources if external else [])],
        "external_sections": [section.__dict__ for section in (external.sections if external else [])],
        "local_observations": local_observations,
        "source_breakdown": source_breakdown,
        "related_model_breakdown": related_model_breakdown,
        "year_breakdown": year_breakdown,
        "body_style_breakdown": body_style_breakdown,
        "transmission_breakdown": transmission_breakdown,
        "trim_breakdown": trim_breakdown,
        "recent_listings": recent_listings,
        "recent_sales": recent_sales,
        "coverage_gaps": coverage_gaps,
        "stats": stats,
    }
    _set_cached_vehicle_profile(normalized_make, normalized_model, year, normalized_currency, payload)
    return payload


async def _distinct_values(session: AsyncSession, stmt) -> list[str]:
    result = await session.execute(stmt)
    values: list[str] = []
    for raw in result.scalars().all():
        if raw is None:
            continue
        value = raw.value if hasattr(raw, "value") else str(raw)
        if value not in values:
            values.append(value)
    return values


def _distinct_array(column):
    return func.array_remove(func.array_agg(func.distinct(column)), None)


def _array_values(raw_values: Any) -> list[str]:
    values: list[str] = []
    for raw in raw_values or []:
        if raw is None:
            continue
        value = raw.value if hasattr(raw, "value") else str(raw)
        if value not in values:
            values.append(value)
    return sorted(values)


async def _count_breakdown(session: AsyncSession, stmt) -> list[dict[str, int]]:
    result = await session.execute(stmt)
    items: list[dict[str, int]] = []
    for raw_label, raw_count in result.all():
        if raw_label is None:
            continue
        label = raw_label.value if hasattr(raw_label, "value") else str(raw_label)
        items.append({"label": label, "count": int(raw_count or 0)})
    return items


def _merge_breakdown_labels(*breakdowns: list[dict[str, int]]) -> list[str]:
    labels: list[str] = []
    for breakdown in breakdowns:
        for item in breakdown:
            label = item["label"]
            if label not in labels:
                labels.append(label)
    return labels


def _choose_primary_currency(
    listing_currency_breakdown: list[dict[str, int]],
    comp_currency_breakdown: list[dict[str, int]],
) -> str | None:
    if not listing_currency_breakdown and not comp_currency_breakdown:
        return None

    listing_counts = {item["label"]: item["count"] for item in listing_currency_breakdown}
    comp_counts = {item["label"]: item["count"] for item in comp_currency_breakdown}
    shared = [
        (
            listing_counts[label] + comp_counts[label],
            comp_counts[label],
            listing_counts[label],
            label,
        )
        for label in listing_counts
        if label in comp_counts
    ]
    if shared:
        shared.sort(reverse=True)
        return shared[0][3]

    combined = [
        (item["count"], item["label"])
        for item in listing_currency_breakdown
    ] + [
        (item["count"], item["label"])
        for item in comp_currency_breakdown
    ]
    combined.sort(reverse=True)
    return combined[0][1]


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged


async def _focus_year_context(
    session: AsyncSession,
    active_listing_filters: list[Any],
    family_comp_filters: list[Any],
    year: int,
    primary_currency: str | None,
) -> dict[str, Any]:
    listing_filters = [*active_listing_filters, Listing.year == year]
    comp_filters = [*family_comp_filters, Comp.year == year]
    if primary_currency:
        listing_filters.append(Listing.currency == primary_currency)
        comp_filters.append(Comp.currency == primary_currency)

    listing_count = int((await session.scalar(select(func.count(Listing.id)).where(*listing_filters))) or 0)
    comp_count = int(
        (
            await session.scalar(
                select(func.count(Comp.id)).where(*comp_filters, Comp.sale_price.is_not(None))
            )
        )
        or 0
    )
    trim_breakdown = await _count_breakdown(
        session,
        select(Listing.trim, func.count(Listing.id).label("count"))
        .where(*listing_filters, Listing.trim.is_not(None))
        .group_by(Listing.trim)
        .order_by(func.count(Listing.id).desc(), Listing.trim)
        .limit(3),
    )
    engine_breakdown = await _count_breakdown(
        session,
        select(Listing.engine_variant, func.count(Listing.id).label("count"))
        .where(*listing_filters, Listing.engine_variant.is_not(None))
        .group_by(Listing.engine_variant)
        .order_by(func.count(Listing.id).desc(), Listing.engine_variant)
        .limit(3),
    )
    if not engine_breakdown:
        engine_breakdown = await _count_breakdown(
            session,
            select(Comp.engine_variant, func.count(Comp.id).label("count"))
            .where(*comp_filters, Comp.engine_variant.is_not(None))
            .group_by(Comp.engine_variant)
            .order_by(func.count(Comp.id).desc(), Comp.engine_variant)
            .limit(3),
        )

    generation_values = await _distinct_values(
        session,
        select(Listing.generation)
        .where(*listing_filters, Listing.generation.is_not(None))
        .limit(3),
    )
    if not generation_values:
        generation_values = await _distinct_values(
            session,
            select(Comp.generation)
            .where(*comp_filters, Comp.generation.is_not(None))
            .limit(3),
        )

    return {
        "listing_count": listing_count,
        "comp_count": comp_count,
        "trims": [item["label"] for item in trim_breakdown],
        "engines": [item["label"] for item in engine_breakdown],
        "generations": generation_values,
    }


def _serialize_recent_listing(listing: Listing) -> dict[str, Any]:
    title = listing.title_raw or " ".join(
        str(part) for part in (listing.year, listing.make, listing.model) if part
    )
    source = listing.source.value if hasattr(listing.source, "value") else str(listing.source)
    status = (
        listing.listing_status.value
        if hasattr(listing.listing_status, "value")
        else str(listing.listing_status)
    )
    return {
        "id": listing.id,
        "title": title,
        "source": source,
        "source_url": listing.source_url,
        "year": listing.year,
        "price": _to_float(listing.asking_price) or _to_float(listing.final_price),
        "currency": listing.currency.value if hasattr(listing.currency, "value") else str(listing.currency),
        "listing_status": status,
        "location": listing.location,
    }


def _serialize_recent_comp(comp: Comp) -> dict[str, Any]:
    source = comp.source.value if hasattr(comp.source, "value") else str(comp.source)
    return {
        "id": comp.id,
        "title": _comp_title(comp),
        "source": source,
        "source_url": comp.source_url,
        "year": comp.year,
        "sale_price": _to_float(comp.sale_price),
        "currency": comp.currency.value if hasattr(comp.currency, "value") else str(comp.currency),
        "sale_date": comp.sale_date,
    }


def _comp_title(comp: Comp) -> str:
    parts = [str(part) for part in (comp.year, comp.make, comp.model) if part]
    if comp.trim:
        parts.append(comp.trim)
    elif comp.engine_variant:
        parts.append(comp.engine_variant)
    elif comp.body_style:
        body_style = comp.body_style.value if hasattr(comp.body_style, "value") else str(comp.body_style)
        parts.append(body_style)
    return " ".join(parts)


def _fallback_overview(make: str, model: str, stats: dict[str, Any]) -> str:
    years = _format_year_range(stats["year_min"], stats["year_max"])
    if years:
        return (
            f"The {make} {model} is tracked here as a collectible vehicle line, with "
            f"observed market coverage spanning {years}. This profile blends live "
            "Garage Radar market data with curated model notes as the library grows."
        )
    return (
        f"The {make} {model} is now supported in Garage Radar. Reference coverage is "
        "still being expanded, but the profile surface is ready to combine live "
        "market data with deeper make/model background."
    )


def _market_summary(
    make: str,
    model: str,
    year: int | None,
    stats: dict[str, Any],
    focus_context: dict[str, Any],
) -> str:
    parts = [
        f"Garage Radar currently has {stats['listing_count']} active listing(s) and "
        f"{stats['comp_count']} completed sale(s) for the {make} {model} family."
    ]
    if year is not None:
        parts.append(
            f"This dossier stays family-level, with {year} treated as the focus year for context."
        )
        if focus_context:
            parts.append(
                f"Tracked {year} coverage currently includes {focus_context['listing_count']} active "
                f"listing(s) and {focus_context['comp_count']} sale(s)."
            )
    currency = stats.get("primary_currency")
    if stats["avg_asking_price"] is not None:
        parts.append(
            "Observed asking prices in "
            f"{currency or 'the primary tracked currency'} average "
            f"{_format_price(stats['avg_asking_price'], currency)}, ranging from "
            f"{_format_price(stats['min_asking_price'], currency)} to "
            f"{_format_price(stats['max_asking_price'], currency)}."
        )
    if stats["avg_sale_price"] is not None:
        parts.append(
            "Observed sale prices in "
            f"{currency or 'the primary tracked currency'} average "
            f"{_format_price(stats['avg_sale_price'], currency)}, ranging from "
            f"{_format_price(stats['min_sale_price'], currency)} to "
            f"{_format_price(stats['max_sale_price'], currency)}."
        )
    if stats["comp_count"] == 0:
        parts.append(
            "Pricing confidence will improve once completed-sale comps are backfilled for this model."
        )
    return " ".join(parts)


def _fallback_highlights(stats: dict[str, Any], trims: list[str]) -> list[str]:
    highlights = [
        "Multi-source market tracking is enabled for this make/model.",
        "Profile data combines curated notes with live listing and comp coverage.",
    ]
    if trims:
        highlights.append(f"Observed trims include {', '.join(trims[:3])}.")
    if stats["comp_count"] == 0:
        highlights.append("Completed-sale coverage is still thin, so price bands may lag.")
    return highlights


def _fallback_questions(make: str, model: str) -> list[str]:
    return [
        f"What years and trims matter most for the {make} {model} market?",
        "Which factory specs or options move value the most?",
        "What documentation and maintenance history should a buyer insist on?",
    ]


def _fallback_buying_tips(body_styles: list[str], transmissions: list[str]) -> list[str]:
    tips = [
        "Verify VIN, title, and maintenance documentation before reading too much into pricing.",
        "Compare condition, originality, and recent work before assuming two examples are true comps.",
    ]
    if body_styles:
        tips.append(f"Body style matters here: watch for differences between {', '.join(body_styles)} examples.")
    if transmissions:
        tips.append(
            f"Transmission can split the market materially; tracked examples include {', '.join(transmissions)}."
        )
    return tips


def _market_signals(
    make: str,
    model: str,
    stats: dict[str, Any],
    recent_sales: list[dict[str, Any]],
    related_model_breakdown: list[dict[str, int]],
    recent_sales_scope: str | None,
) -> list[str]:
    signals: list[str] = []

    avg_ask = stats["avg_asking_price"]
    avg_sale = stats["avg_sale_price"]
    if avg_ask is not None and avg_sale is not None and avg_sale > 0:
        delta_pct = round(((avg_ask - avg_sale) / avg_sale) * 100, 1)
        if abs(delta_pct) < 3:
            signals.append("Tracked asking prices are roughly in line with recent sale prices.")
        elif delta_pct > 0:
            signals.append(
                f"Tracked asks are running about {delta_pct}% above recent sale prices for this model."
            )
        else:
            signals.append(
                f"Tracked asks are running about {abs(delta_pct)}% below recent sale prices for this model."
            )
    elif avg_ask is not None and recent_sales_scope:
        signals.append(
            f"Exact-model sale data is thin, so recent sale examples below use the broader {recent_sales_scope} family."
        )

    if recent_sales:
        latest_sale = recent_sales[0]
        latest_price = latest_sale.get("sale_price")
        latest_date = latest_sale.get("sale_date")
        if latest_price is not None and latest_date:
            signals.append(
                f"The most recent tracked sale closed at "
                f"{_format_price(latest_price, latest_sale.get('currency') or stats.get('primary_currency'))} "
                f"on {latest_date}."
            )

    if related_model_breakdown:
        labels = ", ".join(item["label"] for item in related_model_breakdown[:3])
        signals.append(f"Nearby tracked variants in the {make} {model} family include {labels}.")

    if stats["listing_count"] > 0 and stats["comp_count"] == 0 and not recent_sales_scope:
        signals.append("There are active listings here, but exact completed-sale coverage is still sparse.")

    return signals[:5]


def _local_observations(
    make: str,
    model: str,
    stats: dict[str, Any],
    source_breakdown: list[dict[str, int]],
    year_breakdown: list[dict[str, int]],
    body_style_breakdown: list[dict[str, int]],
    transmission_breakdown: list[dict[str, int]],
    trim_breakdown: list[dict[str, int]],
) -> list[str]:
    observations: list[str] = []
    currency = stats.get("primary_currency")

    years = _format_year_range(stats["year_min"], stats["year_max"])
    if years:
        observations.append(f"Garage Radar currently tracks {make} {model} coverage across {years}.")

    if stats.get("currencies"):
        observations.append(
            f"Tracked market coverage currently spans {', '.join(stats['currencies'])} currencies."
        )

    if source_breakdown:
        lead = source_breakdown[0]
        lead_label = _source_label(lead["label"])
        if len(source_breakdown) == 1:
            observations.append(f"Current market coverage is concentrated in {lead_label}.")
        else:
            observations.append(
                f"Coverage spans {len(source_breakdown)} sources, led by {lead_label}."
            )

    if year_breakdown:
        top_years = ", ".join(item["label"] for item in year_breakdown[:3])
        observations.append(f"Most frequently observed years right now are {top_years}.")

    if body_style_breakdown:
        top = body_style_breakdown[0]
        observations.append(
            f"{top['label']} is the most common tracked body style so far ({top['count']} listing(s))."
        )

    if transmission_breakdown:
        top = transmission_breakdown[0]
        observations.append(
            f"The current transmission mix leans {top['label']} ({top['count']} listing(s))."
        )

    if trim_breakdown:
        labels = ", ".join(item["label"] for item in trim_breakdown[:3])
        observations.append(f"The strongest trim coverage currently includes {labels}.")

    if stats["avg_asking_price"] is not None and stats["avg_sale_price"] is not None:
        ask = stats["avg_asking_price"]
        sale = stats["avg_sale_price"]
        if sale:
            delta_pct = round(((ask - sale) / sale) * 100, 1)
            if abs(delta_pct) < 2:
                observations.append(
                    f"Observed {currency or 'primary-currency'} asking prices are roughly in line with recent sale prices."
                )
            elif delta_pct > 0:
                observations.append(
                    f"Observed {currency or 'primary-currency'} asking prices are running about {delta_pct}% above recent sale prices."
                )
            else:
                observations.append(
                    f"Observed {currency or 'primary-currency'} asking prices are running about {abs(delta_pct)}% below recent sale prices."
                )

    return observations[:6]


def _focus_year_questions(make: str, model: str, year: int | None) -> list[str]:
    if year is None:
        return []
    return [
        f"What changed for the {year} {make} {model} versus the surrounding years?",
        f"Did {year} mark a redesign, generation shift, or meaningful engine change for the {make} {model}?",
    ]


def _focus_year_observations(
    year: int | None,
    focus_context: dict[str, Any],
    curated: dict[str, Any],
) -> list[str]:
    if year is None:
        return []

    observations = [
        f"This profile is organized at the family level; {year} is treated as a focus year rather than a separate market silo."
    ]
    if focus_context:
        if focus_context["listing_count"] == 0 and focus_context["comp_count"] == 0:
            observations.append(f"Local {year} coverage is still thin, so the notes below lean on family-level context.")
        elif focus_context["generations"]:
            observations.append(
                f"Current local {year} coverage maps to {', '.join(focus_context['generations'])}."
            )
        if focus_context["engines"]:
            observations.append(
                f"Tracked {year} engine variants include {', '.join(focus_context['engines'])}."
            )
        if focus_context["trims"]:
            observations.append(
                f"Tracked {year} trims currently include {', '.join(focus_context['trims'])}."
            )

    observations.extend(_curated_focus_notes(curated, year, focus_context.get("generations", [])))
    return observations


def _curated_focus_notes(
    curated: dict[str, Any],
    year: int,
    generations: list[str],
) -> list[str]:
    notes: list[str] = []
    year_notes = curated.get("year_notes")
    if isinstance(year_notes, dict):
        note = year_notes.get(str(year))
        if isinstance(note, str) and note.strip():
            notes.append(note.strip())

    generation_notes = curated.get("generation_notes")
    if isinstance(generation_notes, dict):
        for generation in generations:
            note = generation_notes.get(generation)
            if isinstance(note, str) and note.strip() and note.strip() not in notes:
                notes.append(note.strip())
    return notes


def _format_price(value: float | None, currency: str | None) -> str:
    if value is None:
        return "unknown price"
    return f"{currency or 'USD'} {value:,.0f}"


def _coverage_gaps(
    stats: dict[str, Any],
    source_breakdown: list[dict[str, int]],
    recent_listings: list[dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    if stats["comp_count"] == 0:
        gaps.append(
            "Completed-sale comps are still missing here, so pricing confidence is early."
        )
    if stats["listing_count"] < 3:
        gaps.append(
            "Live listing coverage is still thin, so the current market read may be incomplete."
        )
    if len(source_breakdown) < 2 and stats["listing_count"] > 0:
        gaps.append(
            "Only one source is represented so far for this model, which can skew coverage."
        )
    if stats["avg_asking_price"] is None and stats["listing_count"] > 0:
        gaps.append(
            "Structured asking prices are sparse on the tracked examples, so ask averages are limited."
        )
    if not recent_listings:
        gaps.append(
            "No recent examples have been captured yet for the dossier section."
        )
    return gaps


def _coverage_label(listing_count: int, comp_count: int) -> str:
    if listing_count == 0 and comp_count == 0:
        return "Profile scaffold only"
    if comp_count == 0:
        return "Listings only"
    if comp_count < 5:
        return "Early market coverage"
    return "Active market coverage"


def _source_label(source: str) -> str:
    return {
        "bat": "Bring a Trailer",
        "carsandbids": "Cars & Bids",
        "ebay": "eBay",
        "pcarmarket": "PCarMarket",
    }.get(source, source)


def _format_year_range(year_min: int | None, year_max: int | None) -> str | None:
    if year_min is None and year_max is None:
        return None
    if year_min == year_max:
        return str(year_min)
    if year_min is None:
        return str(year_max)
    if year_max is None:
        return str(year_min)
    return f"{year_min}-{year_max}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "unknown"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
