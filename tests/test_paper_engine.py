#!/usr/bin/env python3
"""Comprehensive tests for paper_engine.py.

Tests cover:
- Market hours edge cases
- SPY data fetching and caching
- Market conditions
- Watchlist loading
- Ticker analysis
- Entry/exit execution
- Signal handling
- Daily signal reset
"""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts' / 'lib'))

from traderlib.paper_state import PaperState, Position
from traderlib.paper_exits import ExitEngine, ExitSignal
from paper_engine import PaperEngine


class MockTicker:
    """Mock yfinance Ticker for testing."""
    def __init__(self, hist_data=None, info=None):
        self._hist = hist_data or pd.DataFrame()
        self._info = info or {}

    def history(self, period=None, interval=None):
        return self._hist

    @property
    def info(self):
        return self._info


def create_sample_hist(days=200, trend='up'):
    """Create sample price history DataFrame."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

    if trend == 'up':
        prices = 100 + (pd.Series(range(days)) * 0.5) + (pd.Series(range(days)).apply(lambda x: x % 5 - 2) * 2)
    elif trend == 'down':
        prices = 150 - (pd.Series(range(days)) * 0.3) + (pd.Series(range(days)).apply(lambda x: x % 5 - 2) * 2)
    else:
        prices = pd.Series([100 + (x % 10 - 5) * 2 for x in range(days)])

    volumes = pd.Series([1000000 + (x % 7) * 100000 for x in range(days)])

    return pd.DataFrame({
        'Open': prices - 1,
        'High': prices + 2,
        'Low': prices - 2,
        'Close': prices,
        'Volume': volumes
    }, index=dates)


def create_engine_with_mocks(initial_capital=100000):
    """Helper to create engine with mocked dependencies."""
    from paper_state import PaperState

    with patch.object(PaperState, '_load_state', return_value=None):
        with patch('builtins.print'):  # Suppress output
            engine = PaperEngine(initial_capital=initial_capital)
            # Ensure clean state
            engine.state.positions = {}
            engine.state.cash = initial_capital
            engine.state.day_pnl = 0.0
            engine.spy_data = None
            engine.spy_last_fetch = None
            return engine


class TestPaperEngineInitialization(unittest.TestCase):
    """Test PaperEngine initialization."""

    def test_default_initialization(self):
        """Test engine initializes with default capital."""
        with patch.object(PaperState, '_load_state', return_value=None):
            with patch('builtins.print'):
                with patch.object(PaperEngine, '_signal_handler'):
                    engine = PaperEngine()

        self.assertEqual(engine.state.initial_capital, 100000.0)
        self.assertEqual(engine.state.cash, 100000.0)
        self.assertEqual(engine.state.positions, {})
        self.assertIsInstance(engine.exits, ExitEngine)
        self.assertFalse(engine.running)
        self.assertEqual(engine.signaled_tickers, set())

    def test_custom_initial_capital(self):
        """Test engine initializes with custom capital."""
        with patch.object(PaperState, '_load_state', return_value=None):
            with patch('builtins.print'):
                engine = PaperEngine(initial_capital=50000)

        self.assertEqual(engine.state.initial_capital, 50000.0)
        self.assertEqual(engine.state.cash, 50000.0)


class TestPaperEngineMarketHours(unittest.TestCase):
    """Test market hours checking."""

    def setUp(self):
        self.et = pytz.timezone('US/Eastern')
        self.engine = create_engine_with_mocks()

    def test_is_market_hours_weekend(self):
        """Test weekend returns False."""
        # Saturday
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 6, 10, 30, 0))
            mock_datetime.now.return_value = now
            self.assertFalse(self.engine._is_market_hours())

        # Sunday
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 7, 10, 30, 0))
            mock_datetime.now.return_value = now
            self.assertFalse(self.engine._is_market_hours())

    def test_is_market_hours_exactly_at_open(self):
        """Test 9:30 AM returns True."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 9, 30, 0))
            mock_datetime.now.return_value = now
            self.assertTrue(self.engine._is_market_hours())

    def test_is_market_hours_just_before_close(self):
        """Test 3:59 PM returns True."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 15, 59, 0))
            mock_datetime.now.return_value = now
            self.assertTrue(self.engine._is_market_hours())

    def test_is_market_hours_exactly_at_close(self):
        """Test 4:00 PM returns False."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 16, 0, 0))
            mock_datetime.now.return_value = now
            self.assertFalse(self.engine._is_market_hours())

    def test_is_market_hours_before_open(self):
        """Test before 9:30 AM returns False."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 9, 0, 0))
            mock_datetime.now.return_value = now
            self.assertFalse(self.engine._is_market_hours())

    def test_is_market_hours_after_close(self):
        """Test after 4:00 PM returns False."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 18, 0, 0))
            mock_datetime.now.return_value = now
            self.assertFalse(self.engine._is_market_hours())


class TestPaperEngineMarketStatus(unittest.TestCase):
    """Test market status formatting."""

    def setUp(self):
        self.et = pytz.timezone('US/Eastern')
        self.engine = create_engine_with_mocks()

    def test_market_status_weekend(self):
        """Test weekend status message."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 6, 10, 0, 0))
            mock_datetime.now.return_value = now
            status = self.engine._get_market_status()
            self.assertIn("CLOSED", status)
            self.assertIn("Weekend", status)

    def test_market_status_pre_market(self):
        """Test pre-market status message."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 8, 0, 0))
            mock_datetime.now.return_value = now
            status = self.engine._get_market_status()
            self.assertIn("PRE-MARKET", status)

    def test_market_status_open(self):
        """Test open market status message."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 10, 30, 0))
            mock_datetime.now.return_value = now
            status = self.engine._get_market_status()
            self.assertIn("OPEN", status)
            self.assertIn("10:30", status)

    def test_market_status_closed(self):
        """Test closed market status message."""
        with patch('paper_engine.datetime') as mock_datetime:
            now = self.et.localize(datetime(2024, 4, 8, 18, 0, 0))
            mock_datetime.now.return_value = now
            status = self.engine._get_market_status()
            self.assertEqual(status, "CLOSED")


class TestPaperEngineSPYData(unittest.TestCase):
    """Test SPY data fetching and caching."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    @patch('paper_engine.yf.Ticker')
    def test_fetch_spy_data_success(self, mock_ticker_class):
        """Test successful SPY data fetch."""
        # Create mock history
        hist_data = pd.DataFrame({
            'Close': [450, 452, 455, 458, 460]
        })
        daily_hist = pd.DataFrame({
            'Close': [455, 460]
        })

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [
            hist_data,  # First call (5m)
            daily_hist   # Second call (daily)
        ]
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._fetch_spy_data()

        self.assertIsNotNone(result)
        self.assertIn('price', result)
        self.assertIn('change_pct', result)
        self.assertIn('timestamp', result)
        self.assertEqual(result['price'], 460)
        self.assertEqual(self.engine.spy_data, result)

    @patch('paper_engine.yf.Ticker')
    def test_fetch_spy_data_caching(self, mock_ticker_class):
        """Test SPY data is cached."""
        hist_data = pd.DataFrame({'Close': [450, 452, 455]})
        daily_hist = pd.DataFrame({'Close': [455, 460]})

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [
            hist_data, daily_hist,
            hist_data, daily_hist  # Second fetch should use cache
        ]
        mock_ticker_class.return_value = mock_ticker

        # First fetch
        result1 = self.engine._fetch_spy_data()

        # Second fetch (should use cache)
        result2 = self.engine._fetch_spy_data()

        # Ticker should only be called once
        self.assertEqual(mock_ticker_class.call_count, 1)
        self.assertEqual(result1, result2)

    @patch('paper_engine.yf.Ticker')
    def test_fetch_spy_data_error_returns_cached(self, mock_ticker_class):
        """Test error returns cached data if available."""
        # Set cached data
        self.engine.spy_data = {'price': 460, 'change_pct': 1.0}

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API Error")
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._fetch_spy_data()

        self.assertIsNotNone(result)
        self.assertEqual(result['price'], 460)


class TestPaperEngineMarketConditions(unittest.TestCase):
    """Test market conditions check."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    def test_market_conditions_pass(self):
        """Test market conditions pass when SPY up."""
        with patch.object(self.engine, '_fetch_spy_data', return_value={
            'price': 460,
            'change_pct': 0.5,
            'timestamp': datetime.now()
        }):
            ok, msg = self.engine._check_market_conditions()
            self.assertTrue(ok)
            self.assertIn("SPY", msg)

    def test_market_conditions_fail_decline(self):
        """Test market conditions fail when SPY down too much."""
        with patch.object(self.engine, '_fetch_spy_data', return_value={
            'price': 450,
            'change_pct': -0.5,  # Below -0.3% threshold
            'timestamp': datetime.now()
        }):
            ok, msg = self.engine._check_market_conditions()
            self.assertFalse(ok)
            self.assertIn("down", msg.lower())

    def test_market_conditions_no_data(self):
        """Test market conditions fail when no SPY data."""
        with patch.object(self.engine, '_fetch_spy_data', return_value=None):
            ok, msg = self.engine._check_market_conditions()
            self.assertFalse(ok)
            self.assertIn("Cannot fetch", msg)


class TestPaperEngineWatchlist(unittest.TestCase):
    """Test watchlist loading."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    @patch('paper_engine.pd.read_csv')
    @patch('paper_engine.WATCHLIST_PATH')
    def test_load_watchlist_success(self, mock_path, mock_read_csv):
        """Test successful watchlist load."""
        mock_path.exists.return_value = True
        mock_read_csv.return_value = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT', 'TSLA'],
            'Pivot_Price': [150.0, 300.0, 200.0],
            'Sector': ['Tech', 'Tech', 'Auto']
        })

        result = self.engine._load_watchlist()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['Ticker'], 'AAPL')

    @patch('paper_engine.WATCHLIST_PATH')
    def test_load_watchlist_no_file(self, mock_path):
        """Test watchlist returns empty when file missing."""
        mock_path.exists.return_value = False

        result = self.engine._load_watchlist()

        self.assertEqual(result, [])

    @patch('paper_engine.pd.read_csv')
    @patch('paper_engine.WATCHLIST_PATH')
    def test_load_watchlist_error(self, mock_path, mock_read_csv):
        """Test watchlist returns empty on error."""
        mock_path.exists.return_value = True
        mock_read_csv.side_effect = Exception("Read error")

        result = self.engine._load_watchlist()

        self.assertEqual(result, [])


class TestPaperEngineAnalyzeTicker(unittest.TestCase):
    """Test ticker analysis."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    def test_analyze_ticker_in_position(self):
        """Test skips if already in position."""
        self.engine.state.positions['AAPL'] = Mock()

        result = self.engine._analyze_ticker({'Ticker': 'AAPL'})

        self.assertIsNone(result)

    def test_analyze_ticker_already_signaled(self):
        """Test skips if already signaled today."""
        self.engine.signaled_tickers.add('AAPL')

        result = self.engine._analyze_ticker({'Ticker': 'AAPL'})

        self.assertIsNone(result)

    def test_analyze_ticker_no_ticker(self):
        """Test returns None if no ticker."""
        result = self.engine._analyze_ticker({})

        self.assertIsNone(result)

    @patch('paper_engine.yf.Ticker')
    def test_analyze_ticker_success(self, mock_ticker_class):
        """Test successful ticker analysis."""
        hist = create_sample_hist(250, 'up')

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {'sector': 'Technology'}
        mock_ticker_class.return_value = mock_ticker

        # Mock SPY data
        self.engine.spy_data = {'price': 460, 'change_pct': 0.5}

        with patch.object(self.engine, '_fetch_spy_data', return_value={
            'price': 460,
            'change_pct': 0.5
        }):
            with patch('paper_engine.yf.Ticker') as mock_spy:
                spy_hist = create_sample_hist(250, 'up')
                spy_hist['Close'] = spy_hist['Close'] * 0.8  # SPY underperforms
                mock_spy.return_value.history.return_value = spy_hist

                result = self.engine._analyze_ticker({
                    'Ticker': 'AAPL',
                    'Pivot_Price': 150.0,
                    'Sector': 'Technology'
                })

        self.assertIsNotNone(result)
        self.assertIn('ticker', result)
        self.assertIn('entry_score', result)
        self.assertIn('stage2', result)
        self.assertEqual(result['ticker'], 'AAPL')


class TestPaperEngineDailySignals(unittest.TestCase):
    """Test daily signal reset."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    def test_reset_signals_new_day(self):
        """Test signals reset on new day."""
        self.engine.signaled_tickers = {'AAPL', 'MSFT'}
        self.engine.last_signal_reset = '2024-04-07'

        with patch('paper_engine.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 4, 8, 9, 30)
            mock_datetime.strftime = datetime.strftime

            self.engine._reset_daily_signals()

        self.assertEqual(self.engine.signaled_tickers, set())
        self.assertEqual(self.engine.last_signal_reset, '2024-04-08')

    def test_reset_signals_same_day(self):
        """Test signals don't reset on same day."""
        self.engine.signaled_tickers = {'AAPL', 'MSFT'}
        self.engine.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        self.engine._reset_daily_signals()

        self.assertEqual(self.engine.signaled_tickers, {'AAPL', 'MSFT'})


class TestPaperEngineRunOnce(unittest.TestCase):
    """Test run_once functionality."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    @patch.object(PaperEngine, '_is_market_hours', return_value=True)
    @patch.object(PaperEngine, '_check_exits')
    @patch.object(PaperEngine, '_check_entries')
    @patch.object(PaperEngine, '_print_status')
    @patch.object(PaperEngine, '_reset_daily_signals')
    def test_run_once_market_open(self, mock_reset, mock_print, mock_entries, mock_exits, mock_hours):
        """Test run_once during market hours."""
        engine = PaperEngine.__new__(PaperEngine)
        engine._reset_daily_signals = mock_reset
        engine._print_status = mock_print
        engine._check_exits = mock_exits
        engine._check_entries = mock_entries
        engine._is_market_hours = mock_hours

        engine.run_once()

        mock_reset.assert_called_once()
        mock_print.assert_called_once()
        mock_exits.assert_called_once()
        mock_entries.assert_called_once()

    @patch.object(PaperEngine, '_is_market_hours', return_value=False)
    @patch.object(PaperEngine, '_print_status')
    @patch.object(PaperEngine, '_reset_daily_signals')
    def test_run_once_market_closed(self, mock_reset, mock_print, mock_hours):
        """Test run_once when market closed."""
        engine = PaperEngine.__new__(PaperEngine)
        engine._reset_daily_signals = mock_reset
        engine._print_status = mock_print
        engine._is_market_hours = mock_hours

        with patch('builtins.print') as mock_bprint:
            engine.run_once()

        mock_reset.assert_called_once()
        mock_print.assert_called_once()
        mock_bprint.assert_called()  # Should print "market closed" message


class TestPaperEngineSignalHandling(unittest.TestCase):
    """Test signal handling."""

    def test_signal_handler_sets_running_false(self):
        """Test SIGINT handler sets running to False."""
        with patch.object(PaperState, '_load_state', return_value=None):
            with patch('builtins.print'):
                engine = PaperEngine.__new__(PaperEngine)
                engine.state = Mock()
                engine.state.initial_capital = 100000
                engine.state.cash = 100000
                engine.state.positions = {}
                engine.exits = Mock()
                engine.running = True
                engine.signaled_tickers = set()
                engine.last_signal_reset = datetime.now().strftime('%Y-%m-%d')
                engine.spy_data = None
                engine.spy_last_fetch = None

                # Call signal handler directly
                engine._signal_handler(2, None)  # SIGINT = 2

                self.assertFalse(engine.running)


class TestPaperEngineExitExecution(unittest.TestCase):
    """Test exit execution."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    def test_execute_exit_success(self):
        """Test successful exit execution."""
        position = Mock()
        position.ticker = 'AAPL'

        signal = ExitSignal(
            should_exit=True,
            reason='STOP_HIT',
            exit_price=145.0,
            r_multiple=-1.0
        )

        mock_result = Mock()
        mock_result.realized_pnl = 500.0

        mock_state = Mock()
        mock_state.close_position = Mock(return_value=mock_result)
        self.engine.state = mock_state

        with patch('builtins.print') as mock_print:
            self.engine._execute_exit(position, signal)

        mock_state.close_position.assert_called_once_with(
            ticker='AAPL',
            exit_price=145.0,
            reason='STOP_HIT'
        )

    def test_execute_exit_none_result(self):
        """Test exit when close_position returns None."""
        position = Mock()
        position.ticker = 'AAPL'

        signal = ExitSignal(
            should_exit=True,
            reason='STOP_HIT',
            exit_price=145.0,
            r_multiple=-1.0
        )

        with patch.object(self.engine.state, 'close_position', return_value=None):
            with patch('builtins.print') as mock_print:
                self.engine._execute_exit(position, signal)

        # Should not print exit message if result is None
        printed = ' '.join([str(call) for call in mock_print.call_args_list])
        self.assertNotIn('AUTO-EXIT', printed)


class TestPaperEngineEntryExecution(unittest.TestCase):
    """Test entry execution."""

    def setUp(self):
        self.engine = create_engine_with_mocks()

    @patch.object(ExitEngine, 'calculate_position_size', return_value=100)
    def test_execute_entry_success(self, mock_calc_size):
        """Test successful entry execution."""
        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'stop': 140.0,
            'target': 170.0,
            'sector': 'Technology',
            'entry_score': 85
        }

        mock_position = Mock()
        mock_state = Mock()
        mock_state.can_enter_position = Mock(return_value=(True, 'OK'))
        mock_state.enter_position = Mock(return_value=mock_position)
        mock_state.get_equity = Mock(return_value=100000)
        self.engine.state = mock_state

        with patch('builtins.print') as mock_print:
            self.engine._execute_entry(analysis)

        mock_state.enter_position.assert_called_once()
        self.assertIn('AAPL', self.engine.signaled_tickers)

    def test_execute_entry_validation_fails(self):
        """Test entry rejected when validation fails."""
        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'stop': 140.0,
            'target': 170.0,
            'sector': 'Technology',
            'entry_score': 85
        }

        with patch.object(self.engine.state, 'can_enter_position', return_value=(False, 'Sector limit')):
            with patch.object(self.engine.state, 'enter_position') as mock_enter:
                self.engine._execute_entry(analysis)

        mock_enter.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
