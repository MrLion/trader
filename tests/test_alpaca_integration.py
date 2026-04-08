#!/usr/bin/env python3
"""Integration tests for Alpaca paper trading engine."""

import asyncio
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from rate_limiter import RateLimiter, APIHealthMonitor
from order_manager import OrderManager, Order, OrderStatus


class MockAlpacaClient:
    """Mock Alpaca client for testing."""

    def __init__(self):
        self.account = {
            'cash': 100000.0,
            'equity': 100000.0,
            'buying_power': 100000.0,
            'status': 'ACTIVE'
        }
        self.positions = {}
        self.orders = {}
        self.order_counter = 0

    def get_account(self):
        return self.account

    def get_latest_price(self, ticker, use_fallback=True):
        # Return mock prices
        prices = {
            'AAPL': 150.0,
            'MSFT': 300.0,
            'GOOGL': 2800.0,
            'SPY': 450.0
        }
        return prices.get(ticker, 100.0)

    def get_historical_bars(self, ticker, days=252, use_fallback=True):
        import pandas as pd
        import numpy as np

        # Generate mock historical data
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        base_price = 100.0

        data = []
        for i, date in enumerate(dates):
            change = np.random.normal(0, 0.02)
            close = base_price * (1 + change)
            high = close * (1 + abs(np.random.normal(0, 0.01)))
            low = close * (1 - abs(np.random.normal(0, 0.01)))
            open_price = close * (1 + np.random.normal(0, 0.005))
            volume = int(np.random.uniform(1000000, 10000000))

            data.append({
                'Open': open_price,
                'High': high,
                'Low': low,
                'Close': close,
                'Volume': volume,
                'Timestamp': date
            })
            base_price = close

        df = pd.DataFrame(data)
        df.set_index('Timestamp', inplace=True)
        return df

    def submit_market_order(self, ticker, shares, side, stop_price=None):
        self.order_counter += 1
        order_id = f"test-order-{self.order_counter}"

        order = {
            'id': order_id,
            'symbol': ticker,
            'qty': float(shares),
            'side': side,
            'type': 'market',
            'status': 'accepted',
            'stop_price': stop_price
        }
        self.orders[order_id] = order

        # Simulate position creation
        if side == 'buy':
            self.positions[ticker] = {
                'symbol': ticker,
                'qty': float(shares),
                'avg_entry_price': self.get_latest_price(ticker),
                'market_value': float(shares) * self.get_latest_price(ticker),
                'current_price': self.get_latest_price(ticker),
                'unrealized_pl': 0.0
            }

        return order

    def get_order(self, order_id):
        order = self.orders.get(order_id)
        if order:
            # Simulate fill after checking
            if order['status'] == 'accepted':
                order['status'] = 'filled'
                order['filled_price'] = self.get_latest_price(order['symbol'])
                order['filled_qty'] = order['qty']
        return order

    def list_positions(self):
        return list(self.positions.values())

    def get_position(self, ticker):
        return self.positions.get(ticker)

    def close_position(self, ticker):
        if ticker in self.positions:
            self.order_counter += 1
            order_id = f"test-order-{self.order_counter}"

            order = {
                'id': order_id,
                'symbol': ticker,
                'qty': self.positions[ticker]['qty'],
                'status': 'filled'
            }
            self.orders[order_id] = order
            del self.positions[ticker]
            return order
        return None


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting functionality."""

    def test_rate_limit_initialization(self):
        """Test rate limiter initializes correctly."""
        limiter = RateLimiter(max_requests=200, window_seconds=60)
        status = limiter.get_status()

        self.assertEqual(status['requests_in_window'], 0)
        self.assertEqual(status['max_requests'], 200)
        self.assertFalse(status['circuit_open'])
        self.assertTrue(status['can_request'])

    def test_rate_limit_tracking(self):
        """Test request tracking."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # Make 5 requests
        for _ in range(5):
            self.assertTrue(limiter.can_make_request())
            limiter.record_request()

        # 6th request should be blocked
        self.assertFalse(limiter.can_make_request())

    def test_error_backoff(self):
        """Test exponential backoff on errors."""
        limiter = RateLimiter()

        # Record errors with rate limit flag
        limiter.record_error(is_rate_limit=True)
        self.assertEqual(limiter.current_delay, 1.0)

        limiter.record_error(is_rate_limit=True)
        self.assertEqual(limiter.current_delay, 2.0)

        limiter.record_error(is_rate_limit=True)
        self.assertEqual(limiter.current_delay, 4.0)

    def test_success_resets_backoff(self):
        """Test successful requests reduce backoff."""
        limiter = RateLimiter()

        limiter.record_error(is_rate_limit=True)
        limiter.record_error(is_rate_limit=True)
        self.assertEqual(limiter.current_delay, 2.0)

        limiter.record_success()
        self.assertEqual(limiter.current_delay, 1.0)

    def test_circuit_breaker(self):
        """Test circuit breaker opens after multiple errors."""
        limiter = RateLimiter()

        # Record 5 requests with errors
        for _ in range(5):
            limiter.record_request()
            limiter.record_error()

        # Circuit should be open
        self.assertTrue(limiter.circuit_open)
        self.assertFalse(limiter.can_make_request())


class TestAPIHealthMonitor(unittest.TestCase):
    """Test API health monitoring."""

    def test_health_initialization(self):
        """Test health monitor initializes correctly."""
        monitor = APIHealthMonitor()
        status = monitor.get_status()

        self.assertEqual(status['primary'], 'alpaca')
        self.assertEqual(status['current'], 'alpaca')
        self.assertTrue(status['providers']['alpaca']['healthy'])

    def test_failure_tracking(self):
        """Test failure tracking."""
        monitor = APIHealthMonitor()

        # Mark some failures
        monitor.mark_failure('alpaca')
        monitor.mark_failure('alpaca')

        # Still healthy (need 3 failures)
        self.assertTrue(monitor.get_status()['providers']['alpaca']['healthy'])

        # Third failure
        monitor.mark_failure('alpaca')
        self.assertFalse(monitor.get_status()['providers']['alpaca']['healthy'])

    def test_recovery(self):
        """Test provider recovery."""
        monitor = APIHealthMonitor()

        # Mark unhealthy
        for _ in range(3):
            monitor.mark_failure('alpaca')

        self.assertFalse(monitor.get_status()['providers']['alpaca']['healthy'])

        # Mark success
        monitor.mark_success('alpaca')
        self.assertTrue(monitor.get_status()['providers']['alpaca']['healthy'])

    def test_fallback_detection(self):
        """Test fallback to healthy provider."""
        monitor = APIHealthMonitor()

        # Mark alpaca unhealthy
        for _ in range(3):
            monitor.mark_failure('alpaca')

        # Should fallback to yfinance
        self.assertTrue(monitor.should_fallback())
        self.assertEqual(monitor.get_provider(), 'yfinance')


class TestOrderManager(unittest.TestCase):
    """Test order management functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_alpaca = MockAlpacaClient()
        self.order_manager = OrderManager(self.mock_alpaca)

    def test_submit_entry(self):
        """Test submitting an entry order."""
        order = self.order_manager.submit_entry('AAPL', shares=100, stop_price=145.0)

        self.assertIsNotNone(order)
        self.assertEqual(order.ticker, 'AAPL')
        self.assertEqual(order.side, 'buy')
        self.assertEqual(order.qty, 100)
        self.assertEqual(order.stop_price, 145.0)
        self.assertEqual(order.status, OrderStatus.SUBMITTED)

    def test_submit_exit(self):
        """Test submitting an exit order."""
        # First create a position
        self.order_manager.submit_entry('AAPL', shares=100, stop_price=145.0)

        # Then exit
        order = self.order_manager.submit_exit('AAPL', shares=100, reason='STOP_HIT')

        self.assertIsNotNone(order)
        self.assertEqual(order.ticker, 'AAPL')
        self.assertEqual(order.side, 'sell')
        self.assertEqual(order.reason, 'STOP_HIT')

    def test_duplicate_prevention(self):
        """Test duplicate order prevention."""
        self.order_manager.submit_entry('AAPL', shares=100, stop_price=145.0)

        # Should detect pending order
        self.assertTrue(self.order_manager.has_pending_order('AAPL'))

    def test_order_status_checking(self):
        """Test order status checking."""
        order = self.order_manager.submit_entry('AAPL', shares=100, stop_price=145.0)

        # Check status (should update to filled)
        updated = self.order_manager.check_order_status(order.id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, OrderStatus.FILLED)
        self.assertIsNotNone(updated.filled_price)
        self.assertIsNotNone(updated.filled_qty)

    def test_position_sync(self):
        """Test position synchronization."""
        # Create a position in mock Alpaca
        self.mock_alpaca.submit_market_order('MSFT', 50, 'buy')

        # Sync with empty local positions
        local_positions = {}
        result = self.order_manager.sync_positions(local_positions)

        self.assertEqual(len(result['added']), 1)
        self.assertEqual(result['added'][0]['ticker'], 'MSFT')
        self.assertEqual(result['added'][0]['qty'], 50)

    def test_get_orders_summary(self):
        """Test order summary."""
        # Submit some orders
        self.order_manager.submit_entry('AAPL', shares=100, stop_price=145.0)
        self.order_manager.submit_entry('MSFT', shares=50, stop_price=295.0)

        summary = self.order_manager.get_orders_summary()

        self.assertEqual(summary['pending'], 2)
        self.assertEqual(len(summary['pending_tickers']), 2)


def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("🧪 ALPACA INTEGRATION TESTS")
    print("=" * 60)
    print()

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIHealthMonitor))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderManager))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
