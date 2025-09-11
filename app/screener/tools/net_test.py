# app/screener/tools/net_diag.py
# NOTE: Do not remove path lines below. They ensure imports work when running as a standalone script.

import sys
import time
import json
import math
import argparse
from pathlib import Path
import httpx

# --- PATHS (keep these) ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent.parent          # -> pump_screener/
APP_DIR = PROJECT_ROOT / "app"                            # -> pump_screener/app/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
# --------------------------

# Optional: use project logger if available; also ALWAYS print to console
try:
    from app.screener.utils.logging_setup import setup_logging
    logger = setup_logging("net_diag")

    def _console(msg): 
        print(msg, flush=True)

    def log(msg):
        _console(msg)
        try: logger.info(msg)
        except Exception: pass

    def warn(msg):
        _console(msg)
        try: logger.warning(msg)
        except Exception: pass

    def err(msg):
        _console(msg)
        try: logger.error(msg)
        except Exception: pass
except Exception:
    def log(msg): print(msg, flush=True)
    def warn(msg): print(msg, flush=True)
    def err(msg): print(msg, flush=True)


BYBIT_BASE = "https://api.bybit.com"

def http_get(path: str, params: dict | None = None, timeout: int = 5):
    """
    HTTP GET via httpx. Returns (status_code, json_obj, latency_ms, raw_text).
    Classifies network errors separately.
    """
    url = f"{BYBIT_BASE}{path}"
    t0 = time.perf_counter()
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"User-Agent": "net-diag/1.0"},
            timeout=httpx.Timeout(timeout, connect=timeout),
        )
        body = resp.text
        latency = int((time.perf_counter() - t0) * 1000)
        try:
            data = resp.json()
        except Exception:
            data = None
        return resp.status_code, data, latency, body
    except httpx.HTTPError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        return None, {"error": str(e)}, latency, ""

def classify(status_code: int | None, payload: dict | None):
    """
    Returns one of: ok, rate_limited, maintenance, server_error, http_error, network_down
    """
    if status_code is None:
        return "network_down"

    # Identify obvious rate-limits
    if status_code in (403, 429):
        return "rate_limited"

    # Try to infer Bybit retCode if present
    ret_code = None
    if isinstance(payload, dict):
        ret_code = payload.get("retCode")
        # Some maintenance codes may appear via /system/status
        if "result" in payload and isinstance(payload["result"], dict):
            st = payload["result"].get("status")
            if str(st).lower() in ("maintenance", "maintaining"):
                return "maintenance"

    if status_code >= 500:
        return "server_error"

    if status_code == 200:
        # Bybit usually uses retCode==0 for success
        if ret_code == 0 or ret_code is None:
            return "ok"
        # Non-zero retCode but HTTP OK -> treat as http_error (logical/API error)
        return "http_error"

    return "http_error"

def probe_market_time(timeout: int = 5):
    return http_get("/v5/market/time", None, timeout)

def probe_system_status(timeout: int = 5):
    return http_get("/v5/system/status", None, timeout)

def probe_tickers(category: str = "linear", symbol: str | None = None, timeout: int = 5):
    params = {"category": category}
    if symbol:
        params["symbol"] = symbol
    return http_get("/v5/market/tickers", params, timeout)

def probe_kline(category: str, symbol: str, interval: str = "1", limit: int = 5, timeout: int = 5):
    params = {"category": category, "symbol": symbol, "interval": interval, "limit": limit}
    return http_get("/v5/market/kline", params, timeout)

def emoji(kind: str) -> str:
    return {
        "ok": "🟢",
        "rate_limited": "🟠",
        "maintenance": "🟣",
        "server_error": "🟥",
        "http_error": "🟧",
        "network_down": "🔴",
    }.get(kind, "⬜")

def main():
    parser = argparse.ArgumentParser(description="Bybit connectivity & limits quick diagnostic")
    parser.add_argument("--cycles", type=int, default=1, help="How many rounds to run")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between rounds")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout seconds")
    parser.add_argument("--category", type=str, default="linear", help="Bybit category (linear, spot, inverse)")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Symbol for specific checks")
    parser.add_argument("--with-kline", action="store_true", help="Also probe short 1m kline")
    args = parser.parse_args()

    counters = {
        "ok": 0, "rate_limited": 0, "maintenance": 0,
        "server_error": 0, "http_error": 0, "network_down": 0
    }
    latencies = []

    for i in range(1, args.cycles + 1):
        log(f"\n=== Round {i}/{args.cycles} ===")

        sc, data, lat, _ = probe_market_time(args.timeout)
        kind = classify(sc, data)
        latencies.append(lat)
        log(f"{emoji(kind)} /v5/market/time  -> {kind.upper()} | {sc} | {lat} ms")
        counters[kind] += 1

        sc, data, lat, _ = probe_system_status(args.timeout)
        kind2 = classify(sc, data)
        log(f"{emoji(kind2)} /v5/system/status -> {kind2.upper()} | {sc} | {lat} ms")
        counters[kind2] += 1

        sc, data, lat, _ = probe_tickers(args.category, args.symbol, args.timeout)
        kind3 = classify(sc, data)
        log(f"{emoji(kind3)} /v5/market/tickers?category={args.category}&symbol={args.symbol} -> {kind3.upper()} | {sc} | {lat} ms")
        counters[kind3] += 1

        if args.with_kline:
            sc, data, lat, _ = probe_kline(args.category, args.symbol, "1", 5, args.timeout)
            kind4 = classify(sc, data)
            log(f"{emoji(kind4)} /v5/market/kline 1m last5 -> {kind4.upper()} | {sc} | {lat} ms")
            counters[kind4] += 1

        if i < args.cycles:
            time.sleep(args.interval)

    # Summary
    total = sum(counters.values())
    ok_share = counters["ok"] / total if total else 0.0
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0

    log("\n--- Summary ---")
    for k in ["ok", "rate_limited", "maintenance", "server_error", "http_error", "network_down"]:
        log(f"{emoji(k)} {k:<13} : {counters[k]}")

    # Recommend OFFLINE_AFTER ~ 3× typical check interval (fallback to 30s)
    recommended_offline_after = max(30, 3 * args.interval)
    log(f"\nSuggested OFFLINE_AFTER_SEC: {recommended_offline_after}  (≈ 3 × interval)")
    log(f"Avg latency: {avg_lat} ms | OK share: {ok_share:.0%}")

    # Exit code: 0 if mostly OK (or only rate-limited/maintenance), 1 if network_down dominated
    hard_fail = counters["network_down"] > 0 and counters["ok"] == 0
    sys.exit(1 if hard_fail else 0)

if __name__ == "__main__":
    main()
