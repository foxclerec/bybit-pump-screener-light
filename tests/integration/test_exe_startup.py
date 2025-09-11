# tests/integration/test_exe_startup.py
"""Integration test: app starts and responds to /api/ping and core endpoints.

Simulates what the exe does on startup (minus pywebview/screener thread):
- App factory creates successfully
- Database initializes
- All API endpoints respond
- Static assets load
"""


class TestExeStartup:
    """Verify the app boots and core endpoints work."""

    def test_ping_responds(self, client):
        resp = client.get("/api/ping")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_homepage_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Pump Alerts" in resp.data

    def test_settings_page_loads(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert b"Detection Rules" in resp.data

    def test_signals_api_responds(self, client):
        resp = client.get("/api/signals")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "signals" in data
        assert "total" in data

    def test_status_api_responds(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "online" in data

    def test_update_check_api_responds(self, client):
        resp = client.get("/api/update-check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "available" in data
        assert "current_version" in data

    def test_mute_api_responds(self, client):
        resp = client.get("/api/mute")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "muted" in data

    def test_static_css_loads(self, client):
        resp = client.get("/static/css/app.css")
        assert resp.status_code == 200
        assert b"--color-bg-base" in resp.data

    def test_static_js_loads(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200

    def test_version_in_context(self, app):
        with app.test_request_context():
            from app.constants import APP_VERSION
            assert APP_VERSION
            assert "." in APP_VERSION
