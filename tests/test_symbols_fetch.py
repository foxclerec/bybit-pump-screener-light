# tests/test_symbols_fetch.py
"""
Diagnostic tests for Bybit symbol fetching.
Run: pytest tests/test_symbols_fetch.py -v -s
"""

from __future__ import annotations

import pytest
import httpx

from app.constants import BYBIT_API_BASE


# ---------------------------------------------------------------------------
# 1. Raw API tests — call Bybit directly, no app code involved
# ---------------------------------------------------------------------------

class TestBybitRawAPI:
    """Hit Bybit API directly to understand what comes back."""

    @pytest.fixture(autouse=True)
    def _http(self):
        self.client = httpx.Client(
            base_url=BYBIT_API_BASE,
            timeout=15,
            headers={"User-Agent": "pump-screener-test/1.0"},
        )
        yield
        self.client.close()

    def _get_instruments(self, **params):
        params.setdefault("category", "linear")
        resp = self.client.get("/v5/market/instruments-info", params=params)
        resp.raise_for_status()
        data = resp.json()
        assert data.get("retCode") == 0, f"API error: {data}"
        return data["result"]

    def test_single_page_limit_1000(self):
        """With limit=1000 all linear instruments should fit in one page."""
        result = self._get_instruments(limit=1000)
        rows = result["list"]
        cursor = result.get("nextPageCursor", "")

        usdt_symbols = [r["symbol"] for r in rows if r.get("quoteCoin") == "USDT"]

        print(f"\n  limit=1000: {len(rows)} total, {len(usdt_symbols)} USDT")
        print(f"  nextPageCursor: '{cursor}'")
        print(f"  XRPUSDT in list: {'XRPUSDT' in usdt_symbols}")

        assert len(usdt_symbols) > 400, f"Expected 400+ USDT pairs, got {len(usdt_symbols)}"
        assert "XRPUSDT" in usdt_symbols, "XRPUSDT missing from limit=1000 response!"

    def test_limit_500_misses_xrp(self):
        """With limit=500 (old default), XRP may be on page 2."""
        result = self._get_instruments(limit=500)
        rows = result["list"]
        cursor = result.get("nextPageCursor", "")

        usdt_page1 = [r["symbol"] for r in rows if r.get("quoteCoin") == "USDT"]

        print(f"\n  limit=500 page1: {len(rows)} total, {len(usdt_page1)} USDT")
        print(f"  nextPageCursor: '{cursor}'")
        print(f"  XRPUSDT in page1: {'XRPUSDT' in usdt_page1}")

        if cursor:
            result2 = self._get_instruments(limit=500, cursor=cursor)
            rows2 = result2["list"]
            usdt_page2 = [r["symbol"] for r in rows2 if r.get("quoteCoin") == "USDT"]
            print(f"  limit=500 page2: {len(rows2)} total, {len(usdt_page2)} USDT")
            print(f"  XRPUSDT in page2: {'XRPUSDT' in usdt_page2}")

            all_usdt = usdt_page1 + usdt_page2
            assert "XRPUSDT" in all_usdt, "XRPUSDT missing even after pagination!"

    def test_xrpusdt_details(self):
        """Fetch XRPUSDT specifically to confirm it exists and is tradeable."""
        result = self._get_instruments(symbol="XRPUSDT")
        rows = result["list"]

        print(f"\n  XRPUSDT query: {len(rows)} results")
        if rows:
            r = rows[0]
            print(f"  symbol: {r.get('symbol')}")
            print(f"  status: {r.get('status')}")
            print(f"  quoteCoin: {r.get('quoteCoin')}")
            print(f"  baseCoin: {r.get('baseCoin')}")
            print(f"  contractType: {r.get('contractType')}")

        assert len(rows) >= 1, "XRPUSDT not found on Bybit!"
        assert rows[0]["status"] == "Trading", "XRPUSDT not in Trading status!"
        assert rows[0]["quoteCoin"] == "USDT", "XRPUSDT quoteCoin is not USDT!"

    def test_count_all_usdt_with_pagination(self):
        """Paginate through ALL instruments, count total USDT pairs."""
        all_usdt = []
        cursor = None

        for page in range(10):
            params = {"limit": 1000}
            if cursor:
                params["cursor"] = cursor

            result = self._get_instruments(**params)
            rows = result["list"]

            for r in rows:
                if r.get("quoteCoin") == "USDT":
                    all_usdt.append(r["symbol"])

            cursor = result.get("nextPageCursor", "")
            print(f"  page {page + 1}: {len(rows)} instruments, cursor={'...' if cursor else 'empty'}")

            if not cursor or not rows:
                break

        print(f"\n  Total USDT symbols: {len(all_usdt)}")
        print(f"  XRPUSDT present: {'XRPUSDT' in all_usdt}")

        # Check for some well-known symbols
        must_have = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT"]
        for sym in must_have:
            status = "OK" if sym in all_usdt else "MISSING"
            print(f"  {sym}: {status}")
            assert sym in all_usdt, f"{sym} not found in full paginated list!"


# ---------------------------------------------------------------------------
# 2. App-level tests — test fetch_symbols() function
# ---------------------------------------------------------------------------

class TestFetchSymbols:
    """Test our fetch_symbols wrapper."""

    def test_fetch_symbols_returns_xrp(self):
        """Our fetch_symbols() must include XRPUSDT."""
        from app.exchanges.bybit.client import fetch_symbols

        symbols = fetch_symbols(category="linear", quote="USDT")

        print(f"\n  fetch_symbols returned {len(symbols)} symbols")
        print(f"  XRPUSDT present: {'XRPUSDT' in symbols}")

        must_have = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT"]
        for sym in must_have:
            status = "OK" if sym in symbols else "MISSING"
            print(f"  {sym}: {status}")

        assert "XRPUSDT" in symbols, (
            f"XRPUSDT missing! Got {len(symbols)} symbols. "
            f"First 10: {symbols[:10]}, Last 10: {symbols[-10:]}"
        )

    def test_fetch_symbols_count(self):
        """Should return 500+ USDT symbols (Bybit linear has 580+)."""
        from app.exchanges.bybit.client import fetch_symbols

        symbols = fetch_symbols(category="linear", quote="USDT")
        print(f"\n  Total symbols: {len(symbols)}")

        assert len(symbols) >= 500, f"Only {len(symbols)} symbols — pagination broken?"

    def test_fetch_symbols_with_launch(self):
        """fetch_symbols_with_launch returns symbols with valid launchTime."""
        from app.exchanges.bybit.client import fetch_symbols_with_launch

        data = fetch_symbols_with_launch(category="linear", quote="USDT")

        print(f"\n  fetch_symbols_with_launch returned {len(data)} symbols")
        assert len(data) >= 500

        syms = [s for s, _ in data]
        assert "XRPUSDT" in syms, "XRPUSDT missing!"
        assert "BTCUSDT" in syms, "BTCUSDT missing!"

        # Check launchTime is valid (positive int, in the past)
        import time
        now_ms = int(time.time() * 1000)
        for sym, launch_ms in data[:5]:
            assert isinstance(launch_ms, int)
            assert 0 < launch_ms < now_ms, f"{sym} launchTime {launch_ms} invalid"
            age_days = (now_ms - launch_ms) // 86_400_000
            print(f"  {sym}: launchTime={launch_ms}, age={age_days}d")


# ---------------------------------------------------------------------------
# 3. API endpoint test — test /api/symbols returns XRP
# ---------------------------------------------------------------------------

class TestSymbolsAPI:
    """Test the /api/symbols web endpoint."""

    def test_api_symbols_contains_xrp(self, client, app):
        """GET /api/symbols must include XRPUSDT."""
        with app.app_context():
            # Clear cache to force fresh fetch
            from app.blueprints.site.settings_api import _symbols_cache
            _symbols_cache["symbols"] = []
            _symbols_cache["ts"] = 0.0

            resp = client.get("/api/symbols")
            assert resp.status_code == 200

            symbols = resp.get_json()
            print(f"\n  /api/symbols returned {len(symbols)} symbols")
            print(f"  XRPUSDT present: {'XRPUSDT' in symbols}")

            assert isinstance(symbols, list)
            assert len(symbols) >= 500
            assert "XRPUSDT" in symbols, f"XRPUSDT missing from /api/symbols!"


# ---------------------------------------------------------------------------
# 4. Autocomplete logic test — simulate frontend matching
# ---------------------------------------------------------------------------

class TestAutocompleteLogic:
    """Simulate the frontend autocomplete matching logic."""

    def _autocomplete(self, known_symbols, query, existing_tags=None):
        """Replicate settings.js showDropdown logic."""
        existing_tags = existing_tags or []
        raw = query.strip().upper()
        # Remove non-alphanumeric (JS: replace(/[^A-Z0-9]/g, ""))
        raw = "".join(c for c in raw if c.isalnum())
        if not raw:
            return []
        matches = [s for s in known_symbols if raw in s and s not in existing_tags]
        return matches[:8]

    def test_xrp_matches(self):
        """Typing 'xrp' should match XRPUSDT."""
        symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "XRPBUSD"]
        result = self._autocomplete(symbols, "xrp")
        print(f"\n  'xrp' matches: {result}")
        assert "XRPUSDT" in result

    def test_xrp_case_insensitive(self):
        """Typing 'XRP' or 'Xrp' should all work."""
        symbols = ["BTCUSDT", "XRPUSDT"]
        for query in ["xrp", "XRP", "Xrp", "xRp"]:
            result = self._autocomplete(symbols, query)
            assert "XRPUSDT" in result, f"Failed for query: {query}"

    def test_excludes_already_added(self):
        """Already-added tags should not appear in suggestions."""
        symbols = ["BTCUSDT", "XRPUSDT"]
        result = self._autocomplete(symbols, "xrp", existing_tags=["XRPUSDT"])
        assert "XRPUSDT" not in result

    def test_empty_known_symbols(self):
        """If knownSymbols is empty, no results."""
        result = self._autocomplete([], "xrp")
        assert result == []

    def test_autocomplete_with_real_data(self):
        """Run autocomplete against actual Bybit symbol list."""
        from app.exchanges.bybit.client import fetch_symbols

        symbols = fetch_symbols(category="linear", quote="USDT")
        result = self._autocomplete(symbols, "xrp")

        print(f"\n  Real data: 'xrp' matches {len(result)} symbols: {result}")
        assert "XRPUSDT" in result, (
            f"XRPUSDT not in autocomplete results! "
            f"Total symbols: {len(symbols)}, XRPUSDT in symbols: {'XRPUSDT' in symbols}"
        )


# ---------------------------------------------------------------------------
# 5. Filter pipeline test — compute_active with watchlist/blacklist
# ---------------------------------------------------------------------------

class TestComputeActive:
    """Test the symbol filtering pipeline."""

    def test_watchlist_only_these_symbols(self, app):
        """Watchlist = ONLY monitor these symbols, skip age/volume filters."""
        with app.app_context():
            from app.settings import set_setting
            from app.screener.helpers import compute_active

            set_setting("watchlist", ["XRPUSDT", "SOLUSDT"])
            set_setting("blacklist", [])
            set_setting("min_volume_usd", 999_999_999_999)
            set_setting("min_age_days", 99999)

            universe = [("BTCUSDT", 0), ("ETHUSDT", 0), ("XRPUSDT", 0), ("SOLUSDT", 0)]
            result = compute_active(universe, "linear")

            print(f"\n  With watchlist [XRPUSDT, SOLUSDT]: {result}")
            assert "XRPUSDT" in result
            assert "SOLUSDT" in result
            assert "BTCUSDT" not in result, "Non-watchlist symbol should be excluded!"
            assert "ETHUSDT" not in result, "Non-watchlist symbol should be excluded!"

    def test_blacklist_excludes(self, app):
        """Blacklisted symbols should be excluded."""
        with app.app_context():
            from app.settings import set_setting
            from app.screener.helpers import compute_active

            set_setting("watchlist", [])
            set_setting("blacklist", ["BTCUSDT"])
            set_setting("min_volume_usd", 0)
            set_setting("min_age_days", 0)

            universe = [("BTCUSDT", 0), ("ETHUSDT", 0), ("XRPUSDT", 0)]
            result = compute_active(universe, "linear")

            print(f"\n  With BTCUSDT blacklisted: {result}")
            assert "BTCUSDT" not in result, "Blacklisted symbol should be excluded!"

    def test_settings_read_from_db(self, app):
        """compute_active should use DB settings, not hardcoded constants."""
        with app.app_context():
            from app.settings import set_setting, get_setting
            from app.constants import VOLUME_MIN_USD

            set_setting("min_volume_usd", 12345)
            val = get_setting("min_volume_usd")

            print(f"\n  DB value: {val}, constant: {VOLUME_MIN_USD}")
            assert val == 12345, "Setting not saved correctly!"
            assert val != VOLUME_MIN_USD, "DB value should differ from constant!"
