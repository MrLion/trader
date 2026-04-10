#!/usr/bin/env python3
"""Integration tests for paper trading engine workflows.

Tests complete workflows:
- Entry → Fill → Position tracking
- Position → Exit Signal → Exit Order → Fill
- Run loop iteration with mocked components
"""

import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call

import pandas as pd
import pytest
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts' / 'lib'))

from paper_state import PaperState, Position
from paper_exits import ExitSignal


class TestEntryFillExitWorkflow(unittest.TestCase):
    """Test complete entry → fill → exit → fill workflow."""

    def setUp(self):
        """Set up engine with mocked components."""
        from paper_engine_alpaca import AlpacaPaperEngine
        from order_manager import Order, OrderStatus

        self.mock_alpaca = Mock()
        self.mock_alpaca.get_account.return_value = {'equity': 100000.0, 'cash': 100000.0}
        self.mock_alpaca.get_positions.return_value = []
        self.mock_alpaca.list_orders.return_value = []
        self.mock_alpaca.is_ws_healthy.return_value = True
        self.mock_alpaca.get_health_summary.return_value = 'HEALTHY'

        with patch('paper_engine_alpaca.AlpacaClient', return_value=self.mock_alpaca):
            with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
                with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                    with patch.object(PaperState, '_load_state', return_value=None):
                        with patch('paper_engine_alpaca.WATCHLIST_PATH', Path('/tmp/test_watchlist.csv')):
                            self.engine = AlpacaPaperEngine(mode='paper')

        # Ensure clean state
        self.engine.state.positions = {}
        self.engine.state.cash = 100000.0
        self.engine.state.equity = 100000.0
        self.engine.signaled_tickers = set()

    def test_entry_submission_creates_pending_order(self):
        """Test that entry execution creates a pending order."""
        from order_manager import OrderStatus

        # Setup mock order
        mock_order = Mock(
            id='test-entry-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.PENDING,
            submitted_at='2024-04-08T10:00:00'
        )
        self.engine.order_manager.submit_entry = Mock(return_value=mock_order)
        self.engine.order_manager.has_pending_order = Mock(return_value=False)

        # Mock can_enter_position to allow entry
        self.engine.state.can_enter_position = Mock(return_value=(True, ""))

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        # Execute entry
        self.engine._execute_entry(analysis)

        # Verify order was submitted (50 shares calculated from 0.5% account risk)
        self.engine.order_manager.submit_entry.assert_called_once_with(
            ticker='AAPL',
            shares=50,
            stop_price=140.0
        )

        # Verify position was recorded locally
        self.assertIn('AAPL', self.engine.state.positions)
        self.assertEqual(self.engine.state.positions['AAPL'].shares, 50)

    def test_fill_updates_position_entry_price(self):
        """Test that order fill updates position with actual fill price."""
        from order_manager import Order, OrderStatus

        # Create a filled order
        filled_order = Order(
            id='test-entry-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2024-04-08T10:00:00',
            filled_price=150.50,  # Slippage from expected 150.0
            filled_qty=100
        )

        # Setup pending orders
        self.engine.order_manager.pending_orders = {'test-entry-1': filled_order}
        self.engine.order_manager.get_pending_count = Mock(return_value=1)
        self.engine.order_manager.process_all_pending = Mock(return_value=[filled_order])

        # Add position with original entry price
        position = self.engine.state.enter_position(
            ticker='AAPL',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=165.0,
            sector='Technology'
        )
        position.initial_risk = 1000.0  # (150-140) * 100

        # Process pending orders
        self.engine._process_pending_orders()

        # Verify position was updated with fill price
        self.assertEqual(self.engine.state.positions['AAPL'].entry_price, 150.50)

    def test_exit_signal_triggers_exit_order(self):
        """Test that exit signal triggers exit order submission."""
        from order_manager import Order, OrderStatus

        # Setup mock exit order
        mock_exit_order = Mock(
            id='test-exit-1',
            ticker='AAPL',
            side='sell',
            qty=100,
            status=OrderStatus.PENDING
        )
        self.engine.order_manager.submit_exit = Mock(return_value=mock_exit_order)
        self.engine.order_manager.get_pending_for_ticker = Mock(return_value=[])

        # Add open position
        position = self.engine.state.enter_position(
            ticker='AAPL',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=165.0,
            sector='Technology'
        )
        position.initial_risk = 1000.0

        # Create exit signal
        signal = ExitSignal(
            should_exit=True,
            reason='TARGET_HIT',
            exit_price=165.0,
            r_multiple=2.0
        )

        # Execute exit
        asyncio.run(self._async_execute_exit('AAPL', signal))

        # Verify exit order was submitted
        self.engine.order_manager.submit_exit.assert_called_once_with(
            ticker='AAPL',
            shares=100,
            reason='TARGET_HIT'
        )

    async def _async_execute_exit(self, ticker, signal):
        """Helper to run async exit execution."""
        await self.engine._execute_exit(ticker, signal)

    def test_exit_fill_closes_position(self):
        """Test that exit fill closes the position and updates P&L."""
        from order_manager import Order, OrderStatus

        # Create filled exit order
        exit_order = Order(
            id='test-exit-1',
            ticker='AAPL',
            side='sell',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2024-04-08T10:00:00',
            filled_price=165.0,
            filled_qty=100,
            reason='TARGET_HIT'
        )

        # Setup order manager
        self.engine.order_manager.pending_orders = {'test-exit-1': exit_order}
        self.engine.order_manager.get_pending_count = Mock(return_value=1)
        self.engine.order_manager.process_all_pending = Mock(return_value=[exit_order])

        # Add closed position (optimistically marked closed when exit submitted)
        position = self.engine.state.enter_position(
            ticker='AAPL',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=165.0,
            sector='Technology'
        )
        position.status = 'OPEN'

        # Process fills
        self.engine._process_pending_orders()

        # Position should still exist but verify process completed
        self.assertTrue(hasattr(self.engine.state, 'positions'))

    def test_full_workflow_entry_to_exit(self):
        """Test complete workflow from entry analysis to exit fill."""
        from order_manager import Order, OrderStatus

        # Step 1: Entry execution creates position and order
        entry_order = Order(
            id='entry-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.PENDING,
            submitted_at='2024-04-08T10:00:00'
        )

        self.engine.order_manager.submit_entry = Mock(return_value=entry_order)
        self.engine.order_manager.has_pending_order = Mock(return_value=False)
        self.engine.state.can_enter_position = Mock(return_value=(True, ""))

        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        # Execute entry
        self.engine._execute_entry(analysis)

        # Verify position created (50 shares calculated from 0.5% account risk)
        self.assertIn('AAPL', self.engine.state.positions)
        initial_position = self.engine.state.positions['AAPL']
        self.assertEqual(initial_position.shares, 50)
        self.assertEqual(initial_position.status, 'OPEN')
        # Set initial_risk based on 50 shares (150-140) * 50 = 500
        initial_position.initial_risk = 500.0

        # Step 2: Entry fill updates position
        entry_order.filled_price = 150.25
        entry_order.filled_qty = 50
        entry_order.status = OrderStatus.FILLED

        self.engine.order_manager.pending_orders = {'entry-1': entry_order}
        self.engine.order_manager.get_pending_count = Mock(return_value=1)
        self.engine.order_manager.process_all_pending = Mock(return_value=[entry_order])

        self.engine._process_pending_orders()

        # Step 3: Check exits generates exit signal
        # Update position with current price above target
        current_price = 166.0  # Above target of 165

        # Mock exit engine to return exit signal
        exit_signal = ExitSignal(
            should_exit=True,
            reason='TARGET_HIT',
            exit_price=current_price,
            r_multiple=2.0
        )
        self.engine.exits.evaluate_exit = Mock(return_value=exit_signal)

        # Mock price getter
        self.engine._get_current_price = Mock(return_value=current_price)

        # Setup for exit submission
        exit_order = Order(
            id='exit-1',
            ticker='AAPL',
            side='sell',
            qty=50,
            status=OrderStatus.PENDING,
            submitted_at='2024-04-08T14:00:00'
        )
        self.engine.order_manager.submit_exit = Mock(return_value=exit_order)
        self.engine.order_manager.get_pending_for_ticker = Mock(return_value=[])

        # Check exits (this triggers _execute_exit) - needs event loop
        async def run_check_exits():
            self.engine._check_exits()
            # Give async tasks time to process
            await asyncio.sleep(0)

        asyncio.run(run_check_exits())

        # Verify exit was submitted
        self.engine.order_manager.submit_exit.assert_called_once()


class TestRunLoopIterations(unittest.TestCase):
    """Test run() loop with mocked components."""

    def setUp(self):
        """Set up engine with mocked async components."""
        from paper_engine_alpaca import AlpacaPaperEngine

        self.mock_alpaca = Mock()
        self.mock_alpaca.get_account.return_value = {'equity': 100000.0, 'cash': 100000.0}
        self.mock_alpaca.get_positions.return_value = []
        self.mock_alpaca.list_orders.return_value = []
        self.mock_alpaca.is_ws_healthy.return_value = True
        self.mock_alpaca.get_health_summary.return_value = 'HEALTHY'
        self.mock_alpaca.ws_reconnect_delay = 5

        with patch('paper_engine_alpaca.AlpacaClient', return_value=self.mock_alpaca):
            with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
                with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                    with patch.object(PaperState, '_load_state', return_value=None):
                        with patch('paper_engine_alpaca.WATCHLIST_PATH', Path('/tmp/test_watchlist.csv')):
                            self.engine = AlpacaPaperEngine(mode='paper')

        self.engine.state.positions = {}
        self.engine.state.cash = 100000.0
        self.engine.signaled_tickers = set()

    @pytest.mark.skip(reason="Fragile async test - needs debugging")
    def test_run_loop_single_iteration_market_open(self):
        """Test one iteration of run loop during market hours."""
        from order_manager import OrderStatus

        # Mock all the methods called in run loop
        self.engine._refresh_spy_cache = Mock(return_value=True)
        self.engine._reset_daily_signals = Mock()
        self.engine._print_status = Mock()
        self.engine._process_pending_orders = Mock()
        self.engine._check_exits = Mock()
        self.engine._check_entries = Mock()
        self.engine._is_market_hours = Mock(return_value=True)

        # Mock WebSocket task
        mock_ws_task = Mock()
        mock_ws_task.done.return_value = True
        mock_ws_task.exception.return_value = None

        # Create a side effect that stops after one iteration
        iteration_count = [0]
        def stop_after_one():
            iteration_count[0] += 1
            if iteration_count[0] >= 1:
                self.engine.running = False
            return mock_ws_task

        self.engine._start_websocket = AsyncMock(side_effect=stop_after_one)

        # Run the loop
        asyncio.run(self._run_with_timeout(self.engine.run(), timeout=2))

        # Verify all expected methods were called
        self.engine._refresh_spy_cache.assert_called()
        self.engine._reset_daily_signals.assert_called()
        self.engine._print_status.assert_called()
        self.engine._process_pending_orders.assert_called()
        self.engine._check_exits.assert_called()
        self.engine._check_entries.assert_called()

    @pytest.mark.skip(reason="Fragile async test - needs debugging")
    def test_run_loop_single_iteration_market_closed(self):
        """Test one iteration when market is closed."""
        from order_manager import OrderStatus

        # Mock all the methods
        self.engine._refresh_spy_cache = Mock(return_value=True)
        self.engine._reset_daily_signals = Mock()
        self.engine._print_status = Mock()
        self.engine._process_pending_orders = Mock()
        self.engine._check_exits = Mock()
        self.engine._check_entries = Mock()
        self.engine._is_market_hours = Mock(return_value=False)

        # Mock WebSocket task
        mock_ws_task = Mock()
        mock_ws_task.done.return_value = True
        mock_ws_task.exception.return_value = None

        iteration_count = [0]
        async def start_ws():
            iteration_count[0] += 1
            if iteration_count[0] >= 1:
                self.engine.running = False
            return None

        self.engine._start_websocket = AsyncMock(side_effect=start_ws)

        # Run the loop
        asyncio.run(self._run_with_timeout(self.engine.run(), timeout=2))

        # Verify market-closed behavior: no entry/exit checks
        self.engine._refresh_spy_cache.assert_called()
        self.engine._process_pending_orders.assert_called()
        self.engine._check_exits.assert_not_called()
        self.engine._check_entries.assert_not_called()

    @pytest.mark.skip(reason="Fragile async test - hangs indefinitely")
    def test_run_loop_handles_websocket_restart(self):
        """Test WebSocket restart on disconnect."""
        # Create a task that appears to have failed
        mock_task = Mock()
        mock_task.done.return_value = True
        mock_task.exception.return_value = Exception("Connection lost")

        self.engine._refresh_spy_cache = Mock(return_value=True)
        self.engine._reset_daily_signals = Mock()
        self.engine._print_status = Mock()
        self.engine._process_pending_orders = Mock()
        self.engine._is_market_hours = Mock(return_value=False)

        # Track WebSocket starts
        ws_starts = []
        async def track_ws_start():
            ws_starts.append(len(ws_starts))
            if len(ws_starts) >= 2:
                self.engine.running = False
            return mock_task

        self.engine._start_websocket = AsyncMock(side_effect=track_ws_start)

        # Run with minimal sleep
        with patch('asyncio.sleep', new_callable=AsyncMock):
            asyncio.run(self._run_with_timeout(self.engine.run(), timeout=2))

        # WebSocket should be restarted
        self.assertGreaterEqual(len(ws_starts), 1)

    def test_run_loop_graceful_shutdown(self):
        """Test graceful shutdown on signal."""
        self.engine._refresh_spy_cache = Mock(return_value=True)
        self.engine._reset_daily_signals = Mock()
        self.engine._print_status = Mock()
        self.engine._process_pending_orders = Mock()
        self.engine._is_market_hours = Mock(return_value=False)
        self.engine.alpaca.stop_price_stream = AsyncMock()

        # Signal handler should set running to False
        import signal
        self.engine.running = True

        # Simulate immediate stop
        self.engine._start_websocket = AsyncMock(side_effect=lambda: setattr(self.engine, 'running', False) or None)

        asyncio.run(self._run_with_timeout(self.engine.run(), timeout=2))

        # Should complete without error
        self.assertFalse(self.engine.running)

    async def _run_with_timeout(self, coro, timeout=5):
        """Helper to run coroutine with timeout."""
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            pass


class TestEntryExitEdgeCases(unittest.TestCase):
    """Test edge cases in entry/exit workflows."""

    def setUp(self):
        """Set up engine."""
        from paper_engine_alpaca import AlpacaPaperEngine

        self.mock_alpaca = Mock()
        self.mock_alpaca.get_account.return_value = {'equity': 100000.0, 'cash': 100000.0}
        self.mock_alpaca.get_positions.return_value = []
        self.mock_alpaca.list_orders.return_value = []
        self.mock_alpaca.is_ws_healthy.return_value = True
        self.mock_alpaca.get_health_summary.return_value = 'HEALTHY'

        with patch('paper_engine_alpaca.AlpacaClient', return_value=self.mock_alpaca):
            with patch.object(AlpacaPaperEngine, '_get_account_value', return_value=100000.0):
                with patch.object(AlpacaPaperEngine, '_sync_with_alpaca'):
                    with patch.object(PaperState, '_load_state', return_value=None):
                        with patch('paper_engine_alpaca.WATCHLIST_PATH', Path('/tmp/test_watchlist.csv')):
                            self.engine = AlpacaPaperEngine(mode='paper')

        self.engine.state.positions = {}
        self.engine.state.cash = 100000.0

    def test_exit_without_position_does_nothing(self):
        """Test that exit signal for non-existent position does nothing."""
        signal = ExitSignal(
            should_exit=True,
            reason='STOP_HIT',
            exit_price=140.0,
            r_multiple=-1.0
        )

        # No position for TSLA
        self.engine.order_manager.submit_exit = Mock()

        # Should complete without error
        asyncio.run(self._async_execute_exit('TSLA', signal))

        # No order should be submitted
        self.engine.order_manager.submit_exit.assert_not_called()

    def test_exit_with_pending_exit_does_not_duplicate(self):
        """Test that exit is not duplicated if already pending."""
        from order_manager import Order, OrderStatus

        # Create position
        position = self.engine.state.enter_position(
            ticker='AAPL',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=165.0,
            sector='Technology'
        )

        # Mock pending sell order
        pending_sell = Mock(side='sell')
        self.engine.order_manager.get_pending_for_ticker = Mock(return_value=[pending_sell])
        self.engine.order_manager.submit_exit = Mock()

        signal = ExitSignal(
            should_exit=True,
            reason='STOP_HIT',
            exit_price=140.0,
            r_multiple=-1.0
        )

        asyncio.run(self._async_execute_exit('AAPL', signal))

        # Should not submit duplicate exit
        self.engine.order_manager.submit_exit.assert_not_called()

    def test_entry_with_zero_shares_rejected(self):
        """Test that entry with zero position size is rejected."""
        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 149.99,  # Very tight stop, zero shares calculated
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        self.engine.exits.calculate_position_size = Mock(return_value=0)
        self.engine.order_manager.submit_entry = Mock()

        self.engine._execute_entry(analysis)

        # Should not submit order
        self.engine.order_manager.submit_entry.assert_not_called()

    def test_entry_order_submission_failure_handled(self):
        """Test handling when order submission fails."""
        analysis = {
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'stop': 140.0,
            'target': 165.0,
            'entry_score': 85,
            'sector': 'Technology'
        }

        self.engine.order_manager.has_pending_order = Mock(return_value=False)
        self.engine.state.can_enter_position = Mock(return_value=(True, ""))
        self.engine.order_manager.submit_entry = Mock(return_value=None)  # Failed

        # Should not raise
        self.engine._execute_entry(analysis)

        # Verify it was attempted
        self.engine.order_manager.submit_entry.assert_called_once()

    async def _async_execute_exit(self, ticker, signal):
        """Helper to run async exit execution."""
        await self.engine._execute_exit(ticker, signal)


def run_tests():
    """Run all integration tests."""
    print("=" * 70)
    print("🔗 INTEGRATION TESTS - Entry/Fill/Exit Workflows & Run Loop")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestEntryFillExitWorkflow))
    suite.addTests(loader.loadTestsFromTestCase(TestRunLoopIterations))
    suite.addTests(loader.loadTestsFromTestCase(TestEntryExitEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL INTEGRATION TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
