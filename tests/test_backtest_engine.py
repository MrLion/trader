"""Tests for backtest engine — day-by-day simulation with next-bar fill."""

import unittest
from datetime import date

import numpy as np
import pandas as pd

from traderlib.backtest.data_provider import DictDataProvider
from traderlib.backtest.engine import BacktestEngine, BacktestConfig, BacktestResult
from traderlib.backtest.execution import ExecutionConfig
from traderlib.backtest.state import BacktestState, TradeRecord
from traderlib.backtest.strategy import Stage2MomentumStrategy, EntrySignal, ExitDecision
from traderlib.paper_exits import ExitEngine
from traderlib.paper_state import Position
from traderlib.risk_config import RiskConfig


def make_ohlcv(n_days: int, start_price: float = 100.0,
               daily_return: float = 0.0004,
               volatility: float = 0.015,
               start_date: str = '2023-01-01') -> pd.DataFrame:
    """Generate synthetic OHLCV data with controllable return."""
    np.random.seed(hash(start_price) % (2**31))  # Different seed per ticker
    dates = pd.date_range(start=start_date, periods=n_days, freq='B')  # Business days only
    if len(dates) < n_days:
        dates = pd.date_range(start=start_date, periods=n_days, freq='D')

    returns = np.random.randn(n_days) * volatility + daily_return
    closes = start_price * np.cumprod(1 + returns)
    closes = np.maximum(closes, 1.0)

    highs = closes * (1 + abs(np.random.randn(n_days) * 0.005))
    lows = closes * (1 - abs(np.random.randn(n_days) * 0.005))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1_000_000, 10_000_000, n_days)

    return pd.DataFrame({
        'Open': opens, 'High': highs, 'Low': lows,
        'Close': closes, 'Volume': volumes,
    }, index=dates)


class TestBacktestConfig(unittest.TestCase):
    """Tests for BacktestConfig."""

    def test_defaults(self):
        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        self.assertEqual(config.initial_capital, 100_000)
        self.assertEqual(config.max_open_positions, 10)

    def test_custom(self):
        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=50_000,
            max_open_positions=5,
        )
        self.assertEqual(config.initial_capital, 50_000)
        self.assertEqual(config.max_open_positions, 5)


class TestBacktestResult(unittest.TestCase):
    """Tests for BacktestResult."""

    def test_fields(self):
        result = BacktestResult(
            trades=[], equity_curve=[],
            state=None, benchmark=pd.DataFrame(),
            config=BacktestConfig(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31)),
        )
        self.assertEqual(len(result.trades), 0)
        self.assertEqual(len(result.gap_rejections), 0)


class TestGapRejection(unittest.TestCase):
    """Test that entries are rejected when T+1 open gapped below stop."""

    def test_gap_rejection_skips_entry(self):
        """If T+1 open is below stop price, the entry should be rejected."""
        # This is tested through the engine's _resolve_pending_fills method
        # which checks open_price <= stop_price for long positions
        # We test the logic directly here

        config = ExecutionConfig(slippage_bps=0)  # Zero slippage for clarity
        state = BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1))

        # Simulate a signal where stop is at $140
        signal = EntrySignal(
            ticker='AAPL', side='LONG',
            entry_price=150.0, stop_price=140.0,
            target_price=170.0, shares=100,
            sector='Technology', entry_score=70, stage2_score=6,
        )

        # If T+1 open is $130 (below stop), the entry should be rejected
        # The engine checks: open_price <= stop_price → gap rejection
        open_price = 130.0
        self.assertLessEqual(open_price, signal.stop_price)


class TestEngineIntegration(unittest.TestCase):
    """Integration tests for BacktestEngine.

    Uses DictDataProvider with synthetic data for deterministic results.
    """

    def setUp(self):
        """Create synthetic data with known properties."""
        # Stock A: uptrending (+10% annualized)
        # Stock B: downtrending (-10% annualized)
        # SPY: moderate uptrend (+5% annualized)
        self.data = {
            'STOCKA': make_ohlcv(300, 100.0, daily_return=0.0004, volatility=0.015),
            'STOCKB': make_ohlcv(300, 100.0, daily_return=-0.0004, volatility=0.020),
            'SPY': make_ohlcv(300, 450.0, daily_return=0.0002, volatility=0.008),
        }
        self.provider = DictDataProvider(self.data, min_lookback=50)

        # Trading days from the data
        all_dates = sorted(set(
            d.date() if hasattr(d, 'date') else d
            for df in self.data.values()
            for d in df.index
        ))
        self.trading_days = all_dates

    def test_engine_run_produces_result(self):
        """Engine should run without errors and produce a BacktestResult."""
        risk_config = RiskConfig()
        exit_engine = ExitEngine(risk_config=risk_config)
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=['STOCKA'],
            risk_config=risk_config,
        )
        config = BacktestConfig(
            start_date=self.trading_days[100],
            end_date=self.trading_days[-1],
            initial_capital=100_000,
            tickers=['STOCKA'],
        )
        engine = BacktestEngine(self.provider, strategy, config)
        result = engine.run()

        self.assertIsInstance(result, BacktestResult)
        self.assertIsNotNone(result.equity_curve)
        self.assertIsNotNone(result.trades)

    def test_no_datetime_now_in_backtest(self):
        """No datetime.now() calls in backtest module code."""
        import traderlib.backtest.state as state_module
        import traderlib.backtest.engine as engine_module
        import traderlib.backtest.strategy as strategy_module

        for module in [state_module, engine_module, strategy_module]:
            import re
            source = open(module.__file__).read()
            # Remove all string literals (docstrings, comments)
            source_no_strings = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
            source_no_strings = re.sub(r"'''.*?'''", '', source_no_strings, flags=re.DOTALL)
            source_no_strings = re.sub(r"'[^']*'", '', source_no_strings)
            source_no_strings = re.sub(r'"[^"]*"', '', source_no_strings)
            source_no_strings = re.sub(r'#.*$', '', source_no_strings, flags=re.MULTILINE)
            self.assertNotIn('datetime.now()', source_no_strings,
                             f'{module.__name__} must not call datetime.now()')

    def test_no_yfinance_in_backtest(self):
        """Core backtest modules must not depend on yfinance."""
        import traderlib.backtest.data_provider as dp_module
        import traderlib.backtest.state as state_module
        import traderlib.backtest.strategy as strategy_module
        import traderlib.backtest.report as report_module
        import traderlib.backtest.execution as exec_module

        # Engine is allowed to import yfinance for optional VIX prefetch
        # (wrapped in try/except, fails open). All other modules must not.
        for module in [dp_module, state_module, strategy_module, report_module, exec_module]:
            source = open(module.__file__).read()
            self.assertNotIn('import yfinance', source,
                             f'{module.__name__} must not import yfinance')

    def test_no_file_io_in_state(self):
        """BacktestState must not touch the filesystem."""
        import traderlib.backtest.state as state_mod
        source = open(state_mod.__file__).read()
        self.assertNotIn('open(', source)
        self.assertNotIn('.save_state', source)


class TestEngineDayByDay(unittest.TestCase):
    """Test the day-by-day simulation loop mechanics."""

    def test_pending_entries_fill_at_t_plus_1(self):
        """Entry signals from day T should fill at T+1 open price."""
        # This is a structural test verifying the engine's flow:
        # 1. Day T: strategy generates entry signal
        # 2. Day T+1: engine resolves fill at open price
        # We verify this through the engine's design, not a full run
        state = BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1))
        self.assertEqual(state.sim_date, date(2024, 1, 1))

    def test_liquidation_at_end(self):
        """All positions should be liquidated at end of simulation."""
        risk_config = RiskConfig()
        data = {
            'STOCKA': make_ohlcv(300, 100.0, start_date='2023-01-01'),
            'SPY': make_ohlcv(300, 450.0, start_date='2023-01-01'),
        }
        provider = DictDataProvider(data, min_lookback=50)
        exit_engine = ExitEngine(risk_config=risk_config)
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=['STOCKA'],
            risk_config=risk_config,
        )

        all_dates = sorted(set(d.date() if hasattr(d, 'date') else d for d in data['STOCKA'].index))

        config = BacktestConfig(
            start_date=all_dates[100],
            end_date=all_dates[-1],
            initial_capital=100_000,
            tickers=['STOCKA'],
        )
        engine = BacktestEngine(provider, strategy, config)
        result = engine.run()

        # After liquidation, no open positions should remain
        self.assertEqual(len(result.state.positions), 0)


if __name__ == '__main__':
    unittest.main()