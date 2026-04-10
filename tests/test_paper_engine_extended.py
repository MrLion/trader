#!/usr/bin/env python3
"""Extended tests for paper_engine_alpaca.py to improve coverage.

Tests additional code paths:
- Market hours edge cases
- SPY cache refresh logic
- Entry filter logic
- Exit execution paths
- Position sizing
- Signal handling
- WebSocket lifecycle
"""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts' / 'lib'))

from paper_state import PaperState, Position
from paper_exits import ExitEngine, ExitSignal


def create_engine_with_mocks(mode='paper', mock_datetime=None):
    """Helper to create engine with all necessary mocks."""
    from paper_engine_alpaca import AlpacaPaperEngine
    from paper_state import PaperState

    with patch('paper_engine_alpaca.AlpacaClient') as mock_client:
        mock_alpaca = mock_client.return_value
        mock_alpaca.get_account.return_value = {'equity': 100000.0, 'cash': 100000.0}
        mock_alpaca.get_positions.return_value = []
        mock_alpaca.list_orders.return_value = []
        mock_alpaca.is_ws_healthy.return_value = True
        mock_alpaca.get_health_summary.return_value = 'HEALTHY'

        # Create engine with patched methods to avoid file operations
        with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
            with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                with patch.object(PaperState, '_load_state', return_value=None):
                    engine = AlpacaPaperEngine(mode=mode)
                    engine.alpaca = mock_alpaca

                    # Ensure clean state
                    engine.state.positions = {}
                    engine.state.cash = 100000.0
                    engine.state.day_pnl = 0.0

                    # Mock state.get_stats() to return actual float values
                    engine.state.get_stats = Mock(return_value={
                        'equity': 100000.0,
                        'cash': 100000.0,
                        'open_positions': 0,
                        'day_pnl': 0.0
                    })

                    return engine, mock_alpaca


class TestPaperEngineMarketHours(unittest.TestCase):
    """Test market hours checking with various edge cases."""

    def setUp(self):
        self.et = pytz.timezone('US/Eastern')

    @patch('paper_engine_alpaca.datetime')
    def test_is_market_hours_exactly_930(self, mock_datetime):
        """Test 9:30 AM is considered market open."""
        now = self.et.localize(datetime(2024, 4, 8, 9, 30, 0))
        mock_datetime.now.return_value = now

        engine, _ = create_engine_with_mocks()
        self.assertTrue(engine._is_market_hours())

    @patch('paper_engine_alpaca.datetime')
    def test_is_market_hours_just_before_close(self, mock_datetime):
        """Test 3:59:59 PM is considered market open."""
        now = self.et.localize(datetime(2024, 4, 8, 15, 59, 59))
        mock_datetime.now.return_value = now

        engine, _ = create_engine_with_mocks()
        self.assertTrue(engine._is_market_hours())

    @patch('paper_engine_alpaca.datetime')
    def test_is_market_hours_exactly_1600(self, mock_datetime):
        """Test 4:00 PM is considered market closed."""
        now = self.et.localize(datetime(2024, 4, 8, 16, 0, 0))
        mock_datetime.now.return_value = now

        engine, _ = create_engine_with_mocks()
        self.assertFalse(engine._is_market_hours())

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market_early_morning(self, mock_datetime):
        """Test 4:00 AM is considered pre-market."""
        now = self.et.localize(datetime(2024, 4, 8, 4, 0, 0))
        mock_datetime.now.return_value = now

        engine, _ = create_engine_with_mocks()
        self.assertTrue(engine._is_pre_market())

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market_before_930(self, mock_datetime):
        """Test 9:29 AM is considered pre-market."""
        now = self.et.localize(datetime(2024, 4, 8, 9, 29, 0))
        mock_datetime.now.return_value = now

        engine, _ = create_engine_with_mocks()
        self.assertTrue(engine._is_pre_market())


class TestPaperEngineSPYCache(unittest.TestCase):
    """Test SPY cache refresh logic."""

    @patch('paper_engine_alpaca.datetime')
    def test_spy_cache_already_fresh(self, mock_datetime):
        """Test that fresh cache is not refreshed unnecessarily."""
        today = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.now.return_value = today
        mock_datetime.strftime = datetime.strftime

        engine, mock_alpaca = create_engine_with_mocks()
        # Set cache to today
        engine.spy_cache = {'date': '2024-04-08', 'return_6m': 15.0, 'price': 450.0}

        # Should return True without fetching new data
        result = engine._refresh_spy_cache()
        self.assertTrue(result)
        # get_historical_bars should NOT be called again
        mock_alpaca.get_historical_bars.assert_not_called()

    @patch('paper_engine_alpaca.datetime')
    def test_spy_cache_insufficient_data(self, mock_datetime):
        """Test handling when SPY data has insufficient bars."""
        today = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.now.return_value = today
        mock_datetime.strftime = datetime.strftime

        engine, mock_alpaca = create_engine_with_mocks()
        # Return very few bars
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [450]}, index=[0])

        engine.spy_cache = {'date': None}

        result = engine._refresh_spy_cache()
        self.assertFalse(result)

    @patch('paper_engine_alpaca.datetime')
    def test_spy_cache_exception(self, mock_datetime):
        """Test handling when SPY fetch raises exception."""
        today = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.now.return_value = today
        mock_datetime.strftime = datetime.strftime

        engine, mock_alpaca = create_engine_with_mocks()
        mock_alpaca.get_historical_bars.side_effect = Exception('Network error')

        engine.spy_cache = {'date': None, 'return_6m': 0.0}

        result = engine._refresh_spy_cache()
        self.assertFalse(result)
        # Should return the fallback value
        spy_return = engine._get_spy_return_6m()
        self.assertEqual(spy_return, 0.0)


class TestPaperEngineEntryFilters(unittest.TestCase):
    """Test entry filter logic comprehensively."""

    def setUp(self):
        self.engine, _ = create_engine_with_mocks()
        self.engine.spy_cache = {
            'date': '2024-04-08',
            'return_6m': 15.0,
            'price': 450.0
        }

    def test_analyze_ticker_in_position(self):
        """Test that tickers in positions are skipped."""
        self.engine.state.positions['AAPL'] = Mock()
        result = self.engine._analyze_ticker('AAPL')
        self.assertIsNone(result)

    def test_analyze_ticker_already_signaled(self):
        """Test that already signaled tickers are skipped."""
        self.engine.signaled_tickers.add('AAPL')
        result = self.engine._analyze_ticker('AAPL')
        self.assertIsNone(result)

    def test_analyze_ticker_insufficient_data(self):
        """Test handling when historical data is insufficient."""
        self.engine.alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [100] * 5})

        result = self.engine._analyze_ticker('AAPL')
        self.assertIsNone(result)

    def test_analyze_ticker_no_price(self):
        """Test handling when current price is unavailable."""
        self.engine.alpaca.get_historical_bars.return_value = pd.DataFrame({
            'Close': [100 + i * 0.1 for i in range(60)],
            'Volume': [1000000] * 60
        })
        self.engine.alpaca.get_latest_price.return_value = None

        result = self.engine._analyze_ticker('AAPL')
        self.assertIsNone(result)


class TestPaperEngineMarketConditions(unittest.TestCase):
    """Test market conditions checking."""

    def setUp(self):
        self.engine, _ = create_engine_with_mocks()

    def test_check_market_conditions_no_spy_price(self):
        """Test when SPY price cannot be fetched."""
        self.engine.alpaca.get_latest_price.return_value = None

        result, msg = self.engine._check_market_conditions()
        self.assertFalse(result)
        self.assertIn('Cannot fetch SPY', msg)

    def test_check_market_conditions_spy_decline(self):
        """Test when SPY is down more than 0.3%."""
        self.engine.alpaca.get_latest_price.return_value = 440.0  # Down from yesterday

        # Mock yfinance via sys.modules
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_hist = pd.DataFrame({'Close': [450.0, 441.5]})  # Previous close ~450
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict('sys.modules', {'yfinance': mock_yf}):
            result, msg = self.engine._check_market_conditions()
            # SPY change: (440-450)/450 = -2.2%
            self.assertFalse(result)

    def test_check_market_conditions_yfinance_fails(self):
        """Test when yfinance fallback also fails."""
        self.engine.alpaca.get_latest_price.return_value = 450.0

        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = Exception('yfinance error')

        with patch.dict('sys.modules', {'yfinance': mock_yf}):
            result, msg = self.engine._check_market_conditions()
            # Should return True as default when can't check
            self.assertTrue(result)


class TestPaperEngineExecuteEntry(unittest.TestCase):
    """Test entry execution logic."""

    def setUp(self):
        self.engine, _ = create_engine_with_mocks()
        self.engine.spy_cache = {
            'date': '2024-04-08',
            'return_6m': 15.0,
            'price': 450.0
        }

    def test_execute_entry_already_signaled(self):
        """Test entry rejected when already signaled."""
        self.engine.signaled_tickers.add('AAPL')

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        self.engine._execute_entry(analysis)
        # Should not create position
        self.assertNotIn('AAPL', self.engine.state.positions)

    def test_execute_entry_pending_order_exists(self):
        """Test entry rejected when order already pending."""
        self.engine.order_manager.pending_orders['AAPL'] = Mock(ticker='AAPL')

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        self.engine._execute_entry(analysis)
        # Should not create position
        self.assertNotIn('AAPL', self.engine.state.positions)

    def test_execute_entry_risk_validation_fails(self):
        """Test entry blocked by risk validation (sector limit reached)."""
        # Mock can_enter_position to simulate sector limit reached
        self.engine.state.can_enter_position = Mock(return_value=(False, "Sector limit reached (3 in Technology)"))
        # Prevent cross-test OrderManager disk pollution from blocking before can_enter_position
        self.engine.order_manager.has_pending_order = Mock(return_value=False)

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        self.engine._execute_entry(analysis)
        # Should not create position due to sector limit
        self.assertNotIn('AAPL', self.engine.state.positions)
        # Verify can_enter_position was called
        self.engine.state.can_enter_position.assert_called_once()


class TestPaperEngineDailyReset(unittest.TestCase):
    """Test daily reset logic."""

    @patch('paper_engine_alpaca.datetime')
    def test_reset_daily_signals_new_day(self, mock_datetime):
        """Test signals reset on new day."""
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        engine, _ = create_engine_with_mocks()
        engine.signaled_tickers.add('AAPL')
        engine.last_signal_reset = '2024-04-07'  # Yesterday

        engine._reset_daily_signals()
        self.assertEqual(len(engine.signaled_tickers), 0)
        self.assertEqual(engine.last_signal_reset, '2024-04-08')

    @patch('paper_engine_alpaca.datetime')
    def test_reset_daily_signals_same_day(self, mock_datetime):
        """Test signals NOT reset on same day."""
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        engine, _ = create_engine_with_mocks()
        engine.signaled_tickers.add('AAPL')
        engine.last_signal_reset = '2024-04-08'  # Today

        engine._reset_daily_signals()
        self.assertEqual(len(engine.signaled_tickers), 1)  # Still there


class TestPaperEngineSignalHandler(unittest.TestCase):
    """Test signal handling for shutdown."""

    def test_signal_handler(self):
        """Test shutdown signal handler."""
        engine, _ = create_engine_with_mocks()
        engine.running = True

        # Call signal handler directly
        import signal
        engine._signal_handler(signal.SIGINT, None)

        self.assertFalse(engine.running)


class TestPaperEnginePrintStatus(unittest.TestCase):
    """Test status printing."""

    @patch('paper_engine_alpaca.datetime')
    def test_print_status_market_open(self, mock_datetime):
        """Test status printing when market is open."""
        et = pytz.timezone('US/Eastern')
        now = et.localize(datetime(2024, 4, 8, 10, 0, 0))  # Market open
        mock_datetime.now.return_value = now

        engine, mock_alpaca = create_engine_with_mocks()
        mock_alpaca.is_ws_healthy.return_value = True
        mock_alpaca.get_health_summary.return_value = 'HEALTHY'

        # Should print without error
        engine._print_status()

    @patch('paper_engine_alpaca.datetime')
    def test_print_status_ws_disconnected(self, mock_datetime):
        """Test status printing when WebSocket is disconnected."""
        et = pytz.timezone('US/Eastern')
        now = et.localize(datetime(2024, 4, 8, 10, 0, 0))  # Market open
        mock_datetime.now.return_value = now

        engine, mock_alpaca = create_engine_with_mocks()
        mock_alpaca.is_ws_healthy.return_value = False
        mock_alpaca.get_health_summary.return_value = 'DEGRADED'
        engine.price_cache = {}  # Empty cache

        # Should print without error
        engine._print_status()


class TestPaperEngineProcessPendingOrders(unittest.TestCase):
    """Test processing pending orders."""

    def test_no_pending_orders(self):
        """Test when no orders are pending."""
        engine, _ = create_engine_with_mocks()

        # Should complete without error
        engine._process_pending_orders()

    def test_pending_orders_processed(self):
        """Test processing filled orders."""
        from order_manager import Order, OrderStatus

        engine, _ = create_engine_with_mocks()

        # Add a filled order
        order = Order(
            id='test-order',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2024-04-08T10:00:00',
            filled_price=150.0,
            filled_qty=100
        )
        engine.order_manager.pending_orders['test-order'] = order

        # Should process without error
        engine._process_pending_orders()


class TestPaperEngineLoadWatchlist(unittest.TestCase):
    """Test watchlist loading."""

    def test_load_watchlist_success(self):
        """Test loading watchlist successfully."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist_path = Path(tmpdir) / 'watchlist.csv'
            watchlist_path.write_text('Ticker,Pivot_Price,Sector\nAAPL,150.0,Technology\n')

            with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path), \
                 patch('paper_engine_alpaca.DATA_DIR', Path(tmpdir)):
                engine, _ = create_engine_with_mocks()
                tickers = engine._load_watchlist_tickers()
                self.assertEqual(tickers, ['AAPL'])

    def test_load_watchlist_file_not_found(self):
        """Test when watchlist file doesn't exist."""
        with patch('paper_engine_alpaca.WATCHLIST_PATH', Path('/nonexistent/watchlist.csv')), \
             patch('paper_engine_alpaca.DATA_DIR', Path('/nonexistent')):
            engine, _ = create_engine_with_mocks()
            tickers = engine._load_watchlist_tickers()
            self.assertEqual(tickers, [])

    def test_load_watchlist_read_error(self):
        """Test handling watchlist read error."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            watchlist_path = Path(tmpdir) / 'watchlist.csv'
            watchlist_path.write_text('invalid csv data {[')  # Invalid CSV

            with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path), \
                 patch('paper_engine_alpaca.DATA_DIR', Path(tmpdir)):
                engine, _ = create_engine_with_mocks()
                tickers = engine._load_watchlist_tickers()
                self.assertEqual(tickers, [])


def run_tests():
    """Run all extended paper engine tests."""
    print("=" * 70)
    print("🧪 EXTENDED PAPER ENGINE TESTS")
    print("=" * 70)
    print()
    print("Testing additional code paths for coverage:")
    print("  • Market hours edge cases")
    print("  • SPY cache refresh logic")
    print("  • Entry filter branches")
    print("  • Market condition checks")
    print("  • Entry execution paths")
    print("  • Daily reset logic")
    print("  • Signal handling")
    print("  • Status printing")
    print("  • Watchlist loading")
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineMarketHours))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineSPYCache))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineEntryFilters))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineMarketConditions))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineExecuteEntry))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineDailyReset))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineSignalHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEnginePrintStatus))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineProcessPendingOrders))
    suite.addTests(loader.loadTestsFromTestCase(TestPaperEngineLoadWatchlist))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL EXTENDED TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
