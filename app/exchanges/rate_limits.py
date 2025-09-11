# app/exchanges/rate_limits.py
"""Exchange-specific rate limit header parsing and 429/403 response handling."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


# --- Rate Limit Header Parsing ------------------------------------------------

# Bybit: X-Bapi-Limit (total), X-Bapi-Limit-Status (remaining)

# Throttle when usage exceeds this fraction of the budget
THROTTLE_THRESHOLD = 0.75


def update_from_headers(
    resp: httpx.Response,
    label: str,
    throttle_fn: callable,
) -> None:
    """Read exchange-specific rate limit headers and throttle if needed.

    Args:
        resp: The HTTP response with headers to parse.
        label: Exchange label (e.g. "bybit").
        throttle_fn: Callable(factor, duration_sec) to slow the rate limiter.
    """
    tag = label.lower()

    if tag == "bybit":
        _parse_bybit_headers(resp, throttle_fn)


def _parse_bybit_headers(resp: httpx.Response, throttle_fn: callable) -> None:
    """Bybit: throttle when remaining requests drop below 25% of limit."""
    limit_str = resp.headers.get("X-Bapi-Limit")
    remaining_str = resp.headers.get("X-Bapi-Limit-Status")
    if not limit_str or not remaining_str:
        return
    try:
        limit = int(limit_str)
        remaining = int(remaining_str)
    except (ValueError, TypeError):
        return
    if limit <= 0:
        return
    usage_ratio = 1.0 - (remaining / limit)
    if usage_ratio > THROTTLE_THRESHOLD:
        factor = max(0.25, 1.0 - usage_ratio)
        throttle_fn(factor, 3.0)
        logger.info("Bybit rate pressure: %d/%d remaining, throttle=%.0f%%",
                     remaining, limit, factor * 100)


# --- 429/403 Rate Limit Response Handling -------------------------------------

MAX_RATE_LIMIT_RETRIES = 2
_BYBIT_403_FALLBACK_SEC = 2.0


def rate_limit_wait(resp: httpx.Response, label: str, rl_attempt: int) -> float | None:
    """Return seconds to wait on a rate-limit response, or None if not rate-limited."""
    status = resp.status_code
    tag = label.lower()

    if tag == "bybit" and status == 403:
        reset_ts = resp.headers.get("X-Bapi-Limit-Reset-Timestamp")
        if reset_ts:
            try:
                reset_ms = int(reset_ts)
                wait = max(0.5, (reset_ms / 1000) - time.time())
                return min(wait, 10.0)
            except (ValueError, TypeError):
                pass
        return _BYBIT_403_FALLBACK_SEC

    if status == 429:
        return _get_retry_after(resp, 2.0 * (rl_attempt + 1))

    return None


def _get_retry_after(resp: httpx.Response, fallback: float) -> float:
    """Parse Retry-After header (seconds). Returns fallback if absent."""
    raw = resp.headers.get("Retry-After")
    if raw:
        try:
            return max(0.5, float(raw))
        except (ValueError, TypeError):
            pass
    return fallback
