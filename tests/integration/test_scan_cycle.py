# tests/integration/test_scan_cycle.py
"""Integration tests simulating a full scan cycle with mock exchange data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.extensions import db
from app.models import Signal, SignalDedup, DetectionRule
from app.settings import set_setting, get_setting
from app.screener.helpers import (
    dedup_key,
    dedup_ok_and_touch,
    insert_signal,
)
from app.screener.detectors.pump_rules import detect_pump


@pytest.mark.usefixtures("db_session")
class TestFullScanCycle:
    """Simulates what runner.py does in one scan iteration."""

    def _clean(self):
        Signal.query.delete()
        SignalDedup.query.delete()
        db.session.commit()

    def test_pump_detected_and_signal_created(self, app):
        """End-to-end: pump detection → dedup check → signal insert."""
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            assert rule is not None

            # Simulate kline data with a pump
            closes = [100.0] * 5 + [103.0]  # 3% pump in last 2 candles

            pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
            assert pct is not None
            assert pct >= rule.threshold_pct

            key = dedup_key("TESTUSDT", rule.id, "bybit")
            assert dedup_ok_and_touch(key, 30) is True

            insert_signal(
                exchange="bybit",
                symbol="TESTUSDT",
                rule_id=rule.id,
                rule_label=f"{rule.threshold_pct:g}%/{rule.lookback_min}m",
                rule_color=rule.color,
                change_pct=float(pct),
                window_min=rule.lookback_min,
                price=103.0,
                when=datetime.now(timezone.utc),
            )

            sig = Signal.query.filter_by(symbol="TESTUSDT").first()
            assert sig is not None
            assert sig.change_pct == pytest.approx(3.0, abs=0.01)
            self._clean()

    def test_dedup_blocks_second_signal(self, app):
        """Same symbol+rule should be blocked within hold period."""
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            closes = [100.0] * 5 + [103.0]

            # First detection
            pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
            key = dedup_key("TESTUSDT", rule.id, "bybit")
            assert dedup_ok_and_touch(key, 30) is True
            insert_signal(
                exchange="bybit", symbol="TESTUSDT", rule_id=rule.id,
                change_pct=float(pct), window_min=rule.lookback_min,
                price=103.0, when=datetime.now(timezone.utc),
            )

            # Second detection immediately — should be blocked
            pct2 = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
            assert pct2 is not None  # pump still detected
            assert dedup_ok_and_touch(key, 30) is False  # but dedup blocks

            assert Signal.query.filter_by(symbol="TESTUSDT").count() == 1
            self._clean()

    def test_no_pump_no_signal(self, app):
        """Flat price → no detection → no signal."""
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            closes = [100.0] * 10  # flat

            pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
            assert pct is None
            assert Signal.query.count() == 0
            self._clean()

    def test_insufficient_data_skipped(self, app):
        """Not enough candles → no detection."""
        with app.app_context():
            rule = DetectionRule.query.first()
            closes = [100.0]  # only 1 candle, need at least lookback+1

            pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
            assert pct is None

    def test_multiple_rules_independent(self, app):
        """Different rules fire independently for the same symbol."""
        with app.app_context():
            self._clean()
            # Create a second, more sensitive rule
            rule1 = DetectionRule.query.first()
            rule2 = DetectionRule(
                name="Sensitive",
                lookback_min=1,
                threshold_pct=0.5,
                color="#ff0000",
                sort_order=1,
            )
            db.session.add(rule2)
            db.session.commit()

            closes = [100.0, 100.0, 100.0, 101.0]

            # Rule1 (2%/2m) should NOT trigger
            pct1 = detect_pump(closes, rule1.lookback_min, rule1.threshold_pct)
            assert pct1 is None

            # Rule2 (0.5%/1m) SHOULD trigger
            pct2 = detect_pump(closes, rule2.lookback_min, rule2.threshold_pct)
            assert pct2 is not None

            key2 = dedup_key("TESTUSDT", rule2.id, "bybit")
            assert dedup_ok_and_touch(key2, 30) is True
            insert_signal(
                exchange="bybit", symbol="TESTUSDT", rule_id=rule2.id,
                rule_label="0.5%/1m", rule_color=rule2.color,
                change_pct=float(pct2), window_min=rule2.lookback_min,
                price=101.0, when=datetime.now(timezone.utc),
            )

            assert Signal.query.filter_by(symbol="TESTUSDT").count() == 1

            # Cleanup
            db.session.delete(rule2)
            self._clean()

    def test_hot_reload_rules(self, app):
        """Simulate what runner.py does: reload rules from DB each cycle."""
        with app.app_context():
            self._clean()
            # Cycle 1: default rule (2%/2m)
            db.session.remove()
            rules = DetectionRule.query.filter_by(enabled=True).all()
            assert len(rules) >= 1

            # Disable all rules
            for r in rules:
                r.enabled = False
            db.session.commit()

            # Cycle 2: no rules
            db.session.remove()
            rules2 = DetectionRule.query.filter_by(enabled=True).all()
            assert len(rules2) == 0

            # Re-enable
            for r in DetectionRule.query.all():
                r.enabled = True
            db.session.commit()
            self._clean()


@pytest.mark.usefixtures("db_session")
class TestSettingsPropagation:
    """Test that settings changes are picked up by helpers."""

    def test_watchlist_change_affects_compute_active(self, app):
        with app.app_context():
            from app.screener.helpers import compute_active
            from unittest.mock import patch

            universe = [
                ("AAAUSDT", 0),
                ("BBBUSDT", 0),
            ]

            set_setting("watchlist", [])
            set_setting("blacklist", [])
            set_setting("min_age_days", 0)

            with patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda s, **k: s):
                r1 = compute_active(universe, "linear")
                assert len(r1) == 2

                set_setting("watchlist", ["AAAUSDT"])
                r2 = compute_active(universe, "linear")
                assert r2 == ["AAAUSDT"]

                set_setting("watchlist", [])

    def test_dedup_hold_minutes_change(self, app):
        """Changing dedupe_hold_minutes should affect dedup behavior."""
        with app.app_context():
            SignalDedup.query.delete()
            db.session.commit()

            # First signal with 30 min hold
            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            assert dedup_ok_and_touch("test:SYM:1", 30) is False

            # But with 0 hold, same key should be allowed
            assert dedup_ok_and_touch("test:SYM:1", 0) is True

            SignalDedup.query.delete()
            db.session.commit()
