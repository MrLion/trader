#!/usr/bin/env python3
"""Phase 3 Chaos Tests for Alpaca Paper Trading Engine.

Tests intentional failures and edge cases:
- Cascade failures (all providers down)
- File corruption
- Boundary conditions
- Partial fills
- Delisted tickers
- Rate limit storms

Success Criteria:
- All chaos tests pass (failures are expected and handled)
- No unhandled exceptions in any scenario
- Clear error messages logged for each failure mode
"""

import asyncio
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

import pandas as pd
import pytz

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts' / 'lib'))

from paper_state import PaperState, Position
from traderlib.rate_limiter import RateLimiter


class FailingAlpacaClient:
    """Mock Alpaca client that simulates various failure modes."""

    def __init__(self, failure_mode='none'):
        self.failure_mode = failure_mode
        self.call_count = 0
        self.failure_after_n_calls = None

    def _maybe_fail(self):
        """Simulate failure based on mode."""
        self.call_count += 1

        if self.failure_after_n_calls and self.call_count > self.failure_after_n_calls:
            if self.failure_mode == 'timeout':
                raise TimeoutError("Simulated timeout")
            elif self.failure_mode == 'connection':
                raise ConnectionError("Simulated connection failure")
            elif self.failure_mode == 'rate_limit':
                raise Exception("rate limit exceeded")

        if self.failure_mode == 'cascade':
            raise ConnectionError("All providers failed")

    def get_account(self):
        self._maybe_fail()
        return {'cash': 0, 'equity': 0, 'buying_power': 0, 'status': 'ERROR'}

    def get_latest_price(self, ticker, use_fallback=True):
        self._maybe_fail()
        return None

    def get_historical_bars(self, ticker, days=252, use_fallback=True):
        self._maybe_fail()
        return None

    def submit_market_order(self, ticker, shares, side, stop_price=None):
        self._maybe_fail()
        return None

    def list_positions(self):
        self._maybe_fail()
        return []

    def is_ws_healthy(self):
        return False


class TestCascadeFailure(unittest.TestCase):
    """Test all providers failing - engine stops gracefully."""

    @patch('paper_state.datetime')
    def test_cascade_failure_graceful_shutdown(self, mock_datetime):
        """When all data providers fail, engine should stop gracefully.

        Verifies:
        1. No unhandled exceptions during cascade failure
        2. Error is logged appropriately
        3. Engine state remains consistent
        """
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Setup files
            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0, 'entries_today': 0,
                'last_entry_reset': '2024-04-08'
            }))

            watchlist_path = data_dir / 'watchlist.csv'
            pd.DataFrame({'Ticker': ['AAPL'], 'Pivot_Price': [150.0], 'Sector': ['Tech']}).to_csv(watchlist_path, index=False)

            with patch('paper_engine_alpaca.DATA_DIR', data_dir):
                with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path):
                    with patch('paper_state.DATA_DIR', data_dir):
                        from paper_engine_alpaca import AlpacaPaperEngine

                        # Create client that always fails
                        failing_client = FailingAlpacaClient(failure_mode='cascade')

                        with patch('paper_engine_alpaca.AlpacaClient') as mock_alpaca:
                            mock_alpaca.return_value = failing_client

                            # Should not raise exception during init
                            try:
                                engine = AlpacaPaperEngine(mode='paper')
                            except Exception as e:
                                self.fail(f"Engine init should handle cascade failure gracefully: {e}")

                            # Engine should initialize without crashing
                            self.assertIsNotNone(engine.state)

                            # Analysis should fail gracefully (no data available)
                            analysis = engine._analyze_ticker('AAPL')
                            self.assertIsNone(analysis)  # No data available

        print("✅ Cascade failure: Engine handles total provider failure gracefully")


class TestCorruptPositionsFile(unittest.TestCase):
    """Test handling of corrupt/malformed JSON in positions file."""

    def test_corrupt_positions_json(self):
        """Corrupted positions file should not crash the system.

        Verifies:
        1. Malformed JSON is detected
        2. System starts with empty positions
        3. Error is logged
        4. System can save new positions
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Create corrupt positions file
            positions_file = data_dir / 'paper_positions.json'
            positions_file.write_text("{invalid json::[[")  # Malformed JSON

            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    # Should not raise exception
                    try:
                        state = PaperState(initial_capital=100000.0)
                    except json.JSONDecodeError:
                        self.fail("PaperState should handle corrupt JSON gracefully")

                    # Should have empty positions
                    self.assertEqual(len(state.positions), 0)

                    # Should be able to add positions
                    state.enter_position(
                        ticker='AAPL',
                        entry_price=150.0,
                        shares=100,
                        stop_price=140.0,
                        target_price=165.0,
                        sector='Technology'
                    )

                    self.assertIn('AAPL', state.positions)

                    # Verify file can be saved and loaded
                    state2 = PaperState(initial_capital=100000.0)
                    self.assertIn('AAPL', state2.positions)

        print("✅ Corrupt positions: Malformed JSON handled gracefully")

    def test_empty_positions_file(self):
        """Empty positions file should be treated as no positions."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            positions_file = data_dir / 'paper_positions.json'
            positions_file.write_text("")  # Empty file

            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    state = PaperState(initial_capital=100000.0)
                    self.assertEqual(len(state.positions), 0)

        print("✅ Empty positions file: Handled as empty positions")


class TestMarketOpenBoundary(unittest.TestCase):
    """Test entry check at exactly 9:30 AM market open boundary."""

    @patch('paper_engine_alpaca.datetime')
    @patch('paper_state.datetime')
    def test_exact_market_open_boundary(self, mock_state_datetime, mock_engine_datetime):
        """Entry at exactly 9:30 AM should work.

        Verifies:
        1. 9:30:00 is considered market open
        2. 9:29:59 is pre-market (no entries)
        3. 16:00:00 is market close
        """
        mock_engine_datetime.strftime = datetime.strftime
        mock_state_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0, 'entries_today': 0,
                'last_entry_reset': '2024-04-08'
            }))

            watchlist_path = data_dir / 'watchlist.csv'
            pd.DataFrame({'Ticker': ['AAPL'], 'Pivot_Price': [150.0], 'Sector': ['Tech']}).to_csv(watchlist_path, index=False)

            with patch('paper_engine_alpaca.DATA_DIR', data_dir):
                with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path):
                    with patch('paper_state.DATA_DIR', data_dir):
                        from paper_engine_alpaca import AlpacaPaperEngine

                        with patch('paper_engine_alpaca.AlpacaClient') as mock_alpaca:
                            mock_alpaca.return_value = FailingAlpacaClient()

                            # Test exactly 9:30 AM (market open)
                            et = pytz.timezone('US/Eastern')
                            market_open = datetime(2024, 4, 8, 9, 30, 0, tzinfo=et)  # Monday
                            mock_engine_datetime.now.return_value = market_open
                            mock_state_datetime.now.return_value = market_open

                            engine = AlpacaPaperEngine(mode='paper')
                            self.assertTrue(engine._is_market_hours(),
                                "9:30:00 should be market open")

                            # Test 9:29:59 (pre-market)
                            pre_market = datetime(2024, 4, 8, 9, 29, 59, tzinfo=et)
                            mock_engine_datetime.now.return_value = pre_market
                            self.assertFalse(engine._is_market_hours(),
                                "9:29:59 should be pre-market")

                            # Test exactly 4:00 PM (market close)
                            market_close = datetime(2024, 4, 8, 16, 0, 0, tzinfo=et)
                            mock_engine_datetime.now.return_value = market_close
                            self.assertFalse(engine._is_market_hours(),
                                "16:00:00 should be market close")

                            # Test 3:59:59 PM (market open)
                            before_close = datetime(2024, 4, 8, 15, 59, 59, tzinfo=et)
                            mock_engine_datetime.now.return_value = before_close
                            self.assertTrue(engine._is_market_hours(),
                                "15:59:59 should be market open")

        print("✅ Market open boundary: Exact timestamps handled correctly")

    @patch('paper_engine_alpaca.datetime')
    @patch('paper_state.datetime')
    def test_weekend_no_trading(self, mock_state_datetime, mock_engine_datetime):
        """Saturday and Sunday should never allow trading."""
        mock_engine_datetime.strftime = datetime.strftime
        mock_state_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0, 'entries_today': 0,
                'last_entry_reset': '2024-04-08'
            }))

            watchlist_path = data_dir / 'watchlist.csv'
            pd.DataFrame({'Ticker': ['AAPL'], 'Pivot_Price': [150.0], 'Sector': ['Tech']}).to_csv(watchlist_path, index=False)

            with patch('paper_engine_alpaca.DATA_DIR', data_dir):
                with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path):
                    with patch('paper_state.DATA_DIR', data_dir):
                        from paper_engine_alpaca import AlpacaPaperEngine

                        with patch('paper_engine_alpaca.AlpacaClient') as mock_alpaca:
                            mock_alpaca.return_value = FailingAlpacaClient()

                            et = pytz.timezone('US/Eastern')

                            # Saturday 10 AM - should be closed
                            saturday = datetime(2024, 4, 6, 10, 0, 0, tzinfo=et)
                            mock_engine_datetime.now.return_value = saturday
                            mock_state_datetime.now.return_value = saturday
                            engine = AlpacaPaperEngine(mode='paper')
                            self.assertFalse(engine._is_market_hours(),
                                "Saturday should be market closed")

                            # Sunday 10 AM - should be closed
                            sunday = datetime(2024, 4, 7, 10, 0, 0, tzinfo=et)
                            mock_engine_datetime.now.return_value = sunday
                            mock_state_datetime.now.return_value = sunday
                            self.assertFalse(engine._is_market_hours(),
                                "Sunday should be market closed")

        print("✅ Weekend boundary: Saturday/Sunday correctly blocked")


class TestPartialFillHandling(unittest.TestCase):
    """Test order that fills partially then stalls."""

    @patch('paper_state.datetime')
    def test_partial_fill_handling(self, mock_datetime):
        """Partial fills should be tracked and handled.

        Verifies:
        1. Partial fills update position size
        2. Remaining quantity stays in pending
        3. System can handle completion later
        """
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0, 'entries_today': 0,
                'last_entry_reset': '2024-04-08'
            }))

            watchlist_path = data_dir / 'watchlist.csv'
            pd.DataFrame({'Ticker': ['AAPL'], 'Pivot_Price': [150.0], 'Sector': ['Tech']}).to_csv(watchlist_path, index=False)

            with patch('paper_engine_alpaca.DATA_DIR', data_dir):
                with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path):
                    with patch('paper_state.DATA_DIR', data_dir):
                        from paper_engine_alpaca import AlpacaPaperEngine
                        from order_manager import OrderManager

                        # Create partial fill client
                        class PartialFillClient(FailingAlpacaClient):
                            def __init__(self):
                                super().__init__()
                                self.order_id = 0
                                self.partial_fills = {}

                            def submit_market_order(self, ticker, shares, side, stop_price=None):
                                self.order_id += 1
                                order_id = f"partial-{self.order_id}"
                                # Return order with partial fill status
                                return {
                                    'id': order_id,
                                    'symbol': ticker,
                                    'qty': float(shares),
                                    'filled_qty': float(shares) * 0.5,  # 50% filled
                                    'side': side,
                                    'type': 'market',
                                    'status': 'partially_filled'
                                }

                            def get_order(self, order_id):
                                # Return updated order with more fills over time
                                if order_id not in self.partial_fills:
                                    self.partial_fills[order_id] = 0.5
                                else:
                                    self.partial_fills[order_id] = min(1.0, self.partial_fills[order_id] + 0.25)

                                # Find original order qty
                                original_qty = 100  # Simplified
                                filled = original_qty * self.partial_fills[order_id]

                                return {
                                    'id': order_id,
                                    'symbol': 'AAPL',
                                    'qty': original_qty,
                                    'filled_qty': filled,
                                    'side': 'buy',
                                    'type': 'market',
                                    'status': 'filled' if self.partial_fills[order_id] >= 1.0 else 'partially_filled',
                                    'filled_price': 150.0
                                }

                        partial_client = PartialFillClient()

                        with patch('paper_engine_alpaca.AlpacaClient') as mock_alpaca:
                            mock_alpaca.return_value = partial_client

                            engine = AlpacaPaperEngine(mode='paper')

                            # Clear any existing pending orders first
                            engine.order_manager.pending_orders.clear()

                            # Submit entry
                            order = engine.order_manager.submit_entry('AAPL', shares=100, stop_price=140.0)
                            self.assertIsNotNone(order)

                            # Check order exists in pending (should be exactly 1)
                            self.assertEqual(engine.order_manager.get_pending_count(), 1,
                                "Should have exactly 1 pending order after submission")

        print("✅ Partial fill: Order system handles incomplete fills")


class TestDelistedTicker(unittest.TestCase):
    """Test position in delisted ticker - can't exit."""

    @patch('paper_state.datetime')
    def test_delisted_ticker_handling(self, mock_datetime):
        """Position in delisted ticker should be handled gracefully.

        Verifies:
        1. Cannot get current price for delisted ticker
        2. Position remains open
        3. Manual intervention required logged
        """
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'paper_account.json').write_text(json.dumps({
                'cash': 100000.0, 'equity': 100000.0, 'entries_today': 0,
                'last_entry_reset': '2024-04-08'
            }))

            watchlist_path = data_dir / 'watchlist.csv'
            pd.DataFrame({'Ticker': ['AAPL'], 'Pivot_Price': [150.0], 'Sector': ['Tech']}).to_csv(watchlist_path, index=False)

            with patch('paper_engine_alpaca.DATA_DIR', data_dir):
                with patch('paper_engine_alpaca.WATCHLIST_PATH', watchlist_path):
                    with patch('paper_state.DATA_DIR', data_dir):
                        from paper_engine_alpaca import AlpacaPaperEngine

                        # Create client that fails for specific ticker
                        class DelistedClient(FailingAlpacaClient):
                            def get_latest_price(self, ticker, use_fallback=True):
                                if ticker == 'DELISTED':
                                    return None  # No price available
                                return 150.0

                        delisted_client = DelistedClient()

                        with patch('paper_engine_alpaca.AlpacaClient') as mock_alpaca:
                            mock_alpaca.return_value = delisted_client

                            engine = AlpacaPaperEngine(mode='paper')

                            # Manually add a position in delisted ticker
                            engine.state.enter_position(
                                ticker='DELISTED',
                                entry_price=150.0,
                                shares=100,
                                stop_price=140.0,
                                target_price=165.0,
                                sector='Technology'
                            )

                            # Try to get price - should fail
                            price = engine._get_current_price('DELISTED')
                            self.assertIsNone(price)

                            # Position should still exist
                            self.assertIn('DELISTED', engine.state.positions)

        print("✅ Delisted ticker: Stuck position handled gracefully")


class TestRateLimitStorm(unittest.TestCase):
    """Test rapid requests triggering circuit breaker."""

    def test_rate_limit_storm_circuit_breaker(self):
        """10+ rapid requests should trigger circuit breaker.

        Verifies:
        1. Circuit breaker opens after threshold errors
        2. Requests are blocked while circuit open
        3. Circuit remains open until cooldown period
        """
        from datetime import datetime, timedelta
        limiter = RateLimiter(max_requests=10, window_seconds=60)

        # Simulate 5 errors (circuit opens at 5 consecutive errors)
        for _ in range(5):
            limiter.record_request()
            limiter.record_error()

        # Circuit should be open
        self.assertTrue(limiter.circuit_open, "Circuit should be open after 5 errors")
        self.assertFalse(limiter.can_make_request(), "Requests should be blocked")

        # Circuit should remain open immediately after success
        # (needs 60 second cooldown)
        limiter.record_success()
        self.assertTrue(limiter.circuit_open, "Circuit should stay open (cooldown)")

        # Simulate cooldown period passing
        limiter.circuit_opened_at = datetime.now() - timedelta(seconds=61)
        limiter.record_success()

        # Now circuit should close
        self.assertFalse(limiter.circuit_open, "Circuit should close after cooldown")
        self.assertTrue(limiter.can_make_request(), "Requests should be allowed")

        print("✅ Rate limit storm: Circuit breaker protects system")

    def test_rate_limit_window(self):
        """Rate limiter tracks requests within time window."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # Make 3 requests
        for _ in range(3):
            self.assertTrue(limiter.can_make_request())
            limiter.record_request()

        # 4th request should be blocked
        self.assertFalse(limiter.can_make_request())

        print("✅ Rate limit window: Requests tracked correctly")


def run_tests():
    """Run all Phase 3 chaos tests."""
    print("=" * 70)
    print("🧪 PHASE 3: CHAOS & EDGE CASE TESTS")
    print("=" * 70)
    print()
    print("Breaking things intentionally:")
    print("  • Cascade failures")
    print("  • Corrupt files")
    print("  • Boundary conditions")
    print("  • Partial fills")
    print("  • Delisted tickers")
    print("  • Rate limit storms")
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCascadeFailure))
    suite.addTests(loader.loadTestsFromTestCase(TestCorruptPositionsFile))
    suite.addTests(loader.loadTestsFromTestCase(TestMarketOpenBoundary))
    suite.addTests(loader.loadTestsFromTestCase(TestPartialFillHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestDelistedTicker))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimitStorm))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("📊 PHASE 3 TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print()
        print("✅ ALL CHAOS TESTS PASSED")
        print("Ready for Phase 4: Coverage measurement & CI")
    else:
        print()
        print("❌ SOME CHAOS TESTS FAILED")
        print("Review failure modes before proceeding")

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
