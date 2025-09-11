# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

Pump Screener Light is a Flask web app that monitors Bybit crypto pairs in real time and fires alerts (sound + UI) when price surges (pumps) are detected. The screener runs as a background CLI process; the web server exposes a live signals table and a JSON API.

## Commands

```bash
# Run the web server (dev)
flask --app app:create_app run

# Run the screener background process
flask --app app:create_app screener-run

# Initialize / reset the database
flask --app app:create_app init-db
```

There are no tests and no lint commands defined.

## Architecture

The app has two independent processes that share a SQLite database:

**Screener process** (`app/screener/runner.py`)
- Loads detection rules from the `DetectionRule` DB table (user-defined: name, lookback minutes, threshold %, color, sound)
- All settings from DB via `get_setting()` (no config.yaml — removed)
- Fetches the Bybit symbol universe every 10 min, rebuilds active list every 15 s using DB settings (age, volume, watchlist, blacklist)
- Primary data via WebSocket, REST fallback; every poll cycle runs `detect_pump()` per symbol per rule
- On hit: writes a `Signal` row, updates `SignalDedup` to suppress repeats (configurable hold), plays a sound via `screener/utils/alert.py`
- Runtime metrics (scan counts, network state) are written to `instance/runtime_metrics.json` via `metrics_store.py`

**Web server** (`app/blueprints/`)
- `site/routes.py` — homepage + `/api/signals` JSON feed (polled every 5 s by the frontend)
- `status/routes.py` — `/api/status` (exchange connectivity) and `/api/ping` (app heartbeat)
- Frontend (`static/js/app.js`) does all live updates; templates are server-rendered Jinja2 with Tailwind CSS

**Pump detection** (`app/screener/detectors/pump_rules.py`)
- `detect_pump(closes, lookback_minutes, min_pct)` — compares latest close to the close N minutes ago; returns actual % if ≥ threshold, else None
- Rules are user-defined in the DB (`DetectionRule` table), not hardcoded — each rule has name, lookback_min, threshold_pct, color, sound_file

**Exchange clients** (`app/exchanges/bybit/`)
- `client.py` — REST client for Bybit v5 API (httpx, instruments list, klines, tickers); in-memory ticker cache (15 s TTL); 3-attempt retry with backoff
- `symbol_age.py` — pages through daily klines to find first trading day; result cached in `SymbolAge` DB table
- `volume_filter.py` — filters by 24h turnover from ticker snapshot

**Symbol filtering pipeline** (`helpers.py:compute_active`)
- Reads `min_age_days`, `min_volume_usd`, `watchlist`, `blacklist` from DB on every call (dynamic, no restart needed)
- Pipeline: universe → age filter → volume filter → add watchlist (bypass filters) → remove blacklist
- Watchlist symbols are always included even if they fail age/volume thresholds
- Blacklist symbols are always excluded regardless of other criteria

**Database models** (`app/models.py`)
- `DetectionRule` — user-defined detection rules (name, lookback_min, threshold_pct, color, sound_file, enabled, sort_order)
- `Signal` — detected pump events (linked to DetectionRule via rule_id)
- `SignalDedup` — per-symbol dedup tracking
- `SymbolAge` — first-trading-day cache
- `Setting` — key-value settings store (timezone, alert preferences, etc.)

## Versioning

**Single source of truth:** `APP_VERSION` in `app/constants.py`. No version in `.env`, `config.py`, or anywhere else.

Format: `MAJOR.MINOR.PATCH` (no `v` prefix in the constant; the `v` is added at display time).

**When to bump (Claude must do this automatically when committing):**

| Change type | Bump | Examples |
|---|---|---|
| Bug fix, typo, style tweak | PATCH | fix signal dedup, fix CSS alignment |
| New feature, new page, new config option | MINOR | add settings page, add exchange adapter |
| Breaking change, DB migration, architecture rewrite | MAJOR | change DB schema, rewrite screener loop |

**Rules:**
- Bump version in the same commit as the change, not separately
- Multiple changes in one commit → use the highest applicable bump
- Never reset PATCH to 0 on MINOR bump (1.2.5 → 1.3.0 is correct, not 1.3.5)
- After bumping, verify no other file defines its own version constant

## Session Management Rules

**Screener process** (`runner.py`):
- The main scan loop MUST call `db.session.remove()` as its FIRST operation, before any reads. This discards the old session and ensures every cycle sees fresh data from the DB (including settings changed by the web server).
- NEVER call `db.session.close()`, `db.session.remove()`, or `refresh_session()` inside utility functions like `get_setting()`, `dedup_ok_and_touch()`, or `insert_signal()`. Session lifecycle is managed at the loop level only.
- Within a single poll cycle, all DB operations share the same session. This is correct and intentional.
- Detection rules and settings are re-read from DB every cycle (after `remove()`). No in-memory caching of DB-sourced config across cycles.

**Web server**: No changes needed. Flask-SQLAlchemy handles session lifecycle per-request automatically.

**Both processes**: SQLite WAL mode and `busy_timeout=5000` are set in `extensions.py`. Do not change. Never create additional SQLAlchemy engines or sessionmakers — use `db.session` exclusively.

**Hot-reloadable settings** (apply within one poll cycle, ~12s): detection rules, thresholds, filters, watchlist, blacklist, sounds, display.

**Restart-required settings**: `active_exchanges`, `kline_interval`, `category` — these affect WS subscriptions created at startup.

## Data Pipeline Rules

- WS primary + REST fallback: always check `len(closes) >= lookback_min + 1` before detection. If WS data is too short, fall back to cache then REST.
- At startup, REST seeding is **blocking** (`seed_and_subscribe(blocking=True)`) so the first scan has full data. For symbols added mid-run via rebuild, seeding is background.
- Log a warning if scan duration exceeds 80% of `poll_seconds`.

## Key Configuration

**Database (SQLite)** — all detection rules and app settings live in the DB, managed via the Settings UI. Detection sensitivity is configured through `DetectionRule` rows (name, lookback minutes, threshold %, color, sound).

**`.env`** — `SECRET_KEY`, `SITE_TITLE`. `DATABASE_URL` can override the default SQLite path. No config.yaml — all settings in DB.

## Sound Alert Backends

Platform-specific; chosen at runtime in `alert.py`:
- Windows: Windows MCI (MP3/WAV)
- macOS: `afplay`
- Linux: `paplay` → `aplay` → `mpg123` → system beep

## Competitors & References

Ориентиры при разработке UI, фич и позиционирования.

**Open-source (GitHub):**
- [binance-pump-alerts](https://github.com/brianleect/binance-pump-alerts) — Python CLI, Binance, Telegram. Взять: watchlist/blacklist, отслеживание новых листингов
- [binancePump](https://github.com/ogu83/binancePump) — JS, веб-интерфейс, заброшен
- [PumpBot](https://github.com/Robert-Ciborowski/PumpBot) — Python + TensorFlow, ML-классификация пампов

**Платные сервисы (UI-референсы):**
- [WunderTrading Pump Screener](https://wundertrading.com/en/pump-screener) — веб, Bybit/Binance, фильтры по OI, звук + Telegram. Лучший UI-референс для скринер-таблицы
- [Gainium](https://gainium.io/crypto-screener) — веб, free-forever модель, чистый UI. Референс для карточек и виджетов
- [MoonTrader](https://www.moontrader.com/) — десктоп, HFT-терминал с pump-детектором. Референс для информационной плотности
- [Elxes](https://elxes.com/) — веб, бесплатный, wick scanner + pump detector. Референс для минималистичного дизайна
- [DYOR.net](https://dyor.net/) — веб, TrendScanner, мультитаймфрейм. Референс для фильтров

**Наша ниша:** единственный open-source памп-скринер с GUI + exe + звуком. 90% конкурентов — CLI-only или веб, 100% не имеют exe.

## Exchange API Docs & SDKs

**Bybit (primary):**
- API docs: https://bybit-exchange.github.io/docs/v5/intro
- Instruments info: https://bybit-exchange.github.io/docs/v5/market/instrument
- REST Market: https://bybit-exchange.github.io/docs/v5/market/kline
- WebSocket Public: https://bybit-exchange.github.io/docs/v5/websocket/public/kline
- Rate limits: https://bybit-exchange.github.io/docs/v5/rate-limit
- Python SDK (pybit): https://github.com/bybit-exchange/pybit
- API connectors: https://github.com/bybit-exchange/api-connectors

**Bybit API gotchas:**
- `/v5/market/instruments-info`: max `limit=1000`, default 500. Linear category has 650+ instruments (580+ USDT). With `limit=500` pagination via `nextPageCursor`/`cursor` is required — symbols are alphabetical, so late-alphabet pairs (XRP, ZEC, etc.) end up on page 2. With `limit=1000` all fit in one page today, but pagination is implemented as safeguard for future growth.
- `/v5/market/tickers`: returns ALL tickers for a category in one call (no pagination needed)
- `pybit` SDK does NOT handle pagination internally — caller must loop with `cursor`

**Binance:**
- API docs: https://developers.binance.com/docs/binance-spot-api-docs/rest-api
- WebSocket Streams: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- Kline endpoint: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data
- Rate limits: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/rate-limits
- Python SDK: https://github.com/binance/binance-connector-python

**OKX:**
- API docs: https://www.okx.com/docs-v5/en/
- REST Market: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks
- WebSocket Public: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-candlesticks-channel
- Rate limits: https://www.okx.com/docs-v5/en/#rest-api-rate-limit
- Python SDK: https://github.com/okxapi/python-okx

## Community References

**AzzraelCode (YouTube + GitHub):**
- GitHub: https://github.com/AzzraelCode
- Profile: "IT Man for Traders" — algorithmic trading tutorials, exchange API examples
- `azzyt-bybit` — Bybit v5 API + pybit SDK (WS batch subscribe pattern, volatility sorting)
- `azzyt-binance` — Binance API + binance-connector (WS listen key renewal, kline callbacks)
- `azzyt-okx` — OKX v5 trading bot (exchange client vs strategy OOP separation)
- `azzyt-okx-api-examples` — Best examples: WS reconnect + checksum validation, rate-limited candle pagination
- Full analysis: `docs/research/l_azzraelcode_repos.md`
