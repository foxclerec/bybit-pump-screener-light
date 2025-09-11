# app/settings.py
"""DB-first settings: get/set key-value pairs with JSON serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.extensions import db
from app.models import Setting


DEFAULTS: dict[str, object] = {
    # Display
    "timezone": "UTC",
    "rows_per_page": 8,
    "show_coinglass": True,
    "show_tradingview": True,
    # Notifications
    "sound_enabled": True,
    "alert_cooldown_seconds": 15,
    "alert_sound_file": "pulse.wav",
    "tray_enabled": True,
    # Filters
    "min_volume_usd": 300_000,
    "min_age_days": 88,
    "watchlist": [],
    "blacklist": [],
    # Scanning
    "active_exchanges": ["bybit"],
    "poll_seconds": 3,
    "max_klines": 200,
    "dedupe_hold_minutes": 30,
    "kline_interval": "1",
    "category": "linear",
    "auto_quote": "USDT",
    "symbols": ["*"],
    # Debug (internal, no UI)
    "log_level": "INFO",
    "debug_symbols": [],
    "debug_samples": 5,
    "active_rebuild_sec": 3,
    "universe_refresh_sec": 600,
}

SUPPORTED_EXCHANGES: list[str] = ["bybit"]

TIMEZONES: list[str] = [
    "UTC",
    "US/Eastern",
    "US/Central",
    "US/Pacific",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Kyiv",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Australia/Sydney",
]


def get_setting(key: str, default: object = None) -> object:
    """Return the value for *key*, JSON-decoded. Falls back to *default*."""
    row = db.session.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return row.value


def set_setting(key: str, value: object) -> None:
    """Upsert a setting. *value* is JSON-serialized before storage."""
    now = datetime.now(timezone.utc)
    serialized = json.dumps(value)
    row = db.session.get(Setting, key)
    if row:
        row.value = serialized
        row.updated_at = now
    else:
        row = Setting(key=key, value=serialized, updated_at=now)
        db.session.add(row)
    db.session.commit()


def seed_defaults() -> None:
    """Insert default settings for keys that don't exist yet."""
    for key, value in DEFAULTS.items():
        if db.session.get(Setting, key) is None:
            set_setting(key, value)


# Section-to-keys mapping for reset
SECTION_KEYS: dict[str, list[str]] = {
    "notifications": ["sound_enabled", "alert_cooldown_seconds", "alert_sound_file", "tray_enabled", "dedupe_hold_minutes", "poll_seconds"],
    "filters": ["min_volume_usd", "min_age_days", "watchlist", "blacklist"],
    "display": ["timezone", "rows_per_page", "show_coinglass", "show_tradingview"],
    "advanced": ["poll_seconds", "max_klines", "active_exchanges"],
}

# Default detection rule (must match init-db seed)
DEFAULT_RULE: dict = {
    "name": "Pump 2%/2m",
    "lookback_min": 2,
    "threshold_pct": 2.0,
    "color": "#10b981",
    "sound_file": "pulse.mp3",
    "sort_order": 0,
}


def reset_section(section: str) -> bool:
    """Reset a single section to defaults. Returns False if unknown section."""
    if section == "rules":
        from app.models import DetectionRule
        DetectionRule.query.delete()
        db.session.add(DetectionRule(**DEFAULT_RULE))
        db.session.commit()
        return True

    keys = SECTION_KEYS.get(section)
    if not keys:
        return False

    for key in keys:
        set_setting(key, DEFAULTS[key])
    return True


def reset_all() -> None:
    """Reset all settings and rules to factory defaults."""
    from app.models import DetectionRule

    for key, value in DEFAULTS.items():
        set_setting(key, value)

    DetectionRule.query.delete()
    db.session.add(DetectionRule(**DEFAULT_RULE))
    db.session.commit()
