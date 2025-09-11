# tests/integration/test_multi_exchange.py
"""Integration tests for multi-exchange signals and cross-exchange dedup."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.models import DetectionRule, Signal, SignalDedup


class TestMultiExchangeSignals:
    """3.B.10 — Same symbol on different exchanges = different signals."""

    def test_same_symbol_different_exchanges(self, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            Signal.query.delete()
            db.session.commit()

            now = datetime.now(timezone.utc)
            s1 = Signal(exchange="bybit", symbol="BTCUSDT", rule_id=rule.id,
                        change_pct=3.0, window="2m", price=100.0, event_ts=now)
            s2 = Signal(exchange="binance", symbol="BTCUSDT", rule_id=rule.id,
                        change_pct=2.5, window="2m", price=100.1, event_ts=now)
            db.session.add_all([s1, s2])
            db.session.commit()

            signals = Signal.query.filter_by(symbol="BTCUSDT").all()
            exchanges = {s.exchange for s in signals}
            assert exchanges == {"bybit", "binance"}
            assert len(signals) == 2

            Signal.query.delete()
            db.session.commit()

    def test_dedup_key_includes_exchange(self, app):
        """Dedup keys should differentiate by exchange:rule_id:symbol."""
        with app.app_context():
            SignalDedup.query.delete()
            db.session.commit()

            now = datetime.now(timezone.utc)
            d1 = SignalDedup(key="bybit:1:BTCUSDT", last_at=now)
            d2 = SignalDedup(key="binance:1:BTCUSDT", last_at=now)
            db.session.add_all([d1, d2])
            db.session.commit()

            assert SignalDedup.query.count() == 2
            assert db.session.get(SignalDedup, "bybit:1:BTCUSDT") is not None
            assert db.session.get(SignalDedup, "binance:1:BTCUSDT") is not None

            SignalDedup.query.delete()
            db.session.commit()

    def test_signals_api_returns_exchange_field(self, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            Signal.query.delete()
            now = datetime.now(timezone.utc)
            db.session.add(Signal(
                exchange="okx", symbol="ETHUSDT", rule_id=rule.id,
                change_pct=4.0, window="2m", price=3000.0, event_ts=now,
            ))
            db.session.commit()

            # Query within same context to avoid session isolation issues
            from app.screener.signals import fetch_last_rows
            rows, total = fetch_last_rows(page=1, per_page=10)
            assert total >= 1
            exchanges = {r.exchange for r in rows}
            assert "okx" in exchanges

            Signal.query.delete()
            db.session.commit()


class TestExchangeAdapterNames:
    """All adapters return expected name property."""

    def test_adapter_registry(self):
        from app.exchanges.bybit.adapter import BybitAdapter

        adapter = BybitAdapter()
        assert adapter.name == "bybit"
