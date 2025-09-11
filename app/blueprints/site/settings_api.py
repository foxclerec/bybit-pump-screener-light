# app/blueprints/site/settings_api.py
"""Settings and rules CRUD API endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from app.extensions import db

# Available rule colors (label -> hex)
RULE_COLORS: list[dict[str, str]] = [
    {"name": "Emerald", "hex": "#10b981"},
    {"name": "Amber", "hex": "#f59e0b"},
    {"name": "Red", "hex": "#ef4444"},
    {"name": "Blue", "hex": "#3b82f6"},
    {"name": "Purple", "hex": "#a855f7"},
    {"name": "Cyan", "hex": "#06b6d4"},
]

def _sounds_dir() -> Path:
    relative = Path(__file__).resolve().parent.parent.parent / "screener" / "assets"
    if relative.exists():
        return relative
    if getattr(sys, "frozen", False):
        frozen = Path(sys._MEIPASS) / "app" / "screener" / "assets"
        if frozen.exists():
            return frozen
    return relative

SOUNDS_DIR = _sounds_dir()

bp = Blueprint("settings_api", __name__)


def _list_sounds() -> list[str]:
    """Return sorted list of unique sound names (without extension)."""
    if not SOUNDS_DIR.is_dir():
        return []
    names = set()
    for f in SOUNDS_DIR.iterdir():
        if f.suffix.lower() in (".mp3", ".wav") and f.is_file():
            names.add(f.stem.capitalize())
    return sorted(names)


def _resolve_sound_file(name: str) -> str | None:
    """Resolve a display name or filename (e.g. 'Chime', 'chime.wav') to actual filename on disk."""
    from pathlib import PurePosixPath
    stem = PurePosixPath(name).stem.lower()
    for ext in (".wav", ".mp3"):
        candidate = SOUNDS_DIR / (stem + ext)
        if candidate.is_file():
            return candidate.name
    return None


# -------- Rules CRUD API --------

def _rule_to_dict(rule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "lookback_min": rule.lookback_min,
        "threshold_pct": rule.threshold_pct,
        "color": rule.color,
        "sound_file": rule.sound_file,
        "enabled": rule.enabled,
        "sort_order": rule.sort_order,
    }


def _validate_rule_data(data: dict) -> str | None:
    """Return error message or None if valid."""
    name = (data.get("name") or "").strip()
    if not name or len(name) > 32:
        return "Name is required (max 32 chars)"

    lookback = data.get("lookback_min")
    if not isinstance(lookback, (int, float)) or not (1 <= lookback <= 60):
        return "Lookback must be 1\u201360 minutes"

    threshold = data.get("threshold_pct")
    if not isinstance(threshold, (int, float)) or not (0.3 <= threshold <= 50):
        return "Threshold must be 0.3\u201350%"

    color = data.get("color", "")
    valid_hexes = {c["hex"] for c in RULE_COLORS}
    if color not in valid_hexes:
        return "Invalid color"

    return None


@bp.get('/api/rules/<int:rule_id>')
def api_get_rule(rule_id: int):
    from app.models import DetectionRule
    rule = db.session.get(DetectionRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404
    return jsonify(_rule_to_dict(rule))


@bp.post('/api/rules')
def api_create_rule():
    from app.models import DetectionRule
    data = request.get_json(silent=True) or {}
    err = _validate_rule_data(data)
    if err:
        return jsonify({"error": err}), 400

    max_order = db.session.query(db.func.max(DetectionRule.sort_order)).scalar() or 0
    rule = DetectionRule(
        name=data["name"].strip(),
        lookback_min=int(data["lookback_min"]),
        threshold_pct=float(data["threshold_pct"]),
        color=data["color"],
        sound_file=data.get("sound_file") or None,
        enabled=bool(data.get("enabled", True)),
        sort_order=max_order + 1,
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(_rule_to_dict(rule)), 201


@bp.put('/api/rules/<int:rule_id>')
def api_update_rule(rule_id: int):
    from app.models import DetectionRule
    rule = db.session.get(DetectionRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    data = request.get_json(silent=True) or {}
    err = _validate_rule_data(data)
    if err:
        return jsonify({"error": err}), 400

    rule.name = data["name"].strip()
    rule.lookback_min = int(data["lookback_min"])
    rule.threshold_pct = float(data["threshold_pct"])
    rule.color = data["color"]
    rule.sound_file = data.get("sound_file") or None
    rule.enabled = bool(data.get("enabled", True))
    db.session.commit()
    return jsonify(_rule_to_dict(rule))


@bp.patch('/api/rules/<int:rule_id>')
def api_patch_rule(rule_id: int):
    from app.models import DetectionRule
    rule = db.session.get(DetectionRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        rule.enabled = bool(data["enabled"])
    db.session.commit()
    return jsonify(_rule_to_dict(rule))


@bp.delete('/api/rules/<int:rule_id>')
def api_delete_rule(rule_id: int):
    from app.models import DetectionRule
    rule = db.session.get(DetectionRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404

    # Prevent deleting the last rule
    if DetectionRule.query.count() <= 1:
        return jsonify({"error": "Cannot delete the last rule"}), 400

    db.session.delete(rule)
    db.session.commit()
    return jsonify({"ok": True})


# -------- Notifications Settings API --------

@bp.get('/api/settings/notifications')
def api_get_notifications():
    from app.settings import get_setting, DEFAULTS
    return jsonify({
        "sound_enabled": get_setting("sound_enabled", DEFAULTS["sound_enabled"]),
        "alert_cooldown_seconds": get_setting("alert_cooldown_seconds", DEFAULTS["alert_cooldown_seconds"]),
        "alert_sound_file": get_setting("alert_sound_file", DEFAULTS["alert_sound_file"]),
        "dedupe_hold_minutes": get_setting("dedupe_hold_minutes", DEFAULTS["dedupe_hold_minutes"]),
        "poll_seconds": get_setting("poll_seconds", DEFAULTS["poll_seconds"]),
    })


@bp.put('/api/settings/notifications')
def api_update_notifications():
    from app.settings import set_setting
    data = request.get_json(silent=True) or {}

    sound_enabled = data.get("sound_enabled")
    if not isinstance(sound_enabled, bool):
        return jsonify({"error": "sound_enabled must be a boolean"}), 400

    cooldown = data.get("alert_cooldown_seconds")
    if not isinstance(cooldown, (int, float)) or not (5 <= cooldown <= 300):
        return jsonify({"error": "Cooldown must be 5\u2013300 seconds"}), 400

    sound_name = data.get("alert_sound_file", "")
    if sound_name:
        resolved = _resolve_sound_file(sound_name)
        if not resolved:
            return jsonify({"error": "Unknown sound"}), 400

    dedupe = data.get("dedupe_hold_minutes")
    if dedupe is not None:
        if not isinstance(dedupe, (int, float)) or not (0 <= dedupe <= 1440):
            return jsonify({"error": "Dedup hold must be 0–1440 minutes"}), 400
        set_setting("dedupe_hold_minutes", int(dedupe))

    poll = data.get("poll_seconds")
    if poll is not None:
        if not isinstance(poll, (int, float)) or not (1 <= poll <= 60):
            return jsonify({"error": "Poll interval must be 1–60 seconds"}), 400
        set_setting("poll_seconds", int(poll))

    set_setting("sound_enabled", sound_enabled)
    set_setting("alert_cooldown_seconds", int(cooldown))
    if sound_name:
        set_setting("alert_sound_file", resolved)
    return jsonify({"ok": True})


# -------- Symbols API --------

_symbols_cache: dict[str, object] = {"symbols": [], "ts": 0.0}
_SYMBOLS_TTL = 600  # 10 min cache


@bp.get('/api/symbols')
def api_symbols():
    """Return list of tradable USDT symbols from Bybit (cached 10 min)."""
    import time
    now = time.time()
    if now - _symbols_cache["ts"] > _SYMBOLS_TTL or not _symbols_cache["symbols"]:
        try:
            from app.exchanges.bybit.client import fetch_symbols
            _symbols_cache["symbols"] = sorted(fetch_symbols())
            _symbols_cache["ts"] = now
        except Exception:
            if _symbols_cache["symbols"]:
                return jsonify(_symbols_cache["symbols"])
            return jsonify([])
    return jsonify(_symbols_cache["symbols"])


# -------- Filters Settings API --------

MAX_TAG_LEN = 24
MAX_TAGS = 100


def _get_valid_symbols() -> set[str]:
    """Return cached set of valid exchange symbols for validation."""
    if _symbols_cache["symbols"]:
        return set(_symbols_cache["symbols"])
    try:
        from app.exchanges.bybit.client import fetch_symbols
        import time
        syms = sorted(fetch_symbols())
        _symbols_cache["symbols"] = syms
        _symbols_cache["ts"] = time.time()
        return set(syms)
    except Exception:
        return set()


def _clean_symbol_list(raw: list) -> list[str]:
    """Sanitize, deduplicate, and validate symbols against exchange."""
    valid = _get_valid_symbols()
    seen: set[str] = set()
    result: list[str] = []
    for item in raw[:MAX_TAGS]:
        tag = "".join(ch for ch in str(item).upper() if ch.isalnum())[:MAX_TAG_LEN]
        if tag and tag not in seen:
            if valid and tag not in valid:
                continue  # skip invalid symbols silently
            seen.add(tag)
            result.append(tag)
    return result


@bp.get('/api/settings/filters')
def api_get_filters():
    from app.settings import get_setting, DEFAULTS
    return jsonify({
        "min_volume_usd": get_setting("min_volume_usd", DEFAULTS["min_volume_usd"]),
        "min_age_days": get_setting("min_age_days", DEFAULTS["min_age_days"]),
        "watchlist": get_setting("watchlist", DEFAULTS["watchlist"]),
        "blacklist": get_setting("blacklist", DEFAULTS["blacklist"]),
    })


@bp.put('/api/settings/filters')
def api_update_filters():
    from app.settings import set_setting
    data = request.get_json(silent=True) or {}

    vol = data.get("min_volume_usd")
    if not isinstance(vol, (int, float)) or not (0 <= vol <= 50_000_000):
        return jsonify({"error": "Volume must be 0\u201350,000,000"}), 400

    age = data.get("min_age_days")
    if not isinstance(age, (int, float)) or not (0 <= age <= 365):
        return jsonify({"error": "Age must be 0\u2013365 days"}), 400

    wl = data.get("watchlist")
    if not isinstance(wl, list):
        return jsonify({"error": "watchlist must be an array"}), 400

    bl = data.get("blacklist")
    if not isinstance(bl, list):
        return jsonify({"error": "blacklist must be an array"}), 400

    set_setting("min_volume_usd", int(vol))
    set_setting("min_age_days", int(age))
    set_setting("watchlist", _clean_symbol_list(wl))
    set_setting("blacklist", _clean_symbol_list(bl))
    return jsonify({"ok": True})


# -------- Display Settings API --------

@bp.get('/api/settings/display')
def api_get_display():
    from app.settings import get_setting, DEFAULTS
    return jsonify({
        "timezone": get_setting("timezone", DEFAULTS["timezone"]),
        "rows_per_page": get_setting("rows_per_page", DEFAULTS["rows_per_page"]),
        "show_coinglass": get_setting("show_coinglass", DEFAULTS["show_coinglass"]),
        "show_tradingview": get_setting("show_tradingview", DEFAULTS["show_tradingview"]),
    })


@bp.put('/api/settings/display')
def api_update_display():
    from app.settings import set_setting, TIMEZONES
    data = request.get_json(silent=True) or {}

    tz = data.get("timezone")
    if not isinstance(tz, str) or tz not in TIMEZONES:
        return jsonify({"error": "Invalid timezone"}), 400

    rows = data.get("rows_per_page")
    if not isinstance(rows, (int, float)) or not (5 <= rows <= 100):
        return jsonify({"error": "Rows per page must be 5\u2013100"}), 400

    show_cg = data.get("show_coinglass")
    if not isinstance(show_cg, bool):
        return jsonify({"error": "show_coinglass must be a boolean"}), 400

    show_tv = data.get("show_tradingview")
    if not isinstance(show_tv, bool):
        return jsonify({"error": "show_tradingview must be a boolean"}), 400

    set_setting("timezone", tz)
    set_setting("rows_per_page", int(rows))
    set_setting("show_coinglass", show_cg)
    set_setting("show_tradingview", show_tv)
    return jsonify({"ok": True})


# -------- Advanced Settings API --------

@bp.get('/api/settings/advanced')
def api_get_advanced():
    from app.settings import get_setting, DEFAULTS
    return jsonify({
        "poll_seconds": get_setting("poll_seconds", DEFAULTS["poll_seconds"]),
        "max_klines": get_setting("max_klines", DEFAULTS["max_klines"]),
        "active_exchanges": get_setting("active_exchanges", DEFAULTS["active_exchanges"]),
    })


@bp.put('/api/settings/advanced')
def api_update_advanced():
    from app.settings import set_setting, SUPPORTED_EXCHANGES
    data = request.get_json(silent=True) or {}

    poll = data.get("poll_seconds")
    if not isinstance(poll, (int, float)) or not (5 <= poll <= 60):
        return jsonify({"error": "Poll interval must be 5\u201360 seconds"}), 400

    klines = data.get("max_klines")
    if not isinstance(klines, (int, float)) or not (10 <= klines <= 500):
        return jsonify({"error": "Max klines must be 10\u2013500"}), 400

    exchanges = data.get("active_exchanges")
    if not isinstance(exchanges, list) or not exchanges:
        return jsonify({"error": "At least one exchange must be selected"}), 400
    clean = [e for e in exchanges if e in SUPPORTED_EXCHANGES]
    if not clean:
        return jsonify({"error": "At least one valid exchange must be selected"}), 400

    set_setting("poll_seconds", int(poll))
    set_setting("max_klines", int(klines))
    set_setting("active_exchanges", clean)
    return jsonify({"ok": True})


# -------- Reset to defaults API --------

@bp.post('/api/settings/reset/<section>')
def api_reset_section(section: str):
    """Reset a single settings section to defaults."""
    from app.settings import reset_section
    if not reset_section(section):
        return jsonify({"error": "Unknown section"}), 400
    return jsonify({"ok": True})


@bp.post('/api/settings/reset')
def api_reset_all():
    """Reset all settings and rules to factory defaults."""
    from app.settings import reset_all
    reset_all()
    return jsonify({"ok": True})


# -------- Sound files API --------

@bp.get('/api/sounds')
def api_list_sounds():
    return jsonify(_list_sounds())


@bp.get('/api/sounds/<path:filename>')
def api_serve_sound(filename: str):
    """Serve a sound file for browser preview. Accepts display name or filename."""
    safe_name = Path(filename).name  # prevent directory traversal
    # Try resolving display name (e.g. "Chime") to actual file
    resolved = _resolve_sound_file(safe_name)
    if resolved:
        return send_from_directory(SOUNDS_DIR, resolved)
    return send_from_directory(SOUNDS_DIR, safe_name)
