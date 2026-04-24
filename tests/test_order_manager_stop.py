#!/usr/bin/env python3
"""Tests for OrderManager stop-entry and limit order support (Phase 3)."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from traderlib.order_manager import OrderManager, Order, OrderStatus, QueuedOrder
from traderlib.alpaca_client import AlpacaClient


class TestOrderManagerStopEntry(unittest.TestCase):
    """Test submit_stop_entry method."""

    def setUp(self):
        """Set up mocked OrderManager."""
        self.mock_alpaca = Mock(spec=AlpacaClient)
        self.mock_alpaca.submit_stop_order = Mock(return_value={
            'id': 'stop-123',
            'symbol': 'AAPL',
            'qty': 100.0,
            'side': 'buy',
            'type': 'stop',
            'status': 'accepted',
            'stop_price': 155.0
        })
        self.mock_alpaca.cancel_order = Mock(return_value=True)

        with patch.dict('os.environ', {'PAPER_TRADING_DATA_DIR': tempfile.gettempdir()}):
            with patch('traderlib.order_manager.threading.Thread'):
                self.om = OrderManager(self.mock_alpaca)
                self.om.pending_orders = {}
                self.om.filled_orders = {}

    def test_submit_stop_entry_direct(self):
        """Test direct stop-entry submission."""
        result = self.om.submit_stop_entry(
            ticker='AAPL',
            shares=100,
            trigger_price=155.0,
            stop_price=140.0,
            target_price=170.0,
            sector='Technology',
            expected_entry_price=150.0,
            pivot_type='vcp',
            entry_mode='breakout'
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.ticker, 'AAPL')
        self.assertEqual(result.side, 'buy')
        self.assertEqual(result.qty, 100)
        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertEqual(result.stop_price, 140.0)
        self.assertEqual(result.target_price, 170.0)
        self.assertEqual(result.sector, 'Technology')
        self.assertEqual(result.expected_entry_price, 150.0)
        self.assertEqual(result.pivot_type, 'vcp')
        self.assertEqual(result.entry_mode, 'breakout')
        self.assertEqual(result.trigger_price, 155.0)
        self.assertEqual(result.order_type, 'stop_entry')
        self.mock_alpaca.submit_stop_order.assert_called_once_with('AAPL', 100, 155.0, 'buy')

    def test_submit_stop_entry_fallback_when_sdk_unavailable(self):
        """Test fallback when SDK doesn't support stop orders."""
        self.mock_alpaca.submit_stop_order.return_value = None

        result = self.om.submit_stop_entry(
            ticker='AAPL',
            shares=100,
            trigger_price=155.0,
            stop_price=140.0
        )

        self.assertIsNone(result)
        self.mock_alpaca.submit_stop_order.assert_called_once()

    def test_cancel_stop_entry(self):
        """Test cancelling stop-entry orders for a ticker."""
        # Add a pending stop-entry order
        order = Order(
            id='stop-123',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=140.0,
            trigger_price=155.0,
            entry_mode='breakout',
            pivot_type='vcp',
            order_type='stop_entry'
        )
        self.om.pending_orders['stop-123'] = order

        result = self.om.cancel_stop_entry('AAPL')

        self.assertTrue(result)
        self.mock_alpaca.cancel_order.assert_called_once_with('stop-123')
        self.assertNotIn('stop-123', self.om.pending_orders)
        self.assertIn('stop-123', self.om.filled_orders)
        self.assertEqual(self.om.filled_orders['stop-123'].status, OrderStatus.CANCELED)

    def test_cancel_stop_entry_no_matching_orders(self):
        """Test cancelling when no stop-entry orders exist for ticker."""
        result = self.om.cancel_stop_entry('TSLA')
        self.assertFalse(result)
        self.mock_alpaca.cancel_order.assert_not_called()

    def test_cancel_stop_entry_skips_non_stop_entry(self):
        """Test that non-stop-entry orders are not cancelled."""
        order = Order(
            id='market-123',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=140.0,
            order_type='entry'
        )
        self.om.pending_orders['market-123'] = order

        result = self.om.cancel_stop_entry('AAPL')

        self.assertFalse(result)
        self.mock_alpaca.cancel_order.assert_not_called()
        self.assertIn('market-123', self.om.pending_orders)

    def test_cancel_stop_entry_alpaca_refuses(self):
        """Test that local state is NOT mutated when Alpaca refuses cancel."""
        order = Order(
            id='stop-123',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            stop_price=140.0,
            trigger_price=155.0,
            entry_mode='breakout',
            pivot_type='vcp',
            order_type='stop_entry'
        )
        self.om.pending_orders['stop-123'] = order
        self.mock_alpaca.cancel_order.return_value = False

        result = self.om.cancel_stop_entry('AAPL')

        self.assertFalse(result)
        self.assertIn('stop-123', self.om.pending_orders)
        self.assertNotIn('stop-123', self.om.filled_orders)
        self.assertEqual(self.om.pending_orders['stop-123'].status, OrderStatus.SUBMITTED)

    def test_submit_stop_entry_invalid_price(self):
        """Test that trigger_price <= stop_price raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.om.submit_stop_entry(
                ticker='AAPL',
                shares=100,
                trigger_price=140.0,
                stop_price=155.0
            )
        self.assertIn('trigger_price', str(ctx.exception))
        self.mock_alpaca.submit_stop_order.assert_not_called()

    def test_stop_entry_queued_when_rate_limited(self):
        """Test stop-entry is queued when TPS limit reached."""
        # Force queue by making _can_submit_directly return False
        with patch.object(self.om, '_can_submit_directly', return_value=False):
            result = self.om.submit_stop_entry(
                ticker='AAPL',
                shares=100,
                trigger_price=155.0,
                stop_price=140.0,
                pivot_type='vcp',
                entry_mode='breakout'
            )

        self.assertIsNone(result)
        self.mock_alpaca.submit_stop_order.assert_not_called()

    def test_queued_stop_entry_executed_by_worker(self):
        """Test that queued stop-entry orders are processed by worker thread."""
        with patch.object(self.om, '_can_submit_directly', return_value=False):
            self.om.submit_stop_entry(
                ticker='AAPL',
                shares=100,
                trigger_price=155.0,
                stop_price=140.0,
                pivot_type='vcp',
                entry_mode='breakout'
            )

        # Manually process queue
        priority, queued = self.om.submission_queue.get_nowait()
        self.om._execute_queued_order(queued)

        self.mock_alpaca.submit_stop_order.assert_called_once_with('AAPL', 100, 155.0, 'buy')


class TestAlpacaClientStopOrder(unittest.TestCase):
    """Test AlpacaClient.submit_stop_order."""

    @patch('traderlib.alpaca_client.TradingClient')
    @patch('traderlib.alpaca_client.StockHistoricalDataClient')
    def test_submit_stop_order_success(self, mock_data_client, mock_trading_client):
        """Test successful stop order submission."""
        mock_order = Mock()
        mock_order.id = 'stop-456'
        mock_order.symbol = 'AAPL'
        mock_order.qty = '100'
        mock_order.side.value = 'buy'
        mock_order.order_type.value = 'stop'
        mock_order.status.value = 'accepted'
        mock_order.stop_price = 155.0

        mock_trading_instance = Mock()
        mock_trading_instance.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading_instance

        with patch.dict('os.environ', {
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret'
        }):
            client = AlpacaClient(mode='paper')
            result = client.submit_stop_order('AAPL', 100, 155.0, 'buy')

        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 'stop-456')
        self.assertEqual(result['symbol'], 'AAPL')
        self.assertEqual(result['type'], 'stop')
        self.assertEqual(result['stop_price'], 155.0)

    @patch('traderlib.alpaca_client.TradingClient')
    @patch('traderlib.alpaca_client.StockHistoricalDataClient')
    def test_submit_limit_order_success(self, mock_data_client, mock_trading_client):
        """Test successful limit order submission."""
        mock_order = Mock()
        mock_order.id = 'limit-789'
        mock_order.symbol = 'AAPL'
        mock_order.qty = '100'
        mock_order.side.value = 'buy'
        mock_order.order_type.value = 'limit'
        mock_order.status.value = 'accepted'
        mock_order.limit_price = 150.0

        mock_trading_instance = Mock()
        mock_trading_instance.submit_order.return_value = mock_order
        mock_trading_client.return_value = mock_trading_instance

        with patch.dict('os.environ', {
            'ALPACA_API_KEY': 'test_key',
            'ALPACA_SECRET_KEY': 'test_secret'
        }):
            client = AlpacaClient(mode='paper')
            result = client.submit_limit_order('AAPL', 100, 150.0, 'buy')

        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 'limit-789')
        self.assertEqual(result['type'], 'limit')
        self.assertEqual(result['limit_price'], 150.0)

    @patch('traderlib.alpaca_client.TradingClient')
    @patch('traderlib.alpaca_client.StockHistoricalDataClient')
    def test_submit_stop_order_auth_failure(self, mock_data_client, mock_trading_client):
        """Test stop order auth failure handling."""
        from alpaca.common.exceptions import APIError

        mock_trading_instance = Mock()
        http_error = Mock()
        http_error.response.status_code = 401
        error = APIError('{"message": "Unauthorized"}', http_error=http_error)
        mock_trading_instance.submit_order.side_effect = error
        mock_trading_client.return_value = mock_trading_instance

        with patch.dict('os.environ', {
            'ALPACA_API_KEY': 'bad_key',
            'ALPACA_SECRET_KEY': 'bad_secret'
        }):
            client = AlpacaClient(mode='paper')
            result = client.submit_stop_order('AAPL', 100, 155.0, 'buy')

        self.assertIsNone(result)

    def test_stop_order_available_guard(self):
        """Test that STOP_ORDER_AVAILABLE guard is True for current SDK."""
        from traderlib.alpaca_client import STOP_ORDER_AVAILABLE
        self.assertTrue(STOP_ORDER_AVAILABLE)

    def test_limit_order_available_guard(self):
        """Test that LIMIT_ORDER_AVAILABLE guard is True for current SDK."""
        from traderlib.alpaca_client import LIMIT_ORDER_AVAILABLE
        self.assertTrue(LIMIT_ORDER_AVAILABLE)


class TestOrderTelemetry(unittest.TestCase):
    """Test telemetry fields on Order dataclass."""

    def test_order_has_telemetry_fields(self):
        """Test Order dataclass includes telemetry fields."""
        order = Order(
            id='test-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            pivot_type='vcp',
            entry_mode='breakout',
            trigger_price=155.0
        )

        self.assertEqual(order.pivot_type, 'vcp')
        self.assertEqual(order.entry_mode, 'breakout')
        self.assertEqual(order.trigger_price, 155.0)

    def test_order_to_dict_includes_telemetry(self):
        """Test Order.to_dict serializes telemetry fields."""
        order = Order(
            id='test-1',
            ticker='AAPL',
            side='buy',
            qty=100,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now().isoformat(),
            pivot_type='range_20d',
            entry_mode='immediate',
            trigger_price=155.0,
            order_type='stop_entry'
        )

        d = order.to_dict()
        self.assertEqual(d['pivot_type'], 'range_20d')
        self.assertEqual(d['entry_mode'], 'immediate')
        self.assertEqual(d['trigger_price'], 155.0)
        self.assertEqual(d['order_type'], 'stop_entry')

    def test_order_from_dict_preserves_telemetry(self):
        """Test Order.from_dict restores telemetry fields."""
        data = {
            'id': 'test-1',
            'ticker': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'status': 'submitted',
            'submitted_at': datetime.now().isoformat(),
            'pivot_type': 'vcp',
            'entry_mode': 'breakout',
            'trigger_price': 155.0,
            'order_type': 'stop_entry'
        }

        order = Order.from_dict(data)
        self.assertEqual(order.pivot_type, 'vcp')
        self.assertEqual(order.entry_mode, 'breakout')
        self.assertEqual(order.trigger_price, 155.0)
        self.assertEqual(order.order_type, 'stop_entry')

    def test_order_from_dict_backward_compat_no_order_type(self):
        """Test Order.from_dict handles old persisted orders without order_type."""
        data = {
            'id': 'test-1',
            'ticker': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'status': 'submitted',
            'submitted_at': datetime.now().isoformat(),
            'stop_price': 140.0,
        }

        order = Order.from_dict(data)
        self.assertIsNone(order.order_type)
        self.assertIsNone(order.pivot_type)
        self.assertIsNone(order.entry_mode)

    def test_order_post_init_invalid_side(self):
        """Test Order.__post_init__ rejects invalid side values."""
        with self.assertRaises(ValueError) as ctx:
            Order(
                id='test-1',
                ticker='AAPL',
                side='hold',
                qty=100,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.now().isoformat()
            )
        self.assertIn("side must be 'buy' or 'sell'", str(ctx.exception))

    def test_order_post_init_stop_entry_requires_trigger(self):
        """Test Order.__post_init__ rejects stop_entry without trigger_price."""
        with self.assertRaises(ValueError) as ctx:
            Order(
                id='test-1',
                ticker='AAPL',
                side='buy',
                qty=100,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.now().isoformat(),
                order_type='stop_entry'
            )
        self.assertIn("stop_entry orders must have trigger_price", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
