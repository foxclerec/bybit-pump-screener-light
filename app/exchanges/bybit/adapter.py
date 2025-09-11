# app/exchanges/bybit/adapter.py
"""Bybit v5 adapter — implements ExchangeAdapter using existing client functions."""

from __future__ import annotations

import logging
from typing import Any

from app.exchanges.base import ExchangeAdapter
from app.exchanges.bybit.client import (
    fetch_symbols as _fetch_symbols,
    fetch_klines as _fetch_klines,
    get_tickers_map as _get_tickers_map,
    _http_get,
)

logger = logging.getLogger(__name__)


class BybitAdapter(ExchangeAdapter):
    """Bybit v5 REST adapter wrapping existing client functions."""

    @property
    def name(self) -> str:
        return "bybit"

    def fetch_symbols(
        self, category: str = "linear", quote: str = "USDT",
    ) -> list[str]:
        return _fetch_symbols(category=category, quote=quote)

    def fetch_klines(
        self,
        symbol: str,
        interval: str = "1",
        limit: int = 30,
        category: str = "linear",
    ) -> list[float]:
        return _fetch_klines(symbol, interval=interval, limit=limit, category=category)

    def fetch_tickers(
        self, category: str = "linear",
    ) -> dict[str, dict[str, Any]]:
        return _get_tickers_map(category=category, allow_stale=True)

    def fetch_daily_klines(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 200,
        category: str = "linear",
    ) -> list[list]:
        data = _http_get(
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": "D",
                "start": start_ms,
                "end": end_ms,
                "limit": limit,
            },
        )
        return (data.get("result") or {}).get("list") or []
