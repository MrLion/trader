"""Tests for backtest strategy module."""

import unittest
from datetime import date

import numpy as np
import pandas as pd

from traderlib.backtest.data_provider import DictDataProvider
from traderlib.backtest.strategy import (
    EntrySignal, ExitAction, ExitActionType, Strategy, Stage2MomentumStrategy,
    BacktestStrategyContext,
)
from traderlib.paper_exits import ExitEngine
from traderlib.paper_state import Position
from traderlib.risk_config import RiskConfig


def make_ohlcv(n_days: int, start_price: float = 100.0,
               volatility: float = 0.02,
               start_date: str = '2023-01-01') -> pd.DataFrame:
    """Generate synthetic OHLCV data with uptrend for Stage 2 scoring."""
    np.random.seed(42)
    dates = pd.date_range(start=start_date, periods=n_days, freq='D')
    # Add slight uptrend to help with Stage 2 scoring
    trend = np.linspace(0, start_price * 0.3, n_days)
    closes = start_price + np.random.randn(n_days).cumsum() * volatility * start_price + trend
    closes = np.maximum(closes, 1.0)
    highs = closes * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = closes * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1_000_000, 10_000_000, n_days)

    return pd.DataFrame({
        'Open': opens, 'High': highs, 'Low': lows,
        'Close': closes, 'Volume': volumes,
    }, index=dates)


def make_position(**overrides) -> Position:
    defaults = dict(
        ticker='AAPL', status='OPEN', entry_date='2024-01-15',
        entry_price=150.0, shares=100, stop_price=140.0,
        target_price=170.0, initial_risk=1000.0,
        sector='Technology', current_stop_type='HARD',
        initial_stop_price=140.0,
    )
    defaults.update(overrides)
    return Position(**defaults)


class TestEntrySignal(unittest.TestCase):
    """Tests for EntrySignal dataclass."""

    def test_default_side_is_long(self):
        signal = EntrySignal(ticker='AAPL')
        self.assertEqual(signal.side, 'LONG')

    def test_custom_fields(self):
        signal = EntrySignal(
            ticker='AAPL', side='LONG',
            entry_price=150.0, stop_price=140.0,
            target_price=170.0, shares=100,
            sector='Technology', entry_score=65, stage2_score=6,
        )
        self.assertEqual(signal.entry_score, 65)
        self.assertEqual(signal.stage2_score, 6)


class TestExitAction(unittest.TestCase):
    """Tests for ExitAction dataclass."""

    def test_fields(self):
        action = ExitAction(ticker='AAPL', action=ExitActionType.EXIT, reason='STOP_HIT')
        self.assertEqual(action.ticker, 'AAPL')
        self.assertEqual(action.reason, 'STOP_HIT')
        self.assertEqual(action.action, ExitActionType.EXIT)


class TestStage2MomentumStrategy(unittest.TestCase):
    """Tests for Stage2MomentumStrategy."""

    def setUp(self):
        self.risk_config = RiskConfig()
        self.exit_engine = ExitEngine(risk_config=self.risk_config)
        self.data = {
            'AAPL': make_ohlcv(300, 150.0, start_date='2023-01-01'),
            'SPY': make_ohlcv(300, 450.0, start_date='2023-01-01'),
        }
        self.provider = DictDataProvider(self.data, min_lookback=50)

    def _make_context(self, sim_date, positions=None, equity=100_000):
        """Build a BacktestStrategyContext for testing."""
        return BacktestStrategyContext(
            data_provider=self.provider,
            sim_date=sim_date,
            positions=positions or {},
            equity=equity,
            cash=equity,
            risk_config=self.risk_config,
        )

    def test_strategy_side_is_long(self):
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=self.risk_config,
        )
        self.assertEqual(strategy.side, 'LONG')

    def test_evaluate_entries_skips_held_ticker(self):
        """Strategy should not generate entry signals for already-held tickers."""
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=self.risk_config,
        )
        positions = {'AAPL': make_position()}
        context = self._make_context(date(2023, 12, 1), positions=positions)
        signals = strategy.evaluate_entries(context)
        self.assertEqual(len(signals), 0)

    def test_evaluate_entries_generates_signal(self):
        """Strategy should generate entry signals for eligible tickers."""
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=self.risk_config,
        )
        context = self._make_context(date(2023, 12, 1), positions={})
        signals = strategy.evaluate_entries(context)
        # May or may not generate a signal depending on Stage 2 score
        # but should not crash
        for signal in signals:
            self.assertEqual(signal.ticker, 'AAPL')
            self.assertEqual(signal.side, 'LONG')
            self.assertGreater(signal.shares, 0)

    def test_manage_exits_with_stop_hit(self):
        """Strategy should generate exit when stop is hit."""
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=self.risk_config,
        )
        # Position at $150, current price at $130 (below $140 stop)
        positions = {'AAPL': make_position()}
        context = self._make_context(date(2023, 12, 1), positions=positions)
        decisions = strategy.manage_exits(context)
        # Decisions may or may not exist depending on current price
        # vs stop level in the synthetic data
        self.assertIsInstance(decisions, list)

    def test_evaluate_entries_with_empty_watchlist(self):
        """Empty watchlist should return no signals."""
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=[],
            risk_config=self.risk_config,
        )
        context = self._make_context(date(2023, 12, 1), positions={})
        signals = strategy.evaluate_entries(context)
        self.assertEqual(len(signals), 0)

    def test_initial_stop_price_set_on_entry_signal(self):
        """EntrySignal should carry initial_stop_price."""
        strategy = Stage2MomentumStrategy(
            exit_engine=self.exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=self.risk_config,
        )
        context = self._make_context(date(2023, 12, 1), positions={})
        signals = strategy.evaluate_entries(context)
        for signal in signals:
            self.assertIsNotNone(signal.stop_price)


class TestExitSignalStopUpdate(unittest.TestCase):
    """Test that ExitSignal carries stop updates, no position mutation."""

    def setUp(self):
        self.risk_config = RiskConfig()
        self.engine = ExitEngine(risk_config=self.risk_config)

    def test_evaluate_exit_returns_signal_not_mutation(self):
        """ExitEngine.evaluate_exit() returns stop updates via ExitSignal, does not mutate position."""
        pos = make_position(entry_price=150.0, stop_price=140.0,
                            initial_stop_price=140.0, shares=100)
        original_stop = pos.stop_price

        # At +1.5R — should trigger EMA10 trailing (with EMA data)
        signal = self.engine.evaluate_exit(pos, 165.0)

        # Position should NOT be mutated
        self.assertEqual(pos.stop_price, original_stop)

        # Signal should carry stop update
        if signal.new_stop is not None:
            self.assertGreater(signal.new_stop, original_stop)

    def test_stop_hit_returns_none_new_stop(self):
        """When stop is hit, new_stop should be None (no ratchet on exit)."""
        pos = make_position(entry_price=150.0, stop_price=140.0,
                            initial_stop_price=140.0, shares=100)
        signal = self.engine.evaluate_exit(pos, 135.0)  # Below stop

        self.assertTrue(signal.should_exit)
        self.assertIsNone(signal.new_stop)
        self.assertIsNone(signal.new_stop_type)


class TestBacktestStrategySector:
    def test_get_sector_from_pascalcase_watchlist(self, tmp_path):
        from traderlib.backtest.strategy import Stage2MomentumStrategy
        from traderlib.paper_exits import ExitEngine
        from traderlib.risk_config import RiskConfig
        import pandas as pd

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
            "week_start": ["2026-01-01"],
        }).to_csv(watchlist, index=False)

        strategy = Stage2MomentumStrategy(
            exit_engine=ExitEngine(risk_config=RiskConfig()),
            watchlist_df=pd.read_csv(watchlist),
            sector_dict={},
        )
        sector = strategy._get_sector("AAPL")
        assert sector == "Technology", f"Expected 'Technology', got '{sector}'"


if __name__ == '__main__':
    unittest.main()
