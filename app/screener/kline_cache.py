# app/screener/kline_cache.py
"""In-memory kline cache with per-symbol TTL."""

from __future__ import annotations

import time


class KlineCache:
    """Cache close prices per symbol with a TTL.

    Klines update once per candle interval (e.g. 60 s for 1m candles).
    Caching with TTL < interval avoids redundant REST calls between updates.
    """

    def __init__(self, ttl_sec: float = 55.0) -> None:
        self._store: dict[str, tuple[float, list[float]]] = {}
        self._ttl = ttl_sec

    def get(self, symbol: str) -> list[float] | None:
        entry = self._store.get(symbol)
        if entry and (time.monotonic() - entry[0]) < self._ttl:
            return entry[1]
        return None

    def put(self, symbol: str, closes: list[float]) -> None:
        self._store[symbol] = (time.monotonic(), closes)

    def clear(self) -> None:
        self._store.clear()

    def purge_expired(self) -> int:
        """Remove entries older than TTL. Returns number of entries removed."""
        now = time.monotonic()
        expired = [k for k, (ts, _) in self._store.items() if (now - ts) >= self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    def __len__(self) -> int:
        return len(self._store)
