"""
Tests for normalization layer.
Run: pytest backend/tests/test_normalize.py -v
"""
import pytest

from datetime import datetime, timezone

from garage_radar.normalize.generation import year_to_generation
from garage_radar.normalize.pipeline import _detect_drivetrain, normalize
from garage_radar.normalize.nlp_flags import (
    extract_all_flags,
    extract_matching_numbers,
    extract_modification_flags,
    extract_original_paint,
    extract_service_history,
)
from garage_radar.normalize.color import normalize_color


# ── Generation tests ──────────────────────────────────────────────────────────

class TestYearToGeneration:
    def test_g1_classic(self):
        assert year_to_generation(1969, make="Porsche", model="911") == "G1"

    def test_g2_impact_bumper(self):
        assert year_to_generation(1976, make="Porsche", model="911") == "G2"

    def test_g3_sc(self):
        assert year_to_generation(1981, make="Porsche", model="911") == "G3"

    def test_g4_carrera_32(self):
        assert year_to_generation(1987, make="Porsche", model="911") == "G4"

    def test_g5_964(self):
        assert year_to_generation(1991, make="Porsche", model="911") == "G5"

    def test_g6_993(self):
        assert year_to_generation(1997, make="Porsche", model="911") == "G6"

    def test_out_of_range_high(self):
        assert year_to_generation(1999, make="Porsche", model="911") is None

    def test_out_of_range_low(self):
        assert year_to_generation(1964, make="Porsche", model="911") is None

    def test_unknown_make_returns_none(self):
        assert year_to_generation(1969, make="DeSoto", model="Firedome") is None

    def test_no_make_returns_none(self):
        assert year_to_generation(1969) is None

    def test_ambiguous_1989_g5_hint(self):
        desc = "1989 Porsche 964 Carrera 2, just serviced"
        assert year_to_generation(1989, desc, make="Porsche", model="911") == "G5"

    def test_ambiguous_1989_g4_hint(self):
        desc = "1989 Porsche 911 Carrera 3.2, Speedster body"
        assert year_to_generation(1989, desc, make="Porsche", model="911") == "G4"

    def test_ambiguous_1994_g6_hint(self):
        desc = "1994 993 Carrera, last air-cooled"
        assert year_to_generation(1994, desc, make="Porsche", model="911") == "G6"

    def test_corvette_c1(self):
        assert year_to_generation(1957, make="Chevrolet", model="Corvette") == "C1"

    def test_corvette_c2(self):
        assert year_to_generation(1965, make="Chevrolet", model="Corvette") == "C2"

    def test_mustang_gen1(self):
        assert year_to_generation(1968, make="Ford", model="Mustang") == "Gen1"

    def test_mustang_gen3(self):
        assert year_to_generation(1985, make="Ford", model="Mustang") == "Gen3"


# ── Color normalization tests ─────────────────────────────────────────────────

class TestColorNormalization:
    def test_exact_alias_guards_red(self):
        color, conf = normalize_color("Guards Red")
        assert color == "red"
        assert conf == 1.0

    def test_case_insensitive(self):
        color, conf = normalize_color("grand prix white")
        assert color == "white"

    def test_canonical_value_passthrough(self):
        color, conf = normalize_color("black")
        assert color == "black"
        assert conf == 1.0

    def test_none_input(self):
        color, conf = normalize_color(None)
        assert color is None
        assert conf == 0.0

    def test_empty_string(self):
        color, conf = normalize_color("  ")
        assert color is None

    def test_unknown_color_fallback(self):
        color, conf = normalize_color("some completely unknown color xyz123")
        assert color == "other"
        assert conf == 0.0


# ── NLP flags tests ───────────────────────────────────────────────────────────

class TestNlpFlags:

    # matching_numbers
    def test_matching_numbers_true(self):
        desc = "The engine is numbers matching and the gearbox is original."
        assert extract_matching_numbers(desc) is True

    def test_matching_numbers_negated(self):
        desc = "This car has had an engine swap and is non-matching."
        assert extract_matching_numbers(desc) is False

    def test_matching_numbers_unknown(self):
        desc = "Nice 993 Carrera for sale."
        assert extract_matching_numbers(desc) is None

    # original_paint
    def test_original_paint_true(self):
        desc = "Confirmed original paint with paint meter readings attached."
        assert extract_original_paint(desc) is True

    def test_original_paint_negated(self):
        desc = "The car was repainted at some point in its history."
        assert extract_original_paint(desc) is False

    def test_original_paint_unknown(self):
        assert extract_original_paint("") is None

    # service_history
    def test_service_history_true(self):
        desc = "Complete service records present from new through an independent Porsche specialist."
        assert extract_service_history(desc) is True

    def test_service_history_negated(self):
        desc = "No service records on hand."
        assert extract_service_history(desc) is False

    # modification_flags
    def test_mods_widebody(self):
        flags = extract_modification_flags("This G5 has a widebody kit installed.")
        assert "widebody" in flags

    def test_mods_aftermarket_wheels(self):
        flags = extract_modification_flags("Running on aftermarket wheels, otherwise stock.")
        assert "aftermarket_wheels" in flags

    def test_mods_none(self):
        desc = "Unmodified original 993 Carrera with factory specification throughout."
        flags = extract_modification_flags(desc)
        assert flags == []

    def test_extract_all_flags_combined(self):
        desc = (
            "1991 964 Carrera 2. Numbers matching engine. Original paint confirmed by paint meter. "
            "Full service records available. Sport exhaust installed."
        )
        result = extract_all_flags(desc)
        assert result["matching_numbers"] is True
        assert result["original_paint"] is True
        assert result["service_history"] is True
        assert "aftermarket_exhaust" in result["modification_flags"]


# ── Drivetrain detection tests ────────────────────────────────────────────────

class TestDetectDrivetrain:
    def test_explicit_awd_raw(self):
        assert _detect_drivetrain("awd", "") == "awd"

    def test_explicit_awd_raw_case_insensitive(self):
        assert _detect_drivetrain("AWD", "") == "awd"

    def test_carrera_4_in_title(self):
        assert _detect_drivetrain("", "1992 Porsche 964 Carrera 4, blue, 55k miles") == "awd"

    def test_c4s_in_title(self):
        assert _detect_drivetrain("", "1997 Porsche 993 C4S Coupe") == "awd"

    def test_c4_in_carrera_4(self):
        assert _detect_drivetrain("", "1996 Porsche 993 Carrera 4 Cabriolet") == "awd"

    def test_targa_4(self):
        assert _detect_drivetrain("", "1992 964 Targa 4") == "awd"

    def test_all_wheel_drive_spelled_out(self):
        assert _detect_drivetrain("", "all wheel drive, manual, 60k miles") == "awd"

    def test_awd_abbreviation_in_text(self):
        assert _detect_drivetrain("", "confirmed AWD, well documented") == "awd"

    def test_carrera_2_is_rwd(self):
        # "Carrera 2" contains no AWD keywords
        assert _detect_drivetrain("", "1992 964 Carrera 2 Coupe") == "rwd"

    def test_g3_sc_is_rwd(self):
        assert _detect_drivetrain("", "1981 Porsche 911 SC Targa") == "rwd"

    def test_g4_carrera_32_is_rwd(self):
        assert _detect_drivetrain("", "1987 Porsche 911 Carrera 3.2 Coupe") == "rwd"

    def test_empty_text_defaults_rwd(self):
        assert _detect_drivetrain("", "") == "rwd"

    def test_rwd_explicit_raw_is_rwd(self):
        assert _detect_drivetrain("rwd", "") == "rwd"

    def test_964_turbo_is_rwd(self):
        # 964 Turbo 3.3/3.6 is rear-wheel drive (unlike 993 Turbo which is AWD)
        assert _detect_drivetrain("", "1993 Porsche 964 Turbo 3.6") == "rwd"


# ── Multi-make pipeline tests ─────────────────────────────────────────────────

class TestMultiMakePipeline:
    """End-to-end normalize() tests for non-Porsche vehicles."""

    def _parsed(self, **kwargs):
        from garage_radar.sources.base import ParsedListing
        defaults = dict(
            source="bat",
            source_url="https://bringatrailer.com/listing/test/",
            scrape_ts=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        defaults.update(kwargs)
        return ParsedListing(**defaults)

    def test_corvette_c2_make_model_extracted(self):
        p = self._parsed(
            title_raw="1965 Chevrolet Corvette Sting Ray Coupe",
            make_raw="Chevrolet",
            model_raw="Corvette",
            year=1965,
            body_style_raw="coupe",
            transmission_raw="4-speed manual",
        )
        result = normalize(p)
        assert result["make"] == "Chevrolet"
        assert result["model"] == "Corvette"
        assert result["year"] == 1965
        assert result["transmission"] == "manual"

    def test_corvette_c2_generation_resolved(self):
        p = self._parsed(
            title_raw="1965 Chevrolet Corvette Sting Ray Coupe",
            make_raw="Chevrolet",
            model_raw="Corvette",
            year=1965,
        )
        result = normalize(p)
        assert result["generation"] == "C2"

    def test_mustang_gen1_generation_resolved(self):
        p = self._parsed(
            title_raw="1968 Ford Mustang Fastback",
            make_raw="Ford",
            model_raw="Mustang",
            year=1968,
        )
        result = normalize(p)
        assert result["generation"] == "Gen1"

    def test_mustang_fastback_body_style(self):
        p = self._parsed(
            title_raw="1968 Ford Mustang Fastback",
            make_raw="Ford",
            model_raw="Mustang",
            year=1968,
            body_style_raw="fastback",
        )
        result = normalize(p)
        assert result["body_style"] == "fastback"

    def test_make_model_from_title_fallback(self):
        """When make_raw/model_raw are absent, pipeline extracts from title.
        Works reliably when the model starts with a digit (e.g. 911, 356).
        """
        p = self._parsed(
            title_raw="1969 Porsche 911 T Coupe",
            year=1969,
        )
        result = normalize(p)
        assert result["make"] == "Porsche"
        assert result["model"] == "911"

    def test_awd_corvette_z06_rwd(self):
        p = self._parsed(
            title_raw="1970 Chevrolet Corvette Z06 Coupe",
            make_raw="Chevrolet",
            model_raw="Corvette",
            year=1970,
        )
        result = normalize(p)
        assert result["drivetrain"] == "rwd"

    def test_unknown_make_generation_is_none(self):
        p = self._parsed(
            title_raw="1962 DeSoto Firedome Coupe",
            make_raw="DeSoto",
            model_raw="Firedome",
            year=1962,
        )
        result = normalize(p)
        assert result["generation"] is None
