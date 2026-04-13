"""Tests for backtest data providers."""

import unittest
from datetime import date

import numpy as np
import pandas as pd

from traderlib.backtest.data_provider import (
    DataFrameProvider,
    DictDataProvider,
    InsufficientDataError,
    AlpacaDataProvider,
)


def make_ohlcv(n_days: int, start_price: float = 100.0,
               volatility: float = 0.02,
               start_date: str = '2023-01-01') -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range(start=start_date, periods=n_days, freq='D')
    closes = start_price + np.random.randn(n_days).cumsum() * volatility * start_price
    closes = np.maximum(closes, 1.0)  # No negative prices
    highs = closes * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = closes * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)
    volumes = np.random.randint(1_000_000, 10_000_000, n_days)

    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes,
    }, index=dates)


class TestDictDataProvider(unittest.TestCase):
    """Tests for DictDataProvider (in-memory test data)."""

    def setUp(self):
        self.data = {
            'AAPL': make_ohlcv(300, 150.0),
            'MSFT': make_ohlcv(300, 300.0),
            'SHORT': make_ohlcv(50, 50.0),  # Too few rows
        }
        self.provider = DictDataProvider(self.data, min_lookback=100)

    def test_get_bars_returns_data(self):
        bars = self.provider.get_bars('AAPL', date(2023, 12, 31))
        self.assertIsInstance(bars, pd.DataFrame)
        self.assertIn('Close', bars.columns)

    def test_get_bars_slices_to_as_of(self):
        as_of = date(2023, 6, 1)
        bars = self.provider.get_bars('AAPL', as_of)
        # All dates should be <= as_of
        for idx in bars.index:
            if hasattr(idx, 'date'):
                self.assertLessEqual(idx.date(), as_of)
            else:
                self.assertLessEqual(idx, as_of)

    def test_get_bars_insufficient_data_raises(self):
        with self.assertRaises(InsufficientDataError) as ctx:
            self.provider.get_bars('SHORT', date(2023, 12, 31))
        self.assertEqual(ctx.exception.ticker, 'SHORT')
        self.assertEqual(ctx.exception.min_required, 100)

    def test_get_bars_unknown_ticker_raises(self):
        with self.assertRaises(InsufficientDataError):
            self.provider.get_bars('UNKNOWN', date(2023, 12, 31))

    def test_get_trading_days(self):
        days = self.provider.get_trading_days(date(2023, 1, 1), date(2023, 1, 31))
        self.assertIsInstance(days, list)
        self.assertTrue(all(isinstance(d, date) for d in days))

    def test_get_current_price(self):
        price = self.provider.get_current_price('AAPL', date(2023, 12, 31))
        self.assertIsNotNone(price)
        self.assertIsInstance(price, float)
        self.assertGreater(price, 0)

    def test_get_current_price_returns_none_for_missing(self):
        price = self.provider.get_current_price('UNKNOWN', date(2023, 12, 31))
        self.assertIsNone(price)


class TestInsufficientDataError(unittest.TestCase):
    """Tests for InsufficientDataError."""

    def test_error_message(self):
        err = InsufficientDataError('AAPL', 50, 252)
        self.assertIn('AAPL', str(err))
        self.assertIn('50', str(err))
        self.assertIn('252', str(err))

    def test_error_attributes(self):
        err = InsufficientDataError('AAPL', 50, 252)
        self.assertEqual(err.ticker, 'AAPL')
        self.assertEqual(err.rows, 50)
        self.assertEqual(err.min_required, 252)


class TestDictDataProviderMinLookback(unittest.TestCase):
    """Tests for configurable min_lookback parameter."""

    def test_custom_min_lookback(self):
        data = {'TICK': make_ohlcv(20, 100.0)}
        provider = DictDataProvider(data, min_lookback=15)
        # Should succeed with 20 rows >= 15 minimum
        bars = provider.get_bars('TICK', date(2023, 12, 31))
        self.assertGreaterEqual(len(bars), 15)

    def test_custom_min_lookback_raises(self):
        data = {'TICK': make_ohlcv(20, 100.0)}
        provider = DictDataProvider(data, min_lookback=50)
        # Should raise with 20 rows < 50 minimum
        with self.assertRaises(InsufficientDataError):
            provider.get_bars('TICK', date(2023, 12, 31))


class TestAlpacaDataProviderInit(unittest.TestCase):
    """Tests for AlpacaDataProvider initialization (no network calls)."""

    def test_init_default(self):
        provider = AlpacaDataProvider()
        self.assertEqual(provider._min_lookback, 252)
        self.assertEqual(provider.tickers_dropped, [])

    def test_init_custom_min_lookback(self):
        provider = AlpacaDataProvider(min_lookback=100)
        self.assertEqual(provider._min_lookback, 100)

    def test_init_with_client(self):
        # None client — should not crash
        provider = AlpacaDataProvider(alpaca_client=None)
        self.assertIsNone(provider._client)


class TestDataFrameProviderProtocol(unittest.TestCase):
    """Tests for DataFrameProvider protocol compliance."""

    def test_dict_provider_is_protocol_compliant(self):
        provider = DictDataProvider({'A': make_ohlcv(100)})
        self.assertIsInstance(provider, DataFrameProvider)

    def test_alpaca_provider_is_protocol_compliant(self):
        provider = AlpacaDataProvider()
        self.assertIsInstance(provider, DataFrameProvider)


if __name__ == '__main__':
    unittest.main()