"""Economic calendar — macroeconomic events via FMP API.

Used to gate entries during high-impact events and manage trading risk
around major economic releases.

Data source: Financial Modeling Prep /stable/economic-calendar
Requires: FMP_API_KEY environment variable (paid plan, 300 req/min, no daily cap)

Fail-open: if FMP is unavailable or the key is missing, all gates are skipped
so trading continues normally rather than blocking on a data outage.

Weekend handling: No API calls are made for weekend dates (Saturday/Sunday).
"""

import os
import time
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

# Load .env from project root if available
from dotenv import load_dotenv
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / '.env')

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/stable"
_REQUEST_TIMEOUT = 5  # seconds


@dataclass(frozen=True)
class EconomicEvent:
    """Represents a single economic event from the calendar.

    Attributes:
        date: Event date in ISO format (YYYY-MM-DD)
        time: Event time (e.g., "08:30", "14:00")
        event: Event name/description (e.g., "CPI MoM", "FOMC Statement")
        impact: Impact level from FMP (low, medium, high) or classified
        estimate: Estimated/consensus value, or None
        previous: Previous reported value, or None
    """
    date: str
    time: str
    event: str
    impact: str
    estimate: Optional[str]
    previous: Optional[str]
    country: str = 'US'

    def __repr__(self) -> str:
        return f"EconomicEvent(date={self.date}, event={self.event}, impact={self.impact})"


class EconomicCalendar:
    """Fetches and caches economic events from FMP.

    One instance per session. In-memory cache keyed by date range.

    Rate limiting: simple token bucket at 300 calls/min matching the FMP
    paid plan limit. Uses a lightweight internal tracker (no dependency on
    traderlib.rate_limiter to keep this module self-contained).
    """

    _MAX_CALLS_PER_MIN = 300

    # Keywords that indicate high-impact events (case-insensitive)
    _HIGH_IMPACT_KEYWORDS = [
        "cpi", "ppi", "fed", "fomc", "nonfarm", "payrolls", "employment"
    ]

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the economic calendar.

        Args:
            api_key: FMP API key. If not provided, reads from FMP_API_KEY env var.
        """
        self._api_key = api_key or os.environ.get("FMP_API_KEY")
        if not self._api_key:
            logger.warning(
                "EconomicCalendar: FMP_API_KEY not set — economic event gates disabled"
            )

        # Cache: "start_date:end_date" -> list of EconomicEvent
        self._cache: dict[str, list[EconomicEvent]] = {}

        # Simple rate limit tracker: timestamps of recent calls
        self._call_times: list[float] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_events(
        self,
        start_date: date,
        end_date: Optional[date] = None
    ) -> list[EconomicEvent]:
        """Fetch economic events for a date range.

        Results are cached for the life of this instance.
        Fails open — returns empty list if FMP is unavailable.
        Weekend dates return empty list (no API call made).

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive). Defaults to start_date.

        Returns:
            List of EconomicEvent objects sorted by date and time.
        """
        if end_date is None:
            end_date = start_date

        # Return empty list for weekend-only requests
        if start_date.weekday() >= 5 and end_date.weekday() >= 5:
            return []

        cache_key = f"{start_date.isoformat()}:{end_date.isoformat()}"

        if cache_key not in self._cache:
            self._cache[cache_key] = self._fetch_events(start_date, end_date)

        return self._cache[cache_key]

    def get_today_events(self) -> list[EconomicEvent]:
        """Get events for today.

        Returns:
            List of EconomicEvent objects for today.
        """
        today = date.today()
        return self.get_events(today, today)

    def get_tomorrow_events(self) -> list[EconomicEvent]:
        """Get events for tomorrow.

        Returns:
            List of EconomicEvent objects for tomorrow.
        """
        tomorrow = date.today() + timedelta(days=1)
        return self.get_events(tomorrow, tomorrow)

    def get_high_impact_events(
        self,
        start_date: date,
        end_date: Optional[date] = None
    ) -> list[EconomicEvent]:
        """Get only high-impact events for a date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive). Defaults to start_date.

        Returns:
            List of high-impact EconomicEvent objects.
        """
        events = self.get_events(start_date, end_date)
        return [e for e in events if self._classify_impact(e) == "high"]

    def invalidate(self, start_date: date, end_date: Optional[date] = None) -> None:
        """Remove date range from cache.

        Args:
            start_date: Start of date range
            end_date: End of date range. Defaults to start_date.
        """
        if end_date is None:
            end_date = start_date
        cache_key = f"{start_date.isoformat()}:{end_date.isoformat()}"
        self._cache.pop(cache_key, None)

    def clear_cache(self) -> None:
        """Clear all cached events."""
        self._cache.clear()

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

    def _is_high_impact_event(self, event_name: str) -> bool:
        """Check if event name contains high-impact keywords.

        Args:
            event_name: The event name to check.

        Returns:
            True if the event is high-impact based on keywords.
        """
        event_lower = event_name.lower()
        return any(keyword in event_lower for keyword in self._HIGH_IMPACT_KEYWORDS)

    def _classify_impact(self, event: EconomicEvent) -> str:
        """Classify event impact level.

        Combines FMP impact with keyword detection. If FMP says high or
        keywords indicate high impact, return high. Otherwise return FMP's value.

        Args:
            event: The economic event to classify.

        Returns:
            Impact level: "low", "medium", or "high".
        """
        if event.impact.lower() == "high" or self._is_high_impact_event(event.event):
            return "high"
        return event.impact.lower()

    def _fetch_events(self, start_date: date, end_date: date) -> list[EconomicEvent]:
        """Fetch events from FMP API.

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of EconomicEvent objects.
        """
        if not self._api_key:
            return []

        self._rate_limit()

        url = f"{_FMP_BASE}/economic-calendar"
        params = {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "apikey": self._api_key
        }

        try:
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            records = resp.json()
        except Exception as exc:
            logger.debug("EconomicCalendar: FMP fetch failed: %s", exc)
            return []

        if not isinstance(records, list):
            logger.debug("EconomicCalendar: unexpected response format")
            return []

        events = []
        for record in records:
            # Skip non-dict records
            if not isinstance(record, dict):
                continue

            # Extract fields with defaults
            date_str = record.get("date")
            time_str = record.get("time", "")
            country = record.get("country", "")
            event_name = record.get("event")
            impact = record.get("impact", "medium")
            estimate = record.get("estimate")
            previous = record.get("previous")

            # Skip records missing required fields
            if not date_str or not event_name:
                continue

            event = EconomicEvent(
                date=date_str,
                time=time_str,
                country=country,
                event=event_name,
                impact=impact,
                estimate=estimate,
                previous=previous
            )
            events.append(event)

        # Sort by date and time
        events.sort(key=lambda e: (e.date, e.time))
        return events
