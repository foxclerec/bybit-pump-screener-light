# app/exchanges/base.py
"""Abstract base class for exchange adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExchangeAdapter(ABC):
    """Unified interface for all exchange adapters.

    Each adapter normalizes exchange-specific responses into a common format
    so that runner, volume_filter, and symbol_age can work exchange-agnostically.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short lowercase identifier, e.g. 'bybit'."""
        ...

    @abstractmethod
    def fetch_symbols(
        self, category: str = "linear", quote: str = "USDT",
    ) -> list[str]:
        """Return tradeable symbol names for the given category and quote asset.

        Example: ["BTCUSDT", "ETHUSDT", ...]
        """
        ...

    @abstractmethod
    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1",
        limit: int = 30,
        category: str = "linear",
    ) -> list[float]:
        """Return close prices ordered oldest-first.

        All exchanges return klines in their own order; the adapter MUST
        normalize to oldest-first so detection logic works uniformly.
        """
        ...

    @abstractmethod
    def fetch_tickers(
        self, category: str = "linear",
    ) -> dict[str, dict[str, Any]]:
        """Return symbol -> ticker dict with at least 'turnover24h' (float|None).

        Used by volume_filter to drop low-volume symbols.
        """
        ...

    @abstractmethod
    def fetch_daily_klines(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 200,
        category: str = "linear",
    ) -> list[list]:
        """Return raw daily kline rows where row[0] is open-timestamp in ms.

        Used by symbol_age to paginate backwards and find first trading day.
        Rows may be in any order; caller handles sorting.
        """
        ...
