"""Earnings calendar — upcoming earnings date lookup via FMP API.

Used to gate entries and force exits before earnings events.

Rules implemented:
- No new entry on the earnings date itself
- Force exit the day before earnings (all reports treated as BMC —
  no AMC/BMC timing field available on FMP stable API)

Data source: Financial Modeling Prep /stable/earnings?symbol=TICKER
Requires: FMP_API_KEY environment variable (paid plan, 300 req/min, no daily cap)

Fail-open: if FMP is unavailable or the key is missing, all gates are skipped
so trading continues normally rather than blocking on a data outage.
"""

import os
import time
import logging
from datetime import date, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/stable"
_REQUEST_TIMEOUT = 5  # seconds


def _prev_trading_day(d: date) -> date:
    """Return the most recent weekday before d (skips weekends, not holidays)."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=Sat, 6=Sun
        prev -= timedelta(days=1)
    return prev


class EarningsCalendar:
    """Fetches and caches upcoming earnings dates from FMP.

    One instance per session. In-memory cache keyed by ticker — one FMP
    call per ticker per trading session regardless of scan frequency.

    Rate limiting: simple token bucket at 300 calls/min matching the FMP
    paid plan limit. Uses a lightweight internal tracker (no dependency on
    traderlib.rate_limiter to keep this module self-contained).
    """

    _MAX_CALLS_PER_MIN = 300

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("FMP_API_KEY")
        if not self._api_key:
            logger.warning(
                "EarningsCalendar: FMP_API_KEY not set — earnings gates disabled"
            )

        # ticker → next earnings date (None = no upcoming earnings found)
        self._cache: dict[str, Optional[date]] = {}

        # Simple rate limit tracker: timestamps of recent calls
        self._call_times: list[float] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_next_earnings(self, ticker: str) -> Optional[date]:
        """Return the next upcoming earnings date for ticker, or None.

        Result is cached for the life of this instance (one trading session).
        Fails open — returns None (no gate) if FMP is unavailable.
        """
        if ticker not in self._cache:
            self._cache[ticker] = self._fetch_next_earnings(ticker)
        return self._cache[ticker]

    def is_earnings_blackout(self, ticker: str, today: date) -> bool:
        """True if today is the earnings date — block new entries."""
        earnings = self.get_next_earnings(ticker)
        if earnings is None:
            return False
        return today == earnings

    def should_force_exit(self, ticker: str, today: date) -> bool:
        """True if position must be exited today to avoid earnings exposure.

        All reports treated as BMC (before market open) — exit the day before.
        This means: force exit when today == earnings_date - 1 trading day.
        """
        earnings = self.get_next_earnings(ticker)
        if earnings is None:
            return False
        return today == _prev_trading_day(earnings)

    def prefetch(self, tickers: list[str]) -> None:
        """Pre-warm cache for a list of tickers (call at session start)."""
        for ticker in tickers:
            if ticker not in self._cache:
                self._cache[ticker] = self._fetch_next_earnings(ticker)

    def invalidate(self, ticker: str) -> None:
        """Remove ticker from cache (e.g. after earnings passes)."""
        self._cache.pop(ticker, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Block until we're within the 300 calls/min budget."""
        now = time.monotonic()
        window = 60.0
        # Prune timestamps older than 1 minute
        self._call_times = [t for t in self._call_times if now - t < window]
        if len(self._call_times) >= self._MAX_CALLS_PER_MIN:
            sleep_for = window - (now - self._call_times[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._call_times.append(time.monotonic())

    def _fetch_next_earnings(self, ticker: str) -> Optional[date]:
        """Fetch earnings history from FMP; return first upcoming date or None."""
        if not self._api_key:
            return None

        self._rate_limit()

        url = f"{_FMP_BASE}/earnings"
        params = {"symbol": ticker, "apikey": self._api_key}

        try:
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            records = resp.json()
        except Exception as exc:
            logger.debug("EarningsCalendar: FMP fetch failed for %s: %s", ticker, exc)
            return None

        if not isinstance(records, list) or not records:
            return None

        today = date.today()
        for record in records:
            raw_date = record.get("date")
            eps_actual = record.get("epsActual")
            if not raw_date:
                continue
            # Upcoming = epsActual is null (not yet reported)
            if eps_actual is not None:
                continue
            try:
                earnings_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            if earnings_date >= today:
                return earnings_date

        return None  # No upcoming earnings found
