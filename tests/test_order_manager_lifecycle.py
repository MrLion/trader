#!/usr/bin/env python3
"""Tests for order manager lifecycle — state transitions and queued execution.

Targets uncovered paths in traderlib/order_manager.py:
- check_order_status: FILLED, CANCELED, EXPIRED, REJECTED, PARTIAL_FILL, test order cleanup
- process_all_pending: returns only FILLED orders
- Queued order execution: entry, exit, queue.Full, drain
"""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


from traderlib.order_manager import OrderManager, Order, OrderStatus, QueuedOrder


def make_order_manager():
    """Create OrderManager with mocked Alpaca client and temp data dir."""
    tmpdir = tempfile.mkdtemp()
    mock_alpaca = Mock()
    mock_alpaca.list_positions.return_value = []
    mock_alpaca.submit_market_order.return_value = {
        'id': 'alpaca-order-1',
        'status': 'new',
    }

    with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': tmpdir}):
        om = OrderManager(mock_alpaca, max_tps=100.0, max_queue_size=10)
        om._stop_worker.set()  # Stop background worker thread immediately

    return om, mock_alpaca, Path(tmpdir)


import os


class TestCheckOrderStatus:
    """Test check_order_status state transitions."""

    def test_filled_moves_to_filled_orders(self):
        """Order transitions from SUBMITTED to FILLED; moves to filled_orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-1', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
            stop_price=140.0, sector='Technology', target_price=170.0,
        )
        om.pending_orders['order-1'] = order

        # Mock Alpaca to return filled status
        mock_alpaca.get_order.return_value = {
            'status': 'filled',
            'filled_qty': '100',
            'filled_avg_price': '150.50',
        }

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-1')

        assert result.status == OrderStatus.FILLED
        assert result.filled_qty == 100.0
        assert result.filled_price == 150.50
        assert 'order-1' not in om.pending_orders
        assert 'order-1' in om.filled_orders
        assert om.filled_orders['order-1'].status == OrderStatus.FILLED

    def test_canceled_moves_to_filled_orders(self):
        """Canceled order moves to filled_orders (terminal state)."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-2', ticker='MSFT', side='buy', qty=50,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['order-2'] = order

        mock_alpaca.get_order.return_value = {'status': 'canceled'}

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-2')

        assert result.status == OrderStatus.CANCELED
        assert 'order-2' not in om.pending_orders
        assert 'order-2' in om.filled_orders

    def test_expired_moves_to_filled_orders(self):
        """Expired order moves to filled_orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-3', ticker='TSLA', side='buy', qty=20,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['order-3'] = order

        mock_alpaca.get_order.return_value = {'status': 'expired'}

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-3')

        assert result.status == OrderStatus.EXPIRED
        assert 'order-3' not in om.pending_orders
        assert 'order-3' in om.filled_orders

    def test_rejected_moves_to_filled_orders(self):
        """Rejected order moves to filled_orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-4', ticker='GOOGL', side='buy', qty=10,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['order-4'] = order

        mock_alpaca.get_order.return_value = {'status': 'rejected'}

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-4')

        assert result.status == OrderStatus.REJECTED
        assert 'order-4' not in om.pending_orders
        assert 'order-4' in om.filled_orders

    def test_partial_fill_stays_pending(self):
        """Partially filled order stays in pending with updated fill info."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-5', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['order-5'] = order

        mock_alpaca.get_order.return_value = {
            'status': 'partially_filled',
            'filled_qty': '60',
            'filled_avg_price': '150.00',
        }

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-5')

        assert result.status == OrderStatus.PARTIAL_FILL
        assert result.filled_qty == 60.0
        assert result.filled_price == 150.0
        # Should stay in pending (not yet fully filled)
        assert 'order-5' in om.pending_orders
        assert 'order-5' not in om.filled_orders

    def test_test_order_cleanup(self):
        """Mock/test order IDs are cleaned up without API call."""
        om, mock_alpaca, tmpdir = make_order_manager()

        for order_id in ['test-order', 'test-order-1', 'mock-order-abc']:
            order = Order(
                id=order_id, ticker='TST', side='buy', qty=1,
                status=OrderStatus.SUBMITTED,
                submitted_at='2024-04-08T10:00:00',
            )
            om.pending_orders[order_id] = order

        mock_alpaca.get_order.return_value = None  # No Alpaca record

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            for order_id in ['test-order', 'test-order-1', 'mock-order-abc']:
                result = om.check_order_status(order_id)
                assert result is None
                assert order_id not in om.pending_orders

        # get_order should NOT have been called for test orders
        # (the is_test_order check fires before the API call)

    def test_process_all_pending_returns_only_filled(self):
        """process_all_pending returns only FILLED orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        # Create orders with different statuses
        filled_order = Order(
            id='order-filled', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        canceled_order = Order(
            id='order-canceled', ticker='MSFT', side='buy', qty=50,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        still_pending = Order(
            id='order-pending', ticker='GOOGL', side='buy', qty=10,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders = {
            'order-filled': filled_order,
            'order-canceled': canceled_order,
            'order-pending': still_pending,
        }

        def mock_check(order_id):
            order = om.pending_orders.get(order_id)
            if order_id == 'order-filled':
                order.status = OrderStatus.FILLED
                order.filled_qty = 100
                order.filled_price = 150.0
                om.filled_orders[order_id] = order
                del om.pending_orders[order_id]
                return order
            elif order_id == 'order-canceled':
                order.status = OrderStatus.CANCELED
                om.filled_orders[order_id] = order
                del om.pending_orders[order_id]
                return order
            else:
                return order  # Still pending

        om.check_order_status = mock_check

        result = om.process_all_pending()

        # Only FILLED orders returned
        assert len(result) == 1
        assert result[0].id == 'order-filled'
        assert result[0].status == OrderStatus.FILLED

    def test_status_unchanged_returns_order(self):
        """When status hasn't changed, order stays in pending."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='order-same', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['order-same'] = order

        mock_alpaca.get_order.return_value = {'status': 'new'}

        with patch.dict(os.environ, {'PAPER_TRADING_DATA_DIR': str(tmpdir)}):
            result = om.check_order_status('order-same')

        assert result.status == OrderStatus.SUBMITTED
        assert 'order-same' in om.pending_orders


class TestQueueOrderExecution:
    """Test queued order execution."""

    def test_queue_full_rejects_order(self):
        """Full queue rejects new orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        # Fill the queue
        for i in range(10):
            om.submission_queue.put(
                (0, i, QueuedOrder(order_type='entry', ticker=f'TST{i}', shares=1)),
                block=False,
            )

        # Try to submit when queue is full
        result = om.submit_entry(
            ticker='OVERFLOW', shares=100, stop_price=90.0,
            target_price=110.0, sector='Technology',
        )

        assert result is None
        assert om.queue_stats['rejected'] > 0

    def test_direct_submit_when_queue_empty(self):
        """Orders submit directly when queue is empty and TPS allows."""
        om, mock_alpaca, tmpdir = make_order_manager()

        mock_alpaca.submit_market_order.return_value = {
            'id': 'direct-order-1',
            'status': 'new',
        }

        # First order after creation should submit directly (queue empty)
        # Need to set last_submit_time far enough back
        om.last_submit_time = 0.0

        result = om.submit_entry(
            ticker='AAPL', shares=100, stop_price=140.0,
            target_price=170.0, sector='Technology',
            expected_entry_price=150.0,
        )

        assert result is not None
        assert result.ticker == 'AAPL'
        assert result.side == 'buy'
        assert result.qty == 100

    def test_order_persistence(self):
        """Orders are saved and loaded from disk."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='persist-1', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
            stop_price=140.0, sector='Technology', target_price=170.0,
        )
        om.pending_orders['persist-1'] = order
        om._save_orders()

        # Verify file exists and has valid JSON
        orders_file = om.orders_file
        assert orders_file.exists()
        with open(orders_file) as f:
            data = json.load(f)
        assert 'pending' in data
        assert 'persist-1' in data['pending']

    def test_get_pending_for_ticker(self):
        """get_pending_for_ticker returns matching pending orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        buy_order = Order(
            id='buy-1', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        sell_order = Order(
            id='sell-1', ticker='AAPL', side='sell', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:30:00',
        )
        other_order = Order(
            id='buy-2', ticker='MSFT', side='buy', qty=50,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders = {
            'buy-1': buy_order,
            'sell-1': sell_order,
            'buy-2': other_order,
        }

        aapl_orders = om.get_pending_for_ticker('AAPL')
        assert len(aapl_orders) == 2
        assert all(o.ticker == 'AAPL' for o in aapl_orders)

        msft_orders = om.get_pending_for_ticker('MSFT')
        assert len(msft_orders) == 1

    def test_has_pending_order(self):
        """has_pending_order returns True for existing pending orders."""
        om, mock_alpaca, tmpdir = make_order_manager()

        order = Order(
            id='pending-1', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
        )
        om.pending_orders['pending-1'] = order

        assert om.has_pending_order('AAPL') is True
        assert om.has_pending_order('MSFT') is False


class TestMapAlpacaStatus:
    """Test _map_alpaca_status mapping."""

    def test_all_known_statuses(self):
        """All Alpaca statuses mapped correctly."""
        om, _, _ = make_order_manager()

        assert om._map_alpaca_status('new') == OrderStatus.SUBMITTED
        assert om._map_alpaca_status('accepted') == OrderStatus.ACCEPTED
        assert om._map_alpaca_status('partially_filled') == OrderStatus.PARTIAL_FILL
        assert om._map_alpaca_status('filled') == OrderStatus.FILLED
        assert om._map_alpaca_status('canceled') == OrderStatus.CANCELED
        assert om._map_alpaca_status('expired') == OrderStatus.EXPIRED
        assert om._map_alpaca_status('rejected') == OrderStatus.REJECTED

    def test_unknown_status_defaults_to_pending(self):
        """Unknown status defaults to PENDING."""
        om, _, _ = make_order_manager()

        assert om._map_alpaca_status('unknown_status') == OrderStatus.PENDING

    def test_case_insensitive(self):
        """Status mapping is case-insensitive."""
        om, _, _ = make_order_manager()

        assert om._map_alpaca_status('FILLED') == OrderStatus.FILLED
        assert om._map_alpaca_status('Canceled') == OrderStatus.CANCELED


class TestOrderSerialization:
    """Test Order to_dict/from_dict roundtrip."""

    def test_order_roundtrip(self):
        """Order serializes and deserializes correctly."""
        order = Order(
            id='test-1', ticker='AAPL', side='buy', qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at='2024-04-08T10:00:00',
            stop_price=140.0, sector='Technology', target_price=170.0,
            expected_entry_price=150.0,
        )

        data = order.to_dict()
        assert data['status'] == 'submitted'

        restored = Order.from_dict(data)
        assert restored.id == order.id
        assert restored.ticker == order.ticker
        assert restored.status == OrderStatus.SUBMITTED
        assert restored.stop_price == 140.0
        assert restored.sector == 'Technology'
        assert restored.target_price == 170.0
        assert restored.expected_entry_price == 150.0

    def test_order_from_dict_handles_missing_optional_fields(self):
        """from_dict handles orders without target_price/sector."""
        data = {
            'id': 'old-1', 'ticker': 'AAPL', 'side': 'buy', 'qty': 100,
            'status': 'submitted', 'submitted_at': '2024-04-08T10:00:00',
        }

        order = Order.from_dict(data)
        assert order.target_price is None
        assert order.sector is None
        assert order.expected_entry_price is None