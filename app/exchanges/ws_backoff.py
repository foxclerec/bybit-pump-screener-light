# app/exchanges/ws_backoff.py
"""Shared exponential backoff helper for WebSocket auto-reconnect."""

from __future__ import annotations

import random

# Backoff defaults (from Phase 3.C.4 spec)
WS_BACKOFF_BASE_SEC = 1.0
WS_BACKOFF_MAX_SEC = 30.0
WS_BACKOFF_JITTER_FACTOR = 0.5


def compute_backoff(
    attempt: int,
    base: float = WS_BACKOFF_BASE_SEC,
    max_delay: float = WS_BACKOFF_MAX_SEC,
) -> float:
    """Return backoff delay in seconds: min(base * 2^attempt, max) + jitter.

    Jitter is uniform random in [0, delay * 0.5] to spread reconnects.
    """
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * WS_BACKOFF_JITTER_FACTOR)
    return delay + jitter
