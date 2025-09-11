# tests/unit/test_settings.py
"""Unit tests for the DB-first settings module."""

import pytest
from app.settings import get_setting, set_setting, seed_defaults, DEFAULTS


@pytest.mark.usefixtures("db_session")
class TestSettings:
    """Tests for get_setting / set_setting / seed_defaults."""

    def test_get_missing_key_returns_default(self, app):
        with app.app_context():
            assert get_setting("nonexistent") is None
            assert get_setting("nonexistent", "fallback") == "fallback"

    def test_set_and_get_string(self, app):
        with app.app_context():
            set_setting("test_str", "hello")
            assert get_setting("test_str") == "hello"

    def test_set_and_get_int(self, app):
        with app.app_context():
            set_setting("test_int", 42)
            assert get_setting("test_int") == 42

    def test_set_and_get_bool(self, app):
        with app.app_context():
            set_setting("test_bool", True)
            assert get_setting("test_bool") is True

    def test_set_and_get_float(self, app):
        with app.app_context():
            set_setting("test_float", 3.14)
            result = get_setting("test_float")
            assert result == pytest.approx(3.14)

    def test_set_updates_existing(self, app):
        with app.app_context():
            set_setting("test_update", "old")
            set_setting("test_update", "new")
            assert get_setting("test_update") == "new"

    def test_seed_defaults_creates_all_keys(self, app):
        with app.app_context():
            # seed_defaults already called in conftest, just verify
            for key in DEFAULTS:
                val = get_setting(key)
                assert val is not None, f"Default key {key!r} missing"

    def test_seed_defaults_does_not_overwrite(self, app):
        with app.app_context():
            set_setting("timezone", "US/Eastern")
            seed_defaults()
            assert get_setting("timezone") == "US/Eastern"
