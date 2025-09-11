# tests/integration/test_sound_api.py
"""Integration tests for sound picker API endpoints."""

from __future__ import annotations

import pytest


class TestSoundListAPI:
    """GET /api/sounds returns available sound names."""

    def test_returns_list(self, client):
        r = client.get("/api/sounds")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert "Pulse" in data
        assert "Boom" in data


class TestNotificationsSaveLoad:
    """PUT + GET /api/settings/notifications round-trip for alert_sound_file."""

    def test_save_and_load_sound_by_filename(self, client):
        r = client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 15,
            "alert_sound_file": "boom.wav",
        })
        assert r.status_code == 200

        r = client.get("/api/settings/notifications")
        assert r.status_code == 200
        assert r.get_json()["alert_sound_file"] == "boom.wav"

    def test_save_and_load_sound_by_display_name(self, client):
        r = client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 15,
            "alert_sound_file": "Pulse",
        })
        assert r.status_code == 200

        r = client.get("/api/settings/notifications")
        assert r.status_code == 200
        assert r.get_json()["alert_sound_file"] == "pulse.wav"

    def test_save_unknown_sound_fails(self, client):
        r = client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 15,
            "alert_sound_file": "doesnotexist.wav",
        })
        assert r.status_code == 400
        assert "Unknown sound" in r.get_json()["error"]

    def test_save_empty_sound_keeps_current(self, client):
        """Empty string for sound should not change the stored value."""
        # Set to boom first
        client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 15,
            "alert_sound_file": "boom.wav",
        })

        # Save with empty sound
        r = client.put("/api/settings/notifications", json={
            "sound_enabled": True,
            "alert_cooldown_seconds": 20,
            "alert_sound_file": "",
        })
        assert r.status_code == 200

        r = client.get("/api/settings/notifications")
        data = r.get_json()
        assert data["alert_sound_file"] == "boom.wav"
        assert data["alert_cooldown_seconds"] == 20


class TestRuleTogglePatch:
    """PATCH /api/rules/<id> for enable/disable toggle."""

    def _get_first_rule_id(self, app):
        with app.app_context():
            from app.models import DetectionRule
            rule = DetectionRule.query.first()
            return rule.id

    def test_toggle_disable(self, app, client):
        rule_id = self._get_first_rule_id(app)
        r = client.patch(f"/api/rules/{rule_id}", json={"enabled": False})
        assert r.status_code == 200
        assert r.get_json()["enabled"] is False

    def test_toggle_enable(self, app, client):
        rule_id = self._get_first_rule_id(app)
        r = client.patch(f"/api/rules/{rule_id}", json={"enabled": True})
        assert r.status_code == 200
        assert r.get_json()["enabled"] is True

    def test_toggle_nonexistent_rule(self, client):
        r = client.patch("/api/rules/99999", json={"enabled": False})
        assert r.status_code == 404
