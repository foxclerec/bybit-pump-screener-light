# app/exchanges/http_client.py
"""Shared resilient HTTP client and rate limiter for all exchange adapters."""

from __future__ import annotations

import logging
import threading
import time

import httpx

from app.constants import (
    HTTP_TIMEOUT_CONNECT_SEC,
    HTTP_TIMEOUT_READ_SEC,
    HTTP_TIMEOUT_WRITE_SEC,
    HTTP_TIMEOUT_POOL_SEC,
    HTTP_MAX_RETRIES,
    HTTP_BACKOFF_BASE_SEC,
    USER_AGENT,
    BYBIT_RATE_LIMIT_PER_SEC,
    DEFAULT_RATE_LIMIT_PER_SEC,
)
from app.exchanges.circuit_breaker import CircuitBreaker
from app.exchanges.rate_limits import (
    update_from_headers,
    rate_limit_wait,
    MAX_RATE_LIMIT_RETRIES,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=HTTP_TIMEOUT_CONNECT_SEC,
    read=HTTP_TIMEOUT_READ_SEC,
    write=HTTP_TIMEOUT_WRITE_SEC,
    pool=HTTP_TIMEOUT_POOL_SEC,
)


# --- Token Bucket Rate Limiter ------------------------------------------------


class TokenBucket:
    """Thread-safe token bucket rate limiter.

    Refills tokens continuously based on elapsed time.
    acquire() blocks until enough tokens are available.
    Supports temporary throttling when rate limit headers indicate pressure.
    """

    def __init__(self, rate_per_sec: float, burst: float | None = None) -> None:
        self.rate = rate_per_sec
        self._base_rate = rate_per_sec
        self.burst = burst if burst is not None else rate_per_sec
        self._tokens = self.burst
        self._last_refill = time.monotonic()
        self._throttle_until: float = 0.0
        self._lock = threading.Lock()

    def acquire(self, weight: float = 1.0) -> None:
        """Block until `weight` tokens are available, then consume them."""
        while True:
            with self._lock:
                now = time.monotonic()
                # Restore base rate after throttle window expires
                if self._throttle_until and now >= self._throttle_until:
                    self.rate = self._base_rate
                    self._throttle_until = 0.0

                elapsed = now - self._last_refill
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                self._last_refill = now

                if self._tokens >= weight:
                    self._tokens -= weight
                    return

                deficit = weight - self._tokens
                wait_sec = deficit / self.rate

            time.sleep(wait_sec)

    def throttle(self, factor: float, duration_sec: float = 5.0) -> None:
        """Temporarily reduce rate by `factor` (0..1) for `duration_sec`.

        Example: throttle(0.5, 5.0) halves the rate for 5 seconds.
        """
        with self._lock:
            self.rate = self._base_rate * max(0.1, min(factor, 1.0))
            self._throttle_until = time.monotonic() + duration_sec


# Per-exchange rate limiter registry
_EXCHANGE_RATES: dict[str, float] = {
    "bybit": BYBIT_RATE_LIMIT_PER_SEC,
}

_rate_limiters: dict[str, TokenBucket] = {}
_circuit_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_rate_limiter(label: str) -> TokenBucket:
    """Return a TokenBucket for the given exchange label (lazy init)."""
    key = label.lower()
    if key not in _rate_limiters:
        with _registry_lock:
            if key not in _rate_limiters:
                rate = _EXCHANGE_RATES.get(key, DEFAULT_RATE_LIMIT_PER_SEC)
                _rate_limiters[key] = TokenBucket(rate)
                logger.debug("Rate limiter created: %s at %s req/s", key, rate)
    return _rate_limiters[key]


def get_circuit_breaker(label: str) -> CircuitBreaker:
    """Return a CircuitBreaker for the given exchange label (lazy init)."""
    key = label.lower()
    if key not in _circuit_breakers:
        with _registry_lock:
            if key not in _circuit_breakers:
                _circuit_breakers[key] = CircuitBreaker(label=f"{key}-rest")
    return _circuit_breakers[key]


# --- HTTP Client Factory -------------------------------------------------------


def create_client(
    base_url: str,
    *,
    timeout: httpx.Timeout | None = None,
) -> httpx.Client:
    """Create a configured httpx.Client for an exchange."""
    return httpx.Client(
        base_url=base_url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout or DEFAULT_TIMEOUT,
    )


# --- Resilient GET with Rate Limiting ------------------------------------------


def resilient_get(
    client: httpx.Client,
    path: str,
    params: dict,
    *,
    label: str = "",
    max_retries: int = HTTP_MAX_RETRIES,
    backoff_base: float = HTTP_BACKOFF_BASE_SEC,
) -> dict | list:
    """HTTP GET with rate limiting, retries, backoff, timeout and logging.

    Handles 429/403 rate-limit responses with exchange-specific wait times.
    Returns parsed JSON (dict or list), or {} on total failure.
    """
    tag = label or str(client.base_url.host)

    # Circuit breaker — fast-fail when exchange is down
    cb = get_circuit_breaker(tag)
    if not cb.allow_request():
        logger.warning("%s %s circuit open — skipping request", tag, path)
        return {}

    # Throttle before sending request
    bucket = get_rate_limiter(tag)
    bucket.acquire()

    last_err: Exception | None = None
    rl_retries = 0  # rate-limit retry counter (separate from regular retries)

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(path, params=params)

            # Check for rate-limit response before raise_for_status
            wait = rate_limit_wait(resp, tag, rl_retries)
            if wait is not None and rl_retries < MAX_RATE_LIMIT_RETRIES:
                rl_retries += 1
                logger.warning(
                    "%s %s rate limited (HTTP %d), waiting %.1fs (rl_retry %d/%d)",
                    tag, path, resp.status_code, wait,
                    rl_retries, MAX_RATE_LIMIT_RETRIES,
                )
                bucket.throttle(0.25, duration_sec=wait + 5.0)
                time.sleep(wait)
                bucket.acquire()
                continue  # retry without consuming a regular attempt

            resp.raise_for_status()
            update_from_headers(resp, tag, bucket.throttle)
            cb.record_success()
            data = resp.json()
            if isinstance(data, (dict, list)):
                return data
            return {}
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
            logger.warning("%s %s attempt %d/%d: %s", tag, path, attempt, max_retries, e)
        except Exception as e:
            last_err = e
            logger.warning("%s %s attempt %d/%d unexpected: %s", tag, path, attempt, max_retries, e)

        if attempt < max_retries:
            bucket.acquire()  # re-acquire token before retry
            time.sleep(backoff_base * attempt)

    cb.record_failure()
    logger.error("%s %s failed after %d attempts: %s", tag, path, max_retries, last_err)
    return {}
