# tests/integration/test_models.py
"""Integration tests for ORM models."""

from datetime import datetime, timezone

from app.extensions import db
from app.models import DetectionRule, Signal, SignalDedup, Setting


class TestDetectionRuleModel:
    """Tests for the DetectionRule model."""

    def test_create_rule(self, app):
        with app.app_context():
            rule = DetectionRule(
                name="IntTest",
                lookback_min=5,
                threshold_pct=3.0,
                color="#ff0000",
                sort_order=99,
            )
            db.session.add(rule)
            db.session.commit()
            assert rule.id is not None
            assert rule.enabled is True

    def test_repr(self, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            r = repr(rule)
            assert "DetectionRule" in r


class TestSignalModel:
    """Tests for the Signal model with rule FK."""

    def test_create_signal_with_rule(self, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            sig = Signal(
                exchange="test",
                symbol="ETHUSDT",
                rule_id=rule.id,
                change_pct=4.2,
                window="5m",
                price=3000.0,
                event_ts=datetime.now(timezone.utc),
            )
            db.session.add(sig)
            db.session.commit()
            assert sig.id is not None
            assert sig.rule.name == rule.name

    def test_signal_repr(self, app):
        with app.app_context():
            sig = Signal.query.first()
            if sig:
                r = repr(sig)
                assert "Signal" in r


class TestSignalDedupModel:
    """Tests for SignalDedup upsert logic."""

    def test_create_and_update_dedup(self, app):
        with app.app_context():
            import uuid
            key = f"TESTUSDT:{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            rec = SignalDedup(key=key, last_at=now)
            db.session.add(rec)
            db.session.commit()
            assert db.session.get(SignalDedup, key) is not None

            # Update
            rec.last_at = datetime.now(timezone.utc)
            db.session.commit()
            updated = db.session.get(SignalDedup, key)
            assert updated.last_at is not None


class TestSettingModel:
    """Tests for the Setting key-value model."""

    def test_setting_round_trip(self, app):
        with app.app_context():
            import uuid
            key = f"test_model_{uuid.uuid4().hex[:8]}"
            s = Setting(
                key=key,
                value='{"a": 1}',
                updated_at=datetime.now(timezone.utc),
            )
            db.session.add(s)
            db.session.commit()
            loaded = db.session.get(Setting, key)
            assert loaded is not None
            assert loaded.value == '{"a": 1}'
