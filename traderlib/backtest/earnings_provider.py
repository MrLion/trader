"""Historical earnings provider for backtesting.

Fetches and caches earnings dates from FMP API for use in backtest simulations.
Implements the same fail-open philosophy as EarningsCalendar.
"""

import json
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests


@dataclass
class EarningsRecord:
    """Single earnings record for a ticker."""
    ticker: str
    earnings_date: date
    eps_actual: Optional[float] = None
    eps_estimate: Optional[float] = None


class HistoricalEarningsProvider:
    """Provides historical earnings dates for backtesting.

    Uses FMP /stable/earnings endpoint (same as live EarningsCalendar).
    Caches data both in-memory and on disk for repeated backtests.

    Rate limiting: 300 requests/minute (FMP paid plan).
    Fail-open: if FMP unavailable or key missing, all gates are skipped.
    """

    _MAX_CALLS_PER_MIN = 300
    _REQUEST_TIMEOUT = 5
    _FMP_BASE = "https://financialmodelingprep.com/stable"

    def __init__(self, fmp_api_key: Optional[str] = None,
                 cache_dir: Optional[Path] = None,
                 cache_ttl_days: int = 30):
        """Initialize the earnings provider.

        Args:
            fmp_api_key: FMP API key. If None, uses FMP_API_KEY env var.
            cache_dir: Directory to cache earnings data. If None, uses data/earnings_cache.
            cache_ttl_days: Days before cache is considered stale.
        """
        self._api_key = fmp_api_key or os.environ.get("FMP_API_KEY")
        self._cache_ttl_days = cache_ttl_days

        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "earnings_cache"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache: ticker -> sorted list of earnings dates
        self._memory_cache: dict[str, list[date]] = {}

        # Rate limiting state
        self._call_times: list[float] = []

    def _rate_limit(self) -> None:
        """Block until within 300 calls/min budget."""
        now = time.monotonic()
        window = 60.0
        # Prune timestamps older than 1 minute
        self._call_times = [t for t in self._call_times if now - t < window]
        if len(self._call_times) >= self._MAX_CALLS_PER_MIN:
            sleep_for = window - (now - self._call_times[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._call_times.append(time.monotonic())

    def _get_cache_path(self, ticker: str) -> Path:
        """Get cache file path for a ticker."""
        return self._cache_dir / f"{ticker.upper()}.json"

    def _is_cache_valid(self, ticker: str) -> bool:
        """Check if cached data is fresh."""
        cache_path = self._get_cache_path(ticker)
        if not cache_path.exists():
            return False

        # Check if cache is older than TTL
        cache_mtime = cache_path.stat().st_mtime
        cache_age_days = (time.time() - cache_mtime) / (24 * 3600)
        return cache_age_days < self._cache_ttl_days

    def _load_from_disk(self, ticker: str) -> Optional[list[date]]:
        """Load earnings dates from disk cache."""
        if not self._is_cache_valid(ticker):
            return None

        cache_path = self._get_cache_path(ticker)
        try:
            with open(cache_path) as f:
                data = json.load(f)
                dates = [date.fromisoformat(d) for d in data.get("dates", [])]
                return sorted(dates)
        except Exception:
            return None

    def _save_to_disk(self, ticker: str, dates: list[date]) -> None:
        """Save earnings dates to disk cache."""
        cache_path = self._get_cache_path(ticker)
        try:
            with open(cache_path, "w") as f:
                json.dump({
                    "ticker": ticker,
                    "dates": [d.isoformat() for d in dates],
                    "cached_at": date.today().isoformat()
                }, f)
        except Exception:
            pass  # Fail silently on cache write failure

    def prefetch(self, tickers: list[str], start: date, end: date) -> None:
        """Bulk fetch earnings dates for a list of tickers.

        First checks memory cache, then disk cache, then fetches from FMP.
        Only fetches tickers not already in memory cache.

        Args:
            tickers: List of stock symbols to fetch earnings for.
            start: Start date for the backtest (not used for filtering).
            end: End date for the backtest (not used for filtering).
        """
        if not self._api_key:
            return  # Fail open - no API key

        tickers_to_fetch = []

        for ticker in tickers:
            ticker = ticker.upper()

            # Skip if already in memory cache
            if ticker in self._memory_cache:
                continue

            # Try loading from disk cache
            cached_dates = self._load_from_disk(ticker)
            if cached_dates is not None:
                self._memory_cache[ticker] = cached_dates
                continue

            tickers_to_fetch.append(ticker)

        # Fetch missing tickers from FMP
        for ticker in tickers_to_fetch:
            self._rate_limit()

            try:
                url = f"{self._FMP_BASE}/earnings"
                params = {"symbol": ticker, "apikey": self._api_key}

                resp = requests.get(
                    url, params=params, timeout=self._REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                records = resp.json()

                if not isinstance(records, list):
                    continue

                # Parse all earnings dates from response
                dates = []
                for record in records:
                    raw_date = record.get("date")
                    if raw_date:
                        try:
                            d = date.fromisoformat(raw_date)
                            dates.append(d)
                        except ValueError:
                            continue

                # Store sorted dates (chronological order)
                sorted_dates = sorted(dates)
                self._memory_cache[ticker] = sorted_dates

                # Save to disk cache
                self._save_to_disk(ticker, sorted_dates)

            except Exception:
                # Fail open for individual tickers
                continue

    def get_next_earnings(self, ticker: str, as_of: date) -> Optional[date]:
        """Get the next earnings date on or after as_of.

        Args:
            ticker: Stock symbol.
            as_of: Reference date.

        Returns:
            Next earnings date, or None if not found or data unavailable.
        """
        ticker = ticker.upper()

        if ticker not in self._memory_cache:
            return None

        dates = self._memory_cache[ticker]

        # Find first date >= as_of
        for d in dates:
            if d >= as_of:
                return d

        return None

    def is_earnings_blackout(self, ticker: str, sim_date: date) -> bool:
        """Check if today is an earnings date (entry blackout).

        Args:
            ticker: Stock symbol.
            sim_date: Current simulation date.

        Returns:
            True if today is earnings date (block new entries).
        """
        next_earnings = self.get_next_earnings(ticker, sim_date)
        if next_earnings is None:
            return False
        return sim_date == next_earnings

    def should_force_exit(self, ticker: str, sim_date: date,
                          trading_days: Optional[list[date]] = None) -> bool:
        """Check if position should be exited to avoid earnings.

        All earnings are treated as BMC (before market open), so we exit
        the trading day before.

        Args:
            ticker: Stock symbol.
            sim_date: Current simulation date.
            trading_days: Optional list of trading days for accurate next-day
                         calculation (handles holidays). If None, uses naive
                         weekend skipping.

        Returns:
            True if tomorrow is earnings (force exit today).
        """
        next_earnings = self.get_next_earnings(ticker, sim_date)
        if next_earnings is None:
            return False

        # Find next trading day after sim_date
        if trading_days:
            # Use provided trading days (more accurate, handles holidays)
            future_days = [d for d in trading_days if d > sim_date]
            if not future_days:
                return False
            tomorrow = future_days[0]
        else:
            # Fallback: naive weekend skipping
            tomorrow = sim_date + timedelta(days=1)
            while tomorrow.weekday() >= 5:  # Skip weekends (5=Sat, 6=Sun)
                tomorrow += timedelta(days=1)

        return tomorrow == next_earnings

    def invalidate_cache(self, ticker: str) -> None:
        """Remove ticker from memory cache (e.g., after earnings passes)."""
        self._memory_cache.pop(ticker.upper(), None)
