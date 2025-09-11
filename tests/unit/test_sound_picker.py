# tests/unit/test_sound_picker.py
"""Unit tests for sound picker: file listing, resolution, validation."""

from __future__ import annotations

import pytest
from pathlib import Path


class TestListSounds:
    """_list_sounds() scans assets/ and returns capitalized stems."""

    def test_returns_list(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _list_sounds
            result = _list_sounds()
            assert isinstance(result, list)

    def test_contains_known_sounds(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _list_sounds
            result = _list_sounds()
            assert "Pulse" in result
            assert "Boom" in result

    def test_sorted_alphabetically(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _list_sounds
            result = _list_sounds()
            assert result == sorted(result)

    def test_no_duplicates(self, app):
        """mp3 and wav of the same name should produce one entry."""
        with app.app_context():
            from app.blueprints.site.settings_api import _list_sounds
            result = _list_sounds()
            assert len(result) == len(set(result))


class TestResolveSoundFile:
    """_resolve_sound_file() accepts display names and filenames."""

    def test_resolve_display_name(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _resolve_sound_file
            assert _resolve_sound_file("Pulse") == "pulse.wav"
            assert _resolve_sound_file("Boom") == "boom.wav"

    def test_resolve_filename_with_extension(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _resolve_sound_file
            assert _resolve_sound_file("pulse.wav") == "pulse.wav"
            assert _resolve_sound_file("boom.wav") == "boom.wav"

    def test_resolve_lowercase(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _resolve_sound_file
            assert _resolve_sound_file("pulse") == "pulse.wav"
            assert _resolve_sound_file("boom") == "boom.wav"

    def test_resolve_unknown_returns_none(self, app):
        with app.app_context():
            from app.blueprints.site.settings_api import _resolve_sound_file
            assert _resolve_sound_file("nonexistent") is None
            assert _resolve_sound_file("") is None
