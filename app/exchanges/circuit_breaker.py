# app/exchanges/circuit_breaker.py
"""Thread-safe circuit breaker for exchange connections (WS + REST).

States:
  CLOSED    — normal operation, requests allowed
  OPEN      — too many failures, requests blocked for a cooldown period
  HALF_OPEN — cooldown expired, one test request allowed to probe recovery
"""

from __future__ import annotations

import logging
import threading
import time

from app.constants import CB_FAILURE_THRESHOLD, CB_OPEN_DURATION_SEC

logger = logging.getLogger(__name__)

# State names
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker: N consecutive failures → open → half-open → closed.

    Thread-safe — all state transitions are protected by a lock.
    """

    def __init__(
        self,
        label: str = "",
        failure_threshold: int = CB_FAILURE_THRESHOLD,
        open_duration_sec: float = CB_OPEN_DURATION_SEC,
    ) -> None:
        self._label = label
        self._threshold = failure_threshold
        self._open_duration = open_duration_sec

        self._state = CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    # -- public interface -------------------------------------------------------

    def allow_request(self) -> bool:
        """Return True if a request is allowed under the current state."""
        with self._lock:
            if self._state == CLOSED:
                return True

            if self._state == OPEN:
                if time.monotonic() - self._opened_at >= self._open_duration:
                    self._state = HALF_OPEN
                    logger.info(
                        "[cb:%s] OPEN → HALF_OPEN (testing one request)",
                        self._label,
                    )
                    return True
                return False

            # HALF_OPEN — allow one test request (already transitioned)
            return True

    def record_success(self) -> None:
        """Reset on success — transition to CLOSED."""
        with self._lock:
            if self._state == CLOSED and self._failure_count == 0:
                return  # nothing to do
            prev = self._state
            self._state = CLOSED
            self._failure_count = 0
            self._opened_at = 0.0
            if prev != CLOSED:
                logger.info("[cb:%s] %s → CLOSED (success)", self._label, prev)

    def record_failure(self) -> None:
        """Increment failure counter; open circuit if threshold reached."""
        with self._lock:
            self._failure_count += 1

            if self._state == HALF_OPEN:
                # Test request failed — reopen
                self._state = OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "[cb:%s] HALF_OPEN → OPEN (test failed, pausing %.0fs)",
                    self._label, self._open_duration,
                )
                return

            if self._failure_count >= self._threshold and self._state == CLOSED:
                self._state = OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "[cb:%s] CLOSED → OPEN (%d consecutive failures, pausing %.0fs)",
                    self._label, self._failure_count, self._open_duration,
                )

    # -- introspection ----------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            # Check for auto-transition on read
            if self._state == OPEN:
                if time.monotonic() - self._opened_at >= self._open_duration:
                    return HALF_OPEN
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count
