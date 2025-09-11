# app/exchanges/bybit/symbol_age.py
"""
Bybit symbol age helper (DB-backed):
- Finds earliest DAILY kline for a symbol (UTC) via /v5/market/kline
- Stores first_ts in DB (SymbolAge) to avoid repeated API calls
- Computes "age in days" on the fly (now - first_ts)
- Provides filter to keep symbols with age >= N days
"""

from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.extensions import db
from app.models import SymbolAge
from app.exchanges.bybit.client import _http_get

from app.constants import (
    AGE_MIN_DAYS,
    AGE_REQUEST_SLEEP_SEC as REQUEST_SLEEP_SEC,
    AGE_DAY_MS as DAY_MS,
)

logger = logging.getLogger(__name__)


# ---------- Core: earliest daily kline ----------
def _first_daily_kline_ts(symbol: str, category: str = "linear") -> Optional[int]:
    """
    Page backwards over daily klines and return earliest timestamp (ms).
    Returns None if API returns nothing.
    """
    end = int(time.time() * 1000)
    earliest = None

    # move by ~500-day windows; 30 iters cover многие годы
    for _ in range(30):
        start = end - 500 * DAY_MS
        data = _http_get(
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": "D",
                "start": start,
                "end": end,
                "limit": 200,
            },
        )
        rows = ((data.get("result") or {}).get("list") or [])
        if not rows:
            end = start - 1
            continue

        try:
            batch_min = min(int(r[0]) for r in rows)
        except (ValueError, TypeError, IndexError) as e:
            logger.warning("Bad kline data for %s: %s", symbol, e)
            break

        earliest = batch_min if earliest is None else min(earliest, batch_min)

        if len(rows) < 200:
            break

        end = batch_min - 1
        time.sleep(REQUEST_SLEEP_SEC)

    return earliest


# ---------- DB helpers ----------
def _get_row(symbol: str, category: str) -> Optional[SymbolAge]:
    return SymbolAge.query.filter_by(symbol=symbol, category=category).first()

def _upsert_row(symbol: str, category: str, first_ts: int, source: str = "bybit") -> SymbolAge:
    first_day = datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc).date()
    now = datetime.now(timezone.utc)

    row = _get_row(symbol, category)
    if row:
        row.first_ts = int(first_ts)
        row.first_day = first_day
        row.checked_at = now
        row.source = source
    else:
        row = SymbolAge(
            symbol=symbol,
            category=category,
            first_ts=int(first_ts),
            first_day=first_day,
            checked_at=now,
            source=source,
        )
        db.session.add(row)

    db.session.commit()
    return row


# ---------- Public: ensure in DB + compute age ----------
def ensure_symbol_age(symbol: str, category: str = "linear", *, force_refresh: bool = False) -> Optional[SymbolAge]:
    """
    Make sure SymbolAge exists in DB for (symbol, category).
    - If missing or force_refresh=True -> fetch earliest kline and upsert.
    - If present -> return row without API call.
    """
    row = _get_row(symbol, category)
    if row and not force_refresh:
        return row

    ts = _first_daily_kline_ts(symbol, category=category)
    if ts is None:
        return None
    return _upsert_row(symbol, category, ts, source="bybit")


def coin_age_days(symbol: str, category: str = "linear", *, force_refresh: bool = False) -> Optional[int]:
    """Return age in days for (symbol, category)."""
    row = ensure_symbol_age(symbol, category=category, force_refresh=force_refresh)
    if not row:
        return None
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return int((now_ms - int(row.first_ts)) // DAY_MS)


# ---------- Public: filter ----------
def filter_symbols_by_age(
    symbols: List[str],
    min_days: int = AGE_MIN_DAYS,
    category: str = "linear",
    allow_on_error: bool = True,
    verbose: bool = True,
    *,
    force_refresh: bool = False,
) -> List[str]:
    """
    Keep only symbols with age >= min_days.
    - Auto-discovers new symbols (stores first_ts into DB on first encounter)
    - allow_on_error=True: keep symbol if age cannot be determined (log only)
    """
    kept: List[str] = []
    checked = 0

    for sym in symbols:
        checked += 1
        try:
            age = coin_age_days(sym, category=category, force_refresh=force_refresh)
            if age is None:
                if allow_on_error:
                    kept.append(sym)
                    if verbose:
                        logger.info("[age] %14s  age: unknown  -> kept (allow_on_error)", sym)
                else:
                    if verbose:
                        logger.info("[age] %14s  age: unknown  -> dropped", sym)
                continue

            if age >= min_days:
                kept.append(sym)
                if verbose:
                    logger.info("[age] %14s  %4dd -> kept", sym, age)
            else:
                if verbose:
                    logger.info("[age] %14s  %4dd -> dropped (< %dd)", sym, age, min_days)
            time.sleep(REQUEST_SLEEP_SEC)
        except Exception as e:
            if allow_on_error:
                kept.append(sym)
                if verbose:
                    logger.warning("[age] %14s  ERROR: %s -> kept (allow_on_error)", sym, e)
            else:
                if verbose:
                    logger.warning("[age] %14s  ERROR: %s -> dropped", sym, e)

    if verbose:
        logger.info("[age] checked: %d | kept: %d | min=%dd", checked, len(kept), min_days)
    return kept


# ---------- Optional maintenance ----------
def invalidate_symbol(symbol: str, category: str = "linear") -> bool:
    """Remove symbol from DB cache; returns True if removed."""
    row = _get_row(symbol, category)
    if row:
        db.session.delete(row)
        db.session.commit()
        return True
    return False

def prewarm_symbols(symbols: List[str], category: str = "linear", *, force_refresh: bool = False) -> None:
    """Populate/refresh DB for a list of symbols."""
    for s in symbols:
        ensure_symbol_age(s, category=category, force_refresh=force_refresh)
        time.sleep(REQUEST_SLEEP_SEC)
