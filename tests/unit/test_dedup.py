# tests/unit/test_dedup.py
"""Unit tests for deduplication logic: dedup_key, dedup_ok_and_touch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import SignalDedup
from app.screener.helpers import dedup_key, dedup_ok_and_touch


class TestDedupKey:

    def test_format(self):
        assert dedup_key("BTCUSDT", 1, "bybit") == "bybit:BTCUSDT:1"

    def test_uppercases_symbol(self):
        assert dedup_key("btcusdt", 1, "bybit") == "bybit:BTCUSDT:1"

    def test_lowercases_exchange(self):
        assert dedup_key("BTCUSDT", 1, "BYBIT") == "bybit:BTCUSDT:1"

    def test_empty_exchange(self):
        assert dedup_key("BTCUSDT", 1) == ":BTCUSDT:1"

    def test_different_rules_different_keys(self):
        k1 = dedup_key("BTCUSDT", 1, "bybit")
        k2 = dedup_key("BTCUSDT", 2, "bybit")
        assert k1 != k2


@pytest.mark.usefixtures("db_session")
class TestDedupOkAndTouch:

    def _clean(self):
        SignalDedup.query.delete()
        db.session.commit()

    def test_first_call_allows(self, app):
        with app.app_context():
            self._clean()
            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            self._clean()

    def test_second_call_within_hold_blocks(self, app):
        with app.app_context():
            self._clean()
            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            assert dedup_ok_and_touch("test:SYM:1", 30) is False
            self._clean()

    def test_second_call_after_hold_allows(self, app):
        with app.app_context():
            self._clean()
            # Insert with old timestamp
            old = datetime.now(timezone.utc) - timedelta(minutes=31)
            rec = SignalDedup(key="test:SYM:1", last_at=old)
            db.session.add(rec)
            db.session.commit()

            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            self._clean()

    def test_different_keys_independent(self, app):
        with app.app_context():
            self._clean()
            assert dedup_ok_and_touch("test:AAA:1", 30) is True
            assert dedup_ok_and_touch("test:BBB:1", 30) is True
            assert dedup_ok_and_touch("test:AAA:1", 30) is False  # blocked
            assert dedup_ok_and_touch("test:BBB:1", 30) is False  # blocked
            self._clean()

    def test_zero_hold_always_allows(self, app):
        with app.app_context():
            self._clean()
            assert dedup_ok_and_touch("test:SYM:1", 0) is True
            assert dedup_ok_and_touch("test:SYM:1", 0) is True
            self._clean()

    def test_naive_datetime_handled(self, app):
        """Old DB entries might have naive (tz-unaware) datetimes."""
        with app.app_context():
            self._clean()
            # Simulate naive datetime stored in DB (no tzinfo)
            old = datetime.utcnow() - timedelta(minutes=31)
            rec = SignalDedup(key="test:SYM:1", last_at=old)
            db.session.add(rec)
            db.session.commit()

            # Should handle and allow since hold expired
            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            self._clean()

    def test_updates_last_at_on_allow(self, app):
        with app.app_context():
            self._clean()
            # Set initial timestamp to a known old value
            old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
            rec = SignalDedup(key="test:SYM:1", last_at=old_time)
            db.session.add(rec)
            db.session.commit()

            # Should allow (60 min > 30 min hold) and update last_at
            assert dedup_ok_and_touch("test:SYM:1", 30) is True
            db.session.refresh(rec)
            updated = rec.last_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            assert updated > old_time
            self._clean()
