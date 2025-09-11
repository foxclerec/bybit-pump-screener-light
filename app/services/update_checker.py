# app/services/update_checker.py
"""Check GitHub Releases for newer app versions."""
from __future__ import annotations

import logging
import threading
import time
from typing import TypedDict

import httpx

from app.constants import APP_VERSION, GITHUB_REPO_URL

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 6 * 3600  # re-check every 6 hours
_REQUEST_TIMEOUT_SEC = 10

# GitHub API endpoint derived from repo URL
# GITHUB_REPO_URL = "https://github.com/foxclerec/bybit-pump-screener-light"
_REPO_SLUG = "/".join(GITHUB_REPO_URL.rstrip("/").split("/")[-2:])
_API_URL = f"https://api.github.com/repos/{_REPO_SLUG}/releases/latest"


class UpdateInfo(TypedDict):
    available: bool
    current_version: str
    latest_version: str | None
    download_url: str | None
    checked_at: float | None


# Module-level cached result
_lock = threading.Lock()
_cached: UpdateInfo = {
    "available": False,
    "current_version": APP_VERSION,
    "latest_version": None,
    "download_url": None,
    "checked_at": None,
}


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse version string like 'v1.39.2' or '1.39.2' into comparable tuple."""
    clean = tag.lstrip("vV").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def _fetch_latest() -> None:
    """Query GitHub Releases API and update cached result."""
    global _cached
    try:
        resp = httpx.get(
            _API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"pump-screener/{APP_VERSION}",
            },
            timeout=_REQUEST_TIMEOUT_SEC,
            follow_redirects=True,
        )
        if resp.status_code == 404:
            # No releases yet — mark as checked so we don't retry immediately
            logger.debug("No GitHub releases found (404)")
            with _lock:
                _cached["checked_at"] = time.time()
            return
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.debug("Update check failed", exc_info=True)
        with _lock:
            _cached["checked_at"] = time.time()
        return

    tag = data.get("tag_name", "")
    html_url = data.get("html_url", "")

    latest = _parse_version(tag)
    current = _parse_version(APP_VERSION)

    if not latest:
        return

    with _lock:
        _cached = {
            "available": latest > current,
            "current_version": APP_VERSION,
            "latest_version": tag.lstrip("vV"),
            "download_url": html_url,
            "checked_at": time.time(),
        }

    if latest > current:
        logger.info("New version available: %s (current: %s)", tag, APP_VERSION)


def get_update_info() -> UpdateInfo:
    """Return cached update info. Re-fetches if stale."""
    with _lock:
        cached = _cached.copy()

    # Trigger background re-check if stale
    if cached["checked_at"] is None or (time.time() - cached["checked_at"]) > CHECK_INTERVAL_SEC:
        threading.Thread(target=_fetch_latest, daemon=True, name="update-check").start()

    return cached


def check_on_startup() -> None:
    """Spawn a background thread to check for updates (non-blocking)."""
    threading.Thread(target=_fetch_latest, daemon=True, name="update-check-startup").start()
