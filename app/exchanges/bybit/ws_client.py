# app/exchanges/bybit/ws_client.py
"""Bybit v5 WebSocket client for real-time kline (candlestick) streams."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from pybit.unified_trading import WebSocket

from app.exchanges.circuit_breaker import CircuitBreaker
from app.exchanges.ws_backoff import compute_backoff
from app.exchanges.ws_window import KlineWindowManager

logger = logging.getLogger(__name__)

# Batch size for subscribe calls (azzyt-bybit pattern)
_SUBSCRIBE_BATCH = 10

# Default rolling window size (enough for max lookback + buffer)
_DEFAULT_WINDOW = 30

# Consider WS disconnected if no data received for this many seconds.
# With 277+ symbols streaming 1-min klines, we normally get updates
# every ~1 second.  30 s silence means something is wrong.
_WS_STALE_SEC = 30.0


class BybitKlineWS:
    """Real-time kline stream via Bybit public WebSocket.

    Maintains a rolling window of close prices per symbol. On each kline
    update the on_kline callback is invoked with the latest closes list.

    Usage::

        ws = BybitKlineWS(
            channel_type="linear",
            interval=1,
            on_kline=lambda sym, closes, confirmed: ...,
        )
        ws.subscribe(["BTCUSDT", "ETHUSDT", ...])
        # ... later
        ws.stop()
    """

    def __init__(
        self,
        channel_type: str = "linear",
        interval: int = 1,
        on_kline: Callable[[str, list[float], bool], None] | None = None,
        window_size: int = _DEFAULT_WINDOW,
    ) -> None:
        self._channel_type = channel_type
        self._interval = interval
        self._on_kline = on_kline
        self._window_size = window_size

        self._wm = KlineWindowManager(window_size)
        self._cb = CircuitBreaker(label="bybit-ws")
        self._subscribed: set[str] = set()
        self._connected = False
        self._stop_event = threading.Event()
        self._reconnect_attempt = 0
        self._reconnect_thread: threading.Thread | None = None
        self._last_data_at: float | None = None

        self._ws: WebSocket | None = None
        self._start_ws()

    # -- lifecycle -------------------------------------------------------------

    def _start_ws(self) -> None:
        """Create and connect the pybit WebSocket."""
        try:
            self._ws = WebSocket(
                testnet=False,
                channel_type=self._channel_type,
            )
            self._connected = True
            self._last_data_at = None
            logger.info(
                "Bybit WS connected (channel=%s, interval=%s)",
                self._channel_type, self._interval,
            )
        except Exception:
            self._connected = False
            logger.exception("Bybit WS connection failed")
            self._schedule_reconnect()

    def stop(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._stop_event.set()
        if self._ws is not None:
            try:
                self._ws.exit()
            except Exception:
                logger.debug("WS exit error (ignored)", exc_info=True)
            self._ws = None
        self._connected = False
        self._subscribed.clear()
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=5)
            self._reconnect_thread = None
        logger.info("Bybit WS stopped")

    def _schedule_reconnect(self) -> None:
        """Start a background reconnect loop with exponential backoff."""
        if self._stop_event.is_set() or not self._subscribed:
            return
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            name="bybit-ws-reconnect",
            daemon=True,
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self) -> None:
        """Attempt reconnect with exponential backoff + jitter.

        pybit has built-in retries (retries=10, restart_on_error=True) for
        transient errors.  This outer loop handles the case where pybit
        exhausts its retries or fails to initialise at all.

        Circuit breaker pauses reconnect attempts after repeated failures.
        """
        while not self._stop_event.is_set() and self._subscribed:
            if not self._cb.allow_request():
                # Circuit open — wait and retry check
                if self._stop_event.wait(1.0):
                    break
                continue

            delay = compute_backoff(self._reconnect_attempt)
            logger.info(
                "Bybit WS reconnect attempt %d in %.1fs",
                self._reconnect_attempt + 1, delay,
            )
            if self._stop_event.wait(delay):
                break
            # Tear down old instance and create a fresh one
            if self._ws is not None:
                try:
                    self._ws.exit()
                except Exception:
                    pass
                self._ws = None
            self._start_ws()
            if self._connected:
                # Re-subscribe all symbols
                saved = list(self._subscribed)
                self._subscribed.clear()
                self.subscribe(saved)
                if self._connected:
                    self._cb.record_success()
                    logger.info("Bybit WS reconnected successfully")
                    return
            self._cb.record_failure()
            self._reconnect_attempt += 1

    @property
    def connected(self) -> bool:
        if not self._connected:
            return False
        # Staleness check: if we were receiving data but it stopped,
        # the underlying pybit connection likely died (ping/pong timeout,
        # DNS failure, etc.).  Mark as disconnected and trigger reconnect.
        if (
            self._last_data_at is not None
            and time.monotonic() - self._last_data_at > _WS_STALE_SEC
        ):
            self._connected = False
            self._schedule_reconnect()
            return False
        return True

    # -- subscriptions ---------------------------------------------------------

    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to kline streams, batching in groups of 10."""
        if not self._ws or not self._connected:
            logger.warning("Cannot subscribe: WS not connected")
            self._schedule_reconnect()
            return

        new = [s for s in symbols if s not in self._subscribed]
        if not new:
            return

        for i in range(0, len(new), _SUBSCRIBE_BATCH):
            batch = new[i : i + _SUBSCRIBE_BATCH]
            try:
                self._ws.kline_stream(
                    interval=self._interval,
                    symbol=batch,
                    callback=self._handle_message,
                )
                self._subscribed.update(batch)
                logger.debug("Subscribed batch (%d symbols): %s", len(batch), batch)
            except Exception:
                logger.exception("Subscribe failed for batch: %s", batch)

        logger.info(
            "Bybit WS subscribed to %d symbols (%d new)",
            len(self._subscribed), len(new),
        )

    def unsubscribe(self, symbols: list[str]) -> None:
        """Remove symbols from tracking (pybit does not expose unsubscribe)."""
        for sym in symbols:
            self._subscribed.discard(sym)
            self._wm.remove(sym)

    # -- message handling ------------------------------------------------------

    def _handle_message(self, message: dict) -> None:
        """Parse incoming kline message and update rolling window."""
        try:
            data_list = message.get("data")
            if not data_list:
                return

            topic = message.get("topic", "")
            # topic format: "kline.{interval}.{symbol}"
            parts = topic.split(".")
            if len(parts) < 3:
                return
            symbol = parts[2]

            self._last_data_at = time.monotonic()

            for candle in data_list:
                close = float(candle["close"])
                confirmed = bool(candle.get("confirm", False))
                closes = self._wm.update(symbol, close, confirmed)

                if self._reconnect_attempt > 0:
                    self._reconnect_attempt = 0
                if self._on_kline:
                    self._on_kline(symbol, closes, confirmed)

        except Exception:
            logger.exception("Error handling WS kline message")

    # -- data access -----------------------------------------------------------

    def get_closes(self, symbol: str) -> list[float] | None:
        return self._wm.get_closes(symbol)

    def seed(self, symbol: str, closes: list[float]) -> None:
        self._wm.seed(symbol, closes)

    def resize_window(self, new_size: int) -> None:
        """Resize the rolling kline window for all symbols."""
        self._window_size = new_size
        self._wm.resize(new_size)

    @property
    def symbol_count(self) -> int:
        return len(self._subscribed)
