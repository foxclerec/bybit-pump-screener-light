# tests/unit/test_signals_crud.py
"""Unit tests for insert_signal and fetch_last_rows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import Signal, DetectionRule
from app.screener.helpers import insert_signal
from app.screener.signals import fetch_last_rows
from app.settings import set_setting


@pytest.mark.usefixtures("db_session")
class TestInsertSignal:

    def _clean(self):
        Signal.query.delete()
        db.session.commit()

    def test_basic_insert(self, app):
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            insert_signal(
                exchange="bybit",
                symbol="BTCUSDT",
                rule_id=rule.id,
                rule_label="2%/2m",
                rule_color="#10b981",
                change_pct=3.5,
                window_min=2,
                price=50000.0,
                when=datetime.now(timezone.utc),
            )
            sig = Signal.query.first()
            assert sig is not None
            assert sig.symbol == "BTCUSDT"
            assert sig.exchange == "bybit"
            assert sig.change_pct == 3.5
            assert sig.window == "2m"
            self._clean()

    def test_symbol_uppercased(self, app):
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            insert_signal(
                exchange="bybit",
                symbol="ethusdt",
                rule_id=rule.id,
                change_pct=2.0,
                window_min=2,
                price=3000.0,
                when=datetime.now(timezone.utc),
            )
            sig = Signal.query.first()
            assert sig.symbol == "ETHUSDT"
            self._clean()

    def test_rule_snapshot_stored(self, app):
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            insert_signal(
                exchange="bybit",
                symbol="BTCUSDT",
                rule_id=rule.id,
                rule_label="custom_label",
                rule_color="#ff0000",
                change_pct=5.0,
                window_min=3,
                price=45000.0,
                when=datetime.now(timezone.utc),
            )
            sig = Signal.query.first()
            assert sig.rule_label == "custom_label"
            assert sig.rule_color == "#ff0000"
            self._clean()


@pytest.mark.usefixtures("db_session")
class TestFetchLastRows:

    def _clean(self):
        Signal.query.delete()
        db.session.commit()

    def _add_signals(self, count, **overrides):
        rule = DetectionRule.query.first()
        now = datetime.now(timezone.utc)
        for i in range(count):
            sig = Signal(
                exchange=overrides.get("exchange", "bybit"),
                symbol=overrides.get("symbol", f"SYM{i}USDT"),
                rule_id=rule.id,
                change_pct=2.0 + i,
                window="2m",
                price=100.0,
                event_ts=now - timedelta(seconds=i),
            )
            db.session.add(sig)
        db.session.commit()

    def test_pagination(self, app):
        with app.app_context():
            self._clean()
            self._add_signals(10)
            rows, total = fetch_last_rows(page=1, per_page=3)
            assert len(rows) == 3
            assert total == 10
            self._clean()

    def test_page_2(self, app):
        with app.app_context():
            self._clean()
            self._add_signals(5)
            rows, total = fetch_last_rows(page=2, per_page=3)
            assert len(rows) == 2
            assert total == 5
            self._clean()

    def test_filter_by_symbol(self, app):
        with app.app_context():
            self._clean()
            self._add_signals(3)
            rows, total = fetch_last_rows(symbol="SYM0USDT", per_page=10)
            assert total == 1
            assert rows[0].symbol == "SYM0USDT"
            self._clean()

    def test_filter_by_exchange(self, app):
        with app.app_context():
            self._clean()
            self._add_signals(2, exchange="bybit")
            self._add_signals(1, exchange="test")
            rows, total = fetch_last_rows(exchange="test", per_page=10)
            assert total == 1
            self._clean()

    def test_watchlist_filters_display(self, app):
        """When watchlist is set, only matching signals are returned."""
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            now = datetime.now(timezone.utc)
            for sym in ["AAAUSDT", "BBBUSDT", "CCCUSDT"]:
                db.session.add(Signal(
                    exchange="bybit", symbol=sym, rule_id=rule.id,
                    change_pct=3.0, window="2m", price=100.0, event_ts=now,
                ))
            db.session.commit()

            set_setting("watchlist", ["AAAUSDT"])
            set_setting("blacklist", [])
            rows, total = fetch_last_rows(per_page=10)
            assert total == 1
            assert rows[0].symbol == "AAAUSDT"

            # Clear watchlist — all signals visible again
            set_setting("watchlist", [])
            rows, total = fetch_last_rows(per_page=10)
            assert total == 3
            self._clean()

    def test_blacklist_filters_display(self, app):
        """Blacklisted symbols should not appear in signal list."""
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            now = datetime.now(timezone.utc)
            for sym in ["AAAUSDT", "BBBUSDT"]:
                db.session.add(Signal(
                    exchange="bybit", symbol=sym, rule_id=rule.id,
                    change_pct=3.0, window="2m", price=100.0, event_ts=now,
                ))
            db.session.commit()

            set_setting("watchlist", [])
            set_setting("blacklist", ["BBBUSDT"])
            rows, total = fetch_last_rows(per_page=10)
            assert total == 1
            assert rows[0].symbol == "AAAUSDT"

            set_setting("blacklist", [])
            self._clean()

    def test_ordered_by_event_ts_desc(self, app):
        with app.app_context():
            self._clean()
            rule = DetectionRule.query.first()
            now = datetime.now(timezone.utc)
            for i, sym in enumerate(["FIRST", "SECOND", "THIRD"]):
                db.session.add(Signal(
                    exchange="bybit", symbol=sym, rule_id=rule.id,
                    change_pct=2.0, window="2m", price=100.0,
                    event_ts=now - timedelta(seconds=i * 10),
                ))
            db.session.commit()

            set_setting("watchlist", [])
            set_setting("blacklist", [])
            rows, _ = fetch_last_rows(per_page=10)
            assert rows[0].symbol == "FIRST"  # most recent
            assert rows[-1].symbol == "THIRD"  # oldest
            self._clean()
