#!/usr/bin/env python3
"""Tests for order lifecycle manager.

Covers:
1. Order dataclass (serialization/deserialization)
2. OrderStatus enum
3. OrderManager initialization and lifecycle
4. Order queue processing
5. Entry/exit order submission
6. Order status checking and mapping
7. Position synchronization
8. Thread safety
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path

from traderlib.order_manager import (
    OrderStatus,
    Order,
    QueuedOrder,
    OrderManager,
    _atomic_write_json,
)


class TestAtomicWriteJson(unittest.TestCase):
    """Test atomic JSON write utility."""

    def test_atomic_write_creates_file(self):
        """Should create file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / 'test.json'
            data = {'key': 'value', 'number': 42}

            _atomic_write_json(filepath, data)

            self.assertTrue(filepath.exists())
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            self.assertEqual(loaded, data)

    def test_atomic_write_removes_temp_on_error(self):
        """Should clean up temp file on error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / 'test.json'

            # Make directory read-only to cause error
            os.chmod(tmpdir, 0o555)
            try:
                with self.assertRaises(OSError):
                    _atomic_write_json(filepath, {'key': 'value'})
            finally:
                os.chmod(tmpdir, 0o755)


class TestOrderStatus(unittest.TestCase):
    """Test OrderStatus enum."""

    def test_all_status_values(self):
        """Should have all expected status values."""
        statuses = [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIAL_FILL,
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
        ]

        self.assertEqual(len(statuses), 8)

    def test_status_values(self):
        """Status values should be correct strings."""
        self.assertEqual(OrderStatus.PENDING.value, 'pending')
        self.assertEqual(OrderStatus.FILLED.value, 'filled')
        self.assertEqual(OrderStatus.REJECTED.value, 'rejected')


class TestOrderDataclass(unittest.TestCase):
    """Test Order dataclass."""

    def test_order_creation(self):
        """Should create Order with required fields."""
        order = Order(
            id='test-order-123',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
        )

        self.assertEqual(order.id, 'test-order-123')
        self.assertEqual(order.ticker, 'AAPL')
        self.assertEqual(order.side, 'buy')
        self.assertEqual(order.qty, 100)
        self.assertIsNone(order.filled_price)

    def test_order_to_dict(self):
        """to_dict should serialize Order correctly."""
        order = Order(
            id='test-123',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.FILLED,
            submitted_at='2024-01-01T00:00:00',
            filled_at='2024-01-01T00:01:00',
            filled_price=150.0,
            filled_qty=100.0,
        )

        data = order.to_dict()

        self.assertEqual(data['id'], 'test-123')
        self.assertEqual(data['status'], 'filled')
        self.assertEqual(data['filled_price'], 150.0)

    def test_order_from_dict(self):
        """from_dict should deserialize Order correctly."""
        data = {
            'id': 'test-123',
            'ticker': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'status': 'filled',
            'submitted_at': '2024-01-01T00:00:00',
            'filled_at': '2024-01-01T00:01:00',
            'filled_price': 150.0,
            'filled_qty': 100.0,
            'target_price': 200.0,
            'sector': 'Technology',
        }

        order = Order.from_dict(data)

        self.assertEqual(order.id, 'test-123')
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.target_price, 200.0)
        self.assertEqual(order.sector, 'Technology')

    def test_order_from_dict_handles_missing_optional(self):
        """from_dict should handle missing optional fields."""
        data = {
            'id': 'test-123',
            'ticker': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'status': 'submitted',
            'submitted_at': '2024-01-01T00:00:00',
        }

        order = Order.from_dict(data)

        self.assertIsNone(order.target_price)
        self.assertIsNone(order.sector)
        self.assertIsNone(order.expected_entry_price)


class TestQueuedOrder(unittest.TestCase):
    """Test QueuedOrder dataclass."""

    def test_queued_order_creation(self):
        """Should create QueuedOrder with required fields."""
        order = QueuedOrder(
            order_type='entry',
            ticker='AAPL',
            shares=100,
        )

        self.assertEqual(order.order_type, 'entry')
        self.assertEqual(order.ticker, 'AAPL')
        self.assertEqual(order.shares, 100)
        self.assertIsNotNone(order.queued_at)

    def test_queued_order_with_callback(self):
        """Should accept optional callback."""
        def callback(result):
            pass

        order = QueuedOrder(
            order_type='entry',
            ticker='AAPL',
            shares=100,
            callback=callback,
        )

        self.assertEqual(order.callback, callback)


class TestOrderManager(unittest.TestCase):
    """Test OrderManager class."""

    def setUp(self):
        """Create mock Alpaca client and temp directory."""
        self.mock_alpaca = Mock()
        self.temp_dir = tempfile.mkdtemp()
        os.environ['PAPER_TRADING_DATA_DIR'] = self.temp_dir

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop('PAPER_TRADING_DATA_DIR', None)

    @patch('traderlib.order_manager.threading.Thread')
    def test_init_creates_directories(self, mock_thread):
        """Init should set up data directories."""
        mock_thread.return_value.start = Mock()

        manager = OrderManager(self.mock_alpaca, max_tps=2.0)

        self.assertEqual(manager.max_tps, 2.0)
        self.assertEqual(manager.min_interval, 0.5)  # 1/2.0
        self.assertEqual(manager.data_dir, Path(self.temp_dir))

    @patch('traderlib.order_manager.threading.Thread')
    def test_init_starts_worker_thread(self, mock_thread):
        """Init should start background worker thread."""
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        manager = OrderManager(self.mock_alpaca, max_tps=2.0)

        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

    def test_can_submit_directly_after_interval(self):
        """Should allow direct submit after interval."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=10.0)  # 0.1s interval
            manager.last_submit_time = 0  # Long ago

            self.assertTrue(manager._can_submit_directly())

    def test_can_submit_directly_within_interval(self):
        """Should not allow direct submit within interval."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=1.0)  # 1s interval
            manager.last_submit_time = time.time()  # Just now

            self.assertFalse(manager._can_submit_directly())

    def test_submit_entry_direct_calls_alpaca(self):
        """Direct entry submit should call Alpaca."""
        self.mock_alpaca.submit_market_order.return_value = {
            'id': 'alpaca-order-123',
            'status': 'accepted',
        }

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)
            manager.last_submit_time = 0

            result = manager._submit_entry_to_alpaca(
                ticker='AAPL',
                shares=100,
                stop_price=90.0,
            )

            self.mock_alpaca.submit_market_order.assert_called_once_with(
                'AAPL', 100, 'buy', 90.0
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.ticker, 'AAPL')

    def test_submit_entry_direct_failure_returns_none(self):
        """Failed Alpaca submit should return None."""
        self.mock_alpaca.submit_market_order.return_value = None

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)
            manager.last_submit_time = 0

            result = manager._submit_entry_to_alpaca(
                ticker='AAPL',
                shares=100,
                stop_price=90.0,
            )

            self.assertIsNone(result)

    def test_submit_exit_direct_calls_alpaca(self):
        """Direct exit submit should call Alpaca submit_market_order."""
        self.mock_alpaca.submit_market_order.return_value = {
            'id': 'alpaca-exit-123',
            'status': 'accepted',
        }

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)
            manager.last_submit_time = 0

            result = manager._submit_exit_to_alpaca(
                ticker='AAPL',
                shares=100,
                reason='STOP_HIT',
            )

            self.mock_alpaca.submit_market_order.assert_called_once_with('AAPL', 100, 'sell')
            self.assertIsNotNone(result)
            self.assertEqual(result.reason, 'STOP_HIT')

    def test_map_alpaca_status(self):
        """Should correctly map Alpaca statuses."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            test_cases = [
                ('new', OrderStatus.SUBMITTED),
                ('accepted', OrderStatus.ACCEPTED),
                ('partially_filled', OrderStatus.PARTIAL_FILL),
                ('filled', OrderStatus.FILLED),
                ('canceled', OrderStatus.CANCELED),
                ('expired', OrderStatus.EXPIRED),
                ('rejected', OrderStatus.REJECTED),
                ('unknown', OrderStatus.PENDING),  # Unknown maps to pending
            ]

            for alpaca_status, expected in test_cases:
                result = manager._map_alpaca_status(alpaca_status)
                self.assertEqual(result, expected, f"Failed for {alpaca_status}")

    def test_get_pending_count(self):
        """Should return correct pending count."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            # Add some pending orders
            order1 = Order(id='1', ticker='AAPL', side='buy', qty=100,
                          status=OrderStatus.PENDING, submitted_at='2024-01-01')
            order2 = Order(id='2', ticker='TSLA', side='buy', qty=50,
                          status=OrderStatus.PENDING, submitted_at='2024-01-01')

            manager.pending_orders['1'] = order1
            manager.pending_orders['2'] = order2

            self.assertEqual(manager.get_pending_count(), 2)

    def test_get_pending_for_ticker(self):
        """Should return orders for specific ticker."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            order1 = Order(id='1', ticker='AAPL', side='buy', qty=100,
                          status=OrderStatus.PENDING, submitted_at='2024-01-01')
            order2 = Order(id='2', ticker='TSLA', side='buy', qty=50,
                          status=OrderStatus.PENDING, submitted_at='2024-01-01')

            manager.pending_orders['1'] = order1
            manager.pending_orders['2'] = order2

            aapl_orders = manager.get_pending_for_ticker('AAPL')
            self.assertEqual(len(aapl_orders), 1)
            self.assertEqual(aapl_orders[0].ticker, 'AAPL')

    def test_has_pending_order(self):
        """Should check for pending orders by ticker."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            order = Order(id='1', ticker='AAPL', side='buy', qty=100,
                          status=OrderStatus.PENDING, submitted_at='2024-01-01')
            manager.pending_orders['1'] = order

            self.assertTrue(manager.has_pending_order('AAPL'))
            self.assertFalse(manager.has_pending_order('TSLA'))

    def test_get_orders_summary(self):
        """Should return order summary."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            summary = manager.get_orders_summary()

            self.assertIn('pending', summary)
            self.assertIn('filled', summary)
            self.assertIn('queue_size', summary)
            self.assertIn('queue_stats', summary)

    def test_get_queue_status(self):
        """Should return queue status."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            status = manager.get_queue_status()

            self.assertIn('queue_size', status)
            self.assertIn('max_size', status)
            self.assertIn('tps_limit', status)
            self.assertIn('stats', status)
            self.assertIn('worker_alive', status)

    def test_shutdown(self):
        """Should shutdown gracefully."""
        mock_thread = Mock()

        with patch('traderlib.order_manager.threading.Thread', return_value=mock_thread):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            manager.shutdown(wait_for_queue=False)

            self.assertTrue(manager._stop_worker.is_set())
            mock_thread.join.assert_called_once()

    def test_wait_for_queue_empty(self):
        """Should wait for queue to empty."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            # Empty queue should return immediately
            result = manager.wait_for_queue_empty(timeout=1.0)
            self.assertTrue(result)

    def test_wait_for_queue_empty_times_out(self):
        """Should return False on timeout."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            # Mock queue as never empty
            manager.submission_queue = Mock()
            manager.submission_queue.empty.return_value = False

            result = manager.wait_for_queue_empty(timeout=0.01)  # Very short timeout
            self.assertFalse(result)


class TestOrderManagerPersistence(unittest.TestCase):
    """Test OrderManager persistence."""

    def setUp(self):
        """Create mock Alpaca client and temp directory."""
        self.mock_alpaca = Mock()
        self.temp_dir = tempfile.mkdtemp()
        os.environ['PAPER_TRADING_DATA_DIR'] = self.temp_dir

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop('PAPER_TRADING_DATA_DIR', None)

    def test_load_orders_from_file(self):
        """Should load orders from file on init."""
        orders_data = {
            'pending': {
                'order-1': {
                    'id': 'order-1',
                    'ticker': 'AAPL',
                    'side': 'buy',
                    'qty': 100,
                    'status': 'submitted',
                    'submitted_at': '2024-01-01T00:00:00',
                }
            },
            'filled': {}
        }

        orders_file = Path(self.temp_dir) / 'alpaca_orders.json'
        with open(orders_file, 'w') as f:
            json.dump(orders_data, f)

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            self.assertIn('order-1', manager.pending_orders)
            self.assertEqual(manager.pending_orders['order-1'].ticker, 'AAPL')

    def test_save_orders_to_file(self):
        """Should save orders to file."""
        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            order = Order(
                id='order-1',
                ticker='AAPL',
                side='buy',
                qty=100,
                status=OrderStatus.SUBMITTED,
                submitted_at='2024-01-01T00:00:00',
            )
            manager.pending_orders['order-1'] = order

            manager._save_orders()

            orders_file = Path(self.temp_dir) / 'alpaca_orders.json'
            self.assertTrue(orders_file.exists())

            with open(orders_file, 'r') as f:
                data = json.load(f)
            self.assertIn('order-1', data['pending'])


class TestOrderManagerSync(unittest.TestCase):
    """Test position synchronization."""

    def setUp(self):
        """Create mock Alpaca client and temp directory."""
        self.mock_alpaca = Mock()
        self.temp_dir = tempfile.mkdtemp()
        os.environ['PAPER_TRADING_DATA_DIR'] = self.temp_dir

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop('PAPER_TRADING_DATA_DIR', None)

    def test_sync_positions_finds_added(self):
        """Should detect positions in Alpaca but not local."""
        self.mock_alpaca.list_positions.return_value = [
            {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.00'},
        ]

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            local_positions = {}
            result = manager.sync_positions(local_positions)

            self.assertEqual(len(result['added']), 1)
            self.assertEqual(result['added'][0]['ticker'], 'AAPL')

    def test_sync_positions_finds_discrepancies(self):
        """Should detect quantity discrepancies."""
        self.mock_alpaca.list_positions.return_value = [
            {'symbol': 'AAPL', 'qty': '150', 'avg_entry_price': '150.00'},
        ]

        with patch('traderlib.order_manager.threading.Thread'):
            from traderlib.paper_state import Position
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            local_pos = Position(
                ticker='AAPL',
                status='OPEN',
                entry_date='2024-01-01',
                entry_price=150.0,
                shares=100,
                stop_price=140.0,
                target_price=180.0,
                initial_risk=1000.0,
                sector='Technology',
            )

            result = manager.sync_positions({'AAPL': local_pos})

            self.assertEqual(len(result['discrepancies']), 1)
            self.assertEqual(result['discrepancies'][0]['alpaca_qty'], 150)
            self.assertEqual(result['discrepancies'][0]['local_qty'], 100)

    def test_sync_positions_finds_synced(self):
        """Should report synced positions."""
        self.mock_alpaca.list_positions.return_value = [
            {'symbol': 'AAPL', 'qty': '100', 'avg_entry_price': '150.00'},
        ]

        with patch('traderlib.order_manager.threading.Thread'):
            from traderlib.paper_state import Position
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)

            local_pos = Position(
                ticker='AAPL',
                status='OPEN',
                entry_date='2024-01-01',
                entry_price=150.0,
                shares=100,
                stop_price=140.0,
                target_price=180.0,
                initial_risk=1000.0,
                sector='Technology',
            )

            result = manager.sync_positions({'AAPL': local_pos})

            self.assertEqual(len(result['synced']), 1)
            self.assertEqual(result['synced'][0]['ticker'], 'AAPL')


class TestOrderManagerCallbacks(unittest.TestCase):
    """Test order callback functionality."""

    def setUp(self):
        """Create mock Alpaca client and temp directory."""
        self.mock_alpaca = Mock()
        self.temp_dir = tempfile.mkdtemp()
        os.environ['PAPER_TRADING_DATA_DIR'] = self.temp_dir

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop('PAPER_TRADING_DATA_DIR', None)

    def test_callback_invoked_on_direct_submit(self):
        """Callback should be invoked on direct submit."""
        callback_called = []

        def test_callback(order):
            callback_called.append(order)

        self.mock_alpaca.submit_market_order.return_value = {
            'id': 'test-order',
            'status': 'accepted',
        }

        with patch('traderlib.order_manager.threading.Thread'):
            manager = OrderManager(self.mock_alpaca, max_tps=2.0)
            manager.last_submit_time = 0

            manager.submit_entry(
                ticker='AAPL',
                shares=100,
                stop_price=90.0,
                callback=test_callback,
            )

            # Give callback time to execute
            time.sleep(0.1)
            self.assertEqual(len(callback_called), 1)


if __name__ == '__main__':
    unittest.main()
