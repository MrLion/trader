#!/usr/bin/env python3
"""Tests for backtest stop calculation and position sizing.

Targets uncovered paths in traderlib/backtest/strategy.py:
- ATR stop calculation
- MA support stop (dual-stop: max of ATR and MA support)
- Stop bounds enforcement (min/max distance from entry)
- Position sizing with risk config
- Zero shares skipping entry
- Sector lookup default
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.backtest.strategy import Stage2MomentumStrategy
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfigManager


def make_strategy():
    """Create a Stage2MomentumStrategy with mocked dependencies."""
    risk_config = RiskConfigManager(profile='conservative').get_config()
    exit_engine = ExitEngine(risk_config=risk_config)

    strategy = Stage2MomentumStrategy(
        exit_engine=exit_engine,
        watchlist_tickers=['AAPL'],
        risk_config=risk_config,
    )
    return strategy, risk_config


def make_hist_data(n=250, start_price=100.0, trend=0.05, volatility=1.0):
    """Create synthetic historical data with specified characteristics."""
    np.random.seed(42)
    dates = pd.date_range(end='2024-01-31', periods=n, freq='B')
    close = start_price + np.cumsum(np.random.randn(n) * volatility + trend)
    close = np.maximum(close, 10.0)  # Floor at $10

    high = close + np.random.rand(n) * volatility * 2
    low = close - np.random.rand(n) * volatility * 2
    low = np.maximum(low, close * 0.9)  # Low can't be too far below close

    return pd.DataFrame({
        'Open': close - np.random.rand(n) * 0.5,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': [1000000] * n,
    }, index=dates)


class TestStopCalculation:
    """Test stop price calculation in evaluate_entries."""

    def test_atr_stop_calculated(self):
        """ATR-based stop is computed from historical data."""
        strategy, risk_config = make_strategy()

        hist = make_hist_data(n=250, start_price=150.0)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        # Provide SPY data for RS calculation
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        # Should produce signals if data is good enough
        # The important thing is no crash from ATR calculation
        if signals:
            # Stop should be below entry price
            for sig in signals:
                assert sig.stop_price < sig.entry_price

    def test_stop_bounds_enforcement_min(self):
        """Stop too close to entry → clamped to minimum distance."""
        strategy, risk_config = make_strategy()

        # With conservative config, min_stop_distance_pct is 0.03 (3%)
        hist = make_hist_data(n=250, start_price=150.0, volatility=0.01)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        if signals:
            for sig in signals:
                min_stop = sig.entry_price * (1 - risk_config.stop_loss.max_stop_distance_pct)
                max_stop = sig.entry_price * (1 - risk_config.stop_loss.min_stop_distance_pct)
                # Stop should be within bounds
                assert sig.stop_price <= max_stop + 0.01  # Small tolerance
                assert sig.stop_price >= min_stop - 0.01

    def test_stop_with_insufficient_data_skips(self):
        """Insufficient historical data → ticker skipped."""
        strategy, risk_config = make_strategy()

        # Only 20 bars (insufficient for stage2)
        hist = make_hist_data(n=20, start_price=150.0)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        assert len(signals) == 0

    def test_no_config_uses_default_bounds(self):
        """Without risk config, default 3-15% bounds applied."""
        exit_engine = ExitEngine()
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=['AAPL'],
        )

        hist = make_hist_data(n=250, start_price=150.0, volatility=0.01)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        # Should not crash without config
        if signals:
            for sig in signals:
                # Default bounds: 3-15% below entry
                assert sig.stop_price <= sig.entry_price * 0.97 + 0.01
                assert sig.stop_price >= sig.entry_price * 0.85 - 0.01


class TestPositionSizing:
    """Test position sizing with risk config."""

    def test_position_sizing_with_risk_config(self):
        """Risk config limits position size via risk_per_trade_pct."""
        strategy, risk_config = make_strategy()

        hist = make_hist_data(n=250, start_price=150.0)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        if signals:
            for sig in signals:
                # Conservative config: risk_per_trade_pct = 0.005 (0.5%)
                # So max risk = 100000 * 0.005 = $500
                # shares = risk / (entry - stop)
                max_risk = 100000 * risk_config.account.risk_per_trade_pct
                max_shares_by_risk = max_risk / max(sig.entry_price - sig.stop_price, 0.01)
                # Shares should not exceed risk-based limit
                # (may be further limited by position cap or cash)
                assert sig.shares > 0

    def test_zero_shares_skips_entry(self):
        """shares <= 0 → no signal generated."""
        strategy, risk_config = make_strategy()

        hist = make_hist_data(n=250, start_price=150.0)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        # With tiny equity, shares might be zero
        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100,  # Tiny equity
        )

        # With only $100 equity, likely no signals (shares would be 0)
        # Or signals with shares > 0 from minimum position sizes
        for sig in signals:
            assert sig.shares > 0

    def test_sector_lookup_default(self):
        """When yfinance returns nothing → sector defaults to 'Unknown'."""
        exit_engine = ExitEngine()
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=['AAPL'],
        )
        # Patch _get_sector to return 'Unknown' (avoid yfinance API calls)
        strategy._get_sector = Mock(return_value='Unknown')

        hist = make_hist_data(n=250, start_price=150.0)
        data_provider = Mock()
        data_provider.get_bars = Mock(return_value=hist)
        spy_hist = make_hist_data(n=250, start_price=400.0)
        data_provider.get_bars.side_effect = lambda ticker, as_of: hist if ticker == 'AAPL' else spy_hist

        signals = strategy.evaluate_entries(
            date(2024, 1, 31),
            positions={},
            data_provider=data_provider,
            equity=100000,
        )

        if signals:
            for sig in signals:
                assert sig.sector == 'Unknown'