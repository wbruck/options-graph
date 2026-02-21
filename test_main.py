import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import _clean_value, _df_to_records, app

client = TestClient(app)


# ---------------------------------------------------------------------------
# _clean_value tests
# ---------------------------------------------------------------------------

class TestCleanValue:
    def test_normal_float(self):
        assert _clean_value(1.5) == 1.5

    def test_zero(self):
        assert _clean_value(0.0) == 0.0

    def test_nan_returns_none(self):
        assert _clean_value(float("nan")) is None

    def test_inf_returns_none(self):
        assert _clean_value(float("inf")) is None

    def test_negative_inf_returns_none(self):
        assert _clean_value(float("-inf")) is None

    def test_integer_passthrough(self):
        assert _clean_value(42) == 42

    def test_string_passthrough(self):
        assert _clean_value("hello") == "hello"

    def test_none_passthrough(self):
        assert _clean_value(None) is None

    def test_bool_passthrough(self):
        assert _clean_value(True) is True


# ---------------------------------------------------------------------------
# _df_to_records tests
# ---------------------------------------------------------------------------

class TestDfToRecords:
    def _make_df(self, rows):
        return pd.DataFrame(rows)

    def test_basic_conversion(self):
        df = self._make_df([
            {"strike": 100.0, "lastPrice": 5.0, "bid": 4.9, "ask": 5.1,
             "volume": 100, "openInterest": 500,
             "impliedVolatility": 0.3, "inTheMoney": True},
        ])
        result = _df_to_records(df)
        assert len(result) == 1
        assert result[0]["strike"] == 100.0
        assert result[0]["lastPrice"] == 5.0
        assert result[0]["inTheMoney"] is True

    def test_nan_values_cleaned(self):
        df = self._make_df([
            {"strike": 100.0, "lastPrice": float("nan"), "bid": 4.9,
             "ask": float("inf"), "volume": 10, "openInterest": 0,
             "impliedVolatility": 0.25, "inTheMoney": False},
        ])
        result = _df_to_records(df)
        assert result[0]["lastPrice"] is None
        assert result[0]["ask"] is None
        assert result[0]["strike"] == 100.0

    def test_multiple_rows(self):
        df = self._make_df([
            {"strike": 100.0, "lastPrice": 5.0, "bid": 4.9, "ask": 5.1,
             "volume": 100, "openInterest": 500,
             "impliedVolatility": 0.3, "inTheMoney": True},
            {"strike": 110.0, "lastPrice": 2.0, "bid": 1.8, "ask": 2.2,
             "volume": 50, "openInterest": 200,
             "impliedVolatility": 0.35, "inTheMoney": False},
        ])
        result = _df_to_records(df)
        assert len(result) == 2
        assert result[0]["strike"] == 100.0
        assert result[1]["strike"] == 110.0

    def test_extra_columns_dropped(self):
        df = self._make_df([
            {"strike": 100.0, "lastPrice": 5.0, "bid": 4.9, "ask": 5.1,
             "volume": 100, "openInterest": 500,
             "impliedVolatility": 0.3, "inTheMoney": True,
             "contractSymbol": "AAPL230120C00100000", "extraCol": "ignored"},
        ])
        result = _df_to_records(df)
        assert "contractSymbol" not in result[0]
        assert "extraCol" not in result[0]

    def test_missing_optional_columns(self):
        df = self._make_df([
            {"strike": 100.0, "lastPrice": 5.0},
        ])
        result = _df_to_records(df)
        assert len(result) == 1
        assert result[0]["strike"] == 100.0
        assert "volume" not in result[0]

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["strike", "lastPrice", "bid", "ask",
                                    "volume", "openInterest",
                                    "impliedVolatility", "inTheMoney"])
        result = _df_to_records(df)
        assert result == []


# ---------------------------------------------------------------------------
# /api/options/{ticker} endpoint tests
# ---------------------------------------------------------------------------

def _mock_chain(calls_data, puts_data):
    chain = MagicMock()
    chain.calls = pd.DataFrame(calls_data)
    chain.puts = pd.DataFrame(puts_data)
    return chain


SAMPLE_CALL = {
    "strike": 150.0, "lastPrice": 10.0, "bid": 9.5, "ask": 10.5,
    "volume": 200, "openInterest": 1000,
    "impliedVolatility": 0.28, "inTheMoney": True,
}

SAMPLE_PUT = {
    "strike": 150.0, "lastPrice": 3.0, "bid": 2.8, "ask": 3.2,
    "volume": 80, "openInterest": 400,
    "impliedVolatility": 0.30, "inTheMoney": False,
}


class TestGetOptionsEndpoint:
    @patch("main.yf.Ticker")
    def test_valid_ticker(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ("2025-01-17", "2025-02-21")
        ticker_inst.fast_info.get.return_value = 155.0
        ticker_inst.option_chain.return_value = _mock_chain(
            [SAMPLE_CALL], [SAMPLE_PUT],
        )

        resp = client.get("/api/options/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["currentPrice"] == 155.0
        assert len(data["expirations"]) == 2
        assert "2025-01-17" in data["calls"]
        assert data["calls"]["2025-01-17"][0]["strike"] == 150.0
        assert data["puts"]["2025-01-17"][0]["strike"] == 150.0

    @patch("main.yf.Ticker")
    def test_ticker_uppercased_and_stripped(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ("2025-01-17",)
        ticker_inst.fast_info.get.return_value = 100.0
        ticker_inst.option_chain.return_value = _mock_chain(
            [SAMPLE_CALL], [SAMPLE_PUT],
        )

        resp = client.get("/api/options/  aapl  ")
        data = resp.json()
        assert data["ticker"] == "AAPL"

    @patch("main.yf.Ticker")
    def test_no_expirations_returns_404(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ()

        resp = client.get("/api/options/INVALID")
        assert resp.status_code == 404
        assert "No options available" in resp.json()["detail"]

    @patch("main.yf.Ticker")
    def test_ticker_not_found_returns_404(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        type(ticker_inst).options = property(lambda self: (_ for _ in ()).throw(Exception("No data")))

        resp = client.get("/api/options/ZZZZZZ")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    @patch("main.yf.Ticker")
    def test_max_six_expirations(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = tuple(f"2025-0{i}-17" for i in range(1, 9))
        ticker_inst.fast_info.get.return_value = 100.0
        ticker_inst.option_chain.return_value = _mock_chain(
            [SAMPLE_CALL], [SAMPLE_PUT],
        )

        resp = client.get("/api/options/AAPL")
        data = resp.json()
        assert len(data["expirations"]) == 6

    @patch("main.yf.Ticker")
    def test_chain_fetch_failure_skipped(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ("2025-01-17", "2025-02-21")
        ticker_inst.fast_info.get.return_value = 100.0

        def side_effect(exp):
            if exp == "2025-01-17":
                raise Exception("network error")
            return _mock_chain([SAMPLE_CALL], [SAMPLE_PUT])

        ticker_inst.option_chain.side_effect = side_effect

        resp = client.get("/api/options/AAPL")
        data = resp.json()
        assert "2025-01-17" not in data["calls"]
        assert "2025-02-21" in data["calls"]

    @patch("main.yf.Ticker")
    def test_all_chains_fail_returns_404(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ("2025-01-17",)
        ticker_inst.fast_info.get.return_value = 100.0
        ticker_inst.option_chain.side_effect = Exception("fail")

        resp = client.get("/api/options/AAPL")
        assert resp.status_code == 404
        assert "Could not retrieve" in resp.json()["detail"]

    @patch("main.yf.Ticker")
    def test_current_price_none_on_failure(self, mock_ticker_cls):
        ticker_inst = MagicMock()
        mock_ticker_cls.return_value = ticker_inst
        ticker_inst.options = ("2025-01-17",)
        ticker_inst.fast_info.get.side_effect = Exception("no price")
        ticker_inst.option_chain.return_value = _mock_chain(
            [SAMPLE_CALL], [SAMPLE_PUT],
        )

        resp = client.get("/api/options/AAPL")
        data = resp.json()
        assert data["currentPrice"] is None
