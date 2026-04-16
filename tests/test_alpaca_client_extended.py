#!/usr/bin/env python3
"""Extended tests for AlpacaClient to improve coverage.

Tests additional code paths:
- Rate limiter integration
- yfinance fallback paths
- WebSocket lifecycle
- Config loading
- Error handling branches
"""

import asyncio
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from traderlib.rate_limiter import RateLimiter


class MockAlpacaAccount:
    """Mock Alpaca account response."""
    def __init__(self):
        self.id = 'test-account-123'
        self.cash = 100000.0
        self.portfolio_value = 100000.0
        self.equity = 100000.0
        self.buying_power = 200000.0
        self.status = 'ACTIVE'
        self.currency = 'USD'


class MockAlpacaOrder:
    """Mock Alpaca order response."""
    def __init__(self, order_id='test-order-123'):
        self.id = order_id
        self.symbol = 'AAPL'
        self.qty = '100'
        self.side = Mock()
        self.side.value = 'buy'
        self.order_type = Mock()
        self.order_type.value = 'market'
        self.status = Mock()
        self.status.value = 'filled'
        self.filled_qty = '100'
        self.filled_avg_price = '150.0'
        self.stop_price = None


class MockAlpacaPosition:
    """Mock Alpaca position response."""
    def __init__(self):
        self.symbol = 'AAPL'
        self.qty = '100'
        self.avg_entry_price = '145.0'
        self.market_value = '15000.0'
        self.current_price = '150.0'
        self.unrealized_pl = '500.0'
        self.unrealized_plpc = '0.034'
        self.change_today = '10.0'


class TestAlpacaClientConfig(unittest.TestCase):
    """Test config loading methods."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test-key', 'ALPACA_SECRET_KEY': 'test-secret'})
    def test_load_config_from_env(self):
        """Test loading config from environment variables."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            client = AlpacaClient(mode='paper')
            self.assertEqual(client.api_key, 'test-key')
            self.assertEqual(client.secret_key, 'test-secret')

    @patch.dict('os.environ', {}, clear=True)
    @patch.dict('os.environ', {}, clear=True)
    def test_load_config_from_file(self):
        """Test loading config from file when env vars not set."""
        import tempfile
        from traderlib.alpaca_client import AlpacaClient, CONFIG_FILE

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / 'config'
            config_dir.mkdir(parents=True)
            config_file = config_dir / 'alpaca_config.json'

            config_file.write_text(json.dumps({
                'paper': {'api_key': 'file-key', 'secret_key': 'file-secret'},
                'historical_days': 200
            }))

            with patch('traderlib.alpaca_client.CONFIG_FILE', config_file), \
                 patch('traderlib.alpaca_client.TradingClient'), \
                 patch('traderlib.alpaca_client.StockHistoricalDataClient'):
                client = AlpacaClient(mode='paper')
                self.assertEqual(client.api_key, 'file-key')
                self.assertEqual(client.secret_key, 'file-secret')
                self.assertEqual(client.historical_days, 200)

    @patch.dict('os.environ', {}, clear=True)
    def test_load_config_missing(self):
        """Test error when config is missing."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('traderlib.alpaca_client.CONFIG_FILE', Path('/nonexistent/config.json')):
            with self.assertRaises(ValueError) as ctx:
                AlpacaClient(mode='paper')
            self.assertIn('API keys not configured', str(ctx.exception))

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def test_load_config_int_default(self):
        """Test loading integer config with default value."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'), \
             patch('alpaca_client.CONFIG_FILE', Path('/nonexistent')):
            client = AlpacaClient(mode='paper')
            # Should use default when config file doesn't exist
            self.assertEqual(client.historical_days, 365)


class TestAlpacaClientRateLimiter(unittest.TestCase):
    """Test rate limiter integration."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient') as mock_trading, \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.mock_trading = mock_trading
            self.client = AlpacaClient(mode='paper')

    def test_rate_limiter_blocks_request(self):
        """Test that rate limiter blocks requests when at limit."""
        # Fill up rate limiter
        for _ in range(200):
            self.client.rate_limiter.record_request()

        # Should not be able to make request
        self.assertFalse(self.client.rate_limiter.can_make_request())

    def test_rate_limiter_clears_old_requests(self):
        """Test that old requests are cleared from window."""
        from datetime import datetime, timedelta

        # Add old request
        old_time = datetime.now() - timedelta(seconds=120)
        self.client.rate_limiter.requests.append(old_time)

        # Should be cleaned up
        self.client.rate_limiter._clean_old_requests()
        self.assertEqual(len(self.client.rate_limiter.requests), 0)

    def test_get_account_rate_limited(self):
        """Test get_account when rate limited."""
        # Fill rate limiter
        for _ in range(200):
            self.client.rate_limiter.record_request()

        with patch.object(self.client.rate_limiter, 'get_wait_time', return_value=0.1):
            with patch.object(self.client.trading_client, 'get_account', return_value=MockAlpacaAccount()):
                with patch('time.sleep') as mock_sleep:
                    account = self.client.get_account()
                    mock_sleep.assert_called_once()
                    self.assertIsNotNone(account)


class TestAlpacaClientFallbacks(unittest.TestCase):
    """Test yfinance fallback functionality."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.client = AlpacaClient(mode='paper')

class TestAlpacaClientOrderMethods(unittest.TestCase):
    """Test order submission and management."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient') as mock_trading, \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.mock_trading = mock_trading
            self.client = AlpacaClient(mode='paper')
            self.client.trading_client = mock_trading.return_value

    def test_submit_market_order_rate_limited(self):
        """Test order submission when rate limited."""
        # Fill rate limiter
        for _ in range(200):
            self.client.rate_limiter.record_request()

        with patch('time.sleep'):
            with patch.object(self.client.trading_client, 'submit_order', return_value=MockAlpacaOrder()):
                order = self.client.submit_market_order('AAPL', 100, 'buy')
                # Should wait and then submit
                self.assertIsNotNone(order)

    def test_submit_market_order_with_stop(self):
        """Test order submission with stop loss."""
        mock_order = MockAlpacaOrder()
        mock_order.stop_price = 140.0

        with patch.object(self.client.trading_client, 'submit_order', return_value=mock_order):
            order = self.client.submit_market_order('AAPL', 100, 'buy', stop_price=140.0)
            self.assertIsNotNone(order)
            self.assertEqual(order['stop_price'], 140.0)

    def test_submit_market_order_sell(self):
        """Test sell order submission."""
        mock_order = MockAlpacaOrder()
        mock_order.side.value = 'sell'

        with patch.object(self.client.trading_client, 'submit_order', return_value=mock_order):
            order = self.client.submit_market_order('AAPL', 100, 'sell')
            self.assertIsNotNone(order)
            self.assertEqual(order['side'], 'sell')

    def test_submit_market_order_api_error(self):
        """Test order submission when API returns error."""
        from alpaca.common.exceptions import APIError

        # Create proper APIError with status_code
        error = APIError('Rate limit exceeded', 429)

        with patch.object(self.client.trading_client, 'submit_order', side_effect=error):
            order = self.client.submit_market_order('AAPL', 100, 'buy')
            self.assertIsNone(order)

    def test_get_order_success(self):
        """Test getting order by ID."""
        mock_order = MockAlpacaOrder()
        mock_order.filled_avg_price = '150.0'

        with patch.object(self.client.trading_client, 'get_order_by_id', return_value=mock_order):
            order = self.client.get_order('test-order-123')
            self.assertIsNotNone(order)
            self.assertEqual(order['id'], 'test-order-123')
            self.assertEqual(order['filled_price'], 150.0)

    def test_get_order_failure(self):
        """Test getting order when it doesn't exist."""
        with patch.object(self.client.trading_client, 'get_order_by_id', side_effect=Exception('Not found')):
            order = self.client.get_order('nonexistent')
            self.assertIsNone(order)

    def test_list_positions_success(self):
        """Test listing positions."""
        with patch.object(self.client.trading_client, 'get_all_positions', return_value=[MockAlpacaPosition()]):
            positions = self.client.list_positions()
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0]['symbol'], 'AAPL')

    def test_list_positions_failure(self):
        """Test listing positions when API fails."""
        with patch.object(self.client.trading_client, 'get_all_positions', side_effect=Exception('API error')):
            positions = self.client.list_positions()
            self.assertEqual(len(positions), 0)

    def test_get_position_success(self):
        """Test getting specific position."""
        with patch.object(self.client.trading_client, 'get_open_position', return_value=MockAlpacaPosition()):
            position = self.client.get_position('AAPL')
            self.assertIsNotNone(position)
            self.assertEqual(position['symbol'], 'AAPL')

    def test_get_position_failure(self):
        """Test getting position when not found."""
        with patch.object(self.client.trading_client, 'get_open_position', side_effect=Exception('Not found')):
            position = self.client.get_position('AAPL')
            self.assertIsNone(position)

    def test_close_position_success(self):
        """Test closing position."""
        mock_order = MockAlpacaOrder()

        with patch.object(self.client.trading_client, 'close_position', return_value=mock_order):
            result = self.client.close_position('AAPL')
            self.assertIsNotNone(result)

    def test_close_position_failure(self):
        """Test closing position when it fails."""
        with patch.object(self.client.trading_client, 'close_position', side_effect=Exception('No position')):
            result = self.client.close_position('AAPL')
            self.assertIsNone(result)

    def test_cancel_all_orders_success(self):
        """Test cancelling all orders."""
        with patch.object(self.client.trading_client, 'cancel_orders', return_value=None):
            result = self.client.cancel_all_orders()
            self.assertTrue(result)

    def test_cancel_all_orders_failure(self):
        """Test cancelling all orders when it fails."""
        with patch.object(self.client.trading_client, 'cancel_orders', side_effect=Exception('API error')):
            result = self.client.cancel_all_orders()
            self.assertFalse(result)


class TestAlpacaClientWebSocket(unittest.TestCase):
    """Test WebSocket functionality."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.client = AlpacaClient(mode='paper')

    def test_is_ws_healthy_no_connection(self):
        """Test WebSocket health check when not connected."""
        self.client.ws_connected = False
        self.assertFalse(self.client.is_ws_healthy())

    def test_is_ws_healthy_no_message(self):
        """Test WebSocket health when no message received."""
        self.client.ws_connected = True
        self.client.last_ws_message = None
        self.assertFalse(self.client.is_ws_healthy())

    def test_is_ws_healthy_stale(self):
        """Test WebSocket health when messages are stale."""
        self.client.ws_connected = True
        self.client.last_ws_message = datetime.now() - timedelta(seconds=120)
        self.assertFalse(self.client.is_ws_healthy())

    def test_is_ws_healthy_fresh(self):
        """Test WebSocket health with recent messages."""
        self.client.ws_connected = True
        self.client.last_ws_message = datetime.now() - timedelta(seconds=30)
        self.assertTrue(self.client.is_ws_healthy())

    def test_get_cached_price_exists(self):
        """Test getting cached price when it exists."""
        self.client.price_cache['AAPL'] = {'price': 150.0, 'timestamp': datetime.now()}
        price = self.client.get_cached_price('AAPL')
        self.assertEqual(price, 150.0)

    def test_get_cached_price_missing(self):
        """Test getting cached price when not in cache."""
        price = self.client.get_cached_price('MISSING')
        self.assertIsNone(price)


class TestAlpacaClientHealth(unittest.TestCase):
    """Test health monitoring."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.client = AlpacaClient(mode='paper')

    def test_check_health(self):
        """Test health check returns expected structure."""
        self.client.ws_connected = True
        self.client.last_ws_message = datetime.now()

        health = self.client.check_health()
        self.assertIn('ws_connected', health)
        self.assertIn('ws_healthy', health)
        self.assertIn('api_errors', health)

    def test_get_health_summary_healthy(self):
        """Test health summary when healthy."""
        self.client.ws_connected = True
        self.client.last_ws_message = datetime.now()
        self.client.api_error_count = 0

        summary = self.client.get_health_summary()
        self.assertIn('✅', summary)

    def test_get_health_summary_degraded(self):
        """Test health summary when degraded."""
        self.client.ws_connected = False
        self.client.api_error_count = 2

        summary = self.client.get_health_summary()
        self.assertIn('❌', summary)


class TestAlpacaClientBatchPrices(unittest.TestCase):
    """Test get_latest_prices_batch method."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.client = AlpacaClient(mode='paper')

    def test_batch_all_cached(self):
        """All tickers in cache should return immediately without API calls."""
        now = datetime.now()
        self.client.price_cache['AAPL'] = {'price': 150.0, 'timestamp': now}
        self.client.price_cache['MSFT'] = {'price': 300.0, 'timestamp': now}

        result = self.client.get_latest_prices_batch(['AAPL', 'MSFT'])
        self.assertEqual(result['AAPL'], 150.0)
        self.assertEqual(result['MSFT'], 300.0)

    def test_batch_position_price(self):
        """Tickers with positions should use position API price."""
        mock_position = Mock()
        mock_position.symbol = 'AAPL'
        mock_position.current_price = 151.0
        mock_position.qty = '10'
        mock_position.avg_entry_price = 148.0
        mock_position.market_value = 1510.0
        mock_position.unrealized_pl = 30.0

        with patch.object(self.client.trading_client, 'get_all_positions', return_value=[mock_position]):
            result = self.client.get_latest_prices_batch(['AAPL'])
            self.assertEqual(result['AAPL'], 151.0)

    def test_batch_quotes_api(self):
        """Tickers not in cache or positions should use batch quotes API."""
        mock_quote = Mock()
        mock_quote.bid_price = 149.5
        mock_quote.ask_price = 150.5

        mock_data = MagicMock()
        mock_data.data = {'MSFT': mock_quote}

        with patch.object(self.client.trading_client, 'get_all_positions', return_value=[]), \
             patch.object(self.client.data_client, 'get_stock_latest_quote', return_value=mock_data):
            result = self.client.get_latest_prices_batch(['MSFT'])
            self.assertAlmostEqual(result['MSFT'], 150.0)

    def test_batch_mixed_sources(self):
        """Prices from cache, positions, and quotes should all work."""
        now = datetime.now()
        # AAPL in cache
        self.client.price_cache['AAPL'] = {'price': 150.0, 'timestamp': now}

        # MSFT via position
        mock_position = Mock()
        mock_position.symbol = 'MSFT'
        mock_position.current_price = 300.0
        mock_position.qty = '5'
        mock_position.avg_entry_price = 290.0
        mock_position.market_value = 1500.0
        mock_position.unrealized_pl = 50.0

        # GOOG via quotes
        mock_quote = Mock()
        mock_quote.bid_price = 139.0
        mock_quote.ask_price = 141.0
        mock_data = MagicMock()
        mock_data.data = {'GOOG': mock_quote}

        with patch.object(self.client.trading_client, 'get_all_positions', return_value=[mock_position]), \
             patch.object(self.client.data_client, 'get_stock_latest_quote', return_value=mock_data):
            result = self.client.get_latest_prices_batch(['AAPL', 'MSFT', 'GOOG'])
            self.assertEqual(result['AAPL'], 150.0)
            self.assertEqual(result['MSFT'], 300.0)
            self.assertAlmostEqual(result['GOOG'], 140.0)

    def test_batch_rate_limited(self):
        """When rate limited, should return None for non-cached tickers."""
        now = datetime.now()
        self.client.price_cache['AAPL'] = {'price': 150.0, 'timestamp': now}

        # Fill rate limiter
        for _ in range(200):
            self.client.rate_limiter.record_request()

        result = self.client.get_latest_prices_batch(['AAPL', 'MSFT'])
        self.assertEqual(result['AAPL'], 150.0)
        self.assertIsNone(result['MSFT'])

    def test_batch_quotes_api_failure(self):
        """Quotes API failure should return None for affected tickers."""
        now = datetime.now()
        self.client.price_cache['AAPL'] = {'price': 150.0, 'timestamp': now}

        with patch.object(self.client.trading_client, 'get_all_positions', return_value=[]), \
             patch.object(self.client.data_client, 'get_stock_latest_quote', side_effect=Exception("API error")):
            result = self.client.get_latest_prices_batch(['AAPL', 'MSFT'])
            self.assertEqual(result['AAPL'], 150.0)
            self.assertIsNone(result['MSFT'])


class TestAlpacaClientHistoricalData(unittest.TestCase):
    """Test historical data fetching with various scenarios."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test', 'ALPACA_SECRET_KEY': 'test'})
    def setUp(self):
        """Set up test fixtures."""
        from traderlib.alpaca_client import AlpacaClient

        with patch('alpaca_client.TradingClient'), \
             patch('alpaca_client.StockHistoricalDataClient'):
            self.client = AlpacaClient(mode='paper')

    def test_get_historical_bars_rate_limited(self):
        """Test historical bars when rate limited - should use fallback."""
        # Fill rate limiter
        for _ in range(200):
            self.client.rate_limiter.record_request()

        with patch.dict('sys.modules', {'yfinance': MagicMock()}):
            import sys
            mock_yf = sys.modules['yfinance']
            mock_ticker = Mock()
            mock_hist = pd.DataFrame({'Close': [100, 101, 102]})
            mock_ticker.history.return_value = mock_hist
            mock_yf.Ticker.return_value = mock_ticker

            bars = self.client.get_historical_bars('AAPL', days=30)
            self.assertIsNotNone(bars)


def run_tests():
    """Run all extended AlpacaClient tests."""
    print("=" * 70)
    print("🧪 EXTENDED ALPACA CLIENT TESTS")
    print("=" * 70)
    print()
    print("Testing additional code paths for coverage:")
    print("  • Config loading (env vars and file)")
    print("  • Rate limiter integration")
    print("  • yfinance fallback paths")
    print("  • Order error handling")
    print("  • WebSocket health checks")
    print("  • Position management edge cases")
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientFallbacks))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientOrderMethods))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientWebSocket))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientHealth))
    suite.addTests(loader.loadTestsFromTestCase(TestAlpacaClientHistoricalData))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("📊 EXTENDED TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print()
        print("✅ ALL EXTENDED TESTS PASSED")
        print("Coverage for alpaca_client.py should now be significantly improved")
    else:
        print()
        print("❌ SOME TESTS FAILED")

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
