"""
Tests for normalization layer.
Run: pytest backend/tests/test_normalize.py -v
"""
import pytest

from garage_radar.normalize.generation import year_to_generation
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
        assert year_to_generation(1969) == "G1"

    def test_g2_impact_bumper(self):
        assert year_to_generation(1976) == "G2"

    def test_g3_sc(self):
        assert year_to_generation(1981) == "G3"

    def test_g4_carrera_32(self):
        assert year_to_generation(1987) == "G4"

    def test_g5_964(self):
        assert year_to_generation(1991) == "G5"

    def test_g6_993(self):
        assert year_to_generation(1997) == "G6"

    def test_out_of_range_high(self):
        assert year_to_generation(1999) is None

    def test_out_of_range_low(self):
        assert year_to_generation(1964) is None

    def test_ambiguous_1989_g5_hint(self):
        desc = "1989 Porsche 964 Carrera 2, just serviced"
        assert year_to_generation(1989, desc) == "G5"

    def test_ambiguous_1989_g4_hint(self):
        desc = "1989 Porsche 911 Carrera 3.2, Speedster body"
        assert year_to_generation(1989, desc) == "G4"

    def test_ambiguous_1994_g6_hint(self):
        desc = "1994 993 Carrera, last air-cooled"
        assert year_to_generation(1994, desc) == "G6"


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

    def test_extract_all_flags(self):
        desc = (
            "1991 964 Carrera 2. Numbers matching engine. Original paint confirmed by paint meter. "
            "Full service records available. Sport exhaust installed."
        )
        result = extract_all_flags(desc)
        assert result["matching_numbers"] is True
        assert result["original_paint"] is True
        assert result["service_history"] is True
        assert "aftermarket_exhaust" in result["modification_flags"]
