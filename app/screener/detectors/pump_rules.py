# app/screener/detectors/pump_rules.py
from __future__ import annotations
from typing import Iterable, Optional

def detect_pump(closes: Iterable[float], lookback_minutes: int, min_pct: float) -> Optional[float]:
    """
    closes: sequence of closing prices (floats), oldest→newest
    lookback_minutes: number of 1m candles to look back
    min_pct: minimal upward percent change to trigger (e.g., 2.0)
    Returns actual pct if >= min_pct, else None.
    """
    buf = list(closes or [])
    n = int(lookback_minutes)
    if not buf or len(buf) <= n:
        return None
    past = float(buf[-(n+1)])
    last = float(buf[-1])
    if past <= 0.0:
        return None
    pct = (last / past - 1.0) * 100.0
    if pct >= float(min_pct):
        return pct
    return None
