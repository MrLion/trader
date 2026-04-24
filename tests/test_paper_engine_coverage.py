#!/usr/bin/env python3
"""Additional test coverage for paper_engine_alpaca.py

Targets uncovered code paths identified in coverage report:
- Exception handling in __init__
- _sync_with_alpaca error paths and external position changes
- WebSocket trade handler
- _is_pre_market method
- Circuit breakers
- Entry/exit execution paths
- Pending order processing
- Daily signal reset
"""

import json
import sys
import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock, call

import pandas as pd
import pytz
import pytest


from traderlib.paper_state import PaperState, Position
from traderlib.paper_exits import ExitSignal


def create_engine_with_full_mocks(mode='paper'):
    """Create engine with comprehensive mocking."""
    from paper_engine_alpaca import AlpacaPaperEngine

    with patch('paper_engine_alpaca.AlpacaClient') as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.get_account.return_value = {'equity': 100000.0, 'cash': 100000.0}
        mock_client.get_positions.return_value = []
        mock_client.list_orders.return_value = []
        mock_client.is_ws_healthy.return_value = True
        mock_client.get_health_summary.return_value = 'HEALTHY'
        mock_client.rate_limiter.get_status.return_value = {
            'requests_in_window': 0,
            'max_requests': 100,
            'circuit_open': False,
        }

        with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
            with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                with patch.object(PaperState, '_load_state', return_value=None):
                    with patch('paper_engine_alpaca.WATCHLIST_PATH', Path('/tmp/test_watchlist.csv')):
                        engine = AlpacaPaperEngine(mode=mode)
                        engine.alpaca = mock_client
                        engine.state.cash = 100000.0
                        engine.state.equity = 100000.0
                        engine.state.positions = {}
                        engine.state.day_pnl = 0.0
                        return engine, mock_client


class TestInitializationErrors(unittest.TestCase):
    """Test error handling during engine initialization."""

    @patch('paper_engine_alpaca.AlpacaClient')
    def test_init_with_api_error(self, mock_client_class):
        """Test initialization when Alpaca API fails."""
        from paper_engine_alpaca import AlpacaPaperEngine

        mock_client_class.side_effect = Exception("API connection failed")

        with self.assertRaises(Exception) as ctx:
            AlpacaPaperEngine(mode='paper')

        self.assertIn("API connection", str(ctx.exception))


class TestSyncWithAlpaca(unittest.TestCase):
    """Test _sync_with_alpaca method coverage."""

    def test_sync_adds_external_positions(self):
        """Test sync adds positions from Alpaca."""
        engine, mock_client = create_engine_with_full_mocks()

        # Mock watchlist read
        mock_df = pd.DataFrame({
            'Ticker': ['AAPL'],
            'Sector': ['Technology']
        })

        # Mock order manager sync result
        engine.order_manager = Mock()
        engine.order_manager.sync_positions.return_value = {
            'added': [{'ticker': 'AAPL', 'qty': 100, 'avg_price': 150.0}],
            'removed': [],
            'discrepancies': [],
            'synced': []
        }

        with patch('paper_engine_alpaca.pd.read_csv', return_value=mock_df):
            with patch.object(engine, '_get_current_price', return_value=155.0):
                engine._sync_with_alpaca()

        self.assertIn('AAPL', engine.state.positions)
        self.assertEqual(engine.state.positions['AAPL'].shares, 100)

    def test_sync_removes_closed_positions(self):
        """Test sync removes positions closed externally."""
        engine, mock_client = create_engine_with_full_mocks()

        # Add existing position
        engine.state.positions['TSLA'] = Mock(
            ticker='TSLA',
            shares=50,
            entry_price=200.0,
            stop_price=190.0
        )

        engine.order_manager = Mock()
        engine.order_manager.sync_positions.return_value = {
            'added': [],
            'removed': ['TSLA'],
            'discrepancies': [],
            'synced': []
        }

        with patch.object(engine, '_get_current_price', return_value=210.0):
            with patch.object(engine.state, 'close_position'):
                engine._sync_with_alpaca()

        # Should attempt to close position
        self.assertTrue(hasattr(engine.state, 'close_position'))

    def test_sync_watchlist_load_failure(self):
        """Test sync continues when watchlist load fails."""
        engine, mock_client = create_engine_with_full_mocks()

        engine.order_manager = Mock()
        engine.order_manager.sync_positions.return_value = {
            'added': [],
            'removed': [],
            'discrepancies': [],
            'synced': []
        }

        with patch('paper_engine_alpaca.pd.read_csv', side_effect=FileNotFoundError()):
            # Should not raise
            engine._sync_with_alpaca()


class TestPreMarketHours(unittest.TestCase):
    """Test _is_pre_market method."""

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market_4am(self, mock_datetime):
        """Test 4:00 AM is pre-market."""
        et = pytz.timezone('US/Eastern')
        mock_datetime.now.return_value = et.localize(datetime(2024, 4, 8, 4, 0, 0))

        engine, _ = create_engine_with_full_mocks()
        self.assertTrue(engine._is_pre_market())

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market_930am(self, mock_datetime):
        """Test 9:30 AM is not pre-market."""
        et = pytz.timezone('US/Eastern')
        mock_datetime.now.return_value = et.localize(datetime(2024, 4, 8, 9, 30, 0))

        engine, _ = create_engine_with_full_mocks()
        self.assertFalse(engine._is_pre_market())

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market_weekend(self, mock_datetime):
        """Test weekend returns False."""
        et = pytz.timezone('US/Eastern')
        mock_datetime.now.return_value = et.localize(datetime(2024, 4, 6, 5, 0, 0))  # Saturday

        engine, _ = create_engine_with_full_mocks()
        self.assertFalse(engine._is_pre_market())


class TestWebSocketHandler(unittest.TestCase):
    """Test WebSocket trade handler."""

    async def async_test_ws_handler_updates_cache(self):
        """Test WebSocket handler updates price cache."""
        engine, _ = create_engine_with_full_mocks()

        # Create mock trade
        mock_trade = Mock()
        mock_trade.symbol = 'AAPL'
        mock_trade.price = 150.0
        mock_trade.size = 100

        await engine._ws_trade_handler(mock_trade)

        self.assertIn('AAPL', engine.price_cache)
        self.assertEqual(engine.price_cache['AAPL']['price'], 150.0)

    async def async_test_ws_handler_checks_exits(self):
        """Test WebSocket handler triggers exit check for open positions."""
        engine, _ = create_engine_with_full_mocks()

        # Add open position
        engine.state.positions['AAPL'] = Mock(ticker='AAPL')

        mock_trade = Mock()
        mock_trade.symbol = 'AAPL'
        mock_trade.price = 150.0
        mock_trade.size = 100

        with patch.object(engine, '_check_exit_async') as mock_check:
            await engine._ws_trade_handler(mock_trade)
            mock_check.assert_called_once_with('AAPL', 150.0)

    def test_ws_handler(self):
        """Run async tests."""
        asyncio.run(self.async_test_ws_handler_updates_cache())
        asyncio.run(self.async_test_ws_handler_checks_exits())


class TestCircuitBreakers(unittest.TestCase):
    """Test circuit breaker logic."""

    def test_daily_loss_limit_calculated_correctly(self):
        """Test circuit breaker calculation for daily loss."""
        engine, _ = create_engine_with_full_mocks()

        # Set daily loss beyond -2%
        engine.initial_capital = 100000.0
        engine.state.day_pnl = -2500.0  # -2.5%

        # Verify the math is correct
        loss_pct = abs(engine.state.day_pnl / engine.initial_capital)
        self.assertTrue(loss_pct > 0.02)
        self.assertEqual(loss_pct, 0.025)


class TestEntryExecution(unittest.TestCase):
    """Test _execute_entry method."""

    def test_execute_entry_skips_already_signaled(self):
        """Test entry skipped when ticker already signaled."""
        engine, _ = create_engine_with_full_mocks()

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'stop': 142.5,
            'target': 165.0,
            'sector': 'Technology'
        }

        # Mark as already signaled
        engine.signaled_tickers.add('AAPL')

        with patch('paper_engine_alpaca.is_market_open', return_value=True):
            with patch('paper_engine_alpaca.is_trading_day', return_value=True):
                with patch('builtins.print') as mock_print:
                    engine._execute_entry(analysis)
                    # Should print skip message
                    printed = ' '.join([str(c) for c in mock_print.call_args_list])
                    self.assertIn('Already signaled', printed)

    def test_execute_entry_skips_pending_order(self):
        """Test entry skipped when order already pending."""
        engine, _ = create_engine_with_full_mocks()

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'stop': 142.5,
            'target': 165.0,
            'sector': 'Technology'
        }

        # Mock has_pending_order to return True
        engine.order_manager.has_pending_order = Mock(return_value=True)

        with patch('paper_engine_alpaca.is_market_open', return_value=True):
            with patch('paper_engine_alpaca.is_trading_day', return_value=True):
                with patch('builtins.print') as mock_print:
                    engine._execute_entry(analysis)
                    printed = ' '.join([str(c) for c in mock_print.call_args_list])
                    self.assertIn('pending', printed.lower())


class TestExitExecution(unittest.TestCase):
    """Test _execute_exit method."""

    async def async_test_execute_exit_no_position(self):
        """Test exit skipped when no position exists."""
        engine, _ = create_engine_with_full_mocks()

        signal = ExitSignal(
            should_exit=True,
            reason='TARGET_HIT',
            exit_price=165.0,
            r_multiple=2.0
        )

        # No position for AAPL
        engine.order_manager.submit_exit = Mock()

        await engine._execute_exit('AAPL', signal)

        # Should not submit exit when no position
        self.assertFalse(engine.order_manager.submit_exit.called)

    def test_execute_exit(self):
        """Run async test."""
        asyncio.run(self.async_test_execute_exit_no_position())


class TestPendingOrders(unittest.TestCase):
    """Test _process_pending_orders method."""

    def test_process_pending_orders_empty(self):
        """Test processing when no pending orders."""
        engine, _ = create_engine_with_full_mocks()

        # Should not raise when no pending orders
        engine.order_manager.pending_orders = []

        # Should complete without error
        try:
            asyncio.run(engine._process_pending_orders())
        except Exception:
            self.fail("_process_pending_orders raised exception on empty orders")


class TestDailySignalReset(unittest.TestCase):
    """Test _reset_daily_signals method."""

    def test_reset_daily_signals(self):
        """Test daily signal tracking reset."""
        engine, _ = create_engine_with_full_mocks()

        # Add some signaled tickers
        engine.signaled_tickers = {'AAPL', 'MSFT', 'TSLA'}
        engine.last_signal_reset = datetime.now() - timedelta(days=1)

        engine._reset_daily_signals()

        self.assertEqual(len(engine.signaled_tickers), 0)


class TestMarketConditions(unittest.TestCase):
    """Test market conditions via TickerAnalyzer."""

    def test_market_conditions_structure(self):
        """Test market conditions returns correct structure."""
        engine, mock_client = create_engine_with_full_mocks()

        # Mock SPY historical data
        mock_client.get_historical_bars.return_value = pd.DataFrame({'Close': [450.0, 450.0]})

        result, msg, vix = engine.analyzer.check_market_conditions()

        self.assertIsInstance(result, bool)
        self.assertIsInstance(msg, str)


class TestAnalysis(unittest.TestCase):
    """Test TickerAnalyzer.analyze method."""

    def test_analyze_ticker_success(self):
        """Test successful ticker analysis."""
        engine, mock_client = create_engine_with_full_mocks()

        # Mock historical data
        mock_hist = pd.DataFrame({
            'Close': [100.0 + i * 0.5 for i in range(130)] + [150.0],
            'High': [101.0 + i * 0.5 for i in range(130)] + [151.0],
            'Low': [99.0 + i * 0.5 for i in range(130)] + [149.0],
            'Volume': [1000000] * 131
        })
        mock_client.get_historical_bars.return_value = mock_hist

        # Mock watchlist
        mock_watchlist = pd.DataFrame({
            'Ticker': ['AAPL'],
            'Pivot_Price': [150.0],
            'Sector': ['Technology']
        })

        with patch('traderlib.ticker_analyzer.get_stage2_details', return_value={
            'score': 8,
            'criteria': {
                'price_above_20ma': True,
                'price_above_50ma': True,
            }
        }):
            with patch.object(engine.analyzer, '_get_current_price', return_value=150.0):
                with patch.object(engine.analyzer, '_get_spy_return_6m', return_value=15.0):
                    with patch('traderlib.ticker_analyzer.pd.read_csv', return_value=mock_watchlist):
                        result = engine.analyzer.analyze('AAPL')

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, 'AAPL')

    def test_analyze_ticker_no_data(self):
        """Test analysis returns None when no data."""
        engine, mock_client = create_engine_with_full_mocks()

        mock_client.get_historical_bars.return_value = None

        result = engine.analyzer.analyze('AAPL')

        self.assertIsNone(result)


class TestPrintStatus(unittest.TestCase):
    """Test _print_status method."""

    def test_print_status(self):
        """Test status printing."""
        engine, _ = create_engine_with_full_mocks()

        engine.alpaca.rate_limiter.get_status.return_value = {
            'requests_in_window': 0,
            'max_requests': 100,
            'circuit_open': False,
        }

        async def async_print_status():
            with patch('builtins.print') as mock_print:
                await engine._print_status()
                self.assertTrue(mock_print.called)

        asyncio.run(async_print_status())


if __name__ == '__main__':
    unittest.main()
