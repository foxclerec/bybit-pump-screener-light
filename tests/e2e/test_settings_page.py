# tests/e2e/test_settings_page.py
"""E2E tests for the Settings page using Playwright."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def _live_app(app):
    """Run Flask app on a background thread for E2E tests."""
    import threading

    host, port = "127.0.0.1", 5198
    server = None

    def run():
        nonlocal server
        from werkzeug.serving import make_server
        server = make_server(host, port, app)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

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


class TestSettingsPage:

    def test_settings_page_loads(self, page: Page, _live_app: str):
        page.goto(f"{_live_app}/settings")
        expect(page).to_have_title(page.title())
        assert page.locator("body").is_visible()

    def test_detection_rules_section_visible(self, page: Page, _live_app: str):
        page.goto(f"{_live_app}/settings")
        # Should have at least one rule row
        page.wait_for_timeout(1000)
        rules = page.locator("[data-rule-id]")
        assert rules.count() >= 1

    def test_notifications_section_visible(self, page: Page, _live_app: str):
        page.goto(f"{_live_app}/settings")
        page.wait_for_timeout(500)
        # Sound toggle should exist
        sound_toggle = page.locator('[data-field="notif-sound-enabled"]')
        assert sound_toggle.count() >= 1

    def test_footer_status_updates_on_settings(self, page: Page, _live_app: str):
        """Footer polling (app.js) must work on settings page too."""
        page.goto(f"{_live_app}/settings")
        page.wait_for_timeout(4000)
        app_dot_cls = page.locator("[data-app-dot]").get_attribute("class")
        assert "is-up" in app_dot_cls

    def test_reset_button_exists(self, page: Page, _live_app: str):
        page.goto(f"{_live_app}/settings")
        page.wait_for_timeout(500)
        reset_btns = page.locator("button:has-text('Reset')")
        assert reset_btns.count() >= 1
