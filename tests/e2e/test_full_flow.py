# tests/e2e/test_full_flow.py
"""E2E test: full user flow — signals table, mute, navigation, settings.

SSE endpoint keeps connection open, so each test creates a fresh page context.
"""

import pytest
from playwright.sync_api import BrowserContext, expect


@pytest.fixture(scope="module")
def _live_app(app):
    """Run Flask app on a background thread for E2E tests."""
    import threading

    host, port = "127.0.0.1", 5193
    server = None

    def run():
        nonlocal server
        from werkzeug.serving import make_server
        server = make_server(host, port, app, threaded=True)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    import time, httpx
    for _ in range(20):
        try:
            httpx.get(f"http://{host}:{port}/api/ping", timeout=1.0)
            break
        except Exception:
            time.sleep(0.2)

    yield f"http://{host}:{port}"

    if server:
        server.shutdown()


@pytest.fixture
def fresh_page(browser):
    """Create a fresh browser context + page per test (avoids SSE carry-over)."""
    ctx = browser.new_context()
    page = ctx.new_page()
    yield page
    page.close()
    ctx.close()


class TestFullFlow:
    """E2E: page rendering, interactions, navigation."""

    def test_homepage_and_ui(self, fresh_page, _live_app: str):
        """Homepage loads, has signals structure, mute button, footer badges."""
        fresh_page.goto(_live_app, wait_until="commit")
        fresh_page.wait_for_timeout(3000)

        content = fresh_page.content()

        # Signals table or empty state
        assert ("signals-desktop-body" in content or "Waiting for signals" in content)

        # Mute button
        assert fresh_page.locator('[data-action="mute-toggle"]').count() > 0

        # Footer badges
        assert fresh_page.locator("[data-app-dot]").count() > 0
        assert fresh_page.locator("[data-screener-dot]").count() > 0
        assert fresh_page.locator("[data-ex-dot]").count() > 0

    def test_api_polling(self, fresh_page, _live_app: str):
        """JS should poll /api/signals."""
        api_called = []
        fresh_page.on("request", lambda req: api_called.append(True) if "/api/signals?" in req.url else None)
        fresh_page.goto(_live_app, wait_until="commit")
        fresh_page.wait_for_timeout(7000)
        assert len(api_called) >= 1, "Expected /api/signals to be polled"

    def test_mute_toggle(self, fresh_page, _live_app: str):
        """Clicking mute should change icon class."""
        fresh_page.goto(_live_app, wait_until="commit")
        fresh_page.wait_for_timeout(2000)

        icon = fresh_page.locator("[data-mute-icon]")
        initial_class = icon.get_attribute("class") or ""

        fresh_page.locator('[data-action="mute-toggle"]').click()
        fresh_page.wait_for_timeout(1500)

        new_class = icon.get_attribute("class") or ""
        assert new_class != initial_class, "Mute icon should change"

    def test_settings_page(self, fresh_page, _live_app: str):
        """Settings page loads with rules and about tab."""
        fresh_page.goto(f"{_live_app}/settings", wait_until="commit")
        fresh_page.wait_for_timeout(1000)

        assert "Detection Rules" in fresh_page.content()

        # About tab
        fresh_page.locator('[data-nav="about"]').click()
        fresh_page.wait_for_timeout(500)
        assert "Version" in fresh_page.content()
        assert fresh_page.locator('[data-action="check-update"]').count() > 0
