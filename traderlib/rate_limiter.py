#!/usr/bin/env python3
"""Rate limiter for Alpaca API with exponential backoff."""

import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict


class RateLimiter:
    """Track API calls and enforce rate limits with backoff."""

    def __init__(self, max_requests: int = 200, window_seconds: int = 60):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window (Alpaca: 200/min)
            window_seconds: Time window for rate limit
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()

        # Error tracking
        self.error_count = 0
        self.last_error_time: Optional[datetime] = None
        self.circuit_open = False
        self.circuit_opened_at: Optional[datetime] = None

        # Backoff settings
        self.base_delay = 1.0
        self.max_delay = 60.0
        self.current_delay = 0.0

    def _clean_old_requests(self):
        """Remove requests outside the time window."""
        cutoff = datetime.now() - timedelta(seconds=self.window_seconds)
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

    def can_make_request(self) -> bool:
        """Check if a request can be made within rate limits."""
        if self.circuit_open:
            return False

        self._clean_old_requests()
        return len(self.requests) < self.max_requests

    def record_request(self):
        """Record that a request was made."""
        self.requests.append(datetime.now())

    def record_error(self, is_rate_limit: bool = False):
        """Record an API error.

        Args:
            is_rate_limit: True if error was a 429 rate limit
        """
        self.error_count += 1
        self.last_error_time = datetime.now()

        if is_rate_limit:
            self._increase_backoff()

        # Circuit breaker: open after 5 errors in 1 minute
        if self.error_count >= 5:
            recent_errors = sum(1 for t in self.requests
                              if datetime.now() - t < timedelta(minutes=1))
            if recent_errors >= 5:
                self._open_circuit()

    def record_success(self):
        """Record a successful request."""
        self.error_count = max(0, self.error_count - 1)
        self.current_delay = max(0, self.current_delay * 0.5)

        if self.circuit_open and self._should_close_circuit():
            self._close_circuit()

    def _increase_backoff(self):
        """Increase backoff delay exponentially."""
        if self.current_delay == 0:
            self.current_delay = self.base_delay
        else:
            self.current_delay = min(self.current_delay * 2, self.max_delay)

    def _open_circuit(self):
        """Open circuit breaker."""
        self.circuit_open = True
        self.circuit_opened_at = datetime.now()
        print(f"⚠️ CIRCUIT BREAKER OPENED at {self.circuit_opened_at}")

    def _close_circuit(self):
        """Close circuit breaker."""
        self.circuit_open = False
        self.circuit_opened_at = None
        self.error_count = 0
        self.current_delay = 0
        print(f"✅ CIRCUIT BREAKER CLOSED")

    def _should_close_circuit(self) -> bool:
        """Check if circuit should be closed (cooldown period passed)."""
        if not self.circuit_opened_at:
            return True
        elapsed = (datetime.now() - self.circuit_opened_at).total_seconds()
        return elapsed >= 60  # 60 second cooldown

    def get_wait_time(self) -> float:
        """Get recommended wait time before next request."""
        if self.circuit_open:
            if self._should_close_circuit():
                return 0.0
            return 60.0  # Wait for circuit cooldown

        self._clean_old_requests()

        if len(self.requests) < self.max_requests:
            return self.current_delay

        # Wait until oldest request expires
        oldest = self.requests[0]
        wait = (oldest + timedelta(seconds=self.window_seconds) - datetime.now()).total_seconds()
        return max(wait, self.current_delay)

    def get_status(self) -> Dict:
        """Get current rate limiter status."""
        self._clean_old_requests()
        return {
            'requests_in_window': len(self.requests),
            'max_requests': self.max_requests,
            'error_count': self.error_count,
            'circuit_open': self.circuit_open,
            'current_delay': self.current_delay,
            'can_request': self.can_make_request()
        }


class APIHealthMonitor:
    """Monitor API health and manage failover."""

    def __init__(self):
        self.providers = {
            'alpaca': {'healthy': True, 'last_check': None, 'failures': 0},
            'yfinance': {'healthy': True, 'last_check': None, 'failures': 0}
        }
        self.primary = 'alpaca'
        self.fallback = 'yfinance'

    def mark_success(self, provider: str):
        """Mark provider as healthy."""
        if provider in self.providers:
            self.providers[provider]['healthy'] = True
            self.providers[provider]['failures'] = 0
            self.providers[provider]['last_check'] = datetime.now()

    def mark_failure(self, provider: str):
        """Mark provider as potentially unhealthy."""
        if provider not in self.providers:
            return

        self.providers[provider]['failures'] += 1
        self.providers[provider]['last_check'] = datetime.now()

        # Mark unhealthy after 3 consecutive failures
        if self.providers[provider]['failures'] >= 3:
            self.providers[provider]['healthy'] = False
            print(f"⚠️ Provider {provider} marked unhealthy")

    def get_provider(self) -> str:
        """Get current data provider."""
        if self.providers[self.primary]['healthy']:
            return self.primary
        if self.providers[self.fallback]['healthy']:
            return self.fallback
        return self.primary  # Return primary even if unhealthy (last resort)

    def should_fallback(self) -> bool:
        """Check if should use fallback provider."""
        return not self.providers[self.primary]['healthy']

    def get_status(self) -> Dict:
        """Get health status of all providers."""
        return {
            'primary': self.primary,
            'fallback': self.fallback,
            'current': self.get_provider(),
            'providers': self.providers.copy()
        }


# Global rate limiters
alpaca_rate_limiter = RateLimiter(max_requests=200, window_seconds=60)
health_monitor = APIHealthMonitor()


if __name__ == "__main__":
    # Test rate limiter
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    print("Testing rate limiter...")
    for i in range(7):
        can_request = limiter.can_make_request()
        wait = limiter.get_wait_time()
        print(f"Request {i+1}: can_request={can_request}, wait={wait:.1f}s")

        if can_request:
            limiter.record_request()
        else:
            print("  Rate limited, simulating wait...")
            time.sleep(0.5)

    print("\nFinal status:", limiter.get_status())
