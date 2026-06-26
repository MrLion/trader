#!/usr/bin/env python3
"""Tests for paper engine fill processing and cooldown tracking.

Covers:
- Buy fill handling (position creation, missing fields, updates)
- Sell fill handling
- Cooldown tracking (exit recording, exponential backoff, reset)
- Timeout/Connection error handling in _execute_entry
"""

import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


from traderlib.paper_state import PaperState, Position
from traderlib.order_manager import Order, OrderStatus


def make_alpaca_engine():
    """Create AlpacaPaperEngine with full mocking for testing."""
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
                    with patch('signal.signal'):
                        engine = AlpacaPaperEngine(mode='paper')
                        engine.alpaca = mock_client
                        engine.state.positions = {}
                        engine.state.cash = 100_000.0
                        engine.state.get_stats = Mock(return_value={
                            'equity': 100_000.0, 'cash': 100_000.0,
                            'open_positions': 0, 'day_pnl': 0.0
                        })
                        return engine, mock_client


# ============================================================================
# Buy fill tests
# ============================================================================

class TestBuyFillProcessing(unittest.TestCase):
    """Tests for buy order fill processing in _process_pending_orders."""

    def test_buy_fill_creates_position_with_correct_entry_price(self):
        """A filled buy order should create a position with the fill price and quantity."""
        engine, _ = make_alpaca_engine()

        order = Order(
            id='test-order-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=151.50,
            filled_qty=100,
            stop_price=140.0,
            sector='Technology',
            target_price=170.0,
            expected_entry_price=150.0,
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order]

        asyncio.run(engine._process_pending_orders())

        assert 'AAPL' in engine.state.positions, "Position should be created for AAPL"
        pos = engine.state.positions['AAPL']
        assert pos.entry_price == 151.50, f"Expected entry_price=151.50, got {pos.entry_price}"
        assert pos.shares == 100, f"Expected shares=100, got {pos.shares}"
        assert pos.stop_price == 140.0, f"Expected stop_price=140.0, got {pos.stop_price}"
        assert pos.sector == 'Technology', f"Expected sector=Technology, got {pos.sector}"

    def test_buy_fill_missing_stop_price_skips_position(self):
        """A filled buy order without a stop_price should NOT create a position."""
        engine, _ = make_alpaca_engine()

        # Test with stop_price=None
        order_no_stop = Order(
            id='test-order-2',
            ticker='MSFT',
            side='buy',
            qty=50,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=300.0,
            filled_qty=50,
            stop_price=None,
            sector='Technology',
            target_price=330.0,
            expected_entry_price=299.0,
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order_no_stop]

        with patch('builtins.print') as mock_print:
            asyncio.run(engine._process_pending_orders())

        assert 'MSFT' not in engine.state.positions, "Position should NOT be created without stop_price"

        # Test with stop_price=0
        order_zero_stop = Order(
            id='test-order-3',
            ticker='GOOG',
            side='buy',
            qty=30,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=140.0,
            filled_qty=30,
            stop_price=0,
            sector='Technology',
            target_price=160.0,
            expected_entry_price=139.0,
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order_zero_stop]

        with patch('builtins.print') as mock_print:
            asyncio.run(engine._process_pending_orders())

        assert 'GOOG' not in engine.state.positions, "Position should NOT be created with stop_price=0"

    def test_buy_fill_missing_filled_qty_uses_order_qty(self):
        """When filled_qty is None or 0, the order's qty should be used as fallback."""
        engine, _ = make_alpaca_engine()

        order = Order(
            id='test-order-4',
            ticker='TSLA',
            side='buy',
            qty=50,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=200.0,
            filled_qty=None,
            stop_price=190.0,
            sector='Consumer Discretionary',
            target_price=220.0,
            expected_entry_price=199.0,
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order]

        with patch('builtins.print') as mock_print:
            asyncio.run(engine._process_pending_orders())

        assert 'TSLA' in engine.state.positions, "Position should be created with qty fallback"
        pos = engine.state.positions['TSLA']
        assert pos.shares == 50, f"Expected shares=50 (from order qty), got {pos.shares}"
        assert pos.entry_price == 200.0, f"Expected entry_price=200.0, got {pos.entry_price}"

    def test_buy_fill_already_holding_ticker_updates_entry_price(self):
        """When a fill arrives for a ticker already in positions, entry_price should be updated."""
        engine, _ = make_alpaca_engine()

        # Pre-create a position for AAPL
        existing_pos = Position(
            ticker='AAPL',
            status='OPEN',
            entry_date=datetime.now().isoformat(),
            entry_price=148.00,
            shares=100,
            stop_price=140.0,
            target_price=165.0,
            initial_risk=800.0,
            sector='Technology',
        )
        engine.state.positions['AAPL'] = existing_pos

        order = Order(
            id='test-order-5',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=155.00,
            filled_qty=100,
            stop_price=142.0,
            sector='Technology',
            target_price=170.0,
            expected_entry_price=150.0,
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order]

        with patch('builtins.print') as mock_print:
            asyncio.run(engine._process_pending_orders())

        pos = engine.state.positions['AAPL']
        assert pos.entry_price == 155.00, f"Expected updated entry_price=155.00, got {pos.entry_price}"
        # The position should still be the same object (not duplicated)
        assert pos is existing_pos, "Should update existing position, not create new one"


# ============================================================================
# Cooldown tests
# ============================================================================

class TestCooldownTracking(unittest.TestCase):
    """Tests for cooldown tracking and re-entry prevention."""

    def test_record_position_exit_loss_increments_consecutive_losses(self):
        """Recording a loss exit should increment consecutive_losses and set last_exit_time."""
        engine, _ = make_alpaca_engine()

        assert 'AAPL' not in engine.consecutive_losses, "Precondition: AAPL not in consecutive_losses"
        assert 'AAPL' not in engine.last_exit_time, "Precondition: AAPL not in last_exit_time"

        engine._record_position_exit('AAPL', -500.0)

        assert engine.consecutive_losses.get('AAPL') == 1, \
            f"Expected consecutive_losses['AAPL']==1, got {engine.consecutive_losses.get('AAPL')}"
        assert 'AAPL' in engine.last_exit_time, "last_exit_time should be set for AAPL"
        # Verify timestamp is recent (within last few seconds)
        elapsed = (datetime.now() - engine.last_exit_time['AAPL']).total_seconds()
        assert elapsed < 5, f"last_exit_time should be recent, was {elapsed}s ago"

    def test_record_position_exit_profit_resets_consecutive_losses(self):
        """Recording a profit exit should reset (delete) consecutive_losses for that ticker."""
        engine, _ = make_alpaca_engine()

        # First record a loss
        engine._record_position_exit('AAPL', -200.0)
        assert engine.consecutive_losses.get('AAPL') == 1, "Loss should be recorded"

        # Then record a profit
        engine._record_position_exit('AAPL', 300.0)

        assert 'AAPL' not in engine.consecutive_losses, \
            f"Profit should reset consecutive_losses, but AAPL still present: {engine.consecutive_losses}"
        # last_exit_time should still be updated
        assert 'AAPL' in engine.last_exit_time, "last_exit_time should still be set"

    def test_record_position_exit_multiple_losses_increments(self):
        """Multiple consecutive losses should increment the counter correctly."""
        engine, _ = make_alpaca_engine()

        engine._record_position_exit('AAPL', -100.0)
        assert engine.consecutive_losses['AAPL'] == 1

        engine._record_position_exit('AAPL', -200.0)
        assert engine.consecutive_losses['AAPL'] == 2

        engine._record_position_exit('AAPL', -150.0)
        assert engine.consecutive_losses['AAPL'] == 3

    def test_check_cooldown_blocks_reentry(self):
        """Ticker in cooldown period should be blocked from re-entry."""
        engine, _ = make_alpaca_engine()

        # Set recent exit time and 1 consecutive loss
        engine.last_exit_time['AAPL'] = datetime.now() - timedelta(minutes=5)
        engine.consecutive_losses['AAPL'] = 1

        can_enter, reason = engine._check_cooldown('AAPL')

        assert can_enter is False, f"Expected cooldown to block re-entry, but got can_enter={can_enter}"
        assert reason is not None, "Reason should be provided when entry is blocked"
        assert 'cooldown' in reason.lower() or 'min remaining' in reason.lower(), \
            f"Expected cooldown-related reason, got: {reason}"

    def test_check_cooldown_allows_reentry_after_cooldown(self):
        """Ticker whose cooldown has expired should be allowed re-entry."""
        engine, _ = make_alpaca_engine()

        # Set exit time well in the past (beyond max_cooldown_minutes)
        max_cooldown = engine.risk_config.cooldown.max_cooldown_minutes
        engine.last_exit_time['AAPL'] = datetime.now() - timedelta(minutes=max_cooldown + 60)
        engine.consecutive_losses['AAPL'] = 3

        can_enter, reason = engine._check_cooldown('AAPL')

        assert can_enter is True, f"Expected re-entry allowed after cooldown, but got can_enter={can_enter}"
        assert reason is None, f"Expected None reason when allowed, got: {reason}"

    def test_check_cooldown_no_exit_history_allows_entry(self):
        """Ticker with no exit history should be allowed entry without restriction."""
        engine, _ = make_alpaca_engine()

        # No exit history for NVDA
        assert 'NVDA' not in engine.last_exit_time
        assert 'NVDA' not in engine.consecutive_losses

        can_enter, reason = engine._check_cooldown('NVDA')

        assert can_enter is True, f"Expected entry allowed for new ticker, got can_enter={can_enter}"
        assert reason is None, f"Expected None reason for new ticker, got: {reason}"

    def test_check_cooldown_exponential_backoff(self):
        """More consecutive losses should result in longer effective cooldown."""
        engine, _ = make_alpaca_engine()

        base_cooldown = engine.risk_config.cooldown.reentry_cooldown_minutes
        multiplier = engine.risk_config.cooldown.consecutive_loss_multiplier
        max_cooldown = engine.risk_config.cooldown.max_cooldown_minutes

        # With 0 consecutive losses (profit trade), effective cooldown = base
        engine.last_exit_time['TST0'] = datetime.now() - timedelta(minutes=base_cooldown / 2)
        engine.consecutive_losses['TST0'] = 0
        # effective_cooldown = base * 2^0 = base
        can_enter, _ = engine._check_cooldown('TST0')
        # Half of base cooldown elapsed => still blocked
        assert can_enter is False, "Should be blocked within base cooldown with 0 losses"

        # With 1 consecutive loss, effective cooldown = base * 2 = 2*base
        engine.last_exit_time['TST1'] = datetime.now() - timedelta(minutes=base_cooldown + 1)
        engine.consecutive_losses['TST1'] = 1
        # effective_cooldown = base * 2^1 = 2*base
        # elapsed = base + 1, which is less than 2*base => blocked
        can_enter, _ = engine._check_cooldown('TST1')
        assert can_enter is False, "Should be blocked with 1 loss and cooldown still active"

        # With 1 loss but beyond effective cooldown
        engine.last_exit_time['TST1b'] = datetime.now() - timedelta(minutes=2 * base_cooldown + 10)
        engine.consecutive_losses['TST1b'] = 1
        can_enter, _ = engine._check_cooldown('TST1b')
        assert can_enter is True, "Should allow entry after exponential cooldown expires"


# ============================================================================
# Timeout / Connection error tests
# ============================================================================

class TestExecuteEntryErrorHandling(unittest.TestCase):
    """Tests for _execute_entry error handling with TimeoutError and ConnectionError."""

    def _make_analysis(self, ticker='TEST'):
        """Create a standard analysis dict for entry."""
        return {
            'ticker': ticker,
            'current': 150.0,
            'stop': 142.5,
            'target': 165.0,
            'sector': 'Technology',
        }

    def test_execute_entry_catches_timeout_error(self):
        """_execute_entry should handle TimeoutError from submit_entry gracefully."""
        engine, _ = make_alpaca_engine()

        analysis = self._make_analysis()

        # Mock all pre-conditions to allow entry
        engine._check_market_hours_for_trading = Mock(return_value=(True, "ok"))
        engine._check_cooldown = Mock(return_value=(True, None))
        engine.order_manager.has_pending_order = Mock(return_value=False)
        engine.exits.calculate_position_size = Mock(return_value=10)
        engine.exits.get_last_position_calc = Mock(return_value={
            'risk_per_share': 7.5,
            'stop_distance_pct': 5.0,
            'constraints_applied': None,
            'rejected': False,
            'position_pct': 1.5,
            'account_risk_dollars': 75.0,
            'account_risk_pct': 0.075,
        })
        engine.state.can_enter_position = Mock(return_value=(True, "ok"))

        # Make submit_entry raise TimeoutError
        engine.order_manager.submit_entry = Mock(side_effect=TimeoutError("Alpaca API timeout"))

        # Should not crash
        with patch('builtins.print') as mock_print:
            engine._execute_entry(analysis)

        # Position should NOT be created
        assert 'TEST' not in engine.state.positions, "No position should be created on timeout"
        # Ticker should NOT be added to signaled set (since order wasn't submitted)
        assert 'TEST' not in engine.signaled_tickers, "Ticker should not be signaled on timeout"

    def test_execute_entry_catches_connection_error(self):
        """_execute_entry should handle ConnectionError from submit_entry gracefully."""
        engine, _ = make_alpaca_engine()

        analysis = self._make_analysis()

        # Mock all pre-conditions to allow entry
        engine._check_market_hours_for_trading = Mock(return_value=(True, "ok"))
        engine._check_cooldown = Mock(return_value=(True, None))
        engine.order_manager.has_pending_order = Mock(return_value=False)
        engine.exits.calculate_position_size = Mock(return_value=10)
        engine.exits.get_last_position_calc = Mock(return_value={
            'risk_per_share': 7.5,
            'stop_distance_pct': 5.0,
            'constraints_applied': None,
            'rejected': False,
            'position_pct': 1.5,
            'account_risk_dollars': 75.0,
            'account_risk_pct': 0.075,
        })
        engine.state.can_enter_position = Mock(return_value=(True, "ok"))

        # Make submit_entry raise ConnectionError
        engine.order_manager.submit_entry = Mock(side_effect=ConnectionError("Alpaca connection lost"))

        # Should not crash
        with patch('builtins.print') as mock_print:
            engine._execute_entry(analysis)

        # Position should NOT be created
        assert 'TEST' not in engine.state.positions, "No position should be created on connection error"
        # Ticker should NOT be added to signaled set
        assert 'TEST' not in engine.signaled_tickers, "Ticker should not be signaled on connection error"


# ============================================================================
# Sell fill tests
# ============================================================================

class TestSellFillProcessing(unittest.TestCase):
    """Tests for sell order fill processing."""

    def test_sell_fill_processes_exit_order(self):
        """A filled sell order should be processed without error."""
        engine, _ = make_alpaca_engine()

        order = Order(
            id='test-exit-1',
            ticker='AAPL',
            side='sell',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now().isoformat(),
            filled_price=165.0,
            filled_qty=100,
            stop_price=None,
            reason='TARGET_HIT',
        )

        engine.order_manager = Mock()
        engine.order_manager.get_pending_count.return_value = 1
        engine.order_manager.process_all_pending.return_value = [order]

        # Should not raise - sell fills are handled by order_manager or elsewhere
        with patch('builtins.print') as mock_print:
            asyncio.run(engine._process_pending_orders())

        # Verify the sell fill message was printed
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        assert 'Exit filled' in printed or 'exit' in printed.lower(), \
            f"Expected exit fill message, got: {printed}"


class TestSameLevelRejection(unittest.TestCase):
    """Tests for same-level re-entry rejection."""

    def test_loss_records_stopped_entry(self):
        """Recording a loss with entry_price should store it in stopped_entries."""
        engine, _ = make_alpaca_engine()
        engine._record_position_exit('MXL', -500.0, entry_price=92.0)
        assert 'MXL' in engine.stopped_entries
        assert len(engine.stopped_entries['MXL']) == 1
        assert engine.stopped_entries['MXL'][0][1] == 92.0

    def test_loss_without_entry_price_warns(self):
        """Recording a loss without entry_price should warn but not crash."""
        engine, _ = make_alpaca_engine()
        engine._record_position_exit('AAPL', -100.0)  # 2-arg legacy call
        assert 'AAPL' not in engine.stopped_entries

    def test_profit_clears_stopped_entries(self):
        """A profitable exit should clear stopped entries for that ticker."""
        engine, _ = make_alpaca_engine()
        engine._record_position_exit('MXL', -500.0, entry_price=92.0)
        assert 'MXL' in engine.stopped_entries
        engine._record_position_exit('MXL', 300.0, entry_price=95.0)
        assert 'MXL' not in engine.stopped_entries

    def test_same_level_rejection_blocks_entry(self):
        """Entry within 2% of a stopped entry should be rejected."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        # Simulate a stopped-out trade at $92
        engine.stopped_entries['MXL'] = [(datetime.now(), 92.0)]
        # Mock _execute_entry dependencies
        engine.signaled_tickers = set()
        engine.order_manager = Mock()
        engine.order_manager.has_pending_order.return_value = False
        analysis = {
            'ticker': 'MXL', 'current': 92.5, 'stop': 87.0, 'target': 105,
            'sector': 'Tech',
        }
        # Capture prints
        with patch('builtins.print') as mock_print:
            engine._execute_entry(analysis)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        assert 'Rejected' in printed or '⛔' in printed

    def test_same_level_rejection_allows_different_price(self):
        """Entry outside 2% of a stopped entry should proceed."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        engine.stopped_entries['MXL'] = [(datetime.now(), 92.0)]
        engine.signaled_tickers = set()
        engine.order_manager = Mock()
        engine.order_manager.has_pending_order.return_value = False
        analysis = {
            'ticker': 'MXL', 'current': 100.0, 'stop': 95.0, 'target': 110,
            'sector': 'Tech',
        }
        with patch('builtins.print') as mock_print:
            engine._execute_entry(analysis)
        printed = ' '.join(str(c) for c in mock_print.call_args_list)
        assert 'Rejected' not in printed and '⛔' not in printed

    def test_same_level_disabled_when_pct_zero(self):
        """When same_level_rejection_pct=0.0, no blocks should apply."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        engine.risk_config.cooldown.same_level_rejection_pct = 0.0
        engine.stopped_entries['MXL'] = [(datetime.now(), 92.0)]
        assert engine._get_active_blocks() == {}

    def test_prune_stopped_entries_removes_old(self):
        """Entries older than the memory window should be pruned."""
        from datetime import datetime, timedelta
        engine, _ = make_alpaca_engine()
        # Old entry (beyond 72h window)
        old_time = datetime.now() - timedelta(minutes=5000)
        engine.stopped_entries['MXL'] = [(old_time, 92.0)]
        engine._prune_stopped_entries('MXL')
        assert engine.stopped_entries.get('MXL', []) == []

    def test_prune_stopped_entries_keeps_recent(self):
        """Entries within the memory window should be kept."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        engine.stopped_entries['MXL'] = [(datetime.now(), 92.0)]
        engine._prune_stopped_entries('MXL')
        assert len(engine.stopped_entries['MXL']) == 1

    def test_multiple_stopped_entries_append(self):
        """Multiple losses should append to the stopped_entries list."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        engine._record_position_exit('MXL', -500.0, entry_price=92.0)
        engine._record_position_exit('MXL', -300.0, entry_price=85.0)
        assert len(engine.stopped_entries['MXL']) == 2

    def test_get_active_blocks_returns_count(self):
        """_get_active_blocks should return count of active stopped entries."""
        from datetime import datetime
        engine, _ = make_alpaca_engine()
        engine.stopped_entries['MXL'] = [(datetime.now(), 92.0), (datetime.now(), 85.0)]
        engine.stopped_entries['VRT'] = [(datetime.now(), 300.0)]
        blocks = engine._get_active_blocks()
        assert blocks['MXL'] == 2
        assert blocks['VRT'] == 1


if __name__ == '__main__':
    unittest.main()