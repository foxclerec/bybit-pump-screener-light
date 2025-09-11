"""
levels_core.py

Core algorithms for finding support/resistance levels from candlestick data.
"""

from typing import List, Dict, Tuple

# ========== CONFIG ==========
LOCAL_WINDOW = 4
MIN_TOUCHES = 2
MIN_DISTANCE_PCT = 10.0
NUM_LEVELS = 3
NUM_SUPPORT_LEVELS = 3
SUPPORT_MIN_DISTANCE_PCT = 10.0
TOUCH_TOLERANCE_PCT = 0.6
CLUSTER_MERGE_PCT = 0.8
ROUNDING_PRECISION = 8


def find_local_peaks(
    candles: List[Dict], window: int, volume_filter: float | None,
) -> List[Tuple[int, float, float]]:
    """
    Find local highs: candle high strictly greater than highs in window on both sides.
    Returns list of (index, price, volume).
    """
    highs = [c["high"] for c in candles]
    volumes = [c["volume"] for c in candles]
    n = len(highs)
    peaks = []
    for i in range(window, n - window):
        left_max = max(highs[i - window : i])
        right_max = max(highs[i + 1 : i + 1 + window])
        if highs[i] > left_max and highs[i] > right_max:
            if volume_filter is not None and volumes[i] < volume_filter:
                continue
            peaks.append((i, highs[i], volumes[i]))
    return peaks


def find_local_troughs(
    candles: List[Dict], window: int, volume_filter: float | None,
) -> List[Tuple[int, float, float]]:
    """
    Find local lows: candle low strictly lower than lows in window on both sides.
    Returns list of (index, price, volume).
    """
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]
    n = len(lows)
    troughs = []
    for i in range(window, n - window):
        left_min = min(lows[i - window : i])
        right_min = min(lows[i + 1 : i + 1 + window])
        if lows[i] < left_min and lows[i] < right_min:
            if volume_filter is not None and volumes[i] < volume_filter:
                continue
            troughs.append((i, lows[i], volumes[i]))
    return troughs


def merge_close_peaks(
    peaks: List[Tuple[int, float, float]], merge_pct: float,
) -> List[Tuple[float, List[int]]]:
    """
    Merge peaks (or troughs) close to each other (within merge_pct).
    Returns list of (merged_price, list_of_indices).
    """
    if not peaks:
        return []
    peaks_sorted = sorted(peaks, key=lambda x: x[1])
    groups: List[List[Tuple[int, float, float]]] = []
    current_group = [peaks_sorted[0]]
    for p in peaks_sorted[1:]:
        prev_price = current_group[-1][1]
        if (p[1] / prev_price - 1.0) * 100.0 <= merge_pct:
            current_group.append(p)
        else:
            groups.append(current_group)
            current_group = [p]
    groups.append(current_group)
    merged = []
    for grp in groups:
        prices = [g[1] for g in grp]
        indices = [g[0] for g in grp]
        avg_price = sum(prices) / len(prices)
        merged.append((avg_price, indices))
    return merged


def count_touches(candles: List[Dict], level: float, tol_pct: float) -> int:
    """
    Count how many candles "touched" the level.
    tol_pct is percent tolerance (e.g. 0.6 => 0.6% of level).
    """
    tol = level * (tol_pct / 100.0)
    count = 0
    for c in candles:
        low = c["low"] - tol
        high = c["high"] + tol
        if low <= level <= high:
            count += 1
    return count


def select_levels_above_price(
    levels: List[float],
    last_close: float,
    min_touches: int,
    candles: List[Dict],
    min_distance_pct: float,
    num_levels: int,
) -> List[float]:
    """Select num_levels resistance levels above last_close."""
    candidates = []
    for lvl in levels:
        if lvl <= last_close:
            continue
        touches = count_touches(candles, lvl, TOUCH_TOLERANCE_PCT)
        if touches >= min_touches:
            candidates.append((lvl, touches))
    candidates.sort(key=lambda x: x[0])
    selected: List[float] = []
    for lvl, _touches in candidates:
        if not selected:
            selected.append(lvl)
        else:
            prev = selected[-1]
            diff_pct = (lvl / prev - 1.0) * 100.0
            if diff_pct >= min_distance_pct:
                selected.append(lvl)
        if len(selected) >= num_levels:
            break
    return selected


def select_levels_below_price(
    levels: List[float],
    last_close: float,
    min_touches: int,
    candles: List[Dict],
    min_distance_pct: float,
    num_levels: int,
) -> List[float]:
    """Select num_levels support levels below last_close."""
    candidates = []
    for lvl in levels:
        if lvl >= last_close:
            continue
        touches = count_touches(candles, lvl, TOUCH_TOLERANCE_PCT)
        if touches >= min_touches:
            candidates.append((lvl, touches))
    candidates.sort(key=lambda x: -x[0])
    selected: List[float] = []
    for lvl, _touches in candidates:
        if not selected:
            selected.append(lvl)
        else:
            prev = selected[-1]
            diff_pct = (prev / lvl - 1.0) * 100.0
            if diff_pct >= min_distance_pct:
                selected.append(lvl)
        if len(selected) >= num_levels:
            break
    return selected


def format_level(lvl: float) -> float:
    return round(lvl, ROUNDING_PRECISION)
