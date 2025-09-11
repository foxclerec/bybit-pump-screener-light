# tests/unit/test_pump_rules.py
"""Unit tests for the pump detection algorithm."""

import pytest
from app.screener.detectors.pump_rules import detect_pump


class TestDetectPump:
    """Tests for detect_pump(closes, lookback_minutes, min_pct)."""

    def test_pump_detected_above_threshold(self):
        closes = [100.0, 100.0, 100.0, 103.0]
        result = detect_pump(closes, lookback_minutes=2, min_pct=2.0)
        assert result is not None
        assert result == pytest.approx(3.0, abs=0.01)

    def test_below_threshold_returns_none(self):
        closes = [100.0, 100.0, 100.0, 101.0]
        result = detect_pump(closes, lookback_minutes=2, min_pct=2.0)
        assert result is None

    def test_exact_threshold_triggers(self):
        closes = [100.0, 100.0, 100.0, 102.0]
        result = detect_pump(closes, lookback_minutes=2, min_pct=2.0)
        assert result is not None
        assert result == pytest.approx(2.0, abs=0.01)

    def test_empty_closes_returns_none(self):
        assert detect_pump([], lookback_minutes=2, min_pct=2.0) is None

    def test_none_closes_returns_none(self):
        assert detect_pump(None, lookback_minutes=2, min_pct=2.0) is None

    def test_insufficient_data_returns_none(self):
        closes = [100.0]
        assert detect_pump(closes, lookback_minutes=2, min_pct=2.0) is None

    def test_zero_past_price_returns_none(self):
        # past price is at index -(lookback+1), so with lookback=2: closes[-3] = 0.0
        closes = [0.0, 50.0, 100.0]
        assert detect_pump(closes, lookback_minutes=2, min_pct=1.0) is None

    def test_negative_change_returns_none(self):
        closes = [100.0, 100.0, 100.0, 90.0]
        assert detect_pump(closes, lookback_minutes=2, min_pct=2.0) is None

    def test_large_pump(self):
        closes = [100.0] * 21 + [115.0]
        result = detect_pump(closes, lookback_minutes=20, min_pct=10.0)
        assert result is not None
        assert result == pytest.approx(15.0, abs=0.01)

    def test_lookback_uses_correct_index(self):
        # closes: index -4 = 100, index -1 = 106 -> 6% over 3 candles
        closes = [50.0, 100.0, 102.0, 104.0, 106.0]
        result = detect_pump(closes, lookback_minutes=3, min_pct=5.0)
        assert result is not None
        assert result == pytest.approx(6.0, abs=0.01)
