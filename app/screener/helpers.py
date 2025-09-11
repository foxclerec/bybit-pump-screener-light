# app/screener/helpers.py

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Signal, SignalDedup
from app.exchanges.bybit.client import fetch_klines
from app.exchanges.bybit.volume_filter import filter_symbols_by_turnover
from app.exchanges.bybit.ws_client import BybitKlineWS
from app.screener.detectors.pump_rules import detect_pump



def dedup_key(symbol: str, rule_id: int, exchange: str = "") -> str:
    """Build per-rule per-exchange dedupe key: ``exchange:SYMBOL:rule_id``."""
    ex = exchange.lower() if exchange else ""
    return f"{ex}:{symbol.upper()}:{rule_id}"


def dedup_ok_and_touch(key: str, hold_minutes: int) -> bool:
    """Return True if we can emit now; also update last_at to now."""
    now = datetime.now(timezone.utc)
    rec = SignalDedup.query.filter_by(key=key).first()
    if rec and rec.last_at:
        last = rec.last_at
        # Ensure timezone-aware for comparison
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last) < timedelta(minutes=int(hold_minutes)):
            return False
    if not rec:
        rec = SignalDedup(key=key, last_at=now)
        db.session.add(rec)
    else:
        rec.last_at = now
    db.session.commit()
    return True


def insert_signal(
    *,
    exchange: str,
    symbol: str,
    rule_id: int,
    rule_label: str = "",
    rule_color: str = "",
    change_pct: float,
    window_min: int,
    price: float,
    when: datetime,
) -> None:
    sig = Signal(
        exchange=str(exchange),
        symbol=str(symbol).upper(),
        rule_id=rule_id,
        rule_label=rule_label,
        rule_color=rule_color,
        change_pct=float(change_pct),
        window=f"{int(window_min)}m",
        price=float(price),
        event_ts=when,
    )
    db.session.add(sig)
    db.session.commit()


def one_shot_diag(
    symbols: list[str],
    interval: str,
    max_k: int,
    rules: list,
    category: str,
) -> None:
    """Diagnostic print for a handful of symbols at startup.

    rules: list of DetectionRule model instances.
    """
    for us in symbols:
        try:
            closes = fetch_klines(us, interval=interval, limit=max_k, category=category)
            if not closes:
                print(f"diag {us}: no data", flush=True)
                continue
            last_price = float(closes[-1])
            parts: list[str] = []
            for rule in rules:
                pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
                val = 0.0 if pct is None else float(pct)
                parts.append(f"{rule.name}={val:.2f}%")
            tail = [float(x) for x in closes[-5:]]
            print(
                f"diag {us} (startup): last={last_price} closes_tail={tail} "
                + " ".join(parts),
                flush=True,
            )
        except Exception as e:
            print(f"diag ERR {us}: {e}", flush=True)


def setup_logging(level_name: str = "INFO") -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(
            logging.Formatter(fmt="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
        )
        root.addHandler(h)
    root.setLevel(level)

    # Suppress noisy library logs
    for name in ("httpx", "httpcore", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)
    # Suppress pybit/websocket reconnect spam — connection state is
    # tracked by our own staleness detection in BybitKlineWS.
    for name in ("pybit", "websocket"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def create_ws_client(
    exchange: str, interval: str, category: str, window_size: int,
) -> BybitKlineWS | None:
    """Create a WS kline client for the given exchange, or None if unsupported."""
    try:
        if exchange == "bybit":
            return BybitKlineWS(channel_type=category, interval=int(interval), window_size=window_size)
    except Exception as exc:
        print(f"WARN: WS client init failed ({exchange}): {exc}", flush=True)
    return None


def seed_and_subscribe(
    ws_client, symbols: list[str], interval: str, kline_limit: int, category: str,
    *, blocking: bool = False,
) -> None:
    """Subscribe to WS and seed history from REST.

    *blocking=True*: seed synchronously with parallel requests (startup).
    *blocking=False*: seed in background thread (symbols added mid-run).
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    ws_client.subscribe(symbols)

    def _seed_one(sym):
        try:
            closes = fetch_klines(sym, interval=interval, limit=kline_limit, category=category)
            if closes:
                ws_client.seed(sym, closes)
        except Exception:
            pass

    def _seed_all():
        workers = min(10, len(symbols)) if symbols else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pool.map(_seed_one, symbols)

    if blocking:
        _seed_all()
    else:
        threading.Thread(target=_seed_all, daemon=True).start()


def compute_active(
    universe_with_launch: list[tuple[str, int]],
    category: str,
    *,
    want_counts: bool = False,
) -> list[str] | tuple[list[str], int]:
    """Filter universe by age, volume, watchlist, and blacklist.

    *universe_with_launch*: list of (symbol, launch_ts_ms) from
    ``fetch_symbols_with_launch()``.  Age is computed from launchTime
    (single API call) instead of per-symbol kline lookups.

    All thresholds are read from DB settings on every call so that
    changes in the UI take effect without restarting the screener.
    """
    from app.settings import get_setting, DEFAULTS
    from app.constants import AGE_MIN_DAYS, VOLUME_MIN_USD

    min_age = int(get_setting("min_age_days", DEFAULTS.get("min_age_days", AGE_MIN_DAYS)))
    min_vol = int(get_setting("min_volume_usd", DEFAULTS.get("min_volume_usd", VOLUME_MIN_USD)))
    watchlist = get_setting("watchlist", []) or []
    blacklist = get_setting("blacklist", []) or []

    watchlist_set = {s.upper() for s in watchlist}
    blacklist_set = {s.upper() for s in blacklist}
    universe_names = [sym for sym, _ in universe_with_launch]
    available = set(universe_names)

    # Watchlist non-empty → ONLY these symbols (skip age/volume filters)
    if watchlist_set:
        active = [s for s in watchlist_set if s in available and s not in blacklist_set]
        aged_cnt = len(active)
        if want_counts:
            return sorted(active), aged_cnt
        return sorted(active)

    # No watchlist → normal pipeline: age → volume → blacklist
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    day_ms = 86_400_000
    aged: list[str] = []
    for sym, launch_ms in universe_with_launch:
        age_days = (now_ms - launch_ms) // day_ms
        if age_days >= min_age:
            aged.append(sym)

    active = filter_symbols_by_turnover(
        aged,
        min_usd=min_vol,
        category=category,
        allow_on_error=True,
        verbose=False,
    )

    if blacklist_set:
        active = [s for s in active if s not in blacklist_set]

    if want_counts:
        return active, len(aged)
    return active
