# tests/test_exchange_adapters.py
"""Unit tests for exchange adapters — mock HTTP, verify data normalization."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Bybit
# ---------------------------------------------------------------------------

class TestBybitClient:
    """Tests for app.exchanges.bybit.client functions."""

    @patch("app.exchanges.bybit.client.resilient_get")
    def test_fetch_symbols(self, mock_get):
        mock_get.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {"symbol": "BTCUSDT", "quoteCoin": "USDT"},
                    {"symbol": "ETHUSDT", "quoteCoin": "USDT"},
                    {"symbol": "BTCEUR", "quoteCoin": "EUR"},
                ]
            },
        }
        from app.exchanges.bybit.client import fetch_symbols
        result = fetch_symbols(category="linear", quote="USDT")
        assert result == ["BTCUSDT", "ETHUSDT"]

    @patch("app.exchanges.bybit.client.resilient_get")
    def test_fetch_symbols_empty(self, mock_get):
        mock_get.return_value = {}
        from app.exchanges.bybit.client import fetch_symbols
        assert fetch_symbols() == []

    @patch("app.exchanges.bybit.client.resilient_get")
    def test_fetch_klines_oldest_first(self, mock_get):
        # Bybit returns newest-first; client must reverse
        mock_get.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    ["1700003000", "105", "106", "104", "105.5", "100"],
                    ["1700002000", "103", "104", "102", "103.5", "100"],
                    ["1700001000", "100", "101", "99", "100.5", "100"],
                ]
            },
        }
        from app.exchanges.bybit.client import fetch_klines
        closes = fetch_klines("BTCUSDT", interval="1", limit=3)
        assert closes == [100.5, 103.5, 105.5]  # oldest-first

    @patch("app.exchanges.bybit.client.resilient_get")
    def test_fetch_klines_empty(self, mock_get):
        mock_get.return_value = {"retCode": 0, "result": {"list": []}}
        from app.exchanges.bybit.client import fetch_klines
        assert fetch_klines("BTCUSDT") == []

    @patch("app.exchanges.bybit.client.resilient_get")
    def test_get_tickers_map_turnover(self, mock_get):
        mock_get.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {"symbol": "BTCUSDT", "turnover24h": "9876543.21"},
                    {"symbol": "ETHUSDT", "turnover24h": "1234567.89"},
                ]
            },
        }
        from app.exchanges.bybit import client as bybit_client
        # Clear cache to force fresh fetch
        bybit_client._tickers_cache.clear()

        result = bybit_client.get_tickers_map(category="linear")
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["turnover24h"] == 9876543.21
        assert result["ETHUSDT"]["turnover24h"] == 1234567.89


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------

class TestBinanceClient:
    """Tests for app.exchanges.binance.client functions."""

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_symbols(self, mock_get):
        mock_get.return_value = {
            "symbols": [
                {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "ETHUSDT", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "BTCEUR", "quoteAsset": "EUR", "status": "TRADING"},
                {"symbol": "XRPUSDT", "quoteAsset": "USDT", "status": "BREAK"},
            ],
        }
        from app.exchanges.binance.client import fetch_symbols
        result = fetch_symbols(category="linear", quote="USDT")
        assert result == ["BTCUSDT", "ETHUSDT"]

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_symbols_empty(self, mock_get):
        mock_get.return_value = {}
        from app.exchanges.binance.client import fetch_symbols
        assert fetch_symbols() == []

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_klines_oldest_first(self, mock_get):
        # Binance returns oldest-first natively
        mock_get.return_value = [
            [1700001000, "100", "101", "99", "100.5", "100", 0, "0", 0, "0", "0", "0"],
            [1700002000, "103", "104", "102", "103.5", "100", 0, "0", 0, "0", "0", "0"],
            [1700003000, "105", "106", "104", "105.5", "100", 0, "0", 0, "0", "0", "0"],
        ]
        from app.exchanges.binance.client import fetch_klines
        closes = fetch_klines("BTCUSDT", interval="1", limit=3)
        assert closes == [100.5, 103.5, 105.5]

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_klines_empty(self, mock_get):
        mock_get.return_value = []
        from app.exchanges.binance.client import fetch_klines
        assert fetch_klines("BTCUSDT") == []

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_tickers_map_turnover(self, mock_get):
        # Binance uses quoteVolume, must be normalized to turnover24h
        mock_get.return_value = [
            {"symbol": "BTCUSDT", "quoteVolume": "9876543.21"},
            {"symbol": "ETHUSDT", "quoteVolume": "1234567.89"},
        ]
        from app.exchanges.binance import client as binance_client
        binance_client._tickers_cache.clear()

        result = binance_client.fetch_tickers_map(category="linear")
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["turnover24h"] == 9876543.21
        assert result["ETHUSDT"]["turnover24h"] == 1234567.89

    @patch("app.exchanges.binance.client.resilient_get")
    def test_fetch_daily_klines(self, mock_get):
        raw_rows = [
            [1700000000000, "100", "101", "99", "100.5", "50"],
            [1700086400000, "101", "102", "100", "101.5", "60"],
        ]
        mock_get.return_value = raw_rows
        from app.exchanges.binance.client import fetch_daily_klines
        result = fetch_daily_klines("BTCUSDT", 1700000000000, 1700200000000)
        assert result == raw_rows


# ---------------------------------------------------------------------------
# OKX
# ---------------------------------------------------------------------------

class TestOkxClient:
    """Tests for app.exchanges.okx.client functions."""

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_symbols(self, mock_get):
        mock_get.return_value = {
            "code": "0",
            "data": [
                {"instId": "BTC-USDT-SWAP", "settleCcy": "USDT", "state": "live"},
                {"instId": "ETH-USDT-SWAP", "settleCcy": "USDT", "state": "live"},
                {"instId": "BTC-EUR-SWAP", "settleCcy": "EUR", "state": "live"},
                {"instId": "XRP-USDT-SWAP", "settleCcy": "USDT", "state": "suspend"},
            ],
        }
        from app.exchanges.okx.client import fetch_symbols
        result = fetch_symbols(category="linear", quote="USDT")
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result
        assert "BTCEUR" not in result
        assert "XRPUSDT" not in result

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_symbols_empty(self, mock_get):
        mock_get.return_value = {"code": "0", "data": []}
        from app.exchanges.okx.client import fetch_symbols
        assert fetch_symbols() == []

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_klines_oldest_first(self, mock_get):
        # OKX returns newest-first; client must reverse
        mock_get.return_value = {
            "code": "0",
            "data": [
                ["1700003000", "105", "106", "104", "105.5", "100", "10000"],
                ["1700002000", "103", "104", "102", "103.5", "100", "10000"],
                ["1700001000", "100", "101", "99", "100.5", "100", "10000"],
            ],
        }
        from app.exchanges.okx.client import fetch_klines
        closes = fetch_klines("BTCUSDT", interval="1", limit=3)
        assert closes == [100.5, 103.5, 105.5]

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_klines_empty(self, mock_get):
        mock_get.return_value = {"code": "0", "data": []}
        from app.exchanges.okx.client import fetch_klines
        assert fetch_klines("BTCUSDT") == []

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_tickers_map_turnover(self, mock_get):
        # OKX uses volCcy24h, must be normalized to turnover24h
        mock_get.return_value = {
            "code": "0",
            "data": [
                {"instId": "BTC-USDT-SWAP", "volCcy24h": "9876543.21"},
                {"instId": "ETH-USDT-SWAP", "volCcy24h": "1234567.89"},
            ],
        }
        from app.exchanges.okx import client as okx_client
        okx_client._tickers_cache.clear()

        result = okx_client.fetch_tickers_map(category="linear")
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["turnover24h"] == 9876543.21
        assert result["ETHUSDT"]["turnover24h"] == 1234567.89

    @patch("app.exchanges.okx.client.resilient_get")
    def test_fetch_daily_klines(self, mock_get):
        raw_rows = [
            ["1700000000000", "100", "101", "99", "100.5", "50", "5000"],
            ["1700086400000", "101", "102", "100", "101.5", "60", "6000"],
        ]
        mock_get.return_value = {"code": "0", "data": raw_rows}
        from app.exchanges.okx.client import fetch_daily_klines
        result = fetch_daily_klines("BTCUSDT", 1700000000000, 1700200000000)
        assert result == raw_rows


# ---------------------------------------------------------------------------
# OKX symbol conversion helpers
# ---------------------------------------------------------------------------

class TestOkxSymbolConversion:
    """Tests for OKX instId <-> symbol conversion."""

    def test_inst_id_to_symbol_swap(self):
        from app.exchanges.okx.client import _inst_id_to_symbol
        assert _inst_id_to_symbol("BTC-USDT-SWAP") == "BTCUSDT"

    def test_inst_id_to_symbol_spot(self):
        from app.exchanges.okx.client import _inst_id_to_symbol
        assert _inst_id_to_symbol("BTC-USDT") == "BTCUSDT"

    def test_symbol_to_inst_id_linear(self):
        from app.exchanges.okx.client import _symbol_to_inst_id
        assert _symbol_to_inst_id("BTCUSDT", "linear") == "BTC-USDT-SWAP"

    def test_symbol_to_inst_id_spot(self):
        from app.exchanges.okx.client import _symbol_to_inst_id
        assert _symbol_to_inst_id("BTCUSDT", "spot") == "BTC-USDT"


# ---------------------------------------------------------------------------
# Adapter interface compliance
# ---------------------------------------------------------------------------

class TestAdapterInterface:
    """Verify all adapters implement ExchangeAdapter correctly."""

    def test_bybit_adapter_name(self):
        from app.exchanges.bybit.adapter import BybitAdapter
        assert BybitAdapter().name == "bybit"

    def test_binance_adapter_name(self):
        from app.exchanges.binance.adapter import BinanceAdapter
        assert BinanceAdapter().name == "binance"

    def test_okx_adapter_name(self):
        from app.exchanges.okx.adapter import OkxAdapter
        assert OkxAdapter().name == "okx"

    def test_all_adapters_are_exchange_adapter(self):
        from app.exchanges.base import ExchangeAdapter
        from app.exchanges.bybit.adapter import BybitAdapter
        from app.exchanges.binance.adapter import BinanceAdapter
        from app.exchanges.okx.adapter import OkxAdapter
        assert isinstance(BybitAdapter(), ExchangeAdapter)
        assert isinstance(BinanceAdapter(), ExchangeAdapter)
        assert isinstance(OkxAdapter(), ExchangeAdapter)
