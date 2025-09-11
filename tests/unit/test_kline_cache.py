# tests/unit/test_kline_cache.py
"""Unit tests for the in-memory kline cache."""

import time
from unittest.mock import patch

from app.screener.kline_cache import KlineCache


class TestKlineCache:
    """Tests for KlineCache get/put/clear/len."""

    def test_put_then_get_returns_data(self):
        cache = KlineCache(ttl_sec=10.0)
        data = [1.0, 2.0, 3.0]
        cache.put("BTCUSDT", data)
        assert cache.get("BTCUSDT") == data

    def test_get_unknown_symbol_returns_none(self):
        cache = KlineCache(ttl_sec=10.0)
        assert cache.get("UNKNOWN") is None

    def test_get_expired_entry_returns_none(self):
        cache = KlineCache(ttl_sec=0.01)
        cache.put("BTCUSDT", [1.0, 2.0])
        time.sleep(0.02)
        assert cache.get("BTCUSDT") is None

    def test_overwrite_returns_new_data(self):
        cache = KlineCache(ttl_sec=10.0)
        cache.put("BTCUSDT", [1.0])
        cache.put("BTCUSDT", [2.0, 3.0])
        assert cache.get("BTCUSDT") == [2.0, 3.0]

    def test_clear_empties_cache(self):
        cache = KlineCache(ttl_sec=10.0)
        cache.put("BTCUSDT", [1.0])
        cache.put("ETHUSDT", [2.0])
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_len_counts_entries(self):
        cache = KlineCache(ttl_sec=10.0)
        assert len(cache) == 0
        cache.put("BTCUSDT", [1.0])
        assert len(cache) == 1
        cache.put("ETHUSDT", [2.0])
        assert len(cache) == 2

    def test_multiple_symbols_independent(self):
        cache = KlineCache(ttl_sec=10.0)
        cache.put("BTCUSDT", [100.0])
        cache.put("ETHUSDT", [200.0])
        assert cache.get("BTCUSDT") == [100.0]
        assert cache.get("ETHUSDT") == [200.0]

    def test_ttl_boundary(self):
        """Entry is still valid right before TTL expires."""
        cache = KlineCache(ttl_sec=1.0)
        with patch("app.screener.kline_cache.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            cache.put("BTCUSDT", [1.0])
            # Just before expiry
            mock_time.monotonic.return_value = 1000.99
            assert cache.get("BTCUSDT") == [1.0]
            # At expiry
            mock_time.monotonic.return_value = 1001.0
            assert cache.get("BTCUSDT") is None
