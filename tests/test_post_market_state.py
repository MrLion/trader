#!/usr/bin/env python3
"""Tests for _load_post_market_state() in paper_engine_alpaca.

Tests the standalone module-level function that loads saved positions,
fetches closing prices, computes today stats, YTD, regime, and equity
sparkline — all without instantiating the engine.

All 12 test cases cover success, partial failure, full fallback, and
edge cases (missing files, too-few bars, empty portfolio history).

Conftest.py already sets PAPER_TRADING_DATA_DIR to a temp dir, so
data_dir() resolves safely and production data is never touched.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, PropertyMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from paper_engine_alpaca import _load_post_market_state  # noqa: E402


# ---------------------------------------------------------------------------
# Test data paths — resolved via PAPER_TRADING_DATA_DIR (set by conftest.py)
# ---------------------------------------------------------------------------

def _ensure_dir(path: Path) -> Path:
    """Create parent directories for *path* and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_positions(mode: str, positions: dict) -> Path:
    """Write synthetic positions.json and return its path."""
    from traderlib.paths import data_dir
    path = _ensure_dir(data_dir() / mode / "positions.json")
    path.write_text(json.dumps(positions))
    return path


def _write_trades(mode: str, trades: list[dict]) -> Path:
    """Write synthetic trades.jsonl and return its path."""
    from traderlib.paths import data_dir
    path = _ensure_dir(data_dir() / mode / "trades.jsonl")
    with open(path, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")
    return path


# ---------------------------------------------------------------------------
# Helper: build a mock AlpacaClient instance
# ---------------------------------------------------------------------------

@pytest.fixture
def alpaca_stub():
    """Patch AlpacaClient at the class level so _load_post_market_state
    instantiates a Mock instead of the real client.

    The fixture yields the instance so individual tests can attach
    side_effect or return_value to its methods.
    """
    with patch("traderlib.alpaca_client.AlpacaClient") as mock_class:
        instance = Mock()
        # Default: all calls return None to simulate failure by default.
        # Tests that need API data override these as needed.
        instance.get_account.return_value = None
        instance.get_latest_prices_batch.return_value = None
        instance.get_portfolio_history.return_value = None
        instance.get_historical_bars.return_value = None
        mock_class.return_value = instance
        yield instance


def _make_portfolio_history(profit_loss_last=0.0, profit_loss_pct_last=0.0,
                            equity_list=None):
    """Build a dict shaped like AlpacaClient.get_portfolio_history() response."""
    if equity_list is None:
        equity_list = [100000.0]
    pl = [0.0] * (len(equity_list) - 1) + [profit_loss_last]
    pl_pct = [0.0] * (len(equity_list) - 1) + [profit_loss_pct_last]
    return {
        "timestamp": list(range(len(equity_list))),
        "equity": list(equity_list),
        "profit_loss": pl,
        "profit_loss_pct": pl_pct,
        "base_value": 100000.0,
        "timeframe": "1D",
    }


def _make_spy_bars(count: int, current_price: float = 510.0) -> pd.DataFrame:
    """Build a synthetic SPY dataframe with *count* bars for regime testing.

    The 50-bar SMA of the generated series will be close to *current_price*
    if *count* >= 50 and the ramp is gradual enough.
    """
    start_price = current_price - 50
    prices = [start_price + (current_price - start_price) * i / max(count - 1, 1)
              for i in range(count)]
    df = pd.DataFrame({"Close": prices})
    return df


# ===========================================================================
# Tests
# ===========================================================================


class TestCashEquityFromAlpaca:
    """_load_post_market_state reads cash/equity from Alpaca get_account."""

    def test_cash_equity_from_alpaca(self, alpaca_stub):
        """Test 1: account data from Alpaca is reflected in state."""
        alpaca_stub.get_account.return_value = {
            "cash": 54200.0, "equity": 110500.0,
        }
        alpaca_stub.get_latest_prices_batch.return_value = {
            "AAPL": 190.50, "NVDA": 900.00,
        }
        _write_positions("paper", {
            "AAPL": {"entry_price": 185.0, "shares": 50, "stop_price": 180.0,
                     "initial_stop_price": 180.0, "current_stop_type": "HARD",
                     "sector": "Technology"},
            "NVDA": {"entry_price": 880.0, "shares": 20, "stop_price": 850.0,
                     "initial_stop_price": 850.0, "current_stop_type": "TRAIL",
                     "sector": "Semiconductors"},
        })

        state = _load_post_market_state("paper")

        assert state["cash"] == 54200.0
        assert state["equity"] == 56300.0  # Alpaca equity - cash = 110500 - 54200


class TestPositionPricesFromAlpaca:
    """_load_post_market_state enriches positions with current_price."""

    def test_position_prices_from_alpaca(self, alpaca_stub):
        """Test 2: positions have current_price from get_latest_prices_batch."""
        alpaca_stub.get_account.return_value = {
            "cash": 50000.0, "equity": 105000.0,
        }
        alpaca_stub.get_latest_prices_batch.return_value = {
            "AAPL": 190.50,
            "NVDA": 900.00,
        }
        _write_positions("paper", {
            "AAPL": {"entry_price": 185.0, "shares": 50, "stop_price": 180.0,
                     "initial_stop_price": 180.0, "current_stop_type": "HARD",
                     "sector": "Technology"},
            "NVDA": {"entry_price": 880.0, "shares": 20, "stop_price": 850.0,
                     "initial_stop_price": 850.0, "current_stop_type": "TRAIL",
                     "sector": "Semiconductors"},
        })

        state = _load_post_market_state("paper")

        assert state["positions"]["AAPL"]["current_price"] == 190.50
        assert state["positions"]["NVDA"]["current_price"] == 900.00


class TestTodayStatsFromTradeLog:
    """today_stats derived from today's EXIT events in trades.jsonl."""

    def test_today_stats_from_trade_log(self, alpaca_stub):
        """Test 3: today_stats counts wins/losses/total_pnl/avg_r from today's EXITs."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        today = datetime.now().strftime("%Y-%m-%d")
        trades = [
            {"event": "EXIT", "ticker": "AAPL",  "timestamp": f"{today}T11:00:00",
             "realized_pnl": 50.0, "initial_risk": 100.0},
            {"event": "EXIT", "ticker": "NVDA",  "timestamp": f"{today}T12:00:00",
             "realized_pnl": -100.0, "initial_risk": 100.0},
            {"event": "EXIT", "ticker": "MSFT",  "timestamp": f"{today}T13:00:00",
             "realized_pnl": 150.0, "initial_risk": 100.0},
            {"event": "EXIT", "ticker": "OLD",   "timestamp": "2026-05-01T12:00:00",
             "realized_pnl": 999.0, "initial_risk": 100.0},  # yesterday — excluded
        ]
        _write_trades("paper", trades)

        state = _load_post_market_state("paper")

        assert state["today_stats"]["wins"] == 2
        assert state["today_stats"]["losses"] == 1
        assert state["today_stats"]["total_pnl"] == 100.0
        # avg_r = (50/100 + (-100/100) + (150/100)) / 3 = (0.5 -1.0 + 1.5) / 3 = 1.0 / 3 ≈ 0.333
        assert abs(state["today_stats"]["avg_r"] - (0.5 - 1.0 + 1.5) / 3) < 0.001


class TestLifetimeCountExcludesScale:
    """lifetime_trade_count counts EXIT events, not SCALE events."""

    def test_lifetime_count_excludes_scale(self, alpaca_stub):
        """Test 4: only EXIT events are counted in lifetime_trade_count."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        trades = [
            {"event": "SCALE", "ticker": "AAPL", "timestamp": "2026-06-01T10:00:00"},
            {"event": "ENTRY", "ticker": "AAPL", "timestamp": "2026-06-01T10:30:00"},
            {"event": "EXIT",  "ticker": "AAPL", "timestamp": "2026-06-01T11:00:00",
             "realized_pnl": 100.0},
            {"event": "SCALE", "ticker": "NVDA", "timestamp": "2026-06-01T11:30:00"},
            {"event": "ENTRY", "ticker": "NVDA", "timestamp": "2026-06-01T12:00:00"},
            {"event": "EXIT",  "ticker": "NVDA", "timestamp": "2026-06-01T13:00:00",
             "realized_pnl": 50.0},
            {"event": "SCALE", "ticker": "MSFT", "timestamp": "2026-06-01T14:00:00"},
            {"event": "EXIT",  "ticker": "MSFT", "timestamp": "2026-06-02T10:00:00",
             "realized_pnl": 200.0},
            {"event": "EXIT",  "ticker": "GOOG", "timestamp": "2026-06-02T11:00:00",
             "realized_pnl": -30.0},
            {"event": "EXIT",  "ticker": "META", "timestamp": "2026-06-02T12:00:00",
             "realized_pnl": 75.0},
        ]
        _write_trades("paper", trades)

        state = _load_post_market_state("paper")

        # 5 EXIT events (3 on June 1-2 + GOOG + META)
        # The function scans the whole file for event == "EXIT"
        assert state["lifetime_trade_count"] == 5


class TestYtdFromPortfolioHistory:
    """ytd_pnl / ytd_pnl_pct from portfolio history."""

    def test_ytd_from_portfolio_history(self, alpaca_stub):
        """Test 5: ytd_pnl comes from profit_loss[-1] in portfolio history."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 105000.0,
        }
        _write_positions("paper", {})
        alpaca_stub.get_portfolio_history.return_value = _make_portfolio_history(
            profit_loss_last=5000.0,
            profit_loss_pct_last=5.0,
            equity_list=[100000.0, 101000.0, 103000.0, 105000.0],
        )
        alpaca_stub.get_historical_bars.return_value = _make_spy_bars(60)

        state = _load_post_market_state("paper")

        assert state["ytd_pnl"] == 5000.0
        assert state["ytd_pnl_pct"] == 5.0


class TestSparklineFromPortfolioHistory:
    """equity_30d derived from portfolio history equity list."""

    def test_sparkline_from_portfolio_history(self, alpaca_stub):
        """Test 6: equity_30d = last 22 elements of equity list."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        equity = [100000.0 + i * 100 for i in range(30)]
        alpaca_stub.get_portfolio_history.return_value = _make_portfolio_history(
            profit_loss_last=3000.0,
            profit_loss_pct_last=3.0,
            equity_list=equity,
        )

        state = _load_post_market_state("paper")

        assert len(state["equity_30d"]) == 22
        assert state["equity_30d"] == equity[-22:]
        assert len(state["equity_all"]) == 30


class TestRegimeBullish:
    """Regime is BULL when SPY price > 50-SMA."""

    def test_regime_bullish(self, alpaca_stub):
        """Test 7: SPY with 60 bars and current_price > 50_sma -> BULL."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        # Gradual ramp so 50-SMA is well below current price
        spy_bars = _make_spy_bars(60, current_price=510.0)
        alpaca_stub.get_historical_bars.return_value = spy_bars

        state = _load_post_market_state("paper")

        assert state["regime"] == "BULL"


class TestRegimeUnknownWhenFewBars:
    """Regime is UNKNOWN when fewer than 50 SPY bars."""

    def test_regime_unknown_when_few_bars(self, alpaca_stub):
        """Test 8: only 30 bars -> UNKNOWN."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        alpaca_stub.get_historical_bars.return_value = _make_spy_bars(30)

        state = _load_post_market_state("paper")

        assert state["regime"] == "UNKNOWN"

    def test_regime_unknown_when_none(self, alpaca_stub):
        """No SPY bars (None) -> UNKNOWN."""
        alpaca_stub.get_account.return_value = {
            "cash": 100000.0, "equity": 100000.0,
        }
        _write_positions("paper", {})
        alpaca_stub.get_historical_bars.return_value = None

        state = _load_post_market_state("paper")

        assert state["regime"] == "UNKNOWN"


class TestAllAlpacaFailureFallback:
    """When all 4 Alpaca calls fail, falls back to yfinance."""

    def test_all_alpaca_failure_fallback(self, alpaca_stub):
        """Test 9: all Alpaca calls raise; yfinance provides prices; valid state returned."""
        # Use 2 tickers so the function hits yf.download (len > 1) instead of yf.Ticker
        _write_positions("paper", {
            "AAPL": {"entry_price": 185.0, "shares": 10, "stop_price": 180.0,
                     "initial_stop_price": 180.0, "current_stop_type": "HARD",
                     "sector": "Technology"},
            "MSFT": {"entry_price": 400.0, "shares": 5, "stop_price": 390.0,
                     "initial_stop_price": 390.0, "current_stop_type": "HARD",
                     "sector": "Technology"},
        })
        # Clear stale trade data from prior tests
        from traderlib.paths import data_dir
        trades_file = data_dir() / "paper" / "trades.jsonl"
        if trades_file.exists():
            trades_file.write_text("")

        # All Alpaca calls raise (already None by default, but be explicit)
        alpaca_stub.get_account.return_value = None
        alpaca_stub.get_latest_prices_batch.return_value = None
        alpaca_stub.get_portfolio_history.side_effect = Exception("network error")
        alpaca_stub.get_historical_bars.side_effect = Exception("network error")

        # Mock yfinance download to return a synthetic dataframe (2 tickers -> yf.download)
        dates = pd.DatetimeIndex(["2026-06-08"])
        # MultiIndex columns: level 0 = "Close", level 1 = ticker
        arrays = [["Close", "Close"], ["AAPL", "MSFT"]]
        tuples = list(zip(*arrays))
        columns = pd.MultiIndex.from_tuples(tuples)
        fake_df = pd.DataFrame(
            [[192.0, 410.0]],
            index=dates,
            columns=columns,
        )

        with patch("yfinance.download", return_value=fake_df) as mock_yf:
            state = _load_post_market_state("paper")

        assert mock_yf.called
        assert state is not None
        assert state["positions"]["AAPL"]["current_price"] == 192.0
        assert state["cash"] == 0.0  # no account data, so falls back
        assert state["regime"] == "UNKNOWN"
        assert state["today_stats"]["total_pnl"] == 0.0
        assert state["ytd_pnl"] is None  # no portfolio hist and no YTD fallback trades
        assert state["equity_30d"] is None
        assert state["equity_all"] is None


class TestPartialFailurePortfolioHistory:
    """When portfolio_history fails, YTD falls back to trade log, sparkline empty."""

    def test_partial_failure_portfolio_history(self, alpaca_stub):
        """Test 10: account + prices succeed; portfolio history fails -> fallback YTD."""
        alpaca_stub.get_account.return_value = {
            "cash": 50000.0, "equity": 105000.0,
        }
        alpaca_stub.get_latest_prices_batch.return_value = {"AAPL": 190.0}
        _write_positions("paper", {
            "AAPL": {"entry_price": 185.0, "shares": 10, "stop_price": 180.0,
                     "initial_stop_price": 180.0, "current_stop_type": "HARD",
                     "sector": "Technology"},
        })
        # Portfolio history fails
        alpaca_stub.get_portfolio_history.return_value = None

        # Provide SPY so regime is computed (not affected)
        alpaca_stub.get_historical_bars.return_value = _make_spy_bars(60, 510.0)

        # Write trades with YTD EXIT events for fallback
        trades = [
            {"event": "EXIT", "ticker": "AAPL", "timestamp": "2026-06-01T11:00:00",
             "realized_pnl": 200.0},
            {"event": "EXIT", "ticker": "NVDA", "timestamp": "2026-06-02T12:00:00",
             "realized_pnl": 300.0},
            {"event": "EXIT", "ticker": "MSFT", "timestamp": "2025-12-31T12:00:00",
             "realized_pnl": 999.0},  # 2025 — excluded from 2026 YTD fallback
        ]
        _write_trades("paper", trades)

        state = _load_post_market_state("paper")

        # Core account/position data present
        assert state["cash"] == 50000.0
        assert state["positions"]["AAPL"]["current_price"] == 190.0

        # Sparkline empty (no portfolio history)
        assert state["equity_30d"] is None
        assert state["equity_all"] is None

        # YTD falls back to sum of 2026 EXIT realized_pnl = 200 + 300 = 500
        assert state["ytd_pnl"] == 500.0

        # Regime still computed from SPY
        assert state["regime"] == "BULL"


class TestMissingPositionsJson:
    """When positions.json does not exist, state has empty positions."""

    def test_missing_positions_json_returns_empty(self, alpaca_stub):
        """Test 11: no positions.json -> empty positions dict, not None."""
        from traderlib.paths import data_dir
        pos_file = data_dir() / "paper" / "positions.json"
        if pos_file.exists():
            pos_file.unlink()
        state = _load_post_market_state("paper")
        # Function still returns a state dict (does not abort when file is missing)
        assert state is not None
        assert state["open_positions"] == 0
        assert state["positions"] == {}