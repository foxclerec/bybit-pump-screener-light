# All settings live here — adjust in code as you wish.

import time
import threading
import httpx
from flask import jsonify
from app.extensions import csrf
from . import bp

# ==== Tunables (edit in code) ================================================

from app.constants import BYBIT_API_BASE
STATUS_PING_ENDPOINT = "/v5/market/time"   # lightweight "are you alive?"
STATUS_TIMEOUT_SEC = 5                     # HTTP timeout for a single probe
STATUS_CACHE_TTL_SEC = 5                   # don't probe more often than this
STATUS_OFFLINE_AFTER_SEC = 35              # age threshold to declare offline
STATUS_FAILS_TO_OFFLINE = 2                # consecutive network fails needed

# If True: rate-limit responses (403/429) still count as "online" connectivity
TREAT_RATE_LIMIT_AS_ONLINE = True

# ==== Module-level state (simple in-memory cache) ============================

_lock = threading.Lock()
_last_check_at = 0.0          # last time we actually probed the API
_last_ok_at = 0.0             # last time we got a "good enough" response
_last_reason = "unknown"       # ok | rate_limited | server_error | http_error | network_down | unknown
_last_latency_ms = None
_consecutive_net_fails = 0

# ==== Helpers ================================================================

def _now() -> float:
    return time.time()

def _http_get(path: str, timeout: int):
    """Lightweight HTTP GET via httpx for exchange health probe."""
    url = f"{BYBIT_API_BASE}{path}"
    t0 = time.perf_counter()
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "status-probe/1.0"},
            timeout=httpx.Timeout(timeout, connect=timeout),
        )
        latency = int((time.perf_counter() - t0) * 1000)
        try:
            data = resp.json()
        except Exception:
            data = None
        return resp.status_code, data, latency
    except (httpx.HTTPStatusError, httpx.HTTPError):
        latency = int((time.perf_counter() - t0) * 1000)
        return None, None, latency

def _classify(status_code: int | None) -> str:
    """Map HTTP outcome to a simple reason string."""
    if status_code is None:
        return "network_down"
    if status_code in (403, 429):
        return "rate_limited"
    if status_code >= 500:
        return "server_error"
    if status_code == 200:
        return "ok"
    return "http_error"

def _probe_if_needed():
    """Run a probe if cache is stale. Updates module state."""
    global _last_check_at, _last_ok_at, _last_reason, _last_latency_ms, _consecutive_net_fails

    now = _now()
    if now - _last_check_at < STATUS_CACHE_TTL_SEC:
        return  # cached

    status_code, _, latency = _http_get(STATUS_PING_ENDPOINT, STATUS_TIMEOUT_SEC)
    reason = _classify(status_code)

    # classify and update state
    if reason == "network_down":
        _consecutive_net_fails += 1
    else:
        _consecutive_net_fails = 0

    # "good enough" connectivity: ok or (rate-limited and we treat it as online)
    good_connectivity = (reason == "ok") or (TREAT_RATE_LIMIT_AS_ONLINE and reason == "rate_limited")
    if good_connectivity:
        _last_ok_at = now

    _last_reason = reason
    _last_latency_ms = latency
    _last_check_at = now

@bp.get("/status")
def get_exchange_status():
    """
    Exchange connectivity status for the footer badge.
    Public endpoint — no auth required.
    """
    with _lock:
        _probe_if_needed()

        now = _now()
        age = int(now - _last_ok_at) if _last_ok_at else None

        hard_offline = _consecutive_net_fails >= STATUS_FAILS_TO_OFFLINE

        online = False
        if _last_ok_at:
            online = (now - _last_ok_at) <= STATUS_OFFLINE_AFTER_SEC
        if hard_offline:
            online = False

        payload = {
            "online": online,
            "reason": _last_reason,
            "checked_at": int(_last_check_at) if _last_check_at else None,
            "last_ok_at": int(_last_ok_at) if _last_ok_at else None,
            "last_ok_age_sec": age,
            "latency_ms": _last_latency_ms,
            "fails_in_row": _consecutive_net_fails,
            "settings": {
                "ttl_sec": STATUS_CACHE_TTL_SEC,
                "offline_after_sec": STATUS_OFFLINE_AFTER_SEC,
            },
        }

    # Read active coin count and screener liveness outside lock (file I/O)
    try:
        from flask import current_app
        from app.screener.metrics_store import get_metric, get_metric_age_sec
        ipath = current_app.instance_path
        payload["active_count"] = get_metric(ipath, "active_count", namespace="screener")
        age = get_metric_age_sec(ipath, "active_count", namespace="screener")
        payload["screener_alive"] = age is not None and age < 30.0
        payload["needs_restart"] = bool(get_metric(ipath, "needs_restart", namespace="screener"))
    except Exception:
        payload["active_count"] = None
        payload["screener_alive"] = False
        payload["needs_restart"] = False

    return jsonify(payload)

@bp.get("/ping")
def ping_app():
    """Simple app heartbeat so the UI can show 'app: connected'."""
    return jsonify({"ok": True, "ts": int(_now())})


@bp.get("/mute")
def get_mute():
    """Return current mute state."""
    from app.screener.utils.tray import is_muted
    return jsonify({"muted": is_muted()})


@bp.post("/mute")
@csrf.exempt
def toggle_mute():
    """Toggle mute state and return new value."""
    from app.screener.utils.tray import toggle_muted
    new_state = toggle_muted()
    return jsonify({"muted": new_state})


@bp.post("/restart")
@csrf.exempt
def restart_app():
    """Trigger full application restart (after sleep/wake)."""
    import os
    import sys
    import subprocess
    from app.screener.runner import _shutdown

    # Signal screener to stop
    _shutdown.set()

    # Clear needs_restart flag
    try:
        from flask import current_app
        from app.screener.metrics_store import set_metric
        set_metric(current_app.instance_path, "needs_restart", False, namespace="screener")
    except Exception:
        pass

    # Launch a new process with delay so current one has time to fully exit
    if getattr(sys, "frozen", False):
        exe = sys.executable
        # Use cmd /c with timeout to delay the new process start
        subprocess.Popen(
            f'cmd /c timeout /t 3 /nobreak >nul && "{exe}"',
            shell=True, close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        )

    # Exit current process
    import threading
    def _delayed_exit():
        import time
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()

    return jsonify({"ok": True, "message": "Restarting..."})


@bp.get("/update-check")
def update_check():
    """Return cached update-availability info (GitHub Releases)."""
    from app.services.update_checker import get_update_info
    return jsonify(get_update_info())
