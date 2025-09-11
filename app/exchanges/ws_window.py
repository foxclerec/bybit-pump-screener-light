# app/exchanges/ws_window.py
"""Shared rolling-window manager for WebSocket kline clients."""

from __future__ import annotations

import threading
from collections import deque


class KlineWindowManager:
    """Thread-safe rolling window of close prices per symbol.

    Used by all exchange WS clients to avoid duplicating the same
    window logic (append confirmed, replace live, seed, get_closes).
    """

    def __init__(self, window_size: int = 30) -> None:
        self._window_size = window_size
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def update(self, symbol: str, close: float, confirmed: bool) -> list[float]:
        """Update window for *symbol* and return current closes list."""
        with self._lock:
            window = self._windows.get(symbol)
            if window is None:
                window = deque(maxlen=self._window_size)
                self._windows[symbol] = window

            if confirmed:
                window.append(close)
            else:
                if window:
                    window[-1] = close
                else:
                    window.append(close)

            return list(window)

    def get_closes(self, symbol: str) -> list[float] | None:
        """Return closes for *symbol*, or None if not tracked."""
        with self._lock:
            window = self._windows.get(symbol)
            return list(window) if window is not None else None

    def seed(self, symbol: str, closes: list[float]) -> None:
        """Pre-fill window with historical closes (from REST)."""
        with self._lock:
            self._windows[symbol] = deque(
                closes[-self._window_size:], maxlen=self._window_size,
            )

    def remove(self, symbol: str) -> None:
        """Remove a symbol from tracking."""
        with self._lock:
            self._windows.pop(symbol, None)

    def resize(self, new_size: int) -> None:
        """Resize all windows to *new_size* (grows or shrinks)."""
        if new_size == self._window_size:
            return
        with self._lock:
            self._window_size = new_size
            for sym in self._windows:
                old = self._windows[sym]
                self._windows[sym] = deque(old, maxlen=new_size)
