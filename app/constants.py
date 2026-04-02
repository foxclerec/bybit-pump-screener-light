# app/constants.py
# Shared constants and defaults. Runtime config will live in DB (Phase 2.E).

# --- Bybit API ---
BYBIT_API_BASE = "https://api.bybit.com"

USER_AGENT = "pump-screener/1.0 (+local)"

# --- HTTP defaults ---
HTTP_TIMEOUT_CONNECT_SEC = 5.0
HTTP_TIMEOUT_READ_SEC = 10.0
HTTP_TIMEOUT_WRITE_SEC = 5.0
HTTP_TIMEOUT_POOL_SEC = 5.0
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_BASE_SEC = 0.6

# --- Rate limits (safe defaults at 80% of exchange limit) ---
BYBIT_RATE_LIMIT_PER_SEC = 96      # 600 req/5s * 0.8
DEFAULT_RATE_LIMIT_PER_SEC = 50    # fallback for unknown exchanges

# --- Exchange defaults ---
DEFAULT_EXCHANGE = "bybit"
DEFAULT_CATEGORY = "linear"

# --- Tickers cache ---
TICKERS_CACHE_TTL_SEC = 15

# --- Kline cache ---
KLINE_CACHE_TTL_SEC = 55.0

# --- Symbol age ---
AGE_MIN_DAYS = 88
AGE_REQUEST_SLEEP_SEC = 0.20
AGE_DAY_MS = 86_400_000

# --- Volume filter ---
VOLUME_MIN_USD = 300_000

# --- Signal pruning ---
SIGNAL_PRUNE_HOURS = 72

# --- Circuit breaker ---
CB_FAILURE_THRESHOLD = 5
CB_OPEN_DURATION_SEC = 30.0

# --- App version (single source of truth) ---
APP_VERSION = "1.44.0"

# --- Project links & contact ---
GITHUB_REPO_URL = "https://github.com/foxclerec/bybit-pump-screener-light"
SUPPORT_EMAIL = "app.screener@proton.me"

# --- Exchange referral codes (set to empty string to disable referral) ---
BYBIT_REFERRAL_CODE = "D5YARGK"

# --- Donation & affiliate ---
DONATION_URL = "https://nowpayments.io/donation/pump_screener"
KOFI_URL = "https://ko-fi.com/pump_screener"
NOWPAYMENTS_REFERRAL_URL = "https://account.nowpayments.io/create-account?link_id=2817648636&utm_source=affiliate_lk&utm_medium=referral"
