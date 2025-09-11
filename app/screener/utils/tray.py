# app/screener/utils/tray.py
"""System tray icon with Mute toggle and Quit action via pystray."""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_WEB_URL = "http://127.0.0.1:5000"
_ICON_SIZE = 64


def _load_icon():
    """Load tray icon image. Favicon on Windows, generated square otherwise."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("[tray] Pillow not installed, cannot create icon")
        return None

    # Try favicon.ico (Windows gets best quality from .ico)
    if sys.platform == "win32":
        ico_path = (
            Path(__file__).resolve().parents[2] / "static" / "favicon" / "favicon.ico"
        )
        # Frozen mode (PyInstaller): look under sys._MEIPASS
        if not ico_path.exists() and getattr(sys, "frozen", False):
            ico_path = Path(sys._MEIPASS) / "app" / "static" / "favicon" / "favicon.ico"
        if ico_path.exists():
            try:
                return Image.open(ico_path)
            except Exception:
                pass

    # Fallback: generate a simple green square
    img = Image.new("RGB", (_ICON_SIZE, _ICON_SIZE), "#10b981")
    dc = ImageDraw.Draw(img)
    # Draw a small "P" indicator
    dc.rectangle(
        (_ICON_SIZE // 4, _ICON_SIZE // 4, 3 * _ICON_SIZE // 4, 3 * _ICON_SIZE // 4),
        fill="#065f46",
    )
    return img


class TrayManager:
    """Manages the system tray icon lifecycle and mute state.

    Usage::

        tray = TrayManager(on_quit=shutdown_event.set)
        tray.start()       # non-blocking, runs icon in daemon thread
        tray.is_muted()    # thread-safe mute check
        tray.stop()        # teardown
    """

    def __init__(
        self,
        on_quit: Optional[Callable[[], None]] = None,
        window: object = None,
    ) -> None:
        self._on_quit = on_quit
        self._window = window  # pywebview window (None in CLI mode)
        self._icon = None
        self._thread: Optional[threading.Thread] = None
        self._available = False

        try:
            import pystray  # noqa: F401
            self._available = True
        except ImportError:
            logger.warning("[tray] pystray not installed, tray disabled")

    @property
    def available(self) -> bool:
        return self._available

    def is_muted(self) -> bool:
        """Thread-safe mute state check (delegates to module-level state)."""
        return _muted.is_set()

    def start(self) -> None:
        """Start the tray icon in a daemon thread. No-op if unavailable."""
        if not self._available:
            return
        try:
            self._icon = self._build_icon()
            if self._icon is None:
                logger.warning("[tray] could not build icon, tray disabled")
                self._available = False
                return
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="tray-icon"
            )
            self._thread.start()
            logger.debug("[tray] system tray started")
        except Exception as exc:
            logger.warning(f"[tray] start failed: {exc!r}")
            self._available = False

    def stop(self) -> None:
        """Stop the tray icon gracefully."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def _run(self) -> None:
        """Blocking run in daemon thread."""
        try:
            self._icon.run()
        except Exception as exc:
            logger.warning(f"[tray] run error: {exc!r}")

    def _build_icon(self):
        """Create the pystray Icon with menu."""
        import pystray

        image = _load_icon()
        if image is None:
            return None

        menu = pystray.Menu(
            pystray.MenuItem("Open", self._on_open, default=True),
            pystray.MenuItem(
                "Mute",
                self._on_mute,
                checked=lambda item: _muted.is_set(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit_click),
        )
        return pystray.Icon("pump-screener", icon=image, title="Pump Screener", menu=menu)

    def _on_open(self, icon, item) -> None:
        """Show the pywebview window, or fall back to browser in CLI mode."""
        if self._window is not None:
            try:
                self._window.show()
                self._window.restore()
            except Exception as exc:
                logger.debug(f"[tray] window show failed: {exc!r}")
            return
        try:
            webbrowser.open(_WEB_URL)
        except Exception as exc:
            logger.debug(f"[tray] open browser failed: {exc!r}")

    def _on_mute(self, icon, item) -> None:
        """Toggle mute state via tray menu."""
        toggle_muted()

    def _on_quit_click(self, icon, item) -> None:
        """Stop tray and signal the screener to shut down."""
        logger.info("[tray] quit requested")
        self.stop()
        if self._on_quit:
            self._on_quit()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass


# ---------- Module-level mute state (works with or without tray) ----------
_muted = threading.Event()


def is_muted() -> bool:
    """Check global mute state. Works with or without system tray."""
    return _muted.is_set()


def set_muted(value: bool) -> None:
    """Set global mute state from any source (tray, API, etc.)."""
    if value:
        _muted.set()
        logger.info("[mute] muted")
    else:
        _muted.clear()
        logger.info("[mute] unmuted")


def toggle_muted() -> bool:
    """Toggle mute and return new state."""
    new_state = not _muted.is_set()
    set_muted(new_state)
    return new_state


# Module-level singleton (lazy, set by runner)
_instance: Optional[TrayManager] = None


def get_tray() -> Optional[TrayManager]:
    """Return the active TrayManager singleton, or None."""
    return _instance


def set_tray(tray: TrayManager) -> None:
    """Register the TrayManager singleton."""
    global _instance
    _instance = tray
