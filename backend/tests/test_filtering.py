from fastapi import HTTPException

from garage_radar.api.filtering import parse_int_values, split_multi_values


class TestSplitMultiValues:
    def test_repeated_and_comma_separated_values_are_flattened(self):
        assert split_multi_values(["Ford, BMW", "Porsche", "bmw"]) == ["Ford", "BMW", "Porsche"]

    def test_empty_values_are_ignored(self):
        assert split_multi_values(["", "  ", "Ford,,BMW"]) == ["Ford", "BMW"]


class TestParseIntValues:
    def test_valid_ints_are_parsed(self):
        assert parse_int_values(["1972, 1974", "1995"], "year") == [1972, 1974, 1995]

    def test_invalid_int_raises_http_400(self):
        try:
            parse_int_values(["1972, nope"], "year")
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Invalid year 'nope'" in exc.detail
        else:
            raise AssertionError("Expected HTTPException for invalid year input")
