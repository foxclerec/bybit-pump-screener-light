# tests/integration/test_auto_update.py
"""Integration test: auto-update checker with mocked GitHub API.

Tests:
- Version comparison logic
- API endpoint returns correct data
- Handles no releases (404)
- Handles newer version available
- Handles network errors gracefully
"""

import time
import threading
from unittest.mock import patch, MagicMock

import pytest

from app.services.update_checker import (
    _parse_version,
    _fetch_latest,
    get_update_info,
    _cached,
    _lock,
)


class TestVersionParsing:
    """Test semver parsing logic."""

    def test_parse_basic(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_parse_with_v_prefix(self):
        assert _parse_version("v1.2.3") == (1, 2, 3)

    def test_parse_with_V_prefix(self):
        assert _parse_version("V2.0.0") == (2, 0, 0)

    def test_parse_two_parts(self):
        assert _parse_version("1.0") == (1, 0)

    def test_parse_empty(self):
        assert _parse_version("") == ()

    def test_parse_garbage(self):
        assert _parse_version("not-a-version") == ()

    def test_comparison_newer(self):
        assert _parse_version("2.0.0") > _parse_version("1.99.99")

    def test_comparison_equal(self):
        assert _parse_version("1.41.0") == _parse_version("v1.41.0")

    def test_comparison_patch(self):
        assert _parse_version("1.41.1") > _parse_version("1.41.0")


class TestUpdateCheckEndpoint:
    """Test /api/update-check endpoint."""

    def test_endpoint_returns_json(self, client):
        resp = client.get("/api/update-check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "available" in data
        assert "current_version" in data
        assert "latest_version" in data
        assert "download_url" in data
        assert "checked_at" in data

    def test_current_version_matches_constant(self, client):
        from app.constants import APP_VERSION
        resp = client.get("/api/update-check")
        data = resp.get_json()
        assert data["current_version"] == APP_VERSION


class TestFetchLatest:
    """Test _fetch_latest with mocked HTTP responses."""

    def _reset_cached(self):
        """Reset module-level cache to defaults."""
        import app.services.update_checker as uc
        with uc._lock:
            uc._cached = {
                "available": False,
                "current_version": uc.APP_VERSION,
                "latest_version": None,
                "download_url": None,
                "checked_at": None,
            }

    def test_no_releases_404(self):
        self._reset_cached()
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("app.services.update_checker.httpx.get", return_value=mock_resp):
            _fetch_latest()

        import app.services.update_checker as uc
        with uc._lock:
            assert uc._cached["checked_at"] is not None
            assert uc._cached["available"] is False

    def test_newer_version_available(self):
        self._reset_cached()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/test/releases/tag/v99.0.0",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.update_checker.httpx.get", return_value=mock_resp):
            _fetch_latest()

        import app.services.update_checker as uc
        with uc._lock:
            assert uc._cached["available"] is True
            assert uc._cached["latest_version"] == "99.0.0"
            assert "v99.0.0" in uc._cached["download_url"]

    def test_same_version_not_available(self):
        self._reset_cached()
        import app.services.update_checker as uc
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": f"v{uc.APP_VERSION}",
            "html_url": "https://github.com/test/releases",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.update_checker.httpx.get", return_value=mock_resp):
            _fetch_latest()

        with uc._lock:
            assert uc._cached["available"] is False

    def test_network_error_graceful(self):
        self._reset_cached()
        with patch("app.services.update_checker.httpx.get", side_effect=Exception("network error")):
            _fetch_latest()

        import app.services.update_checker as uc
        with uc._lock:
            assert uc._cached["checked_at"] is not None
            assert uc._cached["available"] is False
