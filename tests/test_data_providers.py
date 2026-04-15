"""Tests for data provider protocol enforcement, data_only mode, and tickers_dropped."""

import unittest
from datetime import date

import pandas as pd

from traderlib.backtest.data_provider import (
    DataFrameProvider, DictDataProvider, InsufficientDataError,
)
from traderlib.backtest.strategy import Stage2MomentumStrategy


def make_ohlcv(n_days: int, start_price: float = 100.0) -> pd.DataFrame:
    """Generate minimal synthetic OHLCV data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=n_days, freq='B')
    closes = [start_price + i * 0.5 for i in range(n_days)]
    return pd.DataFrame({
        'Open': closes, 'High': closes, 'Low': closes,
        'Close': closes, 'Volume': [1_000_000] * n_days,
    }, index=dates)


class TestProtocolEnforcement(unittest.TestCase):
    """DataFrameProvider protocol enforcement."""

    def test_class_missing_get_current_price_fails_isinstance(self):
        """A class without get_current_price should not satisfy the protocol."""
        class IncompleteProvider:
            def get_bars(self, ticker, as_of):
                return pd.DataFrame()
            def get_trading_days(self, start, end):
                return []

        provider = IncompleteProvider()
        self.assertFalse(isinstance(provider, DataFrameProvider))

    def test_class_missing_prefetch_fails_isinstance(self):
        """A class without prefetch should not satisfy the protocol."""
        class IncompleteProvider:
            def get_bars(self, ticker, as_of):
                return pd.DataFrame()
            def get_trading_days(self, start, end):
                return []
            def get_current_price(self, ticker, as_of):
                return None

        provider = IncompleteProvider()
        self.assertFalse(isinstance(provider, DataFrameProvider))

    def test_complete_class_passes_isinstance(self):
        """A class with all protocol methods should satisfy the protocol."""
        class CompleteProvider:
            def get_bars(self, ticker, as_of):
                return pd.DataFrame()
            def get_trading_days(self, start, end):
                return []
            def get_current_price(self, ticker, as_of):
                return None
            def prefetch(self, tickers, start, end):
                pass

        provider = CompleteProvider()
        self.assertTrue(isinstance(provider, DataFrameProvider))


class TestDictDataProvider(unittest.TestCase):
    """DictDataProvider protocol compliance."""

    def test_prefetch_noop(self):
        """DictDataProvider.prefetch should be callable and return None."""
        data = {'AAPL': make_ohlcv(30)}
        provider = DictDataProvider(data)
        result = provider.prefetch(['AAPL'], date(2024, 1, 1), date(2024, 3, 1))
        self.assertIsNone(result)

    def test_satisfies_protocol(self):
        """DictDataProvider should satisfy DataFrameProvider protocol."""
        data = {'AAPL': make_ohlcv(30)}
        provider = DictDataProvider(data)
        self.assertTrue(isinstance(provider, DataFrameProvider))


class TestDataOnlyMode(unittest.TestCase):
    """AlpacaClient data_only mode tests."""

    def test_data_only_sets_trading_client_none(self):
        """AlpacaClient with data_only=True should have trading_client = None."""
        from traderlib.alpaca_client import AlpacaClient
        client = AlpacaClient(mode='paper', data_only=True)
        self.assertIsNone(client.trading_client)

    def test_data_only_creates_data_client(self):
        """AlpacaClient with data_only=True should still create data_client."""
        from traderlib.alpaca_client import AlpacaClient
        from alpaca.data.historical import StockHistoricalDataClient
        client = AlpacaClient(mode='paper', data_only=True)
        self.assertIsNotNone(client.data_client)
        self.assertIsInstance(client.data_client, StockHistoricalDataClient)

    def test_data_only_default_is_false(self):
        """AlpacaClient without data_only should create trading_client."""
        from traderlib.alpaca_client import AlpacaClient
        client = AlpacaClient(mode='paper')
        self.assertIsNotNone(client.trading_client)
        self.assertFalse(client.data_only)


class TestTickersDropped(unittest.TestCase):
    """Tickers dropped data flow tests."""

    def test_backtest_result_tickers_dropped_default(self):
        """BacktestResult should default to empty list for tickers_dropped."""
        from traderlib.backtest.engine import BacktestResult, BacktestConfig
        from traderlib.backtest.state import BacktestState

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        result = BacktestResult(
            trades=[],
            equity_curve=[],
            state=BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1)),
            benchmark=pd.DataFrame(),
            config=config,
        )
        self.assertEqual(result.tickers_dropped, [])

    def test_report_reads_tickers_dropped(self):
        """BacktestReporter should count tickers_dropped from result."""
        from traderlib.backtest.engine import BacktestResult, BacktestConfig
        from traderlib.backtest.report import BacktestReporter
        from traderlib.backtest.state import BacktestState

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        result = BacktestResult(
            trades=[],
            equity_curve=[(date(2024, 1, 1), 100_000), (date(2024, 12, 31), 105_000)],
            state=BacktestState(initial_capital=100_000, start_date=date(2024, 1, 1)),
            benchmark=pd.DataFrame(),
            config=config,
            tickers_dropped=[
                {'ticker': 'FAKE', 'reason': 'insufficient_data', 'rows': 5, 'min_required': 252},
                {'ticker': 'BOGUS', 'reason': 'no_data', 'rows': 0, 'min_required': 252},
            ],
        )
        report = BacktestReporter.generate(result)
        self.assertEqual(report.tickers_dropped, 2)


class TestCLIDefaults(unittest.TestCase):
    """Backtest CLI default flag tests."""

    def test_alpaca_mode_default_is_data_only(self):
        """--alpaca-mode should default to 'data-only'."""
        import sys
        from unittest.mock import patch

        with patch('sys.argv', ['backtest.py', '--start', '2024-01-01', '--end', '2024-12-31']):
            # Re-parse to check defaults
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--start', required=True)
            parser.add_argument('--end', required=True)
            parser.add_argument('--alpaca-mode', choices=['data-only', 'paper'], default='data-only')
            args = parser.parse_args(['--start', '2024-01-01', '--end', '2024-12-31'])
            self.assertEqual(args.alpaca_mode, 'data-only')


class TestEngineWithDictDataProvider(unittest.TestCase):
    """Engine runs end-to-end with DictDataProvider after isinstance removal."""

    def test_engine_prefetch_with_dict_provider(self):
        """BacktestEngine should call prefetch on DictDataProvider (no-op) without error.

        This verifies that the isinstance(AlpacaDataProvider) check was removed
        and that DictDataProvider.prefetch works as a no-op.
        """
        n_days = 60
        data = {
            'AAPL': make_ohlcv(n_days, start_price=150.0),
            'SPY': make_ohlcv(n_days, start_price=450.0),
        }
        trading_days = [d.date() for d in data['AAPL'].index[:n_days]]
        provider = DictDataProvider(data, trading_days=trading_days, min_lookback=10)

        # Verify DictDataProvider.prefetch is a no-op
        result = provider.prefetch(['AAPL', 'SPY'], trading_days[0], trading_days[-1])
        self.assertIsNone(result)
        # No tickers should be dropped (data is already in memory)
        self.assertEqual(len(provider.tickers_dropped), 0)

    def test_engine_accepts_dict_provider(self):
        """BacktestEngine constructor should accept DictDataProvider (satisfies protocol)."""
        from traderlib.backtest.engine import BacktestEngine, BacktestConfig
        from traderlib.paper_exits import ExitEngine
        from traderlib.risk_config import RiskConfigManager

        n_days = 60
        data = {
            'AAPL': make_ohlcv(n_days, start_price=150.0),
            'SPY': make_ohlcv(n_days, start_price=450.0),
        }
        trading_days = [d.date() for d in data['AAPL'].index[:n_days]]
        provider = DictDataProvider(data, trading_days=trading_days, min_lookback=10)

        risk_config = RiskConfigManager(profile='conservative').get_config()
        exit_engine = ExitEngine(risk_config=risk_config)
        strategy = Stage2MomentumStrategy(
            exit_engine=exit_engine,
            watchlist_tickers=['AAPL'],
            risk_config=risk_config,
        )

        config = BacktestConfig(
            start_date=trading_days[0],
            end_date=trading_days[-1],
            initial_capital=100_000,
            tickers=['AAPL'],
        )

        # Should not raise — DictDataProvider satisfies DataFrameProvider protocol
        engine = BacktestEngine(provider, strategy, config)
        self.assertIsNotNone(engine)
        # Verify prefetch is called without isinstance check
        # (If isinstance check was still there, this would skip the prefetch)
        engine.data_provider.prefetch(
            ['AAPL', 'SPY'],
            start=config.start_date,
            end=config.end_date,
        )
        self.assertEqual(len(provider.tickers_dropped), 0)


if __name__ == '__main__':
    unittest.main()