import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import _clean_value, _df_to_records, compute_profit, app

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
# compute_profit tests
# ---------------------------------------------------------------------------

class TestComputeProfit:
    def test_basic_call_itm(self):
        """ITM call: stock at 160, strike 150, ask 10.50 -> intrinsic 10, profit per contract = (10-10.50)*100."""
        chain = [{"strike": 150.0, "ask": 10.50, "lastPrice": 10.0}]
        result = compute_profit(chain, current_price=160.0, investment=1100.0, option_type="calls")
        assert len(result) == 1
        r = result[0]
        assert r["strike"] == 150.0
        assert r["contracts"] == 1  # floor(1100 / 1050) = 1
        assert r["totalCost"] == 1050.0
        # profit = 1 * max(0, 160-150) * 100 - 1050 = 1000 - 1050 = -50
        assert r["profit"] == -50.0

    def test_basic_call_deep_itm(self):
        """Deep ITM call with enough intrinsic to be profitable."""
        chain = [{"strike": 100.0, "ask": 5.0, "lastPrice": 4.8}]
        result = compute_profit(chain, current_price=110.0, investment=5000.0, option_type="calls")
        r = result[0]
        assert r["contracts"] == 10  # floor(5000 / 500) = 10
        assert r["totalCost"] == 5000.0
        # profit = 10 * max(0, 110-100) * 100 - 5000 = 10000 - 5000 = 5000
        assert r["profit"] == 5000.0

    def test_basic_call_otm(self):
        """OTM call: stock at 140, strike 150 -> intrinsic 0, lose entire premium."""
        chain = [{"strike": 150.0, "ask": 2.0, "lastPrice": 1.8}]
        result = compute_profit(chain, current_price=140.0, investment=1000.0, option_type="calls")
        r = result[0]
        assert r["contracts"] == 5  # floor(1000 / 200) = 5
        assert r["totalCost"] == 1000.0
        # profit = 5 * 0 * 100 - 1000 = -1000
        assert r["profit"] == -1000.0

    def test_basic_put_itm(self):
        """ITM put: stock at 140, strike 150, ask 12.0."""
        chain = [{"strike": 150.0, "ask": 12.0, "lastPrice": 11.5}]
        result = compute_profit(chain, current_price=140.0, investment=1200.0, option_type="puts")
        r = result[0]
        assert r["contracts"] == 1
        assert r["totalCost"] == 1200.0
        # profit = 1 * max(0, 150-140) * 100 - 1200 = 1000 - 1200 = -200
        assert r["profit"] == -200.0

    def test_basic_put_otm(self):
        """OTM put: stock at 160, strike 150 -> intrinsic 0."""
        chain = [{"strike": 150.0, "ask": 1.0, "lastPrice": 0.9}]
        result = compute_profit(chain, current_price=160.0, investment=500.0, option_type="puts")
        r = result[0]
        assert r["contracts"] == 5
        assert r["profit"] == -500.0

    def test_multiple_strikes(self):
        chain = [
            {"strike": 100.0, "ask": 15.0, "lastPrice": 14.5},
            {"strike": 110.0, "ask": 8.0, "lastPrice": 7.5},
            {"strike": 120.0, "ask": 3.0, "lastPrice": 2.8},
        ]
        result = compute_profit(chain, current_price=112.0, investment=3000.0, option_type="calls")
        assert len(result) == 3
        assert result[0]["strike"] == 100.0
        assert result[1]["strike"] == 110.0
        assert result[2]["strike"] == 120.0

    def test_falls_back_to_lastprice_when_ask_zero(self):
        chain = [{"strike": 100.0, "ask": 0, "lastPrice": 5.0}]
        result = compute_profit(chain, current_price=110.0, investment=1000.0, option_type="calls")
        r = result[0]
        assert r["contracts"] == 2  # floor(1000 / 500) = 2
        assert r["totalCost"] == 1000.0

    def test_falls_back_to_lastprice_when_ask_none(self):
        chain = [{"strike": 100.0, "ask": None, "lastPrice": 5.0}]
        result = compute_profit(chain, current_price=110.0, investment=1000.0, option_type="calls")
        assert len(result) == 1
        assert result[0]["contracts"] == 2

    def test_skips_option_with_zero_premium(self):
        chain = [{"strike": 100.0, "ask": 0, "lastPrice": 0}]
        result = compute_profit(chain, current_price=110.0, investment=1000.0, option_type="calls")
        assert result == []

    def test_skips_option_when_too_expensive(self):
        """If a single contract costs more than the investment, it should be skipped."""
        chain = [{"strike": 100.0, "ask": 50.0, "lastPrice": 49.0}]
        result = compute_profit(chain, current_price=155.0, investment=1000.0, option_type="calls")
        # cost per contract = 50 * 100 = 5000 > 1000
        assert result == []

    def test_empty_chain(self):
        result = compute_profit([], current_price=100.0, investment=1000.0)
        assert result == []

    def test_missing_ask_key_uses_lastprice(self):
        chain = [{"strike": 100.0, "lastPrice": 5.0}]
        result = compute_profit(chain, current_price=110.0, investment=1000.0, option_type="calls")
        assert len(result) == 1
        assert result[0]["contracts"] == 2


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
