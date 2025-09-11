# app/exchanges/bybit/client.py
"""Bybit v5 REST client — symbols, klines, tickers."""

from __future__ import annotations

import logging
import time
from typing import Dict, Any, List

import httpx

from app.constants import (
    BYBIT_API_BASE,
    TICKERS_CACHE_TTL_SEC as _TICKERS_TTL_SEC,
)
from app.exchanges.http_client import create_client, resilient_get

logger = logging.getLogger(__name__)

# --- Shared httpx client (reused across module) -------------------------------
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = create_client(BYBIT_API_BASE)
    return _client


def _http_get(path: str, params: dict) -> dict:
    """Bybit GET: shared retry logic + envelope validation."""
    data = resilient_get(_get_client(), path, params, label="Bybit")
    if isinstance(data, dict) and (data.get("retCode") in (0, "0", None) or "result" in data):
        return data
    return data if isinstance(data, dict) else {}


# --- Public API ---------------------------------------------------------------


def fetch_symbols(category: str = "linear", quote: str = "USDT") -> list[str]:
    """Fetch all tradable symbols via paginated instruments-info endpoint."""
    syms: list[str] = []
    cursor: str | None = None

    for _ in range(20):  # safety limit
        params: dict = {"category": category, "limit": 1000}
        if cursor:
            params["cursor"] = cursor

        data = _http_get("/v5/market/instruments-info", params)
        result = data.get("result") or {}
        rows: List[dict] = result.get("list") or []

        for row in rows:
            try:
                if row.get("quoteCoin") == quote and row.get("symbol"):
                    syms.append(str(row["symbol"]))
            except Exception:
                continue

        next_cursor = result.get("nextPageCursor") or ""
        if not next_cursor or not rows:
            break
        cursor = next_cursor

    return syms


def fetch_symbols_with_launch(
    category: str = "linear", quote: str = "USDT",
) -> list[tuple[str, int]]:
    """Fetch symbols with their launchTime (ms) from instruments-info.

    Returns list of (symbol, launch_ts_ms) tuples.
    One API call instead of per-symbol kline lookups.
    """
    result_list: list[tuple[str, int]] = []
    cursor: str | None = None

    for _ in range(20):
        params: dict = {"category": category, "limit": 1000}
        if cursor:
            params["cursor"] = cursor

        data = _http_get("/v5/market/instruments-info", params)
        result = data.get("result") or {}
        rows: List[dict] = result.get("list") or []

        for row in rows:
            try:
                if row.get("quoteCoin") == quote and row.get("symbol"):
                    launch = row.get("launchTime")
                    if launch is not None:
                        result_list.append((str(row["symbol"]), int(launch)))
            except Exception:
                continue

        next_cursor = result.get("nextPageCursor") or ""
        if not next_cursor or not rows:
            break
        cursor = next_cursor

    return result_list


def fetch_klines(
    symbol: str, interval: str = "1", limit: int = 30, category: str = "linear",
) -> list[float]:
    data = _http_get(
        "/v5/market/kline",
        {"category": category, "symbol": symbol, "interval": interval, "limit": limit},
    )
    lst = (data.get("result") or {}).get("list", []) or []
    closes: list[float] = []
    try:
        for k in reversed(lst):  # newest-first -> oldest-first
            if isinstance(k, (list, tuple)) and len(k) >= 5:
                try:
                    closes.append(float(k[4]))
                except Exception:
                    continue
    except Exception:
        closes = []
    return closes


# --- Tickers cache (in-memory) ------------------------------------------------
_tickers_cache: Dict[str, Dict[str, Any]] = {}  # {category: {"ts": float, "data": dict}}


def _fetch_tickers_snapshot(category: str) -> Dict[str, Any]:
    """Fetch raw /v5/market/tickers for a category (linear|spot)."""
    data = _http_get("/v5/market/tickers", {"category": category})
    result = data.get("result") or {}
    rows = result.get("list") or result.get("rows") or []
    return {"rows": rows}


def get_tickers_map(
    category: str = "linear", *, allow_stale: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Return symbol -> ticker map. Uses short in-memory TTL cache."""
    now = time.time()
    entry = _tickers_cache.get(category)
    is_fresh = bool(entry and (now - entry["ts"] < _TICKERS_TTL_SEC))

    if is_fresh:
        return entry["data"]

    try:
        snap = _fetch_tickers_snapshot(category)
        rows = list(snap.get("rows") or [])
        mp: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            sym = r.get("symbol")
            if not sym:
                continue
            turnover = r.get("turnover24h")
            try:
                turnover = float(turnover) if turnover is not None else None
            except Exception:
                turnover = None
            r["turnover24h"] = turnover
            mp[str(sym)] = r
        _tickers_cache[category] = {"ts": now, "data": mp}
        return mp
    except Exception as e:
        logger.warning("Tickers snapshot failed for %s: %s", category, e)
        if allow_stale and entry and entry.get("data"):
            return entry["data"]
        return {}
