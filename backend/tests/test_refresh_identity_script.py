from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "refresh_identity.py"
_SPEC = spec_from_file_location("refresh_identity_script", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_title_for_row_prefers_title_raw():
    class Row:
        title_raw = "2017 Ford Mustang Shelby GT350"
        year = 2017
        make = "Ford"
        model = "Mustang"

    assert _MODULE._title_for_row(Row()) == "2017 Ford Mustang Shelby GT350"


def test_title_for_row_builds_from_trim_when_title_missing():
    class Row:
        title_raw = None
        year = 2019
        make = "BMW"
        model = "M5"
        trim = "Competition"
        engine_variant = None

    assert _MODULE._title_for_row(Row()) == "2019 BMW M5 Competition"
