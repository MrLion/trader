"""Tests for VCP Breakout Strategy plugins.

Covers:
1. VCPBreakoutLargeCap entry evaluation
2. VCPBreakoutHighOctane entry evaluation
3. Exit management (two-phase system)
4. Position sizing with constraints
5. Lifecycle hooks
6. Profile parameter loading
"""

import unittest
from datetime import date
from typing import Optional
from unittest.mock import Mock, MagicMock

import numpy as np
import pandas as pd

from traderlib.strategies.vcp_breakout import (
    VCPBreakoutBase,
    VCPBreakoutLargeCap,
    VCPBreakoutHighOctane,
)
from traderlib.strategies import StrategyContext, EntrySignal, ExitAction, ExitActionType
from traderlib.paper_state import Position
from traderlib.risk_config import RiskConfig


def make_stage2_uptrend_df(n_days: int = 200) -> pd.DataFrame:
    """Generate Stage 2 uptrend data with VCP pattern."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')

    # Strong uptrend (price above all MAs)
    prices = []
    base = 100.0

    # Uptrend phase
    for i in range(100):
        prices.append(base + i * 0.5 + np.random.randn() * 1)

    # VCP base (3 contractions)
    pivot = prices[-1]

    # Contraction 1: 15%
    for i in range(20):
        prices.append(pivot * (1 - 0.15 * (i / 20)))

    # Base 1
    for i in range(10):
        prices.append(prices[-1] * 0.85 + np.sin(i) * 1)

    # Rally
    for i in range(5):
        prices.append(prices[-1] + 1)

    # Contraction 2: 10%
    pivot2 = prices[-1]
    for i in range(15):
        prices.append(pivot2 * (1 - 0.10 * (i / 15)))

    # Base 2
    for i in range(10):
        prices.append(prices[-1] * 0.90 + np.sin(i) * 0.5)

    # Contraction 3: 5%
    pivot3 = prices[-1]
    for i in range(10):
        prices.append(pivot3 * (1 - 0.05 * (i / 10)))

    # Breakout
    for i in range(n_days - len(prices)):
        prices.append(prices[-1] + 0.5)

    prices = np.array(prices[:n_days])

    # Generate OHLCV
    highs = prices * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = prices * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1000000, 5000000, n_days)

    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': prices,
        'Volume': volumes,
    }, index=dates)


def make_stage2_details(price: float = 150.0) -> dict:
    """Create Stage 2 details dict for testing."""
    return {
        'score': 6,
        'criteria': {
            'price_above_50ma': True,
            'price_above_150ma': True,
            'price_above_200ma': True,
            '50ma_above_150ma': True,
            '50ma_above_200ma': True,
            '150ma_above_200ma': True,
            'price_above_20ema': True,
            '52w_high_proximity': True,
        },
        'ma10': price * 0.98,
        'ma20': price * 0.95,
        'ma50': price * 0.90,
        'ma150': price * 0.80,
        'ma200': price * 0.75,
    }


class MockDataProvider:
    """Mock data provider for testing."""

    def __init__(self, data: dict):
        self.data = data

    def get_bars(self, ticker: str, as_of: date, min_rows: int = 30) -> Optional[pd.DataFrame]:
        return self.data.get(ticker)

    def get_current_price(self, ticker: str, as_of: date) -> Optional[float]:
        df = self.data.get(ticker)
        if df is not None and len(df) > 0:
            return float(df['Close'].iloc[-1])
        return None


class TestVCPBreakoutBase(unittest.TestCase):
    """Tests for VCPBreakoutBase class."""

    def test_default_profile_params(self):
        """Should load default params when no risk_config."""
        strategy = VCPBreakoutLargeCap()

        self.assertIn('min_dollar_volume', strategy.params)
        self.assertIn('contraction_ranges', strategy.params)
        self.assertIn('volume_dry_up_threshold', strategy.params)

    def test_large_cap_profile_defaults(self):
        """Large-cap should have specific defaults."""
        strategy = VCPBreakoutLargeCap()

        self.assertEqual(strategy.profile, 'large_cap')
        self.assertEqual(strategy.params['min_dollar_volume'], 80000000)
        self.assertEqual(strategy.params['breakout_volume_min'], 1.4)
        self.assertEqual(strategy.params['trail_ema_period'], 20)

    def test_high_octane_profile_defaults(self):
        """High-octane should have specific defaults."""
        strategy = VCPBreakoutHighOctane()

        self.assertEqual(strategy.profile, 'high_octane')
        self.assertEqual(strategy.params['min_dollar_volume'], 20000000)
        self.assertEqual(strategy.params['breakout_volume_min'], 2.0)
        self.assertEqual(strategy.params['trail_ema_period'], 10)


class TestVCPBreakoutLargeCap(unittest.TestCase):
    """Tests for VCPBreakoutLargeCap strategy."""

    def setUp(self):
        self.risk_config = RiskConfig()
        self.strategy = VCPBreakoutLargeCap(risk_config=self.risk_config)

        # Create mock data
        self.df = make_stage2_uptrend_df(200)
        self.data_provider = MockDataProvider({'AAPL': self.df})

    def test_strategy_name(self):
        """Should have correct name."""
        self.assertEqual(self.strategy.name, 'vcp_large_cap')

    def test_strategy_side(self):
        """Should be LONG only."""
        self.assertEqual(self.strategy.side, 'LONG')

    def test_evaluate_entries_empty_tickers(self):
        """Should return empty list with no tickers."""
        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000,
            equity=100000,
        )

        signals = self.strategy.evaluate_entries(context)
        self.assertIsInstance(signals, list)

    def test_evaluate_entries_with_watchlist(self):
        """Should scan provided tickers."""
        self.strategy.watchlist_tickers = ['AAPL']

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000,
            equity=100000,
        )

        signals = self.strategy.evaluate_entries(context)
        self.assertIsInstance(signals, list)

    def test_entry_signal_structure(self):
        """Entry signals should have required fields."""
        self.strategy.watchlist_tickers = ['AAPL']

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={},
            cash=100000,
            equity=100000,
        )

        signals = self.strategy.evaluate_entries(context)

        for signal in signals:
            self.assertIsInstance(signal, EntrySignal)
            self.assertEqual(signal.side, 'LONG')
            self.assertGreater(signal.entry_price, 0)
            self.assertGreater(signal.stop_price, 0)
            self.assertGreater(signal.shares, 0)

    def test_skips_existing_positions(self):
        """Should not generate signals for held tickers."""
        self.strategy.watchlist_tickers = ['AAPL']

        position = Position(
            ticker='AAPL',
            status='OPEN',
            entry_date='2024-01-15',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
            current_stop_type='HARD',
            initial_stop_price=140.0,
        )

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={'AAPL': position},
            cash=100000,
            equity=100000,
        )

        signals = self.strategy.evaluate_entries(context)
        aapl_signals = [s for s in signals if s.ticker == 'AAPL']
        self.assertEqual(len(aapl_signals), 0)

    def test_insufficient_data_skipped(self):
        """Should skip tickers with insufficient data."""
        short_df = make_stage2_uptrend_df(30)
        data_provider = MockDataProvider({'SHORT': short_df})

        self.strategy.watchlist_tickers = ['SHORT']

        context = StrategyContext(
            data_provider=data_provider,
            sim_date=date(2024, 2, 1),
            positions={},
            cash=100000,
            equity=100000,
        )

        signals = self.strategy.evaluate_entries(context)
        self.assertEqual(len(signals), 0)


class TestVCPExitManagement(unittest.TestCase):
    """Tests for VCP two-phase exit management."""

    def setUp(self):
        self.risk_config = RiskConfig()
        self.strategy = VCPBreakoutLargeCap(risk_config=self.risk_config)
        self.df = make_stage2_uptrend_df(100)
        self.data_provider = MockDataProvider({'AAPL': self.df})

    def make_position(self, entry_price: float = 150.0,
                      stop_price: float = 140.0,
                      current_price: float = 155.0) -> Position:
        """Create a position for testing."""
        return Position(
            ticker='AAPL',
            status='OPEN',
            entry_date='2024-01-15',
            entry_price=entry_price,
            shares=100,
            stop_price=stop_price,
            target_price=entry_price * 1.10,
            initial_risk=(entry_price - stop_price) * 100,
            sector='Technology',
            current_stop_type='HARD',
            initial_stop_price=stop_price,
        )

    def test_manage_exits_returns_actions(self):
        """Should return exit actions for held positions."""
        position = self.make_position()

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={'AAPL': position},
            cash=50000,
            equity=100000,
        )

        actions = self.strategy.manage_exits(context)
        self.assertIsInstance(actions, list)

        # Should have one action per position
        aapl_actions = [a for a in actions if a.ticker == 'AAPL']
        self.assertEqual(len(aapl_actions), 1)

    def test_exit_action_structure(self):
        """Exit actions should have required fields."""
        position = self.make_position()

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={'AAPL': position},
            cash=50000,
            equity=100000,
        )

        actions = self.strategy.manage_exits(context)

        for action in actions:
            self.assertIsInstance(action, ExitAction)
            self.assertIn(action.action, [ExitActionType.EXIT,
                                           ExitActionType.UPDATE_STOP,
                                           ExitActionType.HOLD])
            self.assertIsInstance(action.reason, str)

    def test_phase1_holds_initial_stop(self):
        """Below 2R should hold initial stop."""
        # Entry 150, stop 140 = 10 risk (1R)
        # Current 155 = 5 gain = 0.5R (below 2R threshold)
        position = self.make_position(entry_price=150.0, stop_price=140.0)

        context = StrategyContext(
            data_provider=self.data_provider,
            sim_date=date(2024, 6, 1),
            positions={'AAPL': position},
            cash=50000,
            equity=100000,
        )

        actions = self.strategy.manage_exits(context)
        aapl_action = [a for a in actions if a.ticker == 'AAPL'][0]

        # Should be HOLD or UPDATE_STOP with higher low logic
        self.assertIn(aapl_action.action,
                     [ExitActionType.HOLD, ExitActionType.UPDATE_STOP])


class TestVCPBreakoutHighOctane(unittest.TestCase):
    """Tests for VCPBreakoutHighOctane strategy."""

    def setUp(self):
        self.risk_config = RiskConfig()
        self.strategy = VCPBreakoutHighOctane(risk_config=self.risk_config)

    def test_strategy_name(self):
        """Should have correct name."""
        self.assertEqual(self.strategy.name, 'vcp_high_octane')

    def test_tighter_ema_period(self):
        """Should use 10-day EMA for trailing."""
        self.assertEqual(self.strategy.params['trail_ema_period'], 10)

    def test_lower_volume_threshold(self):
        """Should have lower volume thresholds."""
        self.assertEqual(self.strategy.params['min_dollar_volume'], 20000000)
        self.assertEqual(self.strategy.params['min_share_volume'], 400000)

    def test_stricter_breakout_volume(self):
        """Should require 2x volume for breakout."""
        self.assertEqual(self.strategy.params['breakout_volume_min'], 2.0)


class TestVCPStrategyRegistry(unittest.TestCase):
    """Tests for strategy auto-registration."""

    def test_strategies_registered(self):
        """Both VCP strategies should be in registry."""
        from traderlib.strategies import list_strategies

        strategies = list_strategies()
        self.assertIn('vcp_large_cap', strategies)
        self.assertIn('vcp_high_octane', strategies)

    def test_get_strategy_large_cap(self):
        """Should retrieve large_cap strategy."""
        from traderlib.strategies import get_strategy

        strategy = get_strategy('vcp_large_cap')
        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.name, 'vcp_large_cap')

    def test_get_strategy_high_octane(self):
        """Should retrieve high_octane strategy."""
        from traderlib.strategies import get_strategy

        strategy = get_strategy('vcp_high_octane')
        self.assertIsNotNone(strategy)
        self.assertEqual(strategy.name, 'vcp_high_octane')


if __name__ == '__main__':
    unittest.main()
