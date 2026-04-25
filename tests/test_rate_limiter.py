#!/usr/bin/env python3
"""Tests for rate limiter and circuit breaker.

Covers:
1. Rate limiting (window-based request tracking)
2. Exponential backoff on errors
3. Circuit breaker (open/close logic)
4. API health monitoring
5. Thread safety
"""

import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Add project root to path

from traderlib.rate_limiter import (
    RateLimiter,
    APIHealthMonitor,
    alpaca_rate_limiter,
    health_monitor,
)


class TestRateLimiter(unittest.TestCase):
    """Test RateLimiter class."""

    def setUp(self):
        """Create fresh rate limiter for each test."""
        self.limiter = RateLimiter(max_requests=5, window_seconds=10)

    def test_init_sets_defaults(self):
        """RateLimiter should initialize with correct defaults."""
        self.assertEqual(self.limiter.max_requests, 5)
        self.assertEqual(self.limiter.window_seconds, 10)
        self.assertEqual(self.limiter.base_delay, 1.0)
        self.assertEqual(self.limiter.max_delay, 60.0)
        self.assertFalse(self.limiter.circuit_open)
        self.assertEqual(self.limiter.error_count, 0)

    def test_can_make_request_within_limit(self):
        """Should allow requests within rate limit."""
        for i in range(5):
            self.assertTrue(self.limiter.can_make_request(),
                          f"Request {i+1} should be allowed")

    def test_can_make_request_at_limit(self):
        """Should reject requests at limit."""
        # Fill up to limit
        for i in range(5):
            self.limiter.record_request()

        # Next request should be rejected
        self.assertFalse(self.limiter.can_make_request())

    def test_record_request_tracks_time(self):
        """Recording request should track timestamp."""
        before = datetime.now()
        self.limiter.record_request()
        after = datetime.now()

        self.assertEqual(len(self.limiter.requests), 1)
        recorded_time = self.limiter.requests[0]
        self.assertTrue(before <= recorded_time <= after)

    def test_clean_old_requests_removes_expired(self):
        """Old requests should be cleaned from window."""
        # Manually add old request
        old_time = datetime.now() - timedelta(seconds=20)
        self.limiter.requests.append(old_time)

        # Add recent request
        self.limiter.record_request()

        # Clean should remove old
        self.limiter._clean_old_requests()
        self.assertEqual(len(self.limiter.requests), 1)

    def test_circuit_breaker_opens_after_errors(self):
        """Circuit should open after 5 errors in 1 minute."""
        # Record 5 errors quickly
        for i in range(5):
            self.limiter.record_request()  # Need requests for error window
            time.sleep(0.01)  # Small delay to ensure different timestamps

        for i in range(5):
            self.limiter.record_error()

        self.assertTrue(self.limiter.circuit_open)

    def test_circuit_breaker_blocks_requests(self):
        """Open circuit should block all requests."""
        # Force circuit open
        self.limiter.circuit_open = True
        self.limiter.circuit_opened_at = datetime.now()

        self.assertFalse(self.limiter.can_make_request())

    def test_circuit_breaker_closes_after_cooldown(self):
        """Circuit should close after cooldown period."""
        # Force circuit open with old timestamp
        self.limiter.circuit_open = True
        self.limiter.circuit_opened_at = datetime.now() - timedelta(seconds=61)

        # Should be able to close
        self.assertTrue(self.limiter._should_close_circuit())

    def test_success_reduces_error_count(self):
        """Success should reduce error count."""
        self.limiter.error_count = 3
        self.limiter.record_success()
        self.assertEqual(self.limiter.error_count, 2)

    def test_success_closes_circuit_when_ready(self):
        """Success should close circuit when cooldown passed."""
        self.limiter.circuit_open = True
        self.limiter.circuit_opened_at = datetime.now() - timedelta(seconds=61)
        self.limiter.error_count = 1

        self.limiter.record_success()

        self.assertFalse(self.limiter.circuit_open)

    def test_rate_limit_error_increases_backoff(self):
        """Rate limit errors should increase backoff exponentially."""
        self.limiter.record_error(is_rate_limit=True)
        self.assertEqual(self.limiter.current_delay, 1.0)

        self.limiter.record_error(is_rate_limit=True)
        self.assertEqual(self.limiter.current_delay, 2.0)

        self.limiter.record_error(is_rate_limit=True)
        self.assertEqual(self.limiter.current_delay, 4.0)

    def test_backoff_respects_max(self):
        """Backoff should not exceed max_delay."""
        self.limiter.current_delay = 50.0
        self.limiter._increase_backoff()
        self.assertEqual(self.limiter.current_delay, 60.0)

        self.limiter._increase_backoff()
        self.assertEqual(self.limiter.current_delay, 60.0)  # Capped

    def test_success_halves_backoff(self):
        """Success should reduce backoff by half."""
        self.limiter.current_delay = 8.0
        self.limiter.record_success()
        self.assertEqual(self.limiter.current_delay, 4.0)

    def test_get_wait_time_circuit_open(self):
        """Wait time should be 60s when circuit open."""
        self.limiter.circuit_open = True
        self.limiter.circuit_opened_at = datetime.now()

        wait = self.limiter.get_wait_time()
        self.assertEqual(wait, 60.0)

    def test_get_wait_time_circuit_ready_to_close(self):
        """Wait time should be 0 when circuit ready to close."""
        self.limiter.circuit_open = True
        self.limiter.circuit_opened_at = datetime.now() - timedelta(seconds=61)

        wait = self.limiter.get_wait_time()
        self.assertEqual(wait, 0.0)

    def test_get_wait_time_within_limit(self):
        """Wait time should be current delay when within limit."""
        self.limiter.current_delay = 2.5

        wait = self.limiter.get_wait_time()
        self.assertEqual(wait, 2.5)

    def test_get_wait_time_at_limit(self):
        """Wait time should account for window expiration."""
        # Fill to limit
        for _ in range(5):
            self.limiter.record_request()
            time.sleep(0.01)

        wait = self.limiter.get_wait_time()
        self.assertGreater(wait, 0)  # Should need to wait

    def test_get_status_returns_current_state(self):
        """Status should return current rate limiter state."""
        self.limiter.record_request()
        self.limiter.error_count = 2

        status = self.limiter.get_status()

        self.assertEqual(status['requests_in_window'], 1)
        self.assertEqual(status['max_requests'], 5)
        self.assertEqual(status['error_count'], 2)
        self.assertFalse(status['circuit_open'])
        self.assertTrue(status['can_request'])

    def test_thread_safety_lock_exists(self):
        """RateLimiter should have thread safety lock."""
        self.assertTrue(hasattr(self.limiter, '_lock'))

    def test_default_rate_limiter_exists(self):
        """Global rate limiter should exist."""
        self.assertIsNotNone(alpaca_rate_limiter)
        self.assertEqual(alpaca_rate_limiter.max_requests, 200)
        self.assertEqual(alpaca_rate_limiter.window_seconds, 60)


class TestAPIHealthMonitor(unittest.TestCase):
    """Test APIHealthMonitor class."""

    def setUp(self):
        """Create fresh health monitor for each test."""
        self.monitor = APIHealthMonitor()

    def test_init_sets_providers(self):
        """HealthMonitor should initialize with providers."""
        self.assertIn('alpaca', self.monitor.providers)
        self.assertIn('yfinance', self.monitor.providers)
        self.assertTrue(self.monitor.providers['alpaca']['healthy'])
        self.assertTrue(self.monitor.providers['yfinance']['healthy'])

    def test_mark_success_sets_healthy(self):
        """Marking success should set provider healthy."""
        self.monitor.providers['alpaca']['healthy'] = False
        self.monitor.providers['alpaca']['failures'] = 3

        self.monitor.mark_success('alpaca')

        self.assertTrue(self.monitor.providers['alpaca']['healthy'])
        self.assertEqual(self.monitor.providers['alpaca']['failures'], 0)

    def test_mark_failure_increments_failures(self):
        """Marking failure should increment failure count."""
        self.monitor.mark_failure('alpaca')
        self.assertEqual(self.monitor.providers['alpaca']['failures'], 1)

        self.monitor.mark_failure('alpaca')
        self.assertEqual(self.monitor.providers['alpaca']['failures'], 2)

    def test_mark_failure_unhealthy_after_three(self):
        """Provider should be marked unhealthy after 3 failures."""
        self.monitor.mark_failure('alpaca')
        self.monitor.mark_failure('alpaca')
        self.assertTrue(self.monitor.providers['alpaca']['healthy'])

        self.monitor.mark_failure('alpaca')
        self.assertFalse(self.monitor.providers['alpaca']['healthy'])

    def test_mark_failure_unknown_provider_ignored(self):
        """Marking failure for unknown provider should be ignored."""
        self.monitor.mark_failure('unknown_provider')
        # Should not raise

    def test_get_provider_returns_primary_when_healthy(self):
        """Should return primary when healthy."""
        provider = self.monitor.get_provider()
        self.assertEqual(provider, 'alpaca')

    def test_get_provider_returns_fallback_when_primary_unhealthy(self):
        """Should return fallback when primary unhealthy."""
        self.monitor.providers['alpaca']['healthy'] = False

        provider = self.monitor.get_provider()
        self.assertEqual(provider, 'yfinance')

    def test_get_provider_returns_primary_when_both_unhealthy(self):
        """Should return primary even when both unhealthy (last resort)."""
        self.monitor.providers['alpaca']['healthy'] = False
        self.monitor.providers['yfinance']['healthy'] = False

        provider = self.monitor.get_provider()
        self.assertEqual(provider, 'alpaca')

    def test_should_fallback_returns_false_when_primary_healthy(self):
        """Should not fallback when primary healthy."""
        self.assertFalse(self.monitor.should_fallback())

    def test_should_fallback_returns_true_when_primary_unhealthy(self):
        """Should fallback when primary unhealthy."""
        self.monitor.providers['alpaca']['healthy'] = False
        self.assertTrue(self.monitor.should_fallback())

    def test_get_status_returns_full_state(self):
        """Status should return complete health state."""
        status = self.monitor.get_status()

        self.assertEqual(status['primary'], 'alpaca')
        self.assertEqual(status['fallback'], 'yfinance')
        self.assertEqual(status['current'], 'alpaca')
        self.assertIn('providers', status)

    def test_default_health_monitor_exists(self):
        """Global health monitor should exist."""
        self.assertIsNotNone(health_monitor)
        self.assertIsInstance(health_monitor, APIHealthMonitor)


class TestRateLimiterConcurrency(unittest.TestCase):
    """Test thread safety of rate limiter."""

    def test_concurrent_record_request(self):
        """Concurrent request recording should be thread-safe."""
        import threading

        limiter = RateLimiter(max_requests=100, window_seconds=60)
        errors = []

        def record_many():
            try:
                for _ in range(10):
                    limiter.record_request()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(limiter.requests), 50)


if __name__ == '__main__':
    unittest.main()
