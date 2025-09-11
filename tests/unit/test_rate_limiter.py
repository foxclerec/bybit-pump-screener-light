# tests/unit/test_rate_limiter.py
"""Unit tests for TokenBucket, CircuitBreaker, and rate limit header parsing."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.exchanges.http_client import TokenBucket
from app.exchanges.circuit_breaker import CircuitBreaker, CLOSED, OPEN, HALF_OPEN
from app.exchanges.rate_limits import (
    rate_limit_wait,
    update_from_headers,
    THROTTLE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

class TestTokenBucket:

    def test_acquire_consumes_token(self):
        bucket = TokenBucket(rate_per_sec=100, burst=10)
        # Should not block — bucket starts full
        bucket.acquire(1.0)

    def test_burst_capacity(self):
        bucket = TokenBucket(rate_per_sec=100, burst=5)
        for _ in range(5):
            bucket.acquire(1.0)
        # Bucket should be empty now; next acquire would block
        # Check tokens are depleted by measuring time
        assert bucket._tokens < 1.0

    def test_throttle_reduces_rate(self):
        bucket = TokenBucket(rate_per_sec=100, burst=100)
        bucket.throttle(0.5, duration_sec=10.0)
        assert bucket.rate == 50.0

    def test_throttle_restores_rate_after_expiry(self):
        bucket = TokenBucket(rate_per_sec=100, burst=100)
        bucket.throttle(0.5, duration_sec=0.0)  # expires immediately
        # Trigger restore via acquire
        bucket.acquire(0)
        time.sleep(0.01)
        bucket.acquire(0)
        assert bucket.rate == 100.0

    def test_throttle_clamps_factor(self):
        bucket = TokenBucket(rate_per_sec=100, burst=100)
        bucket.throttle(0.01, duration_sec=5.0)  # below min 0.1
        assert bucket.rate == 10.0  # 100 * 0.1


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_starts_closed(self):
        cb = CircuitBreaker(label="test")
        assert cb.state == CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(label="test", failure_threshold=3, open_duration_sec=30)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == OPEN
        assert cb.allow_request() is False

    def test_below_threshold_stays_closed(self):
        cb = CircuitBreaker(label="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CLOSED
        assert cb.allow_request() is True

    def test_success_resets_counter(self):
        cb = CircuitBreaker(label="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        cb.record_failure()
        assert cb.state == CLOSED

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(label="test", failure_threshold=1, open_duration_sec=0.01)
        cb.record_failure()
        assert cb.state == OPEN
        time.sleep(0.02)
        assert cb.state == HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(label="test", failure_threshold=1, open_duration_sec=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # triggers HALF_OPEN
        cb.record_success()
        assert cb.state == CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(label="test", failure_threshold=1, open_duration_sec=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # triggers HALF_OPEN
        cb.record_failure()
        assert cb.state == OPEN


# ---------------------------------------------------------------------------
# Rate limit response handling (429/403)
# ---------------------------------------------------------------------------

def _make_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    """Create a minimal httpx.Response for testing."""
    req = httpx.Request("GET", "https://example.com/test")
    resp = httpx.Response(status_code, request=req, headers=headers or {})
    return resp


class TestRateLimitWait:

    def test_bybit_403_with_reset_header(self):
        future_ms = int((time.time() + 3.0) * 1000)
        resp = _make_response(403, {"X-Bapi-Limit-Reset-Timestamp": str(future_ms)})
        wait = rate_limit_wait(resp, "bybit", 0)
        assert wait is not None
        assert 0.5 <= wait <= 10.0

    def test_bybit_403_fallback(self):
        resp = _make_response(403)
        wait = rate_limit_wait(resp, "bybit", 0)
        assert wait == 2.0

    def test_generic_429_with_retry_after(self):
        resp = _make_response(429, {"Retry-After": "3"})
        wait = rate_limit_wait(resp, "bybit", 0)
        assert wait == 3.0

    def test_generic_429_fallback(self):
        resp = _make_response(429)
        wait = rate_limit_wait(resp, "bybit", 0)
        assert wait == 2.0  # 2.0 * (0 + 1)

    def test_200_returns_none(self):
        resp = _make_response(200)
        assert rate_limit_wait(resp, "bybit", 0) is None

    def test_generic_429(self):
        resp = _make_response(429)
        wait = rate_limit_wait(resp, "unknown_exchange", 0)
        assert wait is not None


# ---------------------------------------------------------------------------
# Header parsing → throttle
# ---------------------------------------------------------------------------

class TestUpdateFromHeaders:

    def test_bybit_high_usage_throttles(self):
        throttle_fn = MagicMock()
        resp = _make_response(200, {
            "X-Bapi-Limit": "120",
            "X-Bapi-Limit-Status": "20",  # 83% used
        })
        update_from_headers(resp, "bybit", throttle_fn)
        throttle_fn.assert_called_once()

    def test_bybit_low_usage_no_throttle(self):
        throttle_fn = MagicMock()
        resp = _make_response(200, {
            "X-Bapi-Limit": "120",
            "X-Bapi-Limit-Status": "100",  # 17% used
        })
        update_from_headers(resp, "bybit", throttle_fn)
        throttle_fn.assert_not_called()

    def test_missing_headers_no_throttle(self):
        throttle_fn = MagicMock()
        resp = _make_response(200)
        update_from_headers(resp, "bybit", throttle_fn)
        throttle_fn.assert_not_called()


