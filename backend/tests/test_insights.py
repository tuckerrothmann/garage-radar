"""
Insight engine unit tests — no live database required.

The comp cluster SQL queries and upsert logic require a live Postgres DB with
percentile_cont support, so those are integration tests only. What we can fully
unit-test is:

  - _is_new_listing()      — datetime window logic
  - _detect_price_drop()   — price history parsing and threshold math
  - _underpriced_severity() — severity bucketing
  - cluster_key_for()      — key format
  - _to_float()            — Decimal / None coercion

Run: pytest backend/tests/test_insights.py -v
"""
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from garage_radar.insights.alert_engine import (
    _detect_price_drop,
    _is_new_listing,
    _underpriced_severity,
)
from garage_radar.insights.comp_clusters import _to_float, cluster_key_for
from garage_radar.db.models import AlertSeverityEnum


# ── _to_float ─────────────────────────────────────────────────────────────────

class TestToFloat:
    def test_none_returns_none(self):
        assert _to_float(None) is None

    def test_decimal_converts(self):
        assert _to_float(Decimal("97500.50")) == pytest.approx(97500.50)

    def test_int_converts(self):
        assert _to_float(42) == 42.0

    def test_float_passthrough(self):
        assert _to_float(3.14) == pytest.approx(3.14)


# ── cluster_key_for ───────────────────────────────────────────────────────────

class TestClusterKey:
    def test_basic_format(self):
        assert cluster_key_for("G6", "coupe", "manual") == "G6:coupe:manual"

    def test_cabriolet_auto(self):
        assert cluster_key_for("G5", "cabriolet", "auto") == "G5:cabriolet:auto"

    def test_six_speed(self):
        assert cluster_key_for("G6", "coupe", "manual-6sp") == "G6:coupe:manual-6sp"


# ── _is_new_listing ───────────────────────────────────────────────────────────

class TestIsNewListing:
    def test_recent_listing_is_new(self):
        created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        assert _is_new_listing({"created_at": created_at}) is True

    def test_old_listing_is_not_new(self):
        created_at = datetime.now(timezone.utc) - timedelta(hours=30)
        assert _is_new_listing({"created_at": created_at}) is False

    def test_exactly_at_boundary_is_not_new(self):
        # 24 hours ago — just at/past the cutoff
        created_at = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        assert _is_new_listing({"created_at": created_at}) is False

    def test_none_created_at_is_not_new(self):
        assert _is_new_listing({"created_at": None}) is False

    def test_missing_key_is_not_new(self):
        assert _is_new_listing({}) is False

    def test_naive_datetime_handled(self):
        # Should treat naive as UTC, not crash
        created_at = datetime.utcnow() - timedelta(hours=1)
        assert _is_new_listing({"created_at": created_at}) is True

    def test_iso_string_parsed(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        assert _is_new_listing({"created_at": recent}) is True

    def test_invalid_string_returns_false(self):
        assert _is_new_listing({"created_at": "not-a-date"}) is False


# ── _detect_price_drop ────────────────────────────────────────────────────────

class TestDetectPriceDrop:
    """Default threshold: 0.05 (5%)."""

    _THRESHOLD = 0.05

    def _row(self, asking_price, price_history):
        return {"asking_price": asking_price, "price_history": price_history}

    def test_significant_drop_detected(self):
        # $100k → $90k = 10% drop
        row = self._row(90_000, [{"price": 100_000, "ts": "2025-01-01T00:00:00"}])
        result = _detect_price_drop(row, self._THRESHOLD)
        assert result is not None
        drop_pct, old, new = result
        assert drop_pct == pytest.approx(10.0)
        assert old == 100_000
        assert new == 90_000

    def test_small_drop_not_detected(self):
        # $100k → $98k = 2% — below 5% threshold
        row = self._row(98_000, [{"price": 100_000, "ts": "2025-01-01T00:00:00"}])
        assert _detect_price_drop(row, self._THRESHOLD) is None

    def test_price_increase_not_detected(self):
        row = self._row(110_000, [{"price": 100_000, "ts": "2025-01-01T00:00:00"}])
        assert _detect_price_drop(row, self._THRESHOLD) is None

    def test_same_price_not_detected(self):
        row = self._row(100_000, [{"price": 100_000, "ts": "2025-01-01T00:00:00"}])
        assert _detect_price_drop(row, self._THRESHOLD) is None

    def test_no_price_history_returns_none(self):
        assert _detect_price_drop(self._row(90_000, None), self._THRESHOLD) is None

    def test_empty_price_history_returns_none(self):
        assert _detect_price_drop(self._row(90_000, []), self._THRESHOLD) is None

    def test_no_asking_price_returns_none(self):
        assert _detect_price_drop(self._row(None, [{"price": 100_000, "ts": ""}]), self._THRESHOLD) is None

    def test_missing_price_in_history_returns_none(self):
        row = self._row(90_000, [{"ts": "2025-01-01"}])  # no "price" key
        assert _detect_price_drop(row, self._THRESHOLD) is None

    def test_uses_last_history_entry(self):
        # Multi-entry history — uses the last one
        history = [
            {"price": 120_000, "ts": "2025-01-01"},  # oldest
            {"price": 110_000, "ts": "2025-02-01"},  # most recent
        ]
        row = self._row(95_000, history)
        result = _detect_price_drop(row, self._THRESHOLD)
        assert result is not None
        drop_pct, old, new = result
        assert old == 110_000  # compared against last entry, not first
        assert new == 95_000

    def test_json_string_history_parsed(self):
        history = json.dumps([{"price": 100_000, "ts": "2025-01-01"}])
        row = self._row(80_000, history)
        result = _detect_price_drop(row, self._THRESHOLD)
        assert result is not None
        assert result[0] == pytest.approx(20.0)

    def test_exact_threshold_triggers(self):
        # Exactly 5% drop: (100k - 95k) / 100k = 0.05
        row = self._row(95_000, [{"price": 100_000, "ts": "2025-01-01"}])
        result = _detect_price_drop(row, self._THRESHOLD)
        assert result is not None

    def test_zero_old_price_returns_none(self):
        row = self._row(90_000, [{"price": 0, "ts": "2025-01-01"}])
        assert _detect_price_drop(row, self._THRESHOLD) is None


# ── _underpriced_severity ─────────────────────────────────────────────────────

class TestUnderpricedSeverity:
    def test_mild_discount_is_watch(self):
        # -15% to -25%: watch
        assert _underpriced_severity(-15.0) == AlertSeverityEnum.watch
        assert _underpriced_severity(-20.0) == AlertSeverityEnum.watch
        assert _underpriced_severity(-24.9) == AlertSeverityEnum.watch

    def test_deep_discount_is_act(self):
        # -25% or worse: act
        assert _underpriced_severity(-25.0) == AlertSeverityEnum.act
        assert _underpriced_severity(-35.0) == AlertSeverityEnum.act
        assert _underpriced_severity(-50.0) == AlertSeverityEnum.act

    def test_boundary_exactly_25_is_act(self):
        assert _underpriced_severity(-25.0) == AlertSeverityEnum.act

    def test_just_under_25_is_watch(self):
        assert _underpriced_severity(-24.999) == AlertSeverityEnum.watch
