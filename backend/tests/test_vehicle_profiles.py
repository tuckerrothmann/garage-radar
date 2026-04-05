import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from garage_radar.vehicle_profiles import (
    _profile_family_aliases,
    _profile_model_candidates,
    _related_model_scope,
    _resolve_curated_profile,
    _resolve_external_profile,
    build_vehicle_profile,
    clear_vehicle_profile_cache,
)


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[1] / "garage_radar" / "data" / filename


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "unknown"


def test_profile_model_candidates_reduce_to_family_prefixes():
    assert _profile_model_candidates("Mustang Shelby GT350") == [
        "Mustang Shelby GT350",
        "Mustang Shelby",
        "Mustang",
    ]


def test_profile_family_aliases_support_mercedes_classes():
    assert _profile_family_aliases("Mercedes-Benz", "E320 Cabriolet") == ["E-Class"]


def test_profile_family_aliases_support_compact_family_badges():
    assert _profile_family_aliases("Volvo", "V70R") == ["V70"]
    assert _profile_family_aliases("FIAT", "500F") == ["500"]


def test_profile_model_candidates_include_family_aliases():
    assert _profile_model_candidates("E320 Cabriolet", make="Mercedes-Benz") == [
        "E320 Cabriolet",
        "E320",
        "E-Class",
    ]


def test_profile_model_candidates_include_compact_family_aliases():
    assert _profile_model_candidates("V70R", make="Volvo") == [
        "V70R",
        "V70",
    ]


def test_profile_model_candidates_include_hyphen_family_fallback():
    assert _profile_model_candidates("NSX-T") == [
        "NSX-T",
        "NSX",
    ]


def test_profile_model_candidates_include_audi_family_alias():
    assert _profile_model_candidates("A8L 4.0T", make="Audi") == [
        "A8L 4.0T",
        "A8L",
        "A8",
    ]


def test_profile_model_candidates_include_bmw_family_alias():
    assert _profile_model_candidates("530i", make="BMW") == [
        "530i",
        "5-Series",
    ]


def test_related_model_scope_prefers_meaningful_family_not_generic_model():
    assert _related_model_scope("Model S 85") == "Model S"


def test_related_model_scope_can_broaden_to_core_family():
    assert _related_model_scope("Mustang Shelby GT350") == "Mustang"


def test_related_model_scope_can_use_make_specific_aliases():
    assert _related_model_scope("V70R", make="Volvo") == "V70"


def test_resolve_curated_profile_falls_back_to_family_entry(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"ford:mustang": {"overview": "Mustang family profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Ford", "Mustang Shelby GT350")

    assert scope_model == "Mustang"
    assert curated["overview"] == "Mustang family profile"


def test_resolve_curated_profile_can_use_family_alias_entry(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"mercedes-benz:e-class": {"overview": "Mercedes E-Class profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Mercedes-Benz", "E320 Cabriolet")

    assert scope_model == "E-Class"
    assert curated["overview"] == "Mercedes E-Class profile"


def test_resolve_curated_profile_can_use_compact_family_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"volvo:v70": {"overview": "Volvo V70 family profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Volvo", "V70R")

    assert scope_model == "V70"
    assert curated["overview"] == "Volvo V70 family profile"


def test_resolve_curated_profile_can_use_cross_make_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"de-tomaso:pantera": {"overview": "Pantera family profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Ford", "Pantera")

    assert scope_model == "Pantera"
    assert curated["overview"] == "Pantera family profile"


def test_resolve_curated_profile_can_use_hyphen_base_candidate(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"acura:nsx": {"overview": "Acura NSX profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Acura", "NSX-T")

    assert scope_model == "NSX"
    assert curated["overview"] == "Acura NSX profile"


def test_resolve_curated_profile_can_use_audi_family_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"audi:a8": {"overview": "Audi A8 profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Audi", "A8L 4.0T")

    assert scope_model == "A8"
    assert curated["overview"] == "Audi A8 profile"


def test_resolve_curated_profile_can_use_ford_family_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"ford:mustang": {"overview": "Mustang family profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Ford", "Shelby GT350")

    assert scope_model == "Mustang"
    assert curated["overview"] == "Mustang family profile"


def test_resolve_curated_profile_can_use_mercedes_suffix_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"mercedes-benz:sl-class": {"overview": "Mercedes SL profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Mercedes-Benz", "450 SL")

    assert scope_model == "SL-Class"
    assert curated["overview"] == "Mercedes SL profile"


def test_resolve_curated_profile_can_use_numeric_family_reduction(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"chevrolet:silverado": {"overview": "Chevrolet Silverado profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Chevrolet", "Silverado 1500")

    assert scope_model == "Silverado"
    assert curated["overview"] == "Chevrolet Silverado profile"


def test_resolve_curated_profile_can_use_trim_family_reduction(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"ford:fiesta": {"overview": "Ford Fiesta profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Ford", "Fiesta ST")

    assert scope_model == "Fiesta"
    assert curated["overview"] == "Ford Fiesta profile"


def test_resolve_curated_profile_can_use_ford_gt_family_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"ford:mustang": {"overview": "Ford Mustang profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Ford", "GT350SR")

    assert scope_model == "Mustang"
    assert curated["overview"] == "Ford Mustang profile"


def test_resolve_curated_profile_can_use_bmw_series_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"bmw:5-series": {"overview": "BMW 5-Series profile"}},
    )

    scope_model, curated = _resolve_curated_profile("BMW", "M550i xDrive")

    assert scope_model == "5-Series"
    assert curated["overview"] == "BMW 5-Series profile"


def test_resolve_curated_profile_can_use_bmw_m4_family_alias(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"bmw:4-series": {"overview": "BMW 4-Series profile"}},
    )

    scope_model, curated = _resolve_curated_profile("BMW", "M4 CS")

    assert scope_model == "4-Series"
    assert curated["overview"] == "BMW 4-Series profile"


def test_resolve_curated_profile_can_use_ev_family_reduction(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"gmc:hummer": {"overview": "GMC Hummer profile"}},
    )

    scope_model, curated = _resolve_curated_profile("GMC", "Hummer EV")

    assert scope_model == "Hummer"
    assert curated["overview"] == "GMC Hummer profile"


def test_resolve_curated_profile_can_use_hyphen_variant_family(monkeypatch):
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._profile_catalog",
        lambda: {"cadillac:cts": {"overview": "Cadillac CTS profile"}},
    )

    scope_model, curated = _resolve_curated_profile("Cadillac", "CTS-V")

    assert scope_model == "CTS"
    assert curated["overview"] == "Cadillac CTS profile"


def test_every_curated_profile_is_represented_in_model_library():
    curated_catalog = json.loads(_data_path("vehicle_profiles.json").read_text(encoding="utf-8"))
    model_library = json.loads(_data_path("vehicle_model_library.json").read_text(encoding="utf-8"))

    library_keys = {
        f"{_slug(make)}:{_slug(model)}"
        for make, models in model_library.items()
        for model in models
    }

    missing = sorted(set(curated_catalog) - library_keys)

    assert missing == []


def test_resolve_external_profile_falls_back_to_family_entry():
    provider = AsyncMock()
    provider.fetch_profile = AsyncMock(
        side_effect=[None, None, {"title": "Ford Mustang"}]
    )

    scope_model, profile = asyncio.run(
        _resolve_external_profile(provider, "Ford", "Mustang Shelby GT350", year=2017)
    )

    assert scope_model == "Mustang"
    assert profile["title"] == "Ford Mustang"


def test_resolve_external_profile_can_use_cross_make_alias():
    provider = AsyncMock()
    provider.fetch_profile = AsyncMock(
        side_effect=[None, {"title": "De Tomaso Pantera"}]
    )

    scope_model, profile = asyncio.run(
        _resolve_external_profile(provider, "Ford", "Pantera", year=1972)
    )

    assert scope_model == "Pantera"
    assert profile["title"] == "De Tomaso Pantera"


def test_resolve_external_profile_respects_overall_budget(monkeypatch):
    provider = AsyncMock()

    async def slow_fetch(*args, **kwargs):
        await asyncio.sleep(0.05)
        return None

    provider.fetch_profile = AsyncMock(side_effect=slow_fetch)
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles.get_settings",
        lambda: type("Settings", (), {"reference_profile_budget_s": 0.01})(),
    )

    scope_model, profile = asyncio.run(
        _resolve_external_profile(provider, "Ford", "Mustang Shelby GT350", year=2017)
    )

    assert scope_model is None
    assert profile is None


def _execute_result(*, mapping=None, rows=None, scalars=None):
    result = MagicMock()
    if mapping is not None:
        result.mappings.return_value.one.return_value = mapping
    if rows is not None:
        result.all.return_value = rows
    if scalars is not None:
        result.scalars.return_value.all.return_value = scalars
    return result


def test_build_vehicle_profile_reuses_cached_market_payload(monkeypatch):
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(rows=[("USD", 2)]),
            _execute_result(rows=[("USD", 1)]),
            _execute_result(
                mapping={
                    "count": 2,
                    "year_min": 1994,
                    "year_max": 1998,
                    "latest_listing_at": "2026-03-25T12:00:00Z",
                    "body_styles": ["coupe"],
                    "transmissions": ["manual"],
                    "sources": ["bat"],
                    "trims": ["Carrera"],
                }
            ),
            _execute_result(
                mapping={
                    "avg_ask": 85000.0,
                    "min_ask": 80000.0,
                    "max_ask": 90000.0,
                }
            ),
            _execute_result(
                mapping={
                    "count": 1,
                }
            ),
            _execute_result(
                mapping={
                    "priced_count": 1,
                    "count": 1,
                    "avg_sale": 82000.0,
                    "min_sale": 82000.0,
                    "max_sale": 82000.0,
                    "latest_sale_date": "2026-03-01",
                }
            ),
            _execute_result(rows=[("coupe", 2)]),
            _execute_result(rows=[("manual", 2)]),
            _execute_result(rows=[("Carrera", 2)]),
            _execute_result(rows=[("bat", 2)]),
            _execute_result(rows=[(1995, 2)]),
            _execute_result(scalars=[]),
            _execute_result(scalars=[]),
        ]
    )
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._resolve_curated_profile",
        lambda make, model: (None, {}),
    )

    async def _fake_external_profile(*args, **kwargs):
        return None, None

    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._resolve_external_profile",
        _fake_external_profile,
    )
    async def _fake_focus_year_context(*args, **kwargs):
        return {}

    monkeypatch.setattr(
        "garage_radar.vehicle_profiles._focus_year_context",
        _fake_focus_year_context,
    )
    monkeypatch.setattr(
        "garage_radar.vehicle_profiles.get_settings",
        lambda: type("Settings", (), {"vehicle_profile_cache_ttl_s": 60.0})(),
    )

    clear_vehicle_profile_cache()
    try:
        first = asyncio.run(build_vehicle_profile(session, "Porsche", "911", year=1995))
        first_execute_count = session.execute.await_count

        second = asyncio.run(build_vehicle_profile(session, "Porsche", "911", year=1995))

        assert first["stats"]["listing_count"] == 2
        assert second["stats"]["listing_count"] == 2
        assert session.execute.await_count == first_execute_count
    finally:
        clear_vehicle_profile_cache()
