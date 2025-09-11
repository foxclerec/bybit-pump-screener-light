# tests/integration/test_settings_api.py
"""Integration tests for Settings and Rules CRUD API endpoints."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models import DetectionRule


class TestRulesCRUD:
    """Tests for /api/rules endpoints."""

    def test_create_rule(self, client, app):
        resp = client.post("/api/rules", json={
            "name": "Test Create",
            "lookback_min": 5,
            "threshold_pct": 3.0,
            "color": "#10b981",
            "sound_file": "chime.mp3",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Test Create"
        assert data["lookback_min"] == 5
        assert data["threshold_pct"] == 3.0
        # Cleanup
        with app.app_context():
            rule = db.session.get(DetectionRule, data["id"])
            if rule:
                db.session.delete(rule)
                db.session.commit()

    def test_create_rule_validation_name_required(self, client):
        resp = client.post("/api/rules", json={
            "lookback_min": 5,
            "threshold_pct": 3.0,
            "color": "#10b981",
        })
        assert resp.status_code == 400
        assert "Name" in resp.get_json()["error"]

    def test_create_rule_validation_lookback_range(self, client):
        resp = client.post("/api/rules", json={
            "name": "Bad Lookback",
            "lookback_min": 999,
            "threshold_pct": 3.0,
            "color": "#10b981",
        })
        assert resp.status_code == 400
        assert "Lookback" in resp.get_json()["error"]

    def test_create_rule_validation_threshold_range(self, client):
        resp = client.post("/api/rules", json={
            "name": "Bad Threshold",
            "lookback_min": 5,
            "threshold_pct": 0.1,
            "color": "#10b981",
        })
        assert resp.status_code == 400
        assert "Threshold" in resp.get_json()["error"]

    def test_create_rule_validation_invalid_color(self, client):
        resp = client.post("/api/rules", json={
            "name": "Bad Color",
            "lookback_min": 5,
            "threshold_pct": 3.0,
            "color": "#ffffff",
        })
        assert resp.status_code == 400
        assert "color" in resp.get_json()["error"].lower()

    def test_get_rule(self, client, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            rule_id = rule.id
        resp = client.get(f"/api/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.get_json()["id"] == rule_id

    def test_get_rule_not_found(self, client):
        resp = client.get("/api/rules/99999")
        assert resp.status_code == 404

    def test_update_rule(self, client, app):
        with app.app_context():
            rule = DetectionRule.query.first()
            rule_id = rule.id
            original_name = rule.name
        resp = client.put(f"/api/rules/{rule_id}", json={
            "name": "Updated Rule",
            "lookback_min": 10,
            "threshold_pct": 5.0,
            "color": "#ef4444",
        })
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Updated Rule"
        # Restore
        with app.app_context():
            rule = db.session.get(DetectionRule, rule_id)
            rule.name = original_name
            rule.lookback_min = 2
            rule.threshold_pct = 2.0
            rule.color = "#10b981"
            db.session.commit()

    def test_delete_last_rule_prevented(self, client, app):
        with app.app_context():
            # Ensure only one rule exists
            count = DetectionRule.query.count()
            rule = DetectionRule.query.first()
        if count == 1:
            resp = client.delete(f"/api/rules/{rule.id}")
            assert resp.status_code == 400
            assert "last rule" in resp.get_json()["error"].lower()


class TestNotificationsSettings:

    def test_get_notifications(self, client):
        resp = client.get("/api/settings/notifications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sound_enabled" in data
        assert "alert_cooldown_seconds" in data

    def test_update_notifications(self, client):
        resp = client.put("/api/settings/notifications", json={
            "sound_enabled": False,
            "alert_cooldown_seconds": 30,
            "alert_sound_file": "",
        })
        assert resp.status_code == 200
        # Restore
        client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 30,
            "alert_sound_file": "",
        })

    def test_update_notifications_invalid_cooldown(self, client):
        resp = client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 999,
            "alert_sound_file": "",
        })
        assert resp.status_code == 400


class TestFiltersSettings:

    def test_get_filters(self, client):
        resp = client.get("/api/settings/filters")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "min_volume_usd" in data
        assert "watchlist" in data

    def test_update_filters(self, client):
        resp = client.put("/api/settings/filters", json={
            "min_volume_usd": 500000,
            "min_age_days": 30,
            "watchlist": ["BTCUSDT", "ETHUSDT"],
            "blacklist": [],
        })
        assert resp.status_code == 200

    def test_update_filters_bad_volume(self, client):
        resp = client.put("/api/settings/filters", json={
            "min_volume_usd": -1,
            "min_age_days": 30,
            "watchlist": [],
            "blacklist": [],
        })
        assert resp.status_code == 400


class TestDisplaySettings:

    def test_get_display(self, client):
        resp = client.get("/api/settings/display")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "timezone" in data
        assert "rows_per_page" in data

    def test_update_display(self, client):
        resp = client.put("/api/settings/display", json={
            "timezone": "UTC",
            "rows_per_page": 10,
            "show_coinglass": True,
            "show_tradingview": True,
        })
        assert resp.status_code == 200

    def test_update_display_bad_timezone(self, client):
        resp = client.put("/api/settings/display", json={
            "timezone": "Mars/Olympus",
            "rows_per_page": 10,
            "show_coinglass": True,
            "show_tradingview": True,
        })
        assert resp.status_code == 400


class TestAdvancedSettings:

    def test_get_advanced(self, client):
        resp = client.get("/api/settings/advanced")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "poll_seconds" in data
        assert "active_exchanges" in data

    def test_update_advanced(self, client):
        resp = client.put("/api/settings/advanced", json={
            "poll_seconds": 15,
            "max_klines": 50,
            "active_exchanges": ["bybit"],
        })
        assert resp.status_code == 200

    def test_update_advanced_no_exchanges(self, client):
        resp = client.put("/api/settings/advanced", json={
            "poll_seconds": 15,
            "max_klines": 50,
            "active_exchanges": [],
        })
        assert resp.status_code == 400


class TestResetSettings:

    def test_reset_section(self, client):
        resp = client.post("/api/settings/reset/display")
        assert resp.status_code == 200

    def test_reset_unknown_section(self, client):
        resp = client.post("/api/settings/reset/nonexistent")
        assert resp.status_code == 400

    def test_reset_all(self, client):
        resp = client.post("/api/settings/reset")
        assert resp.status_code == 200
