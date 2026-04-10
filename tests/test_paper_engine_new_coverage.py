#!/usr/bin/env python3
"""Additional coverage tests for paper_engine.py and paper_engine_alpaca.py.

Targets uncovered paths identified in the coverage report:
paper_engine.py    (~66% → higher):
  - _fetch_spy_data: insufficient 5m history, < 2 daily bars branch
  - _analyze_ticker: NaN pivot, spy=None RS path, exception handler
  - _check_entries: full scan loop (all filter branches + success)
  - _check_exits:   exit triggered, price fetch failure
  - _print_status

paper_engine_alpaca.py (~64% → higher):
  - _get_current_price: stale cache fallback
  - _check_entries: no watchlist, score rejected, dist rejected, stop rejected
  - _execute_entry: constraints logged, rejected, shares=0, can_enter fails,
                    order fails, order succeeds
  - _execute_exit:  no position guard, pending exit guard, success path
  - _check_exit_async: exit triggered
  - _process_pending_orders: buy fill with position price update
  - _print_status: unrealized PnL with open positions
"""

import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from paper_state import PaperState, Position
from paper_exits import ExitSignal


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_hist(rows=250, base=100.0):
    """Minimal price history DataFrame."""
    closes = [base + i * 0.2 for i in range(rows)]
    return pd.DataFrame({
        'Open':   [c - 0.5 for c in closes],
        'High':   [c + 1.0 for c in closes],
        'Low':    [c - 1.0 for c in closes],
        'Close':  closes,
        'Volume': [1_500_000] * rows,
    })


def make_pe_engine(initial_capital=100_000):
    """Create PaperEngine (yfinance) with minimal mocks."""
    from paper_engine import PaperEngine
    with patch.object(PaperState, '_load_state', return_value=None):
        with patch('builtins.print'):
            engine = PaperEngine(initial_capital=initial_capital)
    engine.state.positions = {}
    engine.state.cash = initial_capital
    engine.spy_data = None
    engine.spy_last_fetch = None
    return engine


def make_alpaca_engine():
    """Create AlpacaPaperEngine with all external calls mocked."""
    from paper_engine_alpaca import AlpacaPaperEngine

    with patch('paper_engine_alpaca.AlpacaClient') as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.get_account.return_value = {'equity': 100_000.0, 'cash': 100_000.0}
        mock_client.get_positions.return_value = []
        mock_client.list_orders.return_value = []
        mock_client.is_ws_healthy.return_value = True
        mock_client.get_health_summary.return_value = 'HEALTHY'

        with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100_000.0):
            with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                with patch.object(PaperState, '_load_state', return_value=None):
                    engine = AlpacaPaperEngine(mode='paper')
                    engine.alpaca = mock_client
                    engine.state.positions = {}
                    engine.state.cash = 100_000.0
                    engine.state.get_stats = Mock(return_value={
                        'equity': 100_000.0, 'cash': 100_000.0,
                        'open_positions': 0, 'day_pnl': 0.0
                    })
                    return engine, mock_client


# ---------------------------------------------------------------------------
# Fix: failing sector-limit test uses max_sector_positions from YAML (now 10)
# ---------------------------------------------------------------------------

class TestSectorLimitWithConfig(unittest.TestCase):
    """Verify sector limit enforcement respects the live risk config value."""

    def test_sector_limit_blocks_entry_when_at_max(self):
        """Entry blocked once sector count reaches max_sector_positions."""
        engine, _ = make_alpaca_engine()

        # Use a low sector limit so we hit it before the daily entry limit
        engine.risk_config.account.max_sector_positions = 3
        engine.risk_config.account.max_entries_per_day = 20

        for i in range(3):
            engine.state.enter_position(
                ticker=f'FILL{i}',
                entry_price=100.0,
                shares=10,
                stop_price=90.0,
                target_price=120.0,
                sector='Technology',
            )

        can_enter, reason = engine.state.can_enter_position(
            'Technology', 1000.0, engine.risk_config
        )
        self.assertFalse(can_enter)
        self.assertIn('Sector limit', reason)

    def test_sector_limit_allows_entry_below_max(self):
        """Entry allowed when sector count is below max."""
        engine, _ = make_alpaca_engine()

        engine.risk_config.account.max_sector_positions = 5
        engine.risk_config.account.max_entries_per_day = 20

        for i in range(4):  # 4 < 5
            engine.state.enter_position(
                ticker=f'FILL{i}',
                entry_price=100.0,
                shares=10,
                stop_price=90.0,
                target_price=120.0,
                sector='Technology',
            )

        can_enter, _ = engine.state.can_enter_position(
            'Technology', 1000.0, engine.risk_config
        )
        self.assertTrue(can_enter)


# ---------------------------------------------------------------------------
# Group 1 — paper_engine.py: _fetch_spy_data uncovered branches
# ---------------------------------------------------------------------------

class TestPaperEngineFetchSPYBranches(unittest.TestCase):

    def setUp(self):
        self.engine = make_pe_engine()

    @patch('paper_engine.yf.Ticker')
    def test_insufficient_5m_history_returns_none(self, mock_ticker_class):
        """< 2 bars in 5m history → returns None, no cache stored."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({'Close': [460.0]})  # 1 row
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._fetch_spy_data()
        self.assertIsNone(result)
        self.assertIsNone(self.engine.spy_data)

    @patch('paper_engine.yf.Ticker')
    def test_daily_hist_less_than_2_rows_uses_current_as_prev(self, mock_ticker_class):
        """When daily_hist has < 2 rows, prev_close = current → change_pct = 0."""
        mock_ticker = MagicMock()
        hist_5m  = pd.DataFrame({'Close': [455.0, 460.0]})
        hist_2d  = pd.DataFrame({'Close': [460.0]})  # only 1 row — branch NOT taken
        mock_ticker.history.side_effect = [hist_5m, hist_2d]
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._fetch_spy_data()

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['change_pct'], 0.0)  # current == prev_close

    @patch('paper_engine.yf.Ticker')
    def test_daily_hist_2_rows_updates_prev_close(self, mock_ticker_class):
        """When daily_hist has >= 2 rows, prev_close = iloc[-2]."""
        mock_ticker = MagicMock()
        hist_5m  = pd.DataFrame({'Close': [450.0, 459.0]})
        hist_2d  = pd.DataFrame({'Close': [450.0, 459.0]})  # prev = 450 → change +2%
        mock_ticker.history.side_effect = [hist_5m, hist_2d]
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._fetch_spy_data()
        self.assertIsNotNone(result)
        expected_pct = ((459.0 / 450.0) - 1) * 100
        self.assertAlmostEqual(result['change_pct'], expected_pct, places=4)


# ---------------------------------------------------------------------------
# Group 2 — paper_engine.py: _analyze_ticker uncovered branches
# ---------------------------------------------------------------------------

class TestPaperEngineAnalyzeTickerBranches(unittest.TestCase):

    def setUp(self):
        self.engine = make_pe_engine()

    @patch('paper_engine.yf.Ticker')
    def test_nan_pivot_uses_recent_high(self, mock_ticker_class):
        """NaN Pivot_Price → pivot calculated from hist['High'].tail(5).max()."""
        hist = make_hist(250)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {'sector': 'Technology'}
        mock_ticker_class.return_value = mock_ticker

        self.engine.spy_data = None
        with patch.object(self.engine, '_fetch_spy_data', return_value=None):
            result = self.engine._analyze_ticker({
                'Ticker': 'AAPL',
                'Pivot_Price': float('nan'),  # NaN pivot
                'Sector': 'Technology',
            })

        # Should succeed and use high-based pivot
        self.assertIsNotNone(result)
        expected_pivot = hist['High'].tail(5).max()
        self.assertAlmostEqual(result['pivot'], expected_pivot, places=2)

    @patch('paper_engine.yf.Ticker')
    def test_spy_none_sets_rs_to_zero(self, mock_ticker_class):
        """When _fetch_spy_data returns None, rs_6m = 0 and analysis still completes."""
        hist = make_hist(250)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker.info = {'sector': 'Technology'}
        mock_ticker_class.return_value = mock_ticker

        with patch.object(self.engine, '_fetch_spy_data', return_value=None):
            result = self.engine._analyze_ticker({
                'Ticker': 'AAPL',
                'Pivot_Price': 120.0,
                'Sector': 'Technology',
            })

        self.assertIsNotNone(result)
        # entry_score should be computed (rs_6m = 0 used as fallback)
        self.assertIn('entry_score', result)

    @patch('paper_engine.yf.Ticker')
    def test_exception_in_analyze_returns_none(self, mock_ticker_class):
        """yfinance exception in _analyze_ticker → returns None gracefully."""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = RuntimeError('network failure')
        mock_ticker_class.return_value = mock_ticker

        result = self.engine._analyze_ticker({'Ticker': 'AAPL', 'Pivot_Price': 120.0})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Group 3 — paper_engine.py: _check_entries filter branches
# ---------------------------------------------------------------------------

class TestPaperEngineCheckEntriesBranches(unittest.TestCase):

    def setUp(self):
        self.engine = make_pe_engine()

    def _make_analysis(self, **overrides):
        base = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'dist_to_pivot': 0.0,
            'stop': 140.0,
            'target': 170.0,
            'stage2': 6,
            'volume_ratio': 2.0,
            'entry_score': 80,
            'atr': 3.0,
            'sector': 'Technology',
        }
        base.update(overrides)
        return base

    def test_market_blocked_aborts_scan(self):
        """Market condition failure → no analysis."""
        with patch.object(self.engine, '_check_market_conditions', return_value=(False, 'SPY down')):
            with patch.object(self.engine, '_analyze_ticker') as mock_analyze:
                self.engine._check_entries()
        mock_analyze.assert_not_called()

    def test_empty_watchlist_aborts_scan(self):
        """Empty watchlist → no analysis."""
        with patch.object(self.engine, '_check_market_conditions', return_value=(True, 'SPY OK')):
            with patch.object(self.engine, '_load_watchlist', return_value=[]):
                with patch.object(self.engine, '_analyze_ticker') as mock_analyze:
                    self.engine._check_entries()
        mock_analyze.assert_not_called()

    def test_low_score_skipped(self):
        """Entry score below threshold → _execute_entry not called."""
        analysis = self._make_analysis(entry_score=30)  # below 60

        with patch.object(self.engine, '_check_market_conditions', return_value=(True, 'OK')):
            with patch.object(self.engine, '_load_watchlist', return_value=[{'Ticker': 'AAPL'}]):
                with patch.object(self.engine, '_analyze_ticker', return_value=analysis):
                    with patch.object(self.engine, '_execute_entry') as mock_exec:
                        self.engine._check_entries()

        mock_exec.assert_not_called()

    def test_too_far_from_pivot_skipped(self):
        """Distance > MAX_DIST_TO_PIVOT → skipped."""
        analysis = self._make_analysis(dist_to_pivot=5.0, entry_score=80)

        with patch.object(self.engine, '_check_market_conditions', return_value=(True, 'OK')):
            with patch.object(self.engine, '_load_watchlist', return_value=[{'Ticker': 'AAPL'}]):
                with patch.object(self.engine, '_analyze_ticker', return_value=analysis):
                    with patch.object(self.engine, '_execute_entry') as mock_exec:
                        self.engine._check_entries()

        mock_exec.assert_not_called()

    def test_low_volume_ratio_skipped(self):
        """volume_ratio < MIN_VOLUME_RATIO → skipped."""
        analysis = self._make_analysis(volume_ratio=0.5, entry_score=80, dist_to_pivot=0.0)

        with patch.object(self.engine, '_check_market_conditions', return_value=(True, 'OK')):
            with patch.object(self.engine, '_load_watchlist', return_value=[{'Ticker': 'AAPL'}]):
                with patch.object(self.engine, '_analyze_ticker', return_value=analysis):
                    with patch.object(self.engine, '_execute_entry') as mock_exec:
                        self.engine._check_entries()

        mock_exec.assert_not_called()

    def test_all_filters_pass_executes_entry(self):
        """All criteria met → _execute_entry called once."""
        analysis = self._make_analysis(entry_score=80, dist_to_pivot=0.0, volume_ratio=2.0)

        with patch.object(self.engine, '_check_market_conditions', return_value=(True, 'OK')):
            with patch.object(self.engine, '_load_watchlist', return_value=[{'Ticker': 'AAPL'}]):
                with patch.object(self.engine, '_analyze_ticker', return_value=analysis):
                    with patch.object(self.engine, '_execute_entry') as mock_exec:
                        with patch('builtins.print'):
                            self.engine._check_entries()

        mock_exec.assert_called_once_with(analysis)


# ---------------------------------------------------------------------------
# Group 4 — paper_engine.py: _check_exits
# ---------------------------------------------------------------------------

class TestPaperEngineCheckExits(unittest.TestCase):

    def setUp(self):
        self.engine = make_pe_engine()

    def _add_position(self, ticker='AAPL'):
        pos = Position(
            ticker=ticker,
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
        )
        self.engine.state.positions[ticker] = pos
        return pos

    @patch('paper_engine.yf.Ticker')
    def test_exit_triggered_calls_execute_exit(self, mock_ticker_class):
        """When exit signal fires, _execute_exit is called."""
        pos = self._add_position()
        hist = pd.DataFrame({'Close': [138.0]})  # below stop
        mock_ticker_class.return_value.history.return_value = hist

        with patch.object(self.engine, '_execute_exit') as mock_exit:
            with patch('builtins.print'):
                self.engine._check_exits()

        mock_exit.assert_called_once()
        signal_arg = mock_exit.call_args[0][1]
        self.assertTrue(signal_arg.should_exit)

    @patch('paper_engine.yf.Ticker')
    def test_hold_shows_position_status(self, mock_ticker_class):
        """No exit signal → position status printed, _execute_exit not called."""
        pos = self._add_position()
        hist = pd.DataFrame({'Close': [155.0]})  # above stop, below target
        mock_ticker_class.return_value.history.return_value = hist

        with patch.object(self.engine, '_execute_exit') as mock_exit:
            with patch('builtins.print') as mock_print:
                self.engine._check_exits()

        mock_exit.assert_not_called()
        # At least one print with ticker info
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('AAPL', printed)

    @patch('paper_engine.yf.Ticker')
    def test_empty_history_skips_position(self, mock_ticker_class):
        """Empty price history → position skipped, no exit triggered."""
        pos = self._add_position()
        mock_ticker_class.return_value.history.return_value = pd.DataFrame({'Close': []})

        with patch.object(self.engine, '_execute_exit') as mock_exit:
            with patch('builtins.print'):
                self.engine._check_exits()

        mock_exit.assert_not_called()

    def test_no_positions_returns_immediately(self):
        """No open positions → check loop is a no-op."""
        self.engine.state.positions = {}
        with patch('builtins.print') as mock_print:
            self.engine._check_exits()
        # Only the header print (if any)
        for call in mock_print.call_args_list:
            self.assertNotIn('Error', str(call))


# ---------------------------------------------------------------------------
# Group 5 — paper_engine.py: _print_status
# ---------------------------------------------------------------------------

class TestPaperEnginePrintStatus(unittest.TestCase):

    def test_print_status_smoke(self):
        """_print_status runs without raising."""
        engine = make_pe_engine()
        with patch('paper_engine.datetime') as mock_dt:
            et = pytz.timezone('US/Eastern')
            mock_dt.now.return_value = et.localize(datetime(2024, 4, 8, 10, 30, 0))
            mock_dt.strftime = datetime.strftime
            # Should not raise
            with patch('builtins.print'):
                engine._print_status()


# ---------------------------------------------------------------------------
# Group 6 — paper_engine_alpaca.py: _get_current_price stale cache fallback
# ---------------------------------------------------------------------------

class TestAlpacaGetCurrentPrice(unittest.TestCase):

    def test_stale_cache_fallback_when_rest_fails(self):
        """Stale cache + REST failure → returns stale price (last resort)."""
        engine, mock_client = make_alpaca_engine()
        # Stale cache entry (old timestamp)
        engine.price_cache['AAPL'] = {
            'price': 149.0,
            'timestamp': datetime(2020, 1, 1, 12, 0, 0),  # Very old
        }
        mock_client.get_latest_price.return_value = None  # REST fails

        with patch('builtins.print'):
            result = engine._get_current_price('AAPL')

        self.assertEqual(result, 149.0)

    def test_no_cache_no_rest_returns_none(self):
        """No cache and REST fails → returns None."""
        engine, mock_client = make_alpaca_engine()
        engine.price_cache = {}
        mock_client.get_latest_price.return_value = None

        result = engine._get_current_price('AAPL')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Group 7 — paper_engine_alpaca.py: _check_entries filter branches
# ---------------------------------------------------------------------------

class TestAlpacaCheckEntriesBranches(unittest.TestCase):

    def _make_analysis(self, **overrides):
        base = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'dist_to_pivot': 0.0,
            'stop': 140.0,    # 6.67% stop distance — within 10% max
            'target': 170.0,
            'stage2': 6,
            'entry_score': 80,
            'sector': 'Technology',
        }
        base.update(overrides)
        return base

    def setUp(self):
        self.engine, _ = make_alpaca_engine()

    def test_no_watchlist_aborts(self):
        """Empty watchlist → no analysis performed."""
        self.engine._check_market_conditions = Mock(return_value=(True, 'SPY OK'))
        self.engine._load_watchlist_tickers = Mock(return_value=[])
        self.engine._analyze_ticker = Mock()

        with patch('builtins.print'):
            self.engine._check_entries()

        self.engine._analyze_ticker.assert_not_called()

    def test_score_filter_rejects(self):
        """Entry score below threshold → _execute_entry not called."""
        analysis = self._make_analysis(entry_score=10)
        self.engine._check_market_conditions = Mock(return_value=(True, 'OK'))
        self.engine._load_watchlist_tickers = Mock(return_value=['AAPL'])
        self.engine._analyze_ticker = Mock(return_value=analysis)
        self.engine._execute_entry = Mock()

        with patch('builtins.print'):
            self.engine._check_entries()

        self.engine._execute_entry.assert_not_called()

    def test_distance_filter_rejects(self):
        """Distance outside ±max → _execute_entry not called."""
        analysis = self._make_analysis(entry_score=80, dist_to_pivot=10.0)
        self.engine._check_market_conditions = Mock(return_value=(True, 'OK'))
        self.engine._load_watchlist_tickers = Mock(return_value=['AAPL'])
        self.engine._analyze_ticker = Mock(return_value=analysis)
        self.engine._execute_entry = Mock()

        with patch('builtins.print'):
            self.engine._check_entries()

        self.engine._execute_entry.assert_not_called()

    def test_stop_distance_filter_rejects(self):
        """Stop > max_stop_distance_pct → _execute_entry not called."""
        # 50% stop distance (stop = 75, current = 150) far exceeds 10% max
        analysis = self._make_analysis(entry_score=80, dist_to_pivot=0.0,
                                       stop=75.0, current=150.0)
        self.engine._check_market_conditions = Mock(return_value=(True, 'OK'))
        self.engine._load_watchlist_tickers = Mock(return_value=['AAPL'])
        self.engine._analyze_ticker = Mock(return_value=analysis)
        self.engine._execute_entry = Mock()

        with patch('builtins.print'):
            self.engine._check_entries()

        self.engine._execute_entry.assert_not_called()

    def test_all_filters_pass_calls_execute(self):
        """All filters pass → _execute_entry called once."""
        analysis = self._make_analysis(entry_score=80, dist_to_pivot=0.0)
        self.engine._check_market_conditions = Mock(return_value=(True, 'OK'))
        self.engine._load_watchlist_tickers = Mock(return_value=['AAPL'])
        self.engine._analyze_ticker = Mock(return_value=analysis)
        self.engine._execute_entry = Mock()

        with patch('builtins.print'):
            self.engine._check_entries()

        self.engine._execute_entry.assert_called_once_with(analysis)


# ---------------------------------------------------------------------------
# Group 8 — paper_engine_alpaca.py: _execute_entry paths
# ---------------------------------------------------------------------------

class TestAlpacaExecuteEntry(unittest.TestCase):

    def _make_analysis(self, ticker='AAPL'):
        return {
            'ticker': ticker,
            'current': 150.0,
            'stop': 140.0,
            'target': 170.0,
            'sector': 'Technology',
            'dist_to_pivot': 0.0,
            'entry_score': 80,
        }

    def setUp(self):
        self.engine, self.mock_client = make_alpaca_engine()

    def test_shares_zero_aborts(self):
        """Position size of 0 → no order submitted."""
        with patch.object(self.engine.exits, 'calculate_position_size', return_value=0):
            with patch.object(self.engine.exits, 'get_last_position_calc', return_value={}):
                with patch('builtins.print'):
                    self.engine._execute_entry(self._make_analysis())

        self.mock_client.submit_market_order.assert_not_called()

    def test_can_enter_fails_aborts(self):
        """can_enter_position returns False → no order submitted."""
        with patch.object(self.engine.exits, 'calculate_position_size', return_value=100):
            with patch.object(self.engine.exits, 'get_last_position_calc',
                              return_value={'constraints_applied': [], 'rejected': False,
                                            'stop_distance_pct': 6.0, 'position_pct': 4.0,
                                            'account_risk_pct': 0.75, 'account_risk_dollars': 750}):
                with patch.object(self.engine.state, 'can_enter_position',
                                  return_value=(False, 'Sector limit reached')):
                    with patch('builtins.print'):
                        self.engine._execute_entry(self._make_analysis())

        self.mock_client.submit_market_order.assert_not_called()

    def test_order_failure_does_not_record_position(self):
        """Order submission failure → no position recorded locally."""
        with patch.object(self.engine.exits, 'calculate_position_size', return_value=100):
            with patch.object(self.engine.exits, 'get_last_position_calc',
                              return_value={'constraints_applied': [], 'rejected': False,
                                            'stop_distance_pct': 6.0, 'position_pct': 4.0,
                                            'account_risk_pct': 0.75, 'account_risk_dollars': 750}):
                with patch.object(self.engine.state, 'can_enter_position',
                                  return_value=(True, 'OK')):
                    with patch.object(self.engine.order_manager, 'submit_entry',
                                      return_value=None):  # order failed
                        with patch('builtins.print'):
                            self.engine._execute_entry(self._make_analysis())

        self.assertNotIn('AAPL', self.engine.state.positions)

    def test_order_success_records_position_and_signals(self):
        """Successful order → position recorded, ticker added to signaled set."""
        mock_order = Mock()
        mock_order.id = 'order-123'

        with patch.object(self.engine.order_manager, 'has_pending_order', return_value=False):
            with patch.object(self.engine.exits, 'calculate_position_size', return_value=50):
                with patch.object(self.engine.exits, 'get_last_position_calc',
                                  return_value={'constraints_applied': [], 'rejected': False,
                                                'stop_distance_pct': 6.0, 'position_pct': 4.0,
                                                'account_risk_pct': 0.75, 'account_risk_dollars': 750}):
                    with patch.object(self.engine.state, 'can_enter_position',
                                      return_value=(True, 'OK')):
                        with patch.object(self.engine.order_manager, 'submit_entry',
                                          return_value=mock_order):
                            with patch('builtins.print'):
                                self.engine._execute_entry(self._make_analysis())

        self.assertIn('AAPL', self.engine.state.positions)
        self.assertIn('AAPL', self.engine.signaled_tickers)

    def test_rejected_by_constraints_aborts(self):
        """calc_meta['rejected'] = True → no order submitted."""
        with patch.object(self.engine.exits, 'calculate_position_size', return_value=100):
            with patch.object(self.engine.exits, 'get_last_position_calc',
                              return_value={'rejected': True,
                                            'rejection_reason': 'stop too wide',
                                            'constraints_applied': [],
                                            'stop_distance_pct': 15.0}):
                with patch('builtins.print'):
                    self.engine._execute_entry(self._make_analysis())

        self.mock_client.submit_market_order.assert_not_called()


# ---------------------------------------------------------------------------
# Group 9 — paper_engine_alpaca.py: _execute_exit (async)
# ---------------------------------------------------------------------------

class TestAlpacaExecuteExit(unittest.TestCase):

    def setUp(self):
        self.engine, _ = make_alpaca_engine()

    def _make_signal(self, reason='STOP_HIT'):
        return ExitSignal(
            should_exit=True,
            reason=reason,
            exit_price=138.0,
            r_multiple=-1.0,
        )

    def _add_position(self, ticker='AAPL'):
        pos = Position(
            ticker=ticker,
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
        )
        self.engine.state.positions[ticker] = pos
        return pos

    def test_no_position_returns_early(self):
        """_execute_exit skips when ticker not in positions."""
        self.engine.order_manager.submit_exit = Mock()

        asyncio.run(self.engine._execute_exit('AAPL', self._make_signal()))

        self.engine.order_manager.submit_exit.assert_not_called()

    def test_pending_exit_order_prevents_duplicate(self):
        """Existing pending sell order → no new order submitted."""
        self._add_position()

        # Mock pending orders with a sell side
        mock_sell_order = Mock()
        mock_sell_order.side = 'sell'
        self.engine.order_manager.get_pending_for_ticker = Mock(return_value=[mock_sell_order])
        self.engine.order_manager.submit_exit = Mock()

        asyncio.run(self.engine._execute_exit('AAPL', self._make_signal()))

        self.engine.order_manager.submit_exit.assert_not_called()

    def test_successful_exit_closes_position(self):
        """Order submitted → position closed, P&L printed."""
        pos = self._add_position()
        mock_order = Mock()
        mock_order.id = 'exit-order-1'

        self.engine.order_manager.get_pending_for_ticker = Mock(return_value=[])
        self.engine.order_manager.submit_exit = Mock(return_value=mock_order)

        with patch('builtins.print'):
            asyncio.run(self.engine._execute_exit('AAPL', self._make_signal()))

        # Position should be closed (removed from positions)
        self.assertNotIn('AAPL', self.engine.state.positions)


# ---------------------------------------------------------------------------
# Group 10 — paper_engine_alpaca.py: _check_exit_async
# ---------------------------------------------------------------------------

class TestAlpacaCheckExitAsync(unittest.TestCase):

    def setUp(self):
        self.engine, _ = make_alpaca_engine()

    def _add_position(self, ticker='AAPL'):
        pos = Position(
            ticker=ticker,
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
        )
        self.engine.state.positions[ticker] = pos
        return pos

    def test_exit_async_no_position_returns(self):
        """_check_exit_async with no position is a no-op."""
        with patch.object(self.engine.exits, 'evaluate_exit') as mock_eval:
            asyncio.run(self.engine._check_exit_async('AAPL', 138.0))
        mock_eval.assert_not_called()

    def test_exit_async_triggers_execute_exit(self):
        """_check_exit_async calls _execute_exit when should_exit is True."""
        self._add_position()

        mock_signal = ExitSignal(should_exit=True, reason='STOP_HIT',
                                 exit_price=138.0, r_multiple=-1.0)
        self.engine.exits.evaluate_exit = Mock(return_value=mock_signal)

        executed = []

        async def fake_execute_exit(ticker, signal):
            executed.append((ticker, signal))

        self.engine._execute_exit = fake_execute_exit

        asyncio.run(self.engine._check_exit_async('AAPL', 138.0))

        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0][0], 'AAPL')

    def test_exit_async_hold_does_not_call_execute(self):
        """_check_exit_async with HOLD signal does not call _execute_exit."""
        self._add_position()

        mock_signal = ExitSignal(should_exit=False, reason='HOLD',
                                 exit_price=155.0, r_multiple=0.5)
        self.engine.exits.evaluate_exit = Mock(return_value=mock_signal)
        self.engine._execute_exit = AsyncMock()

        asyncio.run(self.engine._check_exit_async('AAPL', 155.0))

        self.engine._execute_exit.assert_not_called()


# ---------------------------------------------------------------------------
# Group 11 — paper_engine_alpaca.py: _process_pending_orders buy fill path
# ---------------------------------------------------------------------------

class TestAlpacaProcessPendingOrders(unittest.TestCase):

    def setUp(self):
        self.engine, _ = make_alpaca_engine()

    def test_buy_fill_updates_position_entry_price(self):
        """Filled buy order → position entry price updated to actual fill."""
        from order_manager import Order, OrderStatus

        # Add position at estimated entry price
        pos = Position(
            ticker='AAPL',
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,   # estimated
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
        )
        self.engine.state.positions['AAPL'] = pos

        filled_order = Order(
            id='buy-order-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2026-04-10T10:00:00',
            filled_price=151.50,   # actual fill slightly higher
            filled_qty=100,
        )

        self.engine.order_manager.process_all_pending = Mock(return_value=[filled_order])
        self.engine.order_manager.get_pending_count = Mock(return_value=1)

        with patch.object(self.engine.state, 'save_state'):
            with patch('builtins.print'):
                self.engine._process_pending_orders()

        # Entry price should be updated to the actual fill
        self.assertAlmostEqual(self.engine.state.positions['AAPL'].entry_price, 151.50)

    def test_sell_fill_logged(self):
        """Filled sell order → print confirmation, no crash."""
        from order_manager import Order, OrderStatus

        filled_order = Order(
            id='sell-order-1',
            ticker='AAPL',
            side='sell',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2026-04-10T10:30:00',
            filled_price=155.0,
            filled_qty=100,
            reason='STOP_HIT',
        )

        self.engine.order_manager.process_all_pending = Mock(return_value=[filled_order])
        self.engine.order_manager.get_pending_count = Mock(return_value=1)

        with patch('builtins.print') as mock_print:
            self.engine._process_pending_orders()

        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('AAPL', printed)


# ---------------------------------------------------------------------------
# Group 12 — paper_engine_alpaca.py: _print_status with open positions
# ---------------------------------------------------------------------------

class TestAlpacaPrintStatusWithPositions(unittest.TestCase):

    def setUp(self):
        self.engine, self.mock_client = make_alpaca_engine()

    def test_print_status_calculates_unrealized_pnl(self):
        """Open positions with cached price → unrealized PnL computed."""
        pos = Position(
            ticker='AAPL',
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology',
        )
        self.engine.state.positions['AAPL'] = pos
        # Seed the WebSocket price cache
        self.engine.price_cache['AAPL'] = {
            'price': 160.0,
            'timestamp': datetime.now(),
        }
        self.mock_client.is_ws_healthy.return_value = True
        self.mock_client.get_health_summary.return_value = 'HEALTHY'

        with patch('builtins.print') as mock_print:
            self.engine._print_status()

        # Unrealized PnL = (160 - 150) * 100 = 1000 — formatted as $1,000.00
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('1,000', printed)

    def test_print_status_falls_back_to_alpaca_price(self):
        """Open positions without cache → tries alpaca.get_cached_price."""
        pos = Position(
            ticker='MSFT',
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=300.0,
            shares=10,
            stop_price=280.0,
            target_price=340.0,
            initial_risk=200.0,
            sector='Technology',
        )
        self.engine.state.positions['MSFT'] = pos
        self.engine.price_cache = {}  # no WebSocket cache

        self.mock_client.get_cached_price.return_value = 310.0
        self.mock_client.is_ws_healthy.return_value = False
        self.mock_client.get_health_summary.return_value = 'DEGRADED'
        self.mock_client.get_latest_price.return_value = None

        with patch('builtins.print'):
            # Should not raise
            self.engine._print_status()


if __name__ == '__main__':
    unittest.main()
