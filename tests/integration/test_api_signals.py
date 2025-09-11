# tests/integration/test_api_signals.py
"""Integration tests for GET /api/signals."""

from datetime import datetime, timezone

from app.extensions import db
from app.models import Signal, DetectionRule


class TestApiSignals:
    """Tests for the /api/signals endpoint."""

    def test_empty_db_returns_empty_list(self, client, app):
        with app.app_context():
            Signal.query.delete()
            db.session.commit()

        resp = client.get("/api/signals")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["signals"] == []
        assert body["total"] == 0

    def test_returns_signals_with_expected_keys(self, client, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            sig = Signal(
                exchange="test",
                symbol="BTCUSDT",
                rule_id=rule.id,
                change_pct=5.5,
                window="2m",
                price=50000.0,
                event_ts=datetime.now(timezone.utc),
            )
            db.session.add(sig)
            db.session.commit()

        resp = client.get("/api/signals")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["signals"]) >= 1
        item = body["signals"][0]
        assert "rule_name" in item
        assert "rule_color" in item
        assert "pct" in item
        assert "symbol" in item

    def test_pagination(self, app):
        """Test pagination via fetch_last_rows (avoids cross-connection issues with in-memory SQLite)."""
        from app.screener.signals import fetch_last_rows
        with app.app_context():
            Signal.query.delete()
            rule = DetectionRule.query.first()
            for i in range(5):
                db.session.add(Signal(
                    exchange="test",
                    symbol=f"SYM{i}USDT",
                    rule_id=rule.id,
                    change_pct=2.0 + i,
                    window="2m",
                    price=100.0,
                    event_ts=datetime.now(timezone.utc),
                ))
            db.session.commit()

            rows, total = fetch_last_rows(page=1, per_page=2)
            assert len(rows) == 2
            assert total == 5

            rows3, _ = fetch_last_rows(page=3, per_page=2)
            assert len(rows3) == 1

            Signal.query.delete()
            db.session.commit()

    def test_cache_control_header(self, client):
        resp = client.get("/api/signals")
        assert "no-store" in resp.headers.get("Cache-Control", "")
