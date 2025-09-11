# tests/unit/test_compute_active.py
"""Unit tests for compute_active() symbol filtering pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.extensions import db
from app.settings import set_setting
from app.screener.helpers import compute_active


def _make_universe(symbols: list[str], age_days: int = 100) -> list[tuple[str, int]]:
    """Create universe list with symbols at the given age."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    day_ms = 86_400_000
    launch_ms = now_ms - age_days * day_ms
    return [(s, launch_ms) for s in symbols]


@pytest.mark.usefixtures("db_session")
class TestComputeActive:

    def test_empty_universe_returns_empty(self, app):
        with app.app_context():
            result = compute_active([], "linear")
            assert result == []

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_all_pass_age_filter(self, mock_vol, app):
        with app.app_context():
            set_setting("min_age_days", 10)
            set_setting("watchlist", [])
            set_setting("blacklist", [])
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert set(result) == {"AAAUSDT", "BBBUSDT"}

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_age_filter_excludes_young(self, mock_vol, app):
        with app.app_context():
            set_setting("min_age_days", 90)
            set_setting("watchlist", [])
            set_setting("blacklist", [])
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            day_ms = 86_400_000
            universe = [
                ("OLDUSDT", now_ms - 100 * day_ms),  # 100 days old
                ("NEWUSDT", now_ms - 5 * day_ms),     # 5 days old
            ]
            result = compute_active(universe, "linear")
            assert "OLDUSDT" in result
            assert "NEWUSDT" not in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_blacklist_excludes(self, mock_vol, app):
        with app.app_context():
            set_setting("min_age_days", 10)
            set_setting("watchlist", [])
            set_setting("blacklist", ["BBBUSDT"])
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert "AAAUSDT" in result
            assert "BBBUSDT" not in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_watchlist_only_mode(self, mock_vol, app):
        """When watchlist is non-empty, ONLY watchlist symbols are returned."""
        with app.app_context():
            set_setting("watchlist", ["AAAUSDT"])
            set_setting("blacklist", [])
            universe = _make_universe(["AAAUSDT", "BBBUSDT", "CCCUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert result == ["AAAUSDT"]

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_watchlist_symbol_not_in_universe_excluded(self, mock_vol, app):
        """Watchlist symbol that doesn't exist on exchange is excluded."""
        with app.app_context():
            set_setting("watchlist", ["AAAUSDT", "DOESNOTEXIST"])
            set_setting("blacklist", [])
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert "AAAUSDT" in result
            assert "DOESNOTEXIST" not in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_watchlist_bypasses_age_filter(self, mock_vol, app):
        """Watchlist symbols are included even if they're too young."""
        with app.app_context():
            set_setting("min_age_days", 90)
            set_setting("watchlist", ["NEWUSDT"])
            set_setting("blacklist", [])
            universe = _make_universe(["NEWUSDT"], age_days=5)
            result = compute_active(universe, "linear")
            assert "NEWUSDT" in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_watchlist_plus_blacklist(self, mock_vol, app):
        """Blacklist overrides watchlist."""
        with app.app_context():
            set_setting("watchlist", ["AAAUSDT", "BBBUSDT"])
            set_setting("blacklist", ["BBBUSDT"])
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert "AAAUSDT" in result
            assert "BBBUSDT" not in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_want_counts(self, mock_vol, app):
        with app.app_context():
            set_setting("min_age_days", 10)
            set_setting("watchlist", [])
            set_setting("blacklist", [])
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)
            result, aged_cnt = compute_active(universe, "linear", want_counts=True)
            assert isinstance(result, list)
            assert aged_cnt == 2

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_case_insensitive_watchlist(self, mock_vol, app):
        """Watchlist comparison should be case-insensitive (uppercased)."""
        with app.app_context():
            set_setting("watchlist", ["btcusdt"])  # lowercase input
            set_setting("blacklist", [])
            universe = _make_universe(["BTCUSDT"], age_days=100)
            result = compute_active(universe, "linear")
            assert "BTCUSDT" in result

    @patch("app.screener.helpers.filter_symbols_by_turnover", side_effect=lambda syms, **kw: syms)
    def test_settings_read_dynamically(self, mock_vol, app):
        """Settings should be re-read on every call (no caching)."""
        with app.app_context():
            set_setting("watchlist", [])
            set_setting("blacklist", [])
            set_setting("min_age_days", 10)
            universe = _make_universe(["AAAUSDT", "BBBUSDT"], age_days=100)

            r1 = compute_active(universe, "linear")
            assert len(r1) == 2

            set_setting("blacklist", ["BBBUSDT"])
            r2 = compute_active(universe, "linear")
            assert len(r2) == 1
            assert "BBBUSDT" not in r2
