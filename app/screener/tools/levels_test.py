"""
levels_test.py

Interactive CLI:
 - input coin like "xrp" or "BTC"
 - script converts to <UPPER>USDT (linear perpetual) and queries Bybit V5 klines
 - finds resistance and support levels from historical highs/lows
 - prints levels above/below current price with distance %
"""

import sys
import time
import requests

from app.screener.tools.levels_core import (
    LOCAL_WINDOW,
    MIN_TOUCHES,
    MIN_DISTANCE_PCT,
    NUM_LEVELS,
    NUM_SUPPORT_LEVELS,
    SUPPORT_MIN_DISTANCE_PCT,
    CLUSTER_MERGE_PCT,
    find_local_peaks,
    find_local_troughs,
    merge_close_peaks,
    select_levels_above_price,
    select_levels_below_price,
    format_level,
)

# ========== CONFIG ==========
TIMEFRAME = "4h"
LOOKBACK_BARS = 500
VOLUME_FILTER = None
RETURN_DISTANCE_PCT = True
USE_MULTI_TF = True
DAILY_LOOKBACK = 500

# Bybit V5 market kline endpoint
BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"

# map friendly timeframe to Bybit interval strings
TF_TO_INTERVAL = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W", "1M": "M",
}


def interval_for_tf(tf: str) -> str:
    tf = tf.lower()
    if tf in TF_TO_INTERVAL:
        return TF_TO_INTERVAL[tf]
    if tf.endswith("h"):
        return str(int(tf[:-1]) * 60)
    if tf.endswith("m"):
        return str(int(tf[:-1]))
    return TF_TO_INTERVAL.get("4h", "240")


def fetch_klines_bybit(
    symbol: str, interval: str, limit: int = 500, category: str = "linear",
) -> list[dict]:
    """
    Fetch klines from Bybit V5 (public).
    Returns list of candle dicts: {open, high, low, close, volume, open_time}.
    """
    params = {
        "category": category,
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }
    resp = requests.get(BYBIT_KLINES, params=params, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    j = resp.json()
    if j.get("retCode") != 0:
        raise RuntimeError(f"Bybit error: {j.get('retMsg') or j}")
    lst = list(reversed(j.get("result", {}).get("list", [])))
    candles = []
    for item in lst:
        try:
            candles.append({
                "open_time": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]) if len(item) > 5 else 0.0,
            })
        except Exception:
            continue
    return candles


def process_symbol(symbol_input: str) -> None:
    """Main pipeline for a single input symbol."""
    sym = symbol_input.strip().upper()
    if not sym:
        return
    symbol = sym if sym.endswith("USDT") else sym + "USDT"

    interval = interval_for_tf(TIMEFRAME)
    try:
        candles = fetch_klines_bybit(symbol, interval, limit=LOOKBACK_BARS, category="linear")
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return

    if len(candles) < LOOKBACK_BARS:
        print(f"Warning: fetched only {len(candles)} candles (requested {LOOKBACK_BARS})")
    if not candles:
        print("No candle data returned.")
        return

    last_close = candles[-1]["close"]

    # Primary TF candidates
    peaks_primary = find_local_peaks(candles, LOCAL_WINDOW, VOLUME_FILTER)
    troughs_primary = find_local_troughs(candles, LOCAL_WINDOW, VOLUME_FILTER)

    # Optional daily TF candidates
    peaks_daily: list = []
    troughs_daily: list = []
    daily_candles: list[dict] = []
    if USE_MULTI_TF:
        daily_interval = interval_for_tf("1d")
        try:
            daily_candles = fetch_klines_bybit(symbol, daily_interval, limit=DAILY_LOOKBACK, category="linear")
            if len(daily_candles) < DAILY_LOOKBACK:
                print(f"Note: fetched only {len(daily_candles)} daily candles (requested {DAILY_LOOKBACK})")
            if daily_candles:
                peaks_daily = find_local_peaks(daily_candles, LOCAL_WINDOW, VOLUME_FILTER)
                troughs_daily = find_local_troughs(daily_candles, LOCAL_WINDOW, VOLUME_FILTER)
        except Exception as e:
            print(f"Warning: could not fetch daily candles for {symbol}: {e}")

    # Merge candidates from all TFs
    merged_peaks = merge_close_peaks(peaks_primary + peaks_daily, CLUSTER_MERGE_PCT)
    merged_troughs = merge_close_peaks(troughs_primary + troughs_daily, CLUSTER_MERGE_PCT)

    combined_candles = candles + daily_candles if daily_candles else candles[:]

    # Select final levels
    final_resistances = select_levels_above_price(
        [m[0] for m in merged_peaks], last_close, MIN_TOUCHES, combined_candles, MIN_DISTANCE_PCT, NUM_LEVELS,
    )
    final_supports = select_levels_below_price(
        [m[0] for m in merged_troughs], last_close, MIN_TOUCHES, combined_candles, SUPPORT_MIN_DISTANCE_PCT, NUM_SUPPORT_LEVELS,
    )

    # Pad to fixed length
    final_resistances = final_resistances[:NUM_LEVELS] + [None] * max(0, NUM_LEVELS - len(final_resistances))
    final_supports = final_supports[:NUM_SUPPORT_LEVELS] + [None] * max(0, NUM_SUPPORT_LEVELS - len(final_supports))

    # Print results
    print(f"\nSymbol: {symbol}   last_close: {format_level(last_close)}\n")

    print("Resistances (above price):")
    for i, lvl in enumerate(final_resistances, 1):
        if lvl is None:
            print(f"  Level #{i}: -")
        elif RETURN_DISTANCE_PCT:
            d = (lvl - last_close) / last_close * 100.0
            print(f"  Level #{i}: {format_level(lvl)}   distance: {round(d, 3)}%")
        else:
            print(f"  Level #{i}: {format_level(lvl)}")

    print("\nSupports (below price):")
    for i, lvl in enumerate(final_supports, 1):
        if lvl is None:
            print(f"  Level #{i}: -")
        elif RETURN_DISTANCE_PCT:
            d = (last_close - lvl) / last_close * 100.0
            print(f"  Level #{i}: {format_level(lvl)}   distance_down: {round(d, 3)}%")
        else:
            print(f"  Level #{i}: {format_level(lvl)}")
    print("")


def repl_loop() -> None:
    print("Bybit Levels finder — input coin like 'xrp' or 'BTC' (linear USDT perpetual pairs). Ctrl-C to quit.")
    try:
        while True:
            s = input("symbol> ").strip()
            if not s:
                continue
            process_symbol(s)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)


if __name__ == "__main__":
    repl_loop()

# python -m app.screener.tools.levels_test
