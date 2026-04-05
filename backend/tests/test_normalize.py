"""
Tests for normalization layer.
Run: pytest backend/tests/test_normalize.py -v
"""
from datetime import UTC, datetime

from garage_radar.normalize.body_style import normalize_body_style
from garage_radar.normalize.color import normalize_color
from garage_radar.normalize.generation import year_to_generation
from garage_radar.normalize.nlp_flags import (
    extract_all_flags,
    extract_matching_numbers,
    extract_modification_flags,
    extract_original_paint,
    extract_service_history,
)
from garage_radar.normalize.pipeline import normalize
from garage_radar.normalize.transmission import normalize_transmission
from garage_radar.normalize.vehicle_identity import extract_vehicle_identity
from garage_radar.sources.base import ParsedComp, ParsedListing

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


class TestNormalizePipeline:
    def test_snapshot_path_is_preserved(self):
        parsed = ParsedListing(
            source="bat",
            source_url="https://bringatrailer.com/listing/example/",
            scrape_ts=datetime.now(UTC),
            year=1995,
            title_raw="1995 Porsche 911 Carrera Coupe",
            snapshot_path="data/snapshots/bat/example.html",
        )

        normalized = normalize(parsed)

        assert normalized["snapshot_path"] == "data/snapshots/bat/example.html"

    def test_auction_state_fields_are_preserved(self):
        parsed = ParsedListing(
            source="bat",
            source_url="https://bringatrailer.com/listing/example/",
            scrape_ts=datetime.now(UTC),
            year=1995,
            title_raw="1995 Porsche 911 Carrera Coupe",
            current_bid=82000.0,
            asking_price=82000.0,
            auction_end_at="2026-04-02T18:30:00Z",
            time_remaining_text="3 days",
        )

        normalized = normalize(parsed)

        assert normalized["current_bid"] == 82000.0
        assert normalized["auction_end_at"].isoformat() == "2026-04-02T18:30:00+00:00"
        assert normalized["time_remaining_text"] == "3 days"

    def test_make_and_model_are_inferred_from_title(self):
        parsed = ParsedListing(
            source="bat",
            source_url="https://bringatrailer.com/listing/example/",
            scrape_ts=datetime.now(UTC),
            year=1995,
            title_raw="1995 Porsche 911 Carrera Coupe",
        )

        normalized = normalize(parsed)

        assert normalized["make"] == "Porsche"
        assert normalized["model"] == "911 Carrera"
        assert normalized["generation"] == "G6"

    def test_non_porsche_year_does_not_get_porsche_generation(self):
        parsed = ParsedListing(
            source="manual",
            source_url="https://example.com/listing/bronco",
            scrape_ts=datetime.now(UTC),
            year=1972,
            title_raw="1972 Ford Bronco Wagon",
        )

        normalized = normalize(parsed)

        assert normalized["make"] == "Ford"
        assert normalized["model"] == "Bronco"
        assert normalized["generation"] is None

    def test_comp_normalize_maps_final_price_to_sale_price(self):
        parsed = ParsedComp(
            source="bat",
            source_url="https://bringatrailer.com/listing/example/",
            scrape_ts=datetime.now(UTC),
            year=1995,
            title_raw="1995 Porsche 911 Carrera Coupe",
            final_price=91000.0,
            sale_date="2026-03-20",
            is_completed=True,
        )

        normalized = normalize(parsed)

        assert normalized["sale_price"] == 91000.0
        assert normalized["sale_date"].isoformat() == "2026-03-20"


class TestGenericSpecNormalization:
    def test_body_style_supports_sedan(self):
        assert normalize_body_style("4-Door Sedan") == "sedan"

    def test_body_style_supports_suv(self):
        assert normalize_body_style("Sport Utility Vehicle") == "suv"

    def test_body_style_supports_wagon_aliases(self):
        assert normalize_body_style("Shooting Brake") == "wagon"

    def test_transmission_maps_automatic_variants(self):
        assert normalize_transmission("6-Speed Automatic") == "auto"
        assert normalize_transmission("PDK Dual-Clutch") == "auto"

    def test_transmission_maps_manual_variants(self):
        assert normalize_transmission("5-Speed Manual") == "manual"
        assert normalize_transmission("6-Speed Manual") == "manual-6sp"

    def test_transmission_leaves_ambiguous_speed_unknown(self):
        assert normalize_transmission("6-Speed") is None


class TestVehicleIdentity:
    def test_extracts_multiword_make(self):
        make, model = extract_vehicle_identity("2020 Land Rover Defender 110 First Edition")
        assert make == "Land Rover"
        assert model == "Defender 110"

    def test_extracts_mercedes_alias(self):
        make, model = extract_vehicle_identity("2002 Mercedes-Benz SL500 Silver Arrow")
        assert make == "Mercedes-Benz"
        assert model == "SL500"

    def test_parser_supplied_values_win(self):
        make, model = extract_vehicle_identity(
            "1967 Alfa Romeo Giulia Sprint GTA",
            make_raw="Alfa Romeo",
            model_raw="Giulia",
        )
        assert make == "Alfa Romeo"
        assert model == "Giulia"

    def test_extracts_land_cruiser_as_compound_model(self):
        make, model = extract_vehicle_identity("1976 Toyota Land Cruiser FJ40")
        assert make == "Toyota"
        assert model == "Land Cruiser"

    def test_extracts_range_rover_as_compound_model(self):
        make, model = extract_vehicle_identity("2011 Land Rover Range Rover Supercharged")
        assert make == "Land Rover"
        assert model == "Range Rover Supercharged"

    def test_extracts_grand_wagoneer_as_compound_model(self):
        make, model = extract_vehicle_identity("1987 Jeep Grand Wagoneer")
        assert make == "Jeep"
        assert model == "Grand Wagoneer"

    def test_extracts_v8_vantage_as_compound_model(self):
        make, model = extract_vehicle_identity("2009 Aston Martin V8 Vantage Roadster")
        assert make == "Aston Martin"
        assert model == "V8 Vantage"

    def test_pickup_can_still_be_a_model(self):
        make, model = extract_vehicle_identity("1979 Toyota Pickup 4-Speed")
        assert make == "Toyota"
        assert model == "Pickup"

    def test_model_library_upgrades_focus_rs_over_plain_focus(self):
        make, model = extract_vehicle_identity(
            "2016 Ford Focus RS",
            make_raw="Ford",
            model_raw="Focus",
        )
        assert make == "Ford"
        assert model == "Focus RS"

    def test_model_library_preserves_cl65_amg(self):
        make, model = extract_vehicle_identity("2005 Mercedes-Benz CL65 AMG")
        assert make == "Mercedes-Benz"
        assert model == "CL65 AMG"

    def test_model_library_extracts_shelby_f150(self):
        make, model = extract_vehicle_identity("2020 Ford Shelby F-150 SuperCrew 4x4")
        assert make == "Ford"
        assert model == "Shelby F-150"

    def test_model_library_extracts_ford_pantera(self):
        make, model = extract_vehicle_identity("1972 Ford Pantera")
        assert make == "Ford"
        assert model == "Pantera"

    def test_model_library_extracts_de_tomaso_pantera(self):
        make, model = extract_vehicle_identity("1973 De Tomaso Pantera GTS")
        assert make == "De Tomaso"
        assert model == "Pantera"

    def test_title_model_wins_when_only_formatting_differs(self):
        make, model = extract_vehicle_identity(
            "2016 Ford Focus RS",
            make_raw="Ford",
            model_raw="Focus Rs",
        )
        assert make == "Ford"
        assert model == "Focus RS"

    def test_title_model_wins_when_compact_raw_differs_only_by_spacing(self):
        make, model = extract_vehicle_identity(
            "2013 Lexus LS460 AWD",
            make_raw="Lexus",
            model_raw="LS460",
        )
        assert make == "Lexus"
        assert model == "LS 460"

    def test_model_library_extracts_fiesta_st(self):
        make, model = extract_vehicle_identity("2014 Ford Fiesta ST")
        assert make == "Ford"
        assert model == "Fiesta ST"

    def test_model_library_extracts_lexus_is_300(self):
        make, model = extract_vehicle_identity("2001 Lexus IS 300")
        assert make == "Lexus"
        assert model == "IS 300"

    def test_model_library_extracts_lexus_lc_500h(self):
        make, model = extract_vehicle_identity("2023 Lexus LC 500h")
        assert make == "Lexus"
        assert model == "LC 500h"

    def test_model_library_extracts_porsche_cayenne_variant(self):
        make, model = extract_vehicle_identity("2009 Porsche Cayenne GTS")
        assert make == "Porsche"
        assert model == "Cayenne GTS"

    def test_model_library_extracts_porsche_macan_variant(self):
        make, model = extract_vehicle_identity("2017 Porsche Macan Turbo")
        assert make == "Porsche"
        assert model == "Macan Turbo"

    def test_model_library_extracts_mustang_shelby_variant(self):
        make, model = extract_vehicle_identity("2017 Ford Mustang Shelby GT350")
        assert make == "Ford"
        assert model == "Mustang Shelby GT350"

    def test_model_library_extracts_mustang_gt(self):
        make, model = extract_vehicle_identity(
            "7k-Mile 1989 Ford Mustang GT 5.0 Hatchback 5-Speed Conversion"
        )
        assert make == "Ford"
        assert model == "Mustang GT"

    def test_specialized_title_variant_can_override_broad_raw_model(self):
        make, model = extract_vehicle_identity(
            "Fuel-Injected, 408-Powered 1965 Ford Mustang Fastback GT350SR 5-Speed",
            make_raw="Ford",
            model_raw="Mustang",
        )
        assert make == "Ford"
        assert model == "GT350SR"

    def test_model_library_extracts_trim_even_when_not_first_model_token(self):
        make, model = extract_vehicle_identity(
            "Fuel-Injected, 408-Powered 1965 Ford Mustang Fastback GT350SR 5-Speed"
        )
        assert make == "Ford"
        assert model == "GT350SR"

    def test_model_library_extracts_integra_gsr(self):
        make, model = extract_vehicle_identity("Modified 1998 Acura Integra GS-R Hatchback 5-Speed")
        assert make == "Acura"
        assert model == "Integra GS-R"

    def test_model_library_extracts_integra_ls(self):
        make, model = extract_vehicle_identity("1993 Acura Integra LS Coupe")
        assert make == "Acura"
        assert model == "Integra LS"

    def test_model_library_extracts_bentley_continental_flying_spur(self):
        make, model = extract_vehicle_identity("2008 Bentley Continental Flying Spur")
        assert make == "Bentley"
        assert model == "Continental Flying Spur"

    def test_model_library_extracts_audi_a6_quattro(self):
        make, model = extract_vehicle_identity("2019 Audi A6 Quattro Prestige")
        assert make == "Audi"
        assert model == "A6 Quattro"

    def test_model_library_extracts_audi_tt_32_quattro(self):
        make, model = extract_vehicle_identity("2006 Audi TT Coupe 3.2 Quattro")
        assert make == "Audi"
        assert model == "TT 3.2 Quattro"

    def test_model_library_extracts_wrangler_unlimited_rubicon(self):
        make, model = extract_vehicle_identity("2018 Jeep Wrangler Unlimited Rubicon 4x4")
        assert make == "Jeep"
        assert model == "Wrangler Unlimited Rubicon"

    def test_model_library_extracts_bmw_x5_xdrive48i(self):
        make, model = extract_vehicle_identity("2009 BMW X5 xDrive48i")
        assert make == "BMW"
        assert model == "X5 xDrive48i"

    def test_model_library_extracts_model_t(self):
        make, model = extract_vehicle_identity("1923 Ford Model T Coupe")
        assert make == "Ford"
        assert model == "Model T"

    def test_model_library_extracts_dodge_model_30(self):
        make, model = extract_vehicle_identity("1920 Dodge Brothers Model 30 Touring Project")
        assert make == "Dodge"
        assert model == "Model 30"

    def test_model_library_extracts_honda_acty_street(self):
        make, model = extract_vehicle_identity("1990 Honda Acty Street G 4WD")
        assert make == "Honda"
        assert model == "Acty Street"

    def test_model_library_extracts_lincoln_town_car(self):
        make, model = extract_vehicle_identity("15k-Mile 2006 Lincoln Town Car Signature Limited")
        assert make == "Lincoln"
        assert model == "Town Car"

    def test_model_library_extracts_plymouth_road_runner(self):
        make, model = extract_vehicle_identity("1969 Plymouth Road Runner Coupe Hemi")
        assert make == "Plymouth"
        assert model == "Road Runner"

    def test_model_library_extracts_porsche_911_turbo(self):
        make, model = extract_vehicle_identity("1997 Porsche 911 Turbo")
        assert make == "Porsche"
        assert model == "911 Turbo"

    def test_model_library_extracts_porsche_911sc(self):
        make, model = extract_vehicle_identity("1978 Porsche 911SC Coupe")
        assert make == "Porsche"
        assert model == "911SC"

    def test_model_library_extracts_porsche_911t(self):
        make, model = extract_vehicle_identity("1972 Porsche 911T Targa 5-Speed")
        assert make == "Porsche"
        assert model == "911T"

    def test_model_library_extracts_porsche_911_carrera_4(self):
        make, model = extract_vehicle_identity("1992 Porsche 911 Carrera 4 Coupe 5-Speed")
        assert make == "Porsche"
        assert model == "911 Carrera 4"

    def test_model_library_extracts_porsche_911_targa_4s(self):
        make, model = extract_vehicle_identity(
            "Slate Gray 2021 Porsche 911 Targa 4S Heritage Design Edition 7-Speed"
        )
        assert make == "Porsche"
        assert model == "911 Targa 4S"

    def test_model_library_extracts_land_rover_defender_110(self):
        make, model = extract_vehicle_identity("1999 Land Rover Defender 110")
        assert make == "Land Rover"
        assert model == "Defender 110"

    def test_model_library_extracts_range_rover_supercharged(self):
        make, model = extract_vehicle_identity("2011 Land Rover Range Rover Supercharged")
        assert make == "Land Rover"
        assert model == "Range Rover Supercharged"

    def test_model_library_extracts_wrangler_unlimited(self):
        make, model = extract_vehicle_identity("41k-Mile Modified 2005 Jeep Wrangler Unlimited 6-Speed")
        assert make == "Jeep"
        assert model == "Wrangler Unlimited"

    def test_model_library_extracts_bmw_m5_competition(self):
        make, model = extract_vehicle_identity("2019 BMW M5 Competition")
        assert make == "BMW"
        assert model == "M5 Competition"

    def test_model_library_extracts_bmw_m550i_xdrive(self):
        make, model = extract_vehicle_identity("2020 BMW M550i xDrive")
        assert make == "BMW"
        assert model == "M550i xDrive"

    def test_model_library_extracts_lexus_gs_350(self):
        make, model = extract_vehicle_identity("2017 Lexus GS350 AWD")
        assert make == "Lexus"
        assert model == "GS 350"

    def test_model_library_extracts_lexus_lx_570(self):
        make, model = extract_vehicle_identity("2013 Lexus LX570")
        assert make == "Lexus"
        assert model == "LX 570"

    def test_model_library_extracts_lexus_ls430(self):
        make, model = extract_vehicle_identity("30k-Mile 2006 Lexus LS430")
        assert make == "Lexus"
        assert model == "LS430"

    def test_model_library_extracts_lexus_sc300(self):
        make, model = extract_vehicle_identity("1993 Lexus SC300")
        assert make == "Lexus"
        assert model == "SC300"

    def test_model_library_extracts_lexus_sc_430(self):
        make, model = extract_vehicle_identity("2005 Lexus SC430")
        assert make == "Lexus"
        assert model == "SC 430"

    def test_model_library_extracts_fiat_500f(self):
        make, model = extract_vehicle_identity("1968 Fiat 500F")
        assert make == "Fiat"
        assert model == "500F"

    def test_model_library_extracts_mercedes_cl55_amg(self):
        make, model = extract_vehicle_identity("2003 Mercedes-Benz CL55 AMG")
        assert make == "Mercedes-Benz"
        assert model == "CL55 AMG"

    def test_model_library_extracts_mercedes_e320_cdi(self):
        make, model = extract_vehicle_identity("2006 Mercedes-Benz E320 CDI")
        assert make == "Mercedes-Benz"
        assert model == "E320 CDI"

    def test_model_library_extracts_mercedes_e320_cabriolet(self):
        make, model = extract_vehicle_identity("31k-Mile 1995 Mercedes-Benz E320 Cabriolet")
        assert make == "Mercedes-Benz"
        assert model == "E320 Cabriolet"

    def test_model_library_extracts_mercedes_450_sl(self):
        make, model = extract_vehicle_identity("1979 Mercedes-Benz 450SL")
        assert make == "Mercedes-Benz"
        assert model == "450 SL"

    def test_model_library_extracts_mitsubishi_montero_ls(self):
        make, model = extract_vehicle_identity("1995 Mitsubishi Montero LS")
        assert make == "Mitsubishi"
        assert model == "Montero LS"

    def test_model_library_extracts_nissan_300zx_twin_turbo(self):
        make, model = extract_vehicle_identity("1994 Nissan 300ZX Twin Turbo 5-Speed")
        assert make == "Nissan"
        assert model == "300ZX Twin Turbo"

    def test_model_library_extracts_aston_martin_rapide_s(self):
        make, model = extract_vehicle_identity("2016 Aston Martin Rapide S")
        assert make == "Aston Martin"
        assert model == "Rapide S"

    def test_model_library_extracts_tesla_model_3(self):
        make, model = extract_vehicle_identity("2019 Tesla Model 3 Performance")
        assert make == "Tesla"
        assert model == "Model 3"

    def test_model_library_extracts_tesla_model_s_85(self):
        make, model = extract_vehicle_identity("2,300-Mile 2014 Tesla Model S 85")
        assert make == "Tesla"
        assert model == "Model S 85"

    def test_model_library_extracts_toyota_4runner(self):
        make, model = extract_vehicle_identity("2011 Toyota 4Runner Limited 4x4")
        assert make == "Toyota"
        assert model == "4Runner"

    def test_model_library_extracts_toyota_supra(self):
        make, model = extract_vehicle_identity("1990 Toyota Supra Turbo")
        assert make == "Toyota"
        assert model == "Supra"

    def test_model_library_extracts_subaru_forester_20xt(self):
        make, model = extract_vehicle_identity("2018 Subaru Forester 2.0XT Touring")
        assert make == "Subaru"
        assert model == "Forester 2.0XT"

    def test_model_library_extracts_volkswagen_touareg_tdi(self):
        make, model = extract_vehicle_identity("2011 Volkswagen Touareg TDI Executive")
        assert make == "Volkswagen"
        assert model == "Touareg TDI"

    def test_model_library_extracts_volkswagen_westfalia(self):
        make, model = extract_vehicle_identity("1974 Volkswagen Type 2 Westfalia 4-Speed")
        assert make == "Volkswagen"
        assert model == "Westfalia"

    def test_model_library_extracts_volvo_v60_recharge_t8(self):
        make, model = extract_vehicle_identity("2021 Volvo V60 Recharge T8 Polestar Engineered")
        assert make == "Volvo"
        assert model == "V60 Recharge T8"

    def test_model_library_extracts_volvo_xc70(self):
        make, model = extract_vehicle_identity("2009 Volvo XC70 3.2 AWD")
        assert make == "Volvo"
        assert model == "XC70"

    def test_title_can_override_generic_raw_make_and_model(self):
        make, model = extract_vehicle_identity(
            "1985 Porsche 944",
            make_raw="Pcarmarket",
            model_raw="Auctions",
        )
        assert make == "Porsche"
        assert model == "944"
