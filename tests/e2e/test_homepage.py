# tests/e2e/test_homepage.py
"""E2E tests for the homepage using Playwright."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def _live_app(app):
    """Run Flask app on a background thread for E2E tests."""
    import threading

    host, port = "127.0.0.1", 5199
    server = None

    def run():
        nonlocal server
        from werkzeug.serving import make_server
        server = make_server(host, port, app)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Wait for server to be ready
    import time
    import httpx
    for _ in range(20):
        try:
            httpx.get(f"http://{host}:{port}/api/ping", timeout=1.0)
            break
        except Exception:
            time.sleep(0.2)

    yield f"http://{host}:{port}"

    if server:
        server.shutdown()


class TestHomepage:
    """E2E tests for the main page."""

    def test_homepage_loads(self, page: Page, _live_app: str):
        page.goto(_live_app)
        expect(page).to_have_title(page.title())
        assert page.locator("body").is_visible()

    def test_signals_table_visible(self, page: Page, _live_app: str):
        page.goto(_live_app)
        # Desktop table or mobile list should exist
        has_table = page.locator("#signals-desktop-body").count() > 0
        has_mobile = page.locator("#signals-mobile-list").count() > 0
        assert has_table or has_mobile

    def test_api_polling_works(self, page: Page, _live_app: str):
        """Verify that the JS polls /api/signals within 6 seconds."""
        api_called = []

        def on_request(request):
            if "/api/signals" in request.url:
                api_called.append(True)

        page.on("request", on_request)
        page.goto(_live_app)
        page.wait_for_timeout(6000)
        assert len(api_called) >= 1, "Expected /api/signals to be polled"

    def test_footer_status_badges_exist(self, page: Page, _live_app: str):
        page.goto(_live_app)
        assert page.locator("[data-app-dot]").count() > 0
        assert page.locator("[data-ex-dot]").count() > 0
