# tests/integration/test_security.py
"""Integration tests for security hardening (3.G)."""

from __future__ import annotations

import pytest

from app.extensions import db


class TestHostHeaderValidation:
    """3.G.2 — Host header validation middleware."""

    def test_localhost_allowed(self, client):
        resp = client.get("/api/ping", headers={"Host": "localhost:5000"})
        assert resp.status_code == 200

    def test_127_allowed(self, client):
        resp = client.get("/api/ping", headers={"Host": "127.0.0.1:5000"})
        assert resp.status_code == 200

    def test_external_host_rejected(self, client):
        resp = client.get("/api/ping", headers={"Host": "evil.com"})
        assert resp.status_code == 403

    def test_private_ip_rejected(self, client):
        resp = client.get("/api/ping", headers={"Host": "192.168.1.1:5000"})
        assert resp.status_code == 403


class TestOriginValidation:
    """3.G.3 — Origin check on mutating endpoints."""

    def test_no_origin_allowed(self, client):
        # Same-origin or curl — no Origin header
        resp = client.post("/api/settings/reset", json={})
        assert resp.status_code == 200

    def test_localhost_origin_allowed(self, client):
        resp = client.post("/api/settings/reset", json={},
                           headers={"Origin": "http://localhost:5000"})
        assert resp.status_code == 200

    def test_evil_origin_rejected(self, client):
        resp = client.post("/api/settings/reset", json={},
                           headers={"Origin": "http://evil.com"})
        assert resp.status_code == 403

    def test_get_ignores_origin(self, client):
        resp = client.get("/api/ping",
                          headers={"Origin": "http://evil.com"})
        assert resp.status_code == 200


class TestSqliteWalMode:
    """3.G.1 — SQLite WAL mode and busy_timeout."""

    def test_wal_mode_active(self, app):
        with app.app_context():
            result = db.session.execute(db.text("PRAGMA journal_mode")).scalar()
            assert result == "wal"

    def test_busy_timeout_set(self, app):
        with app.app_context():
            result = db.session.execute(db.text("PRAGMA busy_timeout")).scalar()
            assert result == 5000
