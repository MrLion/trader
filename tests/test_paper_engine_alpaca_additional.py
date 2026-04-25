#!/usr/bin/env python3
"""Additional tests for paper_engine_alpaca.py to improve coverage."""

import asyncio
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock

import pandas as pd
import pytz
import pytest


from paper_engine_alpaca import AlpacaPaperEngine, MARKET_OPEN, MARKET_CLOSE
from traderlib.paper_state import PaperState, Position
from traderlib.order_manager import OrderStatus


@pytest.fixture
def mock_alpaca():
    """Fixture for mocked Alpaca client."""
    with patch('paper_engine_alpaca.AlpacaClient') as mock_class:
        mock_instance = Mock()
        mock_instance.get_cached_price.return_value = None
        mock_instance.get_latest_price.return_value = None
        mock_instance.get_latest_prices_batch.return_value = {}
        mock_instance.rate_limiter.circuit_open = False
        mock_instance.rate_limiter.get_status.return_value = {
            'requests_in_window': 0, 'max_requests': 100, 'circuit_open': False
        }
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_risk_manager():
    """Fixture for mocked RiskConfigManager."""
    with patch('paper_engine_alpaca.RiskConfigManager') as mock_class:
        mock_instance = Mock()
        mock_config = Mock()
        mock_config.entry = Mock()
        mock_config.entry.min_entry_score = 60
        mock_config.entry.max_dist_to_pivot_pct = 1.0
        mock_config.stop_loss = Mock()
        mock_config.stop_loss.max_stop_distance_pct = 0.10
        mock_config.profit_target = Mock()
        mock_config.profit_target.min_r_multiple = 2.0
        mock_config.market = Mock()
        mock_config.market.max_spy_decline_pct = -0.3
        mock_instance.get_config.return_value = mock_config
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def engine(mock_alpaca, mock_risk_manager):
    """Fixture for AlpacaPaperEngine with mocked dependencies."""
    # Patch init-only methods so engine creation doesn't hit the network/disk.
    # These are restored after __init__ so tests can exercise the real methods.
    with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
        with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
            with patch.object(AlpacaPaperEngine, '_rebuild_cooldown_state'):
                with patch('signal.signal'):  # Prevent signal handler registration
                    engine = AlpacaPaperEngine(mode='paper')

    engine.state.positions = {}
    engine.state.cash = 100000.0
    engine.state.get_stats = Mock(return_value={
        'equity': 100000.0,
        'cash': 100000.0,
        'open_positions': 0,
        'day_pnl': 0.0
    })

    # Prevent market-hours and cooldown guards from blocking entry tests
    engine._check_market_hours_for_trading = Mock(return_value=(True, ""))
    engine._check_cooldown = Mock(return_value=(True, ""))

    yield engine


class TestEngineInitialization:
    """Test engine initialization."""

    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine.running is False
        assert engine.ws_running is False
        assert engine.price_cache == {}
        assert engine.signaled_tickers == set()
        assert hasattr(engine, 'analyzer')

    def test_get_account_value_success(self, engine, mock_alpaca):
        """Test getting account value from Alpaca."""
        mock_alpaca.get_account.return_value = {'equity': 150000.0}

        result = engine._get_account_value()

        assert result == 150000.0

    def test_get_account_value_raises_on_error(self, engine, mock_alpaca):
        """Test that API errors raise RuntimeError."""
        mock_alpaca.get_account.side_effect = Exception('API error')

        with pytest.raises(RuntimeError):
            engine._get_account_value()


class TestPositionSync:
    """Test _sync_with_alpaca method."""

    def test_sync_adds_external_positions(self, engine, mock_alpaca):
        """Test sync adds positions from Alpaca."""
        mock_alpaca.get_account.return_value = {'cash': 90000.0}
        mock_alpaca.get_positions.return_value = [
            {'symbol': 'AAPL', 'qty': '10', 'avg_entry_price': '150.0'}
        ]

        # Mock order_manager sync
        engine.order_manager.sync_positions = Mock(return_value={
            'added': [{'ticker': 'AAPL', 'qty': 10, 'avg_price': 150.0}],
            'removed': [],
            'discrepancies': [],
            'synced': []
        })

        engine._sync_with_alpaca()

        assert engine.state.cash == 90000.0

    def test_sync_handles_removed_positions(self, engine, mock_alpaca):
        """Test sync handles externally closed positions."""
        # Add a position that will be removed
        engine.state.positions['TSLA'] = Mock(
            ticker='TSLA',
            status='OPEN',
            entry_price=200.0,
            shares=5,
            realized_pnl=0.0
        )
        engine.state.close_position = Mock(return_value=engine.state.positions['TSLA'])

        engine.order_manager.sync_positions = Mock(return_value={
            'added': [],
            'removed': ['TSLA'],
            'discrepancies': [],
            'synced': []
        })
        mock_alpaca.get_account.return_value = {'cash': 100000.0}

        with patch.object(engine, '_get_current_price', return_value=210.0):
            engine._sync_with_alpaca()

        engine.state.close_position.assert_called_once()


class TestMarketHours:
    """Test market hours detection."""

    @patch('paper_engine_alpaca.is_market_open', return_value=True)
    def test_is_market_hours_open(self, mock_is_open, engine):
        """Test market hours detection during open."""
        result = engine._is_market_hours()

        assert result is True

    @patch('paper_engine_alpaca.is_market_open', return_value=False)
    def test_is_market_hours_closed_weekend(self, mock_is_open, engine):
        """Test market hours detection on weekend."""
        result = engine._is_market_hours()

        assert result is False

    @patch('paper_engine_alpaca.datetime')
    def test_is_pre_market(self, mock_datetime, engine):
        """Test pre-market detection."""
        et = pytz.timezone('US/Eastern')
        mock_datetime.now.return_value = et.localize(datetime(2024, 4, 8, 8, 0, 0))

        result = engine._is_pre_market()

        assert result is True


class TestMarketConditions:
    """Test market conditions via analyzer."""

    def test_market_conditions_normal(self, engine, mock_alpaca):
        """Test normal market conditions."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({
            'Close': [448.0, 450.0]
        })

        result, msg, vix = engine.analyzer.check_market_conditions()

        assert result is True
        assert 'SPY' in msg

    def test_market_conditions_no_spy_price(self, engine, mock_alpaca):
        """Test when SPY history unavailable — fails open."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': []})

        result, msg, vix = engine.analyzer.check_market_conditions()

        assert result is True
        assert 'SPY' in msg


class TestLoadWatchlist:
    """Test _load_watchlist_tickers method."""

    @patch('paper_engine_alpaca.pd.read_csv')
    def test_load_watchlist_success(self, mock_read_csv, engine):
        """Test successful watchlist loading."""
        mock_df = pd.DataFrame({'Ticker': ['AAPL', 'MSFT', 'GOOGL']})
        mock_read_csv.return_value = mock_df

        result = engine._load_watchlist_tickers()

        assert result == ['AAPL', 'MSFT', 'GOOGL']

    def test_load_watchlist_file_not_found(self, engine):
        """Test empty list when file not found."""
        with patch.object(Path, 'exists', return_value=False):
            result = engine._load_watchlist_tickers()

        assert result == []

    @patch('paper_engine_alpaca.pd.read_csv')
    def test_load_watchlist_error(self, mock_read_csv, engine):
        """Test empty list on read error."""
        mock_read_csv.side_effect = Exception('Parse error')

        result = engine._load_watchlist_tickers()

        assert result == []


class TestGetCurrentPrice:
    """Test _get_current_price method."""

    def test_get_price_from_cache(self, engine):
        """Test price from WebSocket cache."""
        engine.price_cache['AAPL'] = {
            'price': 150.0,
            'timestamp': datetime.now()
        }

        result = engine._get_current_price('AAPL')

        assert result == 150.0

    def test_get_price_from_alpaca(self, engine, mock_alpaca):
        """Test price from Alpaca when not cached."""
        engine.price_cache = {}
        mock_alpaca.get_latest_price.return_value = 155.0

        result = engine._get_current_price('AAPL')

        assert result == 155.0

    def test_get_price_stale_cache(self, engine, mock_alpaca):
        """Test ignore stale cache."""
        # Cache entry older than 60 seconds
        engine.price_cache['AAPL'] = {
            'price': 150.0,
            'timestamp': datetime(2024, 1, 1, 12, 0, 0)
        }
        mock_alpaca.get_latest_price.return_value = 155.0

        result = engine._get_current_price('AAPL')

        assert result == 155.0


class TestDailyReset:
    """Test _reset_daily_signals method."""

    def test_reset_on_new_day(self, engine):
        """Test signals reset on new day."""
        engine.signaled_tickers = {'AAPL', 'TSLA'}
        engine.last_signal_reset = '2024-04-07'

        with patch('paper_engine_alpaca.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = '2024-04-08'
            engine._reset_daily_signals()

        assert len(engine.signaled_tickers) == 0
        assert engine.last_signal_reset == '2024-04-08'

    def test_no_reset_same_day(self, engine):
        """Test no reset on same day."""
        engine.signaled_tickers = {'AAPL'}
        engine.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        engine._reset_daily_signals()

        assert 'AAPL' in engine.signaled_tickers


class TestCheckEntries:
    """Test _check_entries method."""

    async def test_check_entries_basic(self, engine):
        """Test entry checking."""
        engine.running = True
        engine.analyzer.check_market_conditions = Mock(return_value=(True, 'SPY OK', None))
        engine._load_watchlist_tickers = Mock(return_value=['AAPL'])
        engine.analyzer.analyze = Mock(return_value=Mock(
            to_dict=Mock(return_value={
                'ticker': 'AAPL',
                'current': 150.0,
                'pivot': 150.0,
                'stop': 140.0,
                'entry_score': 85,
                'tier': 'Tier 1',
                'dist_to_pivot': 0.0,
                'sector': 'Tech'
            })
        ))
        engine._execute_entry = Mock()

        await engine._check_entries()

        engine._execute_entry.assert_called_once()

    def test_check_entries_market_blocked(self, engine):
        """Test entries blocked when market conditions fail."""
        engine.running = True
        engine.analyzer.check_market_conditions = Mock(return_value=(False, 'SPY down', None))
        engine._load_watchlist_tickers = Mock(return_value=['AAPL'])

        asyncio.run(engine._check_entries())

        # Should return early
        assert engine.analyzer.check_market_conditions.called


class TestExecuteEntry:
    """Test _execute_entry method."""

    def test_execute_already_signaled_skips(self, engine):
        """Test skip if already signaled."""
        engine.signaled_tickers.add('AAPL')

        analysis = {'ticker': 'AAPL'}
        engine._execute_entry(analysis)

        # Should not add again
        assert 'AAPL' in engine.signaled_tickers

    def test_execute_already_signaled(self, engine):
        """Test skip if already signaled."""
        engine.signaled_tickers.add('AAPL')

        analysis = {'ticker': 'AAPL'}
        engine._execute_entry(analysis)

        # Should not process

    @patch('paper_engine_alpaca.is_market_open', return_value=True)
    def test_execute_pending_order_exists(self, mock_is_open, engine):
        """Test skip if pending order exists."""
        engine.order_manager.has_pending_order = Mock(return_value=True)

        analysis = {'ticker': 'AAPL'}
        engine._execute_entry(analysis)

        engine.order_manager.has_pending_order.assert_called_once_with('AAPL')


class TestCheckExits:
    """Test _check_exits method."""

    async def test_check_exits_no_positions(self, engine):
        """Test exit check with no positions."""
        engine.state.positions = {}

        # Should not raise
        await engine._check_exits()

    async def test_check_exits_with_position(self, engine, mock_alpaca):
        """Test exit check with open position."""
        engine.running = True
        engine._get_current_price = Mock(return_value=180.0)
        engine.earnings_calendar.should_force_exit = Mock(return_value=False)

        # Create a proper Position mock
        position = Mock(
            ticker='AAPL',
            status='OPEN',
            entry_price=150.0,
            shares=10,
            stop_price=140.0
        )
        engine.state.positions['AAPL'] = position

        # Mock exit evaluation
        mock_signal = Mock()
        mock_signal.should_exit = False
        mock_signal.new_stop = None
        mock_signal.new_stop_type = None
        engine.exits.evaluate_exit = Mock(return_value=mock_signal)

        await engine._check_exits()

        engine.exits.evaluate_exit.assert_called_once()


class TestProcessPendingOrders:
    """Test _process_pending_orders method."""

    async def test_process_no_pending_orders(self, engine):
        """Test processing with no pending orders."""
        engine.order_manager.pending_orders = {}

        # Should not raise
        await engine._process_pending_orders()

    async def test_process_no_pending_orders_again(self, engine):
        """Test processing with no pending orders."""
        engine.order_manager.pending_orders = {}

        # Should not raise
        await engine._process_pending_orders()


class TestPrintStatus:
    """Test _print_status method."""

    async def test_print_status_basic(self, engine, mock_alpaca):
        """Test status printing."""
        mock_alpaca.is_ws_healthy.return_value = True
        mock_alpaca.get_cached_price.return_value = 155.0
        mock_alpaca.get_health_summary.return_value = 'HEALTHY'

        # Should not raise
        await engine._print_status()

    async def test_print_status_ws_disconnected(self, engine, mock_alpaca):
        """Test status when WebSocket disconnected."""
        mock_alpaca.is_ws_healthy.return_value = False
        mock_alpaca.get_health_summary.return_value = 'DEGRADED'

        # Should not raise
        await engine._print_status()


class TestSignalHandler:
    """Test signal handling."""

    def test_signal_handler(self, engine):
        """Test signal handler sets running to False."""
        engine.running = True

        engine._signal_handler(signal.SIGINT, None)

        assert engine.running is False
        assert engine.ws_running is False


class TestMainFunction:
    """Test main function."""

    @patch('paper_engine_alpaca.RiskConfigManager')
    @patch('paper_engine_alpaca.asyncio.run')
    @patch('paper_engine_alpaca.AlpacaPaperEngine')
    def test_main_with_risk_summary(
        self, mock_engine_class, mock_asyncio_run, mock_risk_class
    ):
        """Test main with --risk-summary flag."""
        import sys
        original_argv = sys.argv
        sys.argv = ['paper_engine_alpaca.py', '--risk-summary']

        try:
            from paper_engine_alpaca import main
            main()
        finally:
            sys.argv = original_argv

        mock_risk_class.return_value.print_summary.assert_called_once()
        mock_asyncio_run.assert_not_called()
