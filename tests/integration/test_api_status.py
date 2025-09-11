# tests/integration/test_api_status.py
"""Integration tests for GET /api/ping and GET /api/status."""


class TestApiPing:
    """Tests for the /api/ping heartbeat endpoint."""

    def test_ping_returns_ok(self, client):
        resp = client.get("/api/ping")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "ts" in data


class TestApiStatus:
    """Tests for the /api/status exchange connectivity endpoint."""

    def test_status_returns_expected_keys(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "online" in data
        assert "reason" in data
