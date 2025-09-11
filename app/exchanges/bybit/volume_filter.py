# app/exchanges/bybit/volume_filter.py
"""
Filter symbols by 24h turnover (USD) using Bybit /v5/market/tickers snapshot.
- One snapshot per category with short in-memory TTL (provided by bybit_client.get_tickers_map)
- Drops symbols below the threshold
"""

from __future__ import annotations
import logging
from typing import List

from app.constants import VOLUME_MIN_USD, DEFAULT_CATEGORY

from app.exchanges.bybit.client import get_tickers_map

logger = logging.getLogger(__name__)

def filter_symbols_by_turnover(
    symbols: List[str],
    min_usd: float = VOLUME_MIN_USD,
    category: str = DEFAULT_CATEGORY,
    allow_on_error: bool = True,
    verbose: bool = True,
) -> List[str]:
    """
    Keep only symbols with turnover24h >= min_usd.
    - Uses a single batched snapshot (cached) for the whole category.
    - If allow_on_error=True and turnover is unknown, keep the symbol (log only).
    """
    kept: List[str] = []
    dropped = 0

    try:
        tickers = get_tickers_map(category=category, allow_stale=True)
    except Exception as e:
        logger.warning("[vol] ERROR fetching tickers: %s (allow_on_error=%s)", e, allow_on_error)
        return list(symbols) if allow_on_error else []

    for sym in symbols:
        row = tickers.get(sym)
        tv = row.get("turnover24h") if row else None

        if tv is None:
            if allow_on_error:
                kept.append(sym)
                if verbose:
                    logger.info("[vol] %14s  turnover: unknown -> kept (allow_on_error)", sym)
            else:
                dropped += 1
                if verbose:
                    logger.info("[vol] %14s  turnover: unknown -> dropped", sym)
            continue

        if tv >= min_usd:
            kept.append(sym)
            if verbose:
                logger.info("[vol] %14s  24h=$%,.0f -> kept (>= $%,.0f)", sym, tv, min_usd)
        else:
            dropped += 1
            if verbose:
                logger.info("[vol] %14s  24h=$%,.0f -> dropped (< $%,.0f)", sym, tv, min_usd)

    if verbose:
        logger.info("[vol] checked: %d | kept: %d | dropped: %d | min=$%,.0f", len(symbols), len(kept), dropped, min_usd)
    return kept
