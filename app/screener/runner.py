# app/screener/runner.py
from __future__ import annotations

import signal
import threading
import time
from datetime import datetime, timezone

from app.constants import APP_VERSION, KLINE_CACHE_TTL_SEC
from app.extensions import db
from app.exchanges.bybit.client import fetch_symbols, fetch_symbols_with_launch, fetch_klines
from app.settings import get_setting, DEFAULTS
from app.models import DetectionRule
from app.screener.detectors.pump_rules import detect_pump
from app.screener.kline_cache import KlineCache
from app.screener.utils.alert import set_sound_files, play_alert
from app.screener.utils.tray import TrayManager, set_tray, get_tray
from app.screener.metrics_store import set_metric
from app.screener.helpers import (
    dedup_key,
    dedup_ok_and_touch,
    insert_signal,
    one_shot_diag,
    setup_logging,
    compute_active,
    create_ws_client,
    seed_and_subscribe,
)

# Consecutive disconnected polls before falling back to REST
_WS_FALLBACK_POLLS = 2


_shutdown = threading.Event()


def _handle_shutdown(signum: int, _frame: object) -> None:
    print("", flush=True)
    _shutdown.set()


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  {ts}  {msg}", flush=True)


def run_screener(app) -> None:
    # Signal handlers can only be set from the main thread.
    # In desktop mode (pywebview), run_screener runs in a child thread.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

    with app.app_context():
        def _s(key: str) -> object:
            return get_setting(key, DEFAULTS.get(key))

        # Suppress library noise FIRST, before any imports trigger logs
        setup_logging(str(_s("log_level")))

        # All config from DB
        active_exchanges = _s("active_exchanges") or ["bybit"]
        exchange = str(active_exchanges[0]) if active_exchanges else "bybit"
        interval = str(_s("kline_interval"))
        category = str(_s("category"))
        symbols_cfg = _s("symbols") or ["*"]
        auto_quote = str(_s("auto_quote"))

        hold_minutes = int(_s("dedupe_hold_minutes"))
        poll_seconds = float(_s("poll_seconds"))
        max_k = int(_s("max_klines"))

        # Prune stale dedup entries on startup (older than hold period)
        from datetime import timedelta as _td
        from app.models import SignalDedup
        _prune_cutoff = datetime.now(timezone.utc) - _td(minutes=hold_minutes)
        _pruned = SignalDedup.query.filter(SignalDedup.last_at < _prune_cutoff).delete()
        db.session.commit()
        if _pruned:
            _log(f"Pruned {_pruned} stale dedup entries (older than {hold_minutes}m)")
        debug_symbols = [str(s).upper() for s in (_s("debug_symbols") or [])]
        debug_samples = max(0, int(_s("debug_samples")))

        ACTIVE_REBUILD_SEC = float(_s("active_rebuild_sec"))
        UNIVERSE_REFRESH_SEC = float(_s("universe_refresh_sec"))

        snd_on = bool(_s("sound_enabled"))

        # Load detection rules from DB
        rules = DetectionRule.query.filter_by(enabled=True).order_by(DetectionRule.sort_order).all()
        if not rules:
            print("  ERROR  No enabled detection rules — nothing to detect", flush=True)
            return

        # Register sound files per rule (falls back to global default)
        try:
            global_sound = _s("alert_sound_file") or "pulse.wav"
            sounds = {"default": global_sound}
            for r in rules:
                sounds[r.name] = r.sound_file or global_sound
            set_sound_files(sounds)
        except Exception:
            set_sound_files(None)

        # Compute kline limit from rules
        min_len = max(r.lookback_min for r in rules) + 1
        kline_limit = min_len + 5
        if max_k:
            kline_limit = min(kline_limit, max_k)

        # ── Startup report (BEFORE network calls) ──────────────
        divider = "  " + "-" * 46
        print("", flush=True)
        print(divider, flush=True)
        print(f"  Pump Screener v{APP_VERSION}", flush=True)
        print(divider, flush=True)
        print("", flush=True)
        print(f"  Exchange    {exchange.upper()}", flush=True)
        print(f"  Category    {category} / {auto_quote}", flush=True)
        print(f"  Interval    {interval}m candles, poll every {poll_seconds:.0f}s", flush=True)
        print(f"  Sound       {'ON' if snd_on else 'OFF'} ({global_sound})", flush=True)
        print("", flush=True)
        print(f"  Rules ({len(rules)}):", flush=True)
        for r in rules:
            status = "ON" if r.enabled else "OFF"
            print(f"    - {r.threshold_pct:g}% / {r.lookback_min}m  [{status}]", flush=True)
        print("", flush=True)

        # System tray (optional, skip if already created by desktop launcher)
        tray = get_tray()
        if tray is None:
            tray_on = _s("tray_enabled")
            if tray_on is None:
                tray_on = True
            if tray_on:
                tray = TrayManager(on_quit=_shutdown.set)
                if tray.available:
                    set_tray(tray)
                    tray.start()
                else:
                    tray = None

        # Resolve symbols (network call)
        use_auto = (symbols_cfg == ["*"] or "*" in symbols_cfg)
        if use_auto:
            _log("Loading coins from exchange...")
            try:
                base_with_launch = fetch_symbols_with_launch(category=category, quote=auto_quote)
                symbols, aged_cnt = compute_active(base_with_launch, category, want_counts=True)
                set_metric(app.instance_path, "active_count", len(symbols), namespace="screener")
                min_age = int(_s("min_age_days"))
                min_vol = int(_s("min_volume_usd"))
                _log(f"Coins: {len(base_with_launch)} listed -> {aged_cnt} aged (>={min_age}d) -> {len(symbols)} active (>=${min_vol:,.0f})")
            except Exception as e:
                _log(f"ERROR  Failed to fetch symbols: {e}")
                base_with_launch = []
                symbols = []
        else:
            base_symbols = [str(s).upper() for s in symbols_cfg]
            symbols = base_symbols[:]
            _log(f"Coins: {len(symbols)} (manual list)")

        if not symbols:
            _log("ERROR  No symbols resolved — exiting.")
            return

        print("", flush=True)
        print(divider, flush=True)
        print("  Waiting for signals...", flush=True)
        print(divider, flush=True)
        print("", flush=True)

        # Startup diagnostics
        if debug_symbols:
            sample = debug_symbols[:debug_samples] if debug_samples > 0 else debug_symbols
            one_shot_diag(sample, interval, kline_limit, rules, category)

        # Kline cache (REST fallback)
        cache = KlineCache(ttl_sec=KLINE_CACHE_TTL_SEC)

        # WebSocket client
        ws_client = create_ws_client(exchange, interval, category, window_size=kline_limit)
        if ws_client:
            _log(f"WebSocket connecting to {exchange.upper()}...")
            seed_and_subscribe(ws_client, symbols, interval, kline_limit, category, blocking=True)
            _log(f"WebSocket ready ({len(symbols)} symbols)")
        else:
            _log(f"No WebSocket for {exchange}, using REST")

        # timers for periodic refresh
        next_active_rebuild = time.time() + ACTIVE_REBUILD_SEC
        next_universe_refresh = time.time() + UNIVERSE_REFRESH_SEC

        last_network_ok = True
        ws_disconnected_polls = 0
        ws_was_fallback = False
        _loop_n = 0
        _last_loop_wall = time.time()
        _SLEEP_GAP_SEC = 30.0  # wall-clock gap to detect system sleep

        while not _shutdown.is_set():
            _loop_n += 1
            loop_start = time.time()
            now_ts = time.time()

            # Detect system sleep: if wall-clock gap >> poll interval, request restart
            wall_gap = now_ts - _last_loop_wall
            if wall_gap > _SLEEP_GAP_SEC and _loop_n > 1:
                _log(f"STATUS  System wake detected (gap={wall_gap:.0f}s), requesting restart...")
                set_metric(app.instance_path, "active_count", None, namespace="screener")
                set_metric(app.instance_path, "needs_restart", True, namespace="screener")
            _last_loop_wall = now_ts

            # Periodic cache maintenance (every ~50 cycles / ~10 min)
            if _loop_n % 50 == 0:
                cache.purge_expired()

            # Fresh session every cycle — sees changes from web server
            db.session.remove()

            # Hot-reload dedupe_hold and poll_seconds from DB
            hold_minutes = int(_s("dedupe_hold_minutes"))
            poll_seconds = float(_s("poll_seconds"))

            # Hot-reload detection rules (picks up new/edited/toggled rules)
            rules = DetectionRule.query.filter_by(enabled=True).order_by(DetectionRule.sort_order).all()
            if rules:
                new_len = max(r.lookback_min for r in rules) + 1
                if new_len != min_len:
                    min_len = new_len
                    kline_limit = min_len + 5
                    if max_k:
                        kline_limit = min(kline_limit, max_k)
                    # Resize WS window and re-seed all symbols so REST fallback
                    # is not needed for every symbol while WS accumulates candles
                    if ws_client:
                        ws_client.resize_window(kline_limit)
                        seed_and_subscribe(ws_client, symbols, interval, kline_limit, category)
                    _log(f"STATUS  Rules reloaded ({len(rules)} active, min_len={min_len})")

            # --- periodic refresh of universe and active list ---
            if use_auto and now_ts >= next_universe_refresh:
                try:
                    base_with_launch = fetch_symbols_with_launch(category=category, quote=auto_quote)
                except Exception as e:
                    _log(f"WARN    Universe refresh failed: {e}")
                finally:
                    next_universe_refresh = now_ts + UNIVERSE_REFRESH_SEC

            if use_auto and now_ts >= next_active_rebuild:
                try:
                    old_n = len(symbols)
                    new_active, aged_cnt = compute_active(base_with_launch, category, want_counts=True)
                    if new_active:
                        if len(new_active) != old_n:
                            _log(f"STATUS  Coins: {old_n} -> {len(new_active)}")
                        # Subscribe new symbols to WS
                        if ws_client:
                            added = [s for s in new_active if s not in symbols]
                            if added:
                                seed_and_subscribe(ws_client, added, interval, kline_limit, category)
                        symbols = new_active
                        set_metric(app.instance_path, "active_count", len(symbols), namespace="screener")
                except Exception as e:
                    _log(f"WARN    Active rebuild failed: {e}")
                    set_metric(app.instance_path, "active_count", None, namespace="screener")
                finally:
                    next_active_rebuild = now_ts + ACTIVE_REBUILD_SEC

            # --- WS connectivity check ---
            use_ws = False
            if ws_client:
                if ws_client.connected:
                    ws_disconnected_polls = 0
                    use_ws = True
                    if ws_was_fallback:
                        _log("STATUS  WebSocket restored")
                        ws_was_fallback = False
                else:
                    ws_disconnected_polls += 1
                    if ws_disconnected_polls > _WS_FALLBACK_POLLS and not ws_was_fallback:
                        _log("STATUS  WebSocket lost, using REST fallback")
                        ws_was_fallback = True

            # --- scan symbols ---
            any_fetch_ok = False
            scanned = 0
            signals_emitted = 0

            for sym in symbols:
                try:
                    closes = None
                    # Try WS data first
                    if use_ws:
                        closes = ws_client.get_closes(sym)
                    # Fall back to cache / REST
                    if closes is None or len(closes) < min_len:
                        cached = cache.get(sym)
                        if cached and len(cached) >= min_len:
                            closes = cached
                    if closes is None or len(closes) < min_len:
                        rest = fetch_klines(sym, interval=interval, limit=kline_limit, category=category)
                        if rest:
                            cache.put(sym, rest)
                            closes = rest
                    any_fetch_ok = True

                    if not closes or len(closes) < min_len:
                        continue

                    scanned += 1
                    last_price = float(closes[-1])
                    now_dt = datetime.now(timezone.utc)

                    for rule in rules:
                        pct = detect_pump(closes, rule.lookback_min, rule.threshold_pct)
                        if pct is None:
                            continue
                        key = dedup_key(sym, rule.id, exchange)
                        if not dedup_ok_and_touch(key, hold_minutes):
                            continue
                        insert_signal(
                            exchange=exchange,
                            symbol=sym,
                            rule_id=rule.id,
                            rule_label=f"{rule.threshold_pct:g}%/{rule.lookback_min}m",
                            rule_color=rule.color or "#10b981",
                            change_pct=float(pct),
                            window_min=rule.lookback_min,
                            price=last_price,
                            when=now_dt,
                        )
                        _log(
                            f"SIGNAL  {sym:<20} +{pct:.2f}%  "
                            f"({rule.threshold_pct:g}%/{rule.lookback_min}m)  "
                            f"@ {last_price}"
                        )
                        if snd_on:
                            play_alert(rule.name)
                        signals_emitted += 1
                except Exception as e:
                    _log(f"ERROR   {sym}: {e}")
                    continue

            # Network state log
            if (not any_fetch_ok) and last_network_ok:
                _log("STATUS  Network DOWN — retrying...")
                last_network_ok = False
                set_metric(app.instance_path, "active_count", None, namespace="screener")
            elif any_fetch_ok and (not last_network_ok):
                _log("STATUS  Network restored")
                last_network_ok = True

            # Scan duration warning
            elapsed = time.time() - loop_start
            if elapsed > poll_seconds * 0.8:
                _log(f"WARN    Scan took {elapsed:.1f}s (poll interval is {poll_seconds:.0f}s)")

            # Sleep to maintain poll cadence (interruptible by shutdown signal)
            to_sleep = max(0.0, float(poll_seconds) - elapsed)
            if to_sleep > 0:
                _shutdown.wait(timeout=to_sleep)

        if ws_client:
            ws_client.stop()
        if tray:
            tray.stop()
        print("", flush=True)
        print("  ──────────────────────────────────────────────", flush=True)
        _log("Screener stopped")
        print("  ──────────────────────────────────────────────", flush=True)
