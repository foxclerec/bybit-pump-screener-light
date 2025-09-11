# main.py
"""Desktop entry point — launches Flask + screener inside a native pywebview window.

Architecture (single process, multi-thread):
    Main thread:   webview.start()         — native GUI event loop (blocks)
      Thread 1:    Flask (werkzeug)        — threaded WSGI server on random port
      Thread 2:    Screener scan loop      — started once on window.initialized
      Thread 3:    System tray (pystray)   — started alongside screener

Usage:
    python main.py                          # production desktop mode
    flask --app app:create_app run          # dev mode (no pywebview)
    flask --app app:create_app screener-run # dev mode (screener only)
"""

from __future__ import annotations

import atexit
import socket
import sys
import threading
from pathlib import Path

import webview
from werkzeug.serving import make_server

from app import create_app
from app.constants import APP_VERSION
from app.paths import get_data_dir, is_frozen
from app.screener.runner import run_screener, _shutdown
from app.screener.utils.tray import TrayManager, set_tray, get_tray
from app.settings import get_setting

_LOCK_NAME = "pump_screener.lock"


def _get_icon_path() -> str | None:
    """Resolve icon path — works in both dev and frozen (PyInstaller) mode."""
    if is_frozen():
        p = Path(sys._MEIPASS) / "app" / "static" / "favicon" / "favicon.ico"
    else:
        p = Path(__file__).parent / "app" / "static" / "favicon" / "favicon.ico"
    return str(p) if p.exists() else None


# ---------------------------------------------------------------------------
# Single-instance guard
# ---------------------------------------------------------------------------

def _lock_path() -> Path:
    return get_data_dir() / _LOCK_NAME


def _is_already_running() -> bool:
    lock = _lock_path()
    if not lock.exists():
        return False
    try:
        port = int(lock.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _write_lock(port: int) -> None:
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(port), encoding="utf-8")


def _remove_lock() -> None:
    try:
        _lock_path().unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if _is_already_running():
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Pump Screener is already running.\nCheck the system tray.",
                "Pump Screener",
                0x40,
            )
        except Exception:
            print("Pump Screener is already running.", flush=True)
        sys.exit(0)

    app = create_app()

    # Start Flask on a threaded werkzeug server
    port = _find_free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    flask_thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="flask-server",
    )
    flask_thread.start()

    _write_lock(port)
    atexit.register(_remove_lock)

    window = webview.create_window(
        title=f"Pump Screener v{APP_VERSION}",
        url=f"http://127.0.0.1:{port}",
        width=1200,
        height=800,
        confirm_close=True,
    )

    _force_quit = threading.Event()

    def _on_started() -> None:
        """Fires ONCE when the GUI is initialized (not on every page navigation)."""
        # System tray
        with app.app_context():
            tray_on = get_setting("tray_enabled", True)
        if tray_on:
            tray = TrayManager(
                on_quit=lambda: (_force_quit.set(), _shutdown.set()),
                window=window,
            )
            if tray.available:
                set_tray(tray)
                tray.start()

        # Screener loop
        screener = threading.Thread(
            target=run_screener, args=(app,), daemon=True, name="screener",
        )
        screener.start()

    def _on_closing() -> bool:
        if _force_quit.is_set():
            return True
        tray = get_tray()
        if tray is not None and tray.available:
            window.hide()
            return False
        return True

    def _on_closed() -> None:
        _shutdown.set()
        server.shutdown()

    # 'initialized' fires ONCE per window lifecycle (not on navigation)
    window.events.initialized += _on_started
    window.events.closing += _on_closing
    window.events.closed += _on_closed

    webview.start(
        private_mode=False,
        icon=_get_icon_path(),
    )


if __name__ == "__main__":
    main()
