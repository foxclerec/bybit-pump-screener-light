# tests/e2e/test_live_signals.py
"""E2E tests: signal insertion → table update → footer → SSE, all within 3 seconds."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

import httpx
import pytest
from playwright.sync_api import Page, expect

from app.extensions import db
from app.models import Signal, SignalDedup, DetectionRule
from app.settings import set_setting


@pytest.fixture(scope="module")
def _e2e_server(app):
    """Threaded Flask server for E2E tests."""
    host, port = "127.0.0.1", 5201
    server = None

    def run():
        nonlocal server
        from werkzeug.serving import make_server
        server = make_server(host, port, app, threaded=True)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    for _ in range(20):
        try:
            httpx.get(f"http://{host}:{port}/api/ping", timeout=1.0)
            break
        except Exception:
            time.sleep(0.2)

    yield f"http://{host}:{port}"

    if server:
        server.shutdown()


class TestLiveSignals:
    """Verify that signals inserted into DB appear in the frontend within 3 seconds."""

    def test_signal_appears_in_table_within_3_seconds(self, page: Page, _e2e_server: str, app):
        """Insert a signal → verify it shows in the desktop table within 3 seconds."""
        with app.app_context():
            Signal.query.delete()
            SignalDedup.query.delete()
            db.session.commit()

        page.goto(_e2e_server)
        page.wait_for_timeout(1000)

        # Insert signal
        with app.app_context():
            rule = DetectionRule.query.first()
            sig = Signal(
                exchange="bybit",
                symbol="E2ETEST",
                rule_id=rule.id,
                rule_label="2%/2m",
                rule_color="#10b981",
                change_pct=4.5,
                window="2m",
                price=99.99,
                event_ts=datetime.now(timezone.utc),
            )
            db.session.add(sig)
            db.session.commit()

        # Wait for signal to appear (max 3 seconds)
        start = time.time()
        found = False
        for _ in range(30):  # poll 30 times, 100ms each = 3s max
            tbody = page.locator("#signals-desktop-body")
            if tbody.count() > 0:
                html = tbody.inner_html()
                if "E2ETEST" in html:
                    found = True
                    break
            page.wait_for_timeout(100)

        elapsed = time.time() - start
        assert found, f"Signal E2ETEST did not appear in table within 3 seconds (waited {elapsed:.1f}s)"
        assert elapsed < 3.0, f"Signal appeared but took {elapsed:.1f}s (expected < 3s)"

        # Cleanup
        with app.app_context():
            Signal.query.delete()
            SignalDedup.query.delete()
            db.session.commit()

    def test_signal_shows_correct_data(self, page: Page, _e2e_server: str, app):
        """Verify signal data is rendered correctly."""
        with app.app_context():
            Signal.query.delete()
            db.session.commit()
            rule = DetectionRule.query.first()
            db.session.add(Signal(
                exchange="bybit",
                symbol="DATAUSDT",
                rule_id=rule.id,
                rule_label="2%/2m",
                rule_color="#ff0000",
                change_pct=7.77,
                window="2m",
                price=123.45,
                event_ts=datetime.now(timezone.utc),
            ))
            db.session.commit()

        page.goto(_e2e_server)
        page.wait_for_timeout(3000)

        tbody = page.locator("#signals-desktop-body")
        html = tbody.inner_html()
        assert "DATAUSDT" in html
        assert "7.77" in html

        with app.app_context():
            Signal.query.delete()
            db.session.commit()

    def test_empty_state_shows_waiting(self, page: Page, _e2e_server: str, app):
        """With no signals, empty state should display."""
        with app.app_context():
            Signal.query.delete()
            db.session.commit()

        page.goto(_e2e_server)
        page.wait_for_timeout(2000)

        body = page.content()
        assert "Waiting for signals" in body or "empty-state" in body

    def test_clear_signals_button_works(self, page: Page, _e2e_server: str, app):
        """Clear all signals via the button."""
        with app.app_context():
            Signal.query.delete()
            rule = DetectionRule.query.first()
            db.session.add(Signal(
                exchange="bybit", symbol="CLEARME", rule_id=rule.id,
                change_pct=5.0, window="2m", price=100.0,
                event_ts=datetime.now(timezone.utc),
            ))
            db.session.commit()

        page.goto(_e2e_server)
        page.wait_for_timeout(2000)

        # Should see the signal
        assert "CLEARME" in page.content()

        # Click clear
        clear_btn = page.locator('[data-action="clear-signals"]').first
        if clear_btn.count() > 0:
            clear_btn.click()
            # Confirm dialog
            page.wait_for_timeout(500)
            confirm = page.locator("button:has-text('Clear')")
            if confirm.count() > 0:
                confirm.click()

            page.wait_for_timeout(2000)

            with app.app_context():
                assert Signal.query.count() == 0


class TestFooterUpdates:
    """Verify footer badges update correctly."""

    def test_app_badge_shows_up(self, page: Page, _e2e_server: str):
        """App badge should show 'up' (green) when server is running."""
        page.goto(_e2e_server)
        page.wait_for_timeout(4000)

        app_dot = page.locator("[data-app-dot]")
        assert app_dot.count() > 0
        cls = app_dot.get_attribute("class") or ""
        assert "is-up" in cls, f"Expected app badge 'is-up', got class='{cls}'"

    def test_coins_badge_updates(self, page: Page, _e2e_server: str, app):
        """Coins badge should show a number from metrics store."""
        # Write metric
        from app.screener.metrics_store import set_metric
        with app.app_context():
            set_metric(app.instance_path, "active_count", 42, namespace="screener")

        page.goto(_e2e_server)
        page.wait_for_timeout(4000)

        coins_label = page.locator("[data-coins-label]")
        if coins_label.count() > 0:
            text = coins_label.inner_text()
            assert "42" in text, f"Expected coins badge to show 42, got '{text}'"

    def test_coins_badge_updates_when_metric_changes(self, page: Page, _e2e_server: str, app):
        """Coins count should update when metrics change, within 6 seconds."""
        from app.screener.metrics_store import set_metric
        with app.app_context():
            set_metric(app.instance_path, "active_count", 100, namespace="screener")

        page.goto(_e2e_server)
        page.wait_for_timeout(4000)

        # Now change the metric
        with app.app_context():
            set_metric(app.instance_path, "active_count", 200, namespace="screener")

        # Wait for update (max 6 seconds — 3s poll + buffer)
        start = time.time()
        found = False
        for _ in range(60):
            coins = page.locator("[data-coins-label]")
            if coins.count() > 0 and "200" in coins.inner_text():
                found = True
                break
            page.wait_for_timeout(100)

        elapsed = time.time() - start
        assert found, f"Coins badge did not update to 200 within 6s (waited {elapsed:.1f}s)"


class TestSettingsImpact:
    """Verify that settings changes reflect in the UI."""

    def test_watchlist_filters_signal_display(self, page: Page, _e2e_server: str, app):
        """When watchlist is set, only matching signals should appear."""
        with app.app_context():
            Signal.query.delete()
            rule = DetectionRule.query.first()
            now = datetime.now(timezone.utc)
            for sym in ["AAAUSDT", "BBBUSDT"]:
                db.session.add(Signal(
                    exchange="bybit", symbol=sym, rule_id=rule.id,
                    change_pct=3.0, window="2m", price=100.0, event_ts=now,
                ))
            db.session.commit()

            set_setting("watchlist", ["AAAUSDT"])
            set_setting("blacklist", [])

        page.goto(_e2e_server)
        page.wait_for_timeout(3000)

        body = page.content()
        assert "AAAUSDT" in body
        assert "BBBUSDT" not in body

        # Cleanup
        with app.app_context():
            set_setting("watchlist", [])
            Signal.query.delete()
            db.session.commit()
