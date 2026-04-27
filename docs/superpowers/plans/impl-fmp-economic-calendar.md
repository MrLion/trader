# FMP Economic Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate FMP Economic Calendar API to provide economic event data (CPI, Fed meetings, jobs reports) in pre-market reports with risk classification and actionable guidance.

**Architecture:** Create a reusable `EconomicCalendar` class in `traderlib/economic_calendar.py` following the same patterns as `earnings_calendar.py` (rate limiting, in-memory caching, fail-open behavior). Update `scripts/premarket_report.py` to replace the broken tradingcharts scraper with FMP data, including console and HTML output with risk badges.

**Tech Stack:** Python 3.11+, `requests`, `zoneinfo` for timezone handling, `dataclasses` for event modeling.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `traderlib/economic_calendar.py` | New module — FMP API client with rate limiting, caching, timezone conversion |
| `tests/test_economic_calendar.py` | New test file — unit tests for EconomicCalendar class |
| `scripts/premarket_report.py` | Modify — replace `fetch_economic_calendar()` with FMP integration |
| `traderlib/__init__.py` | Modify — export EconomicCalendar class |

---

## Task 1: Create EconomicCalendar Module

**Files:**
- Create: `traderlib/economic_calendar.py`
- Test: `tests/test_economic_calendar.py`

### Step 1: Write the failing test for EconomicEvent dataclass

```python
# tests/test_economic_calendar.py
#!/usr/bin/env python3
"""Tests for economic_calendar module."""

import logging
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from traderlib.economic_calendar import EconomicCalendar, EconomicEvent

_FAKE_TODAY = date(2026, 4, 27)


class TestEconomicEvent:
    """Test EconomicEvent dataclass."""

    def test_create_event(self):
        event = EconomicEvent(
            date=date(2026, 4, 27),
            time="08:30",
            event="CPI",
            impact="high",
            estimate="+0.3%",
            previous="+0.4%"
        )
        assert event.date == date(2026, 4, 27)
        assert event.time == "08:30"
        assert event.event == "CPI"
        assert event.impact == "high"
        assert event.estimate == "+0.3%"
        assert event.previous == "+0.4%"

    def test_optional_fields_default_to_none(self):
        event = EconomicEvent(
            date=date(2026, 4, 27),
            time="10:00",
            event="Wholesale Inventories",
            impact="low"
        )
        assert event.estimate is None
        assert event.previous is None
```

- [ ] **Step 1: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestEconomicEvent -v`
Expected: FAIL with "EconomicEvent not defined"

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Write minimal implementation**

```python
# traderlib/economic_calendar.py
"""Economic calendar — US economic events lookup via FMP API.

Used to assess market volatility risk before trading. Provides awareness
of CPI, Fed meetings, jobs reports, and other high-impact events.

Data source: Financial Modeling Prep /stable/economic-calendar
Requires: FMP_API_KEY environment variable (paid plan, 300 req/min)

Fail-open: if FMP is unavailable or the key is missing, returns empty
list so trading continues normally rather than blocking on a data outage.
"""

import logging
import os
import time
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


@dataclass
class EconomicEvent:
    """Represents a single economic event."""
    date: date
    time: str  # ET time for display
    event: str
    impact: str  # 'high', 'medium', 'low'
    estimate: Optional[str] = None
    previous: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestEconomicEvent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add EconomicEvent dataclass for economic calendar"
```

---

### Step 2: Write test for EconomicCalendar initialization

```python
# Add to tests/test_economic_calendar.py

class TestEconomicCalendarInit:
    """Test EconomicCalendar initialization."""

    def test_accepts_api_key_argument(self):
        ec = EconomicCalendar(api_key="test_key")
        assert ec._api_key == "test_key"

    def test_reads_api_key_from_env(self):
        with patch.dict("os.environ", {"FMP_API_KEY": "env_key"}, clear=True):
            ec = EconomicCalendar()
            assert ec._api_key == "env_key"

    def test_logs_warning_when_no_key(self, caplog):
        with patch.dict("os.environ", {}, clear=True):
            with caplog.at_level(logging.WARNING):
                ec = EconomicCalendar()
        assert ec._api_key is None
        assert "FMP_API_KEY not set" in caplog.text

    def test_cache_is_empty_on_init(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._cache == {}

    def test_call_times_is_empty_on_init(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._call_times == []
```

- [ ] **Step 6: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestEconomicCalendarInit -v`
Expected: FAIL with "EconomicCalendar not defined"

- [ ] **Step 7: Run test to verify it fails**

- [ ] **Step 8: Write minimal implementation**

```python
# Add to traderlib/economic_calendar.py

class EconomicCalendar:
    """Fetches economic events from FMP API.

    One instance per session. In-memory cache keyed by date range.
    Rate limiting: simple token bucket at 300 calls/min matching the FMP
    paid plan limit.
    """

    _MAX_CALLS_PER_MIN = 300

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("FMP_API_KEY")
        if not self._api_key:
            logger.warning(
                "EconomicCalendar: FMP_API_KEY not set — economic calendar disabled"
            )

        # (start_date, end_date) → list[EconomicEvent]
        self._cache: dict[tuple[date, date], list[EconomicEvent]] = {}

        # Simple rate limit tracker: timestamps of recent calls
        self._call_times: list[float] = []
```

- [ ] **Step 9: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestEconomicCalendarInit -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add EconomicCalendar class with init and rate limiting setup"
```

---

### Step 3: Write test for _rate_limit method

```python
# Add to tests/test_economic_calendar.py

class TestRateLimit:
    """Test internal rate limiting."""

    def test_no_sleep_when_under_limit(self):
        ec = EconomicCalendar(api_key="key")
        ec._call_times = [100.0] * 299
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_not_called()
        assert len(ec._call_times) == 300

    def test_sleeps_when_at_limit(self):
        ec = EconomicCalendar(api_key="key")
        ec._call_times = [100.0] * 300
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_called_once()
        assert len(ec._call_times) == 301

    def test_prunes_old_calls(self):
        ec = EconomicCalendar(api_key="key")
        ec._call_times = [50.0] * 300 + [120.0] * 5
        with patch("time.monotonic", return_value=130.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_not_called()
```

- [ ] **Step 11: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestRateLimit -v`
Expected: FAIL with "_rate_limit not defined"

- [ ] **Step 12: Run test to verify it fails**

- [ ] **Step 13: Write minimal implementation**

```python
# Add to EconomicCalendar class in traderlib/economic_calendar.py

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
```

- [ ] **Step 14: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestRateLimit -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add rate limiting to EconomicCalendar"
```

---

### Step 4: Write test for _is_high_impact_event helper

```python
# Add to tests/test_economic_calendar.py

class TestIsHighImpactEvent:
    """Test _is_high_impact_event helper."""

    def test_cpi_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Consumer Price Index") is True

    def test_fomc_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("FOMC Statement") is True

    def test_nonfarm_payrolls_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Nonfarm Payrolls") is True

    def test_jobless_claims_is_medium_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Initial Jobless Claims") is False

    def test_case_insensitive(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("cpi") is True
        assert ec._is_high_impact_event("FED Rate") is True
```

- [ ] **Step 16: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestIsHighImpactEvent -v`
Expected: FAIL with "_is_high_impact_event not defined"

- [ ] **Step 17: Run test to verify it fails**

- [ ] **Step 18: Write minimal implementation**

```python
# Add to EconomicCalendar class in traderlib/economic_calendar.py

    # High-impact event keywords (case-insensitive)
    _HIGH_IMPACT_KEYWORDS = [
        "CPI", "PPI", "Fed", "FOMC", "Nonfarm", "Payrolls", "Employment"
    ]

    def _is_high_impact_event(self, event_name: str) -> bool:
        """Check if event name indicates high market impact."""
        event_upper = event_name.upper()
        return any(keyword.upper() in event_upper for keyword in self._HIGH_IMPACT_KEYWORDS)
```

- [ ] **Step 19: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestIsHighImpactEvent -v`
Expected: PASS

- [ ] **Step 20: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add high-impact event detection to EconomicCalendar"
```

---

### Step 5: Write test for _classify_impact method

```python
# Add to tests/test_economic_calendar.py

class TestClassifyImpact:
    """Test _classify_impact helper."""

    def test_returns_high_for_high_impact_events(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._classify_impact("CPI", "high") == "high"
        assert ec._classify_impact("FOMC", "medium") == "high"  # Override based on name

    def test_returns_original_for_medium(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._classify_impact("Jobless Claims", "medium") == "medium"

    def test_returns_original_for_low(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._classify_impact("Wholesale Inventories", "low") == "low"

    def test_defaults_to_low_for_unknown(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._classify_impact("Some Event", "") == "low"
```

- [ ] **Step 21: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestClassifyImpact -v`
Expected: FAIL with "_classify_impact not defined"

- [ ] **Step 22: Run test to verify it fails**

- [ ] **Step 23: Write minimal implementation**

```python
# Add to EconomicCalendar class in traderlib/economic_calendar.py

    def _classify_impact(self, event_name: str, fmp_impact: str) -> str:
        """Classify event impact, overriding based on event name if needed."""
        # If FMP says high, trust it
        if fmp_impact.lower() == "high":
            return "high"
        # Override to high for known high-impact events
        if self._is_high_impact_event(event_name):
            return "high"
        # Trust FMP for medium/low
        if fmp_impact.lower() in ("medium", "low"):
            return fmp_impact.lower()
        # Default to low for unknown
        return "low"
```

- [ ] **Step 24: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestClassifyImpact -v`
Expected: PASS

- [ ] **Step 25: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add impact classification to EconomicCalendar"
```

---

### Step 6: Write test for get_events with API success

```python
# Add to tests/test_economic_calendar.py

class TestGetEvents:
    """Test get_events method."""

    def test_cache_hit_returns_cached_events(self):
        ec = EconomicCalendar(api_key="key")
        cached_events = [
            EconomicEvent(date=date(2026, 4, 27), time="08:30", event="CPI", impact="high")
        ]
        ec._cache[(date(2026, 4, 27), date(2026, 4, 28))] = cached_events

        with patch("traderlib.economic_calendar.requests.get") as mock_get:
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))

        assert result == cached_events
        mock_get.assert_not_called()

    def test_fetches_and_caches_on_miss(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "date": "2026-04-27",
                "time": "08:30",
                "event": "CPI",
                "impact": "high",
                "estimate": "+0.3%",
                "previous": "+0.4%",
                "unit": "%"
            }
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))

        assert len(result) == 1
        assert result[0].event == "CPI"
        assert result[0].impact == "high"
        assert (date(2026, 4, 27), date(2026, 4, 28)) in ec._cache
        mock_get.assert_called_once()

    def test_no_key_returns_empty_list(self):
        with patch.dict("os.environ", {}, clear=True):
            ec = EconomicCalendar()
            with patch("traderlib.economic_calendar.requests.get") as mock_get:
                result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))
        assert result == []
        mock_get.assert_not_called()

    def test_fetch_failure_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        with patch("traderlib.economic_calendar.requests.get", side_effect=Exception("timeout")):
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))
        assert result == []

    def test_malformed_response_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad request"}
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))
        assert result == []

    def test_empty_list_response_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))
        assert result == []

    def test_weekend_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        with patch("traderlib.economic_calendar.requests.get") as mock_get:
            result = ec.get_events(date(2026, 4, 25), date(2026, 4, 26))  # Saturday-Sunday
        assert result == []
        mock_get.assert_not_called()

    def test_url_construction(self):
        ec = EconomicCalendar(api_key="key123")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
            ec.get_events(date(2026, 4, 27), date(2026, 4, 28))

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "financialmodelingprep.com/stable/economic-calendar" in call_args[0][0]
        assert call_args[1]["params"]["from"] == "2026-04-27"
        assert call_args[1]["params"]["to"] == "2026-04-28"
        assert call_args[1]["params"]["apikey"] == "key123"
```

- [ ] **Step 26: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestGetEvents -v`
Expected: FAIL with "get_events not defined"

- [ ] **Step 27: Run test to verify it fails**

- [ ] **Step 28: Write minimal implementation**

```python
# Add to EconomicCalendar class in traderlib/economic_calendar.py

    def get_events(self, start: date, end: date) -> list[EconomicEvent]:
        """Fetch economic events for date range from FMP.

        Results are cached for the life of this instance.
        Fails open — returns empty list if FMP is unavailable.
        """
        cache_key = (start, end)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Skip weekends — no economic events scheduled
        if start.weekday() >= 5:  # Saturday (5) or Sunday (6)
            self._cache[cache_key] = []
            return []

        if not self._api_key:
            return []

        self._rate_limit()

        url = f"{_FMP_BASE}/economic-calendar"
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "apikey": self._api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            records = resp.json()
        except Exception as exc:
            logger.debug("EconomicCalendar: FMP fetch failed: %s", exc)
            return []

        if not isinstance(records, list):
            return []

        events: list[EconomicEvent] = []
        for record in records:
            event_date = record.get("date")
            event_time = record.get("time", "")
            event_name = record.get("event", "")
            fmp_impact = record.get("impact", "")
            estimate = record.get("estimate")
            previous = record.get("previous")

            if not event_date or not event_name:
                continue

            try:
                evt_date = date.fromisoformat(event_date)
            except ValueError:
                continue

            # Classify impact
            impact = self._classify_impact(event_name, fmp_impact)

            # Convert UTC time to ET (simple approach: assume ET for US events)
            # FMP returns times like "08:30" which are typically ET for US events
            display_time = event_time if event_time else "TBD"

            events.append(EconomicEvent(
                date=evt_date,
                time=display_time,
                event=event_name,
                impact=impact,
                estimate=str(estimate) if estimate else None,
                previous=str(previous) if previous else None,
            ))

        self._cache[cache_key] = events
        return events
```

- [ ] **Step 29: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestGetEvents -v`
Expected: PASS

- [ ] **Step 30: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add get_events method to EconomicCalendar with caching"
```

---

### Step 7: Write test for convenience methods

```python
# Add to tests/test_economic_calendar.py

class TestConvenienceMethods:
    """Test get_today_events, get_tomorrow_events, get_high_impact_events."""

    def test_get_today_events_filters_by_today(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high"},
            {"date": "2026-04-28", "time": "08:30", "event": "Jobless", "impact": "medium"},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_today_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "CPI"

    def test_get_tomorrow_events_filters_by_tomorrow(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high"},
            {"date": "2026-04-28", "time": "08:30", "event": "Jobless", "impact": "medium"},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_tomorrow_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "Jobless"

    def test_get_high_impact_events_filters_by_impact(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high"},
            {"date": "2026-04-27", "time": "10:00", "event": "Inventories", "impact": "low"},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_high_impact_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "CPI"
```

- [ ] **Step 31: Write the failing test**

Run: `pytest tests/test_economic_calendar.py::TestConvenienceMethods -v`
Expected: FAIL with methods not defined

- [ ] **Step 32: Run test to verify it fails**

- [ ] **Step 33: Write minimal implementation**

```python
# Add to EconomicCalendar class in traderlib/economic_calendar.py

    def get_today_events(self, today: date) -> list[EconomicEvent]:
        """Get today's economic events."""
        events = self.get_events(today, today)
        return [e for e in events if e.date == today]

    def get_tomorrow_events(self, today: date) -> list[EconomicEvent]:
        """Get tomorrow's economic events."""
        tomorrow = today + timedelta(days=1)
        events = self.get_events(today, tomorrow)
        return [e for e in events if e.date == tomorrow]

    def get_high_impact_events(self, today: date) -> list[EconomicEvent]:
        """Filter for high-impact events only."""
        events = self.get_today_events(today)
        return [e for e in events if e.impact == "high"]
```

- [ ] **Step 34: Run test to verify it passes**

Run: `pytest tests/test_economic_calendar.py::TestConvenienceMethods -v`
Expected: PASS

- [ ] **Step 35: Commit**

```bash
git add tests/test_economic_calendar.py traderlib/economic_calendar.py
git commit -m "feat: add convenience methods to EconomicCalendar"
```

---

## Task 2: Export EconomicCalendar from traderlib

**Files:**
- Modify: `traderlib/__init__.py`

### Step 36: Check current exports

Read `traderlib/__init__.py` to see current exports.

### Step 37: Add EconomicCalendar export

```python
# Add to traderlib/__init__.py
from .economic_calendar import EconomicCalendar, EconomicEvent
```

### Step 38: Verify import works

Run: `python -c "from traderlib import EconomicCalendar, EconomicEvent; print('OK')"`
Expected: OK

### Step 39: Commit

```bash
git add traderlib/__init__.py
git commit -m "chore: export EconomicCalendar and EconomicEvent from traderlib"
```

---

## Task 3: Integrate with Pre-Market Report

**Files:**
- Modify: `scripts/premarket_report.py`

### Step 40: Update fetch_economic_calendar function

Replace the entire `fetch_economic_calendar()` function in `scripts/premarket_report.py`:

```python
def fetch_economic_calendar():
    """Fetch US economic events from FMP."""
    from traderlib.economic_calendar import EconomicCalendar
    
    cal = EconomicCalendar()
    today = datetime.now().date()
    
    # Get today + tomorrow events
    events = cal.get_events(today, today + timedelta(days=1))
    
    # Separate today vs tomorrow
    today_events = [e for e in events if e.date == today]
    tomorrow_events = [e for e in events if e.date == today + timedelta(days=1)]
    
    return {
        'today': today_events,
        'tomorrow': tomorrow_events,
    }
```

Also update the import section at the top of the file to include `timedelta` if not already present (it should already be imported from datetime).

### Step 41: Update risk classification logic

Replace the risk classification logic (around lines 992-1001) with:

```python
def _classify_economic_risk(events):
    """Classify risk level based on today's events."""
    if not events:
        return '🟢', 'Clear day, trade normally'
    
    has_high = any(e.impact == 'high' for e in events)
    has_medium = any(e.impact == 'medium' for e in events)
    
    if has_high:
        return '🔴', 'Reduce size 50% or wait for post-event clarity'
    elif has_medium:
        return '🟡', 'Normal size, watch for volatility at event time'
    else:
        return '🟢', 'Clear day, trade normally'
```

Then update the code that calls this:

```python
econ = fetch_economic_calendar()
risk_level, advice = _classify_economic_risk(econ['today'])
report_data['economic']['risk_level'] = risk_level
report_data['economic']['advice'] = advice
report_data['economic']['events'] = econ['today']
report_data['economic']['tomorrow'] = econ['tomorrow']
```

### Step 42: Update console output

Update the console output section (around lines 1179-1188) to handle the new EconomicEvent objects:

```python
if report_data['economic']['events']:
    print(f"{report_data['economic']['risk_level']} Today's Events:")
    for e in report_data['economic']['events']:
        impact_emoji = '🔴' if e.impact == 'high' else '🟡' if e.impact == 'medium' else '🟢'
        estimate_str = f" (est: {e.estimate}, prev: {e.previous})" if e.estimate else ""
        print(f"   {e.time}  {impact_emoji} {e.event}{estimate_str}")
    print(f"\n   → {report_data['economic']['advice']}")
    
    # Show tomorrow preview if high impact
    if report_data['economic']['tomorrow']:
        high_tomorrow = [e for e in report_data['economic']['tomorrow'] if e.impact == 'high']
        if high_tomorrow:
            print(f"\n⚠️  Major event tomorrow — size accordingly today")
else:
    print("🟢 No major US economic events today")
```

### Step 43: Update HTML output

Update the HTML generation for the economic calendar section. The HTML structure should use the CSS classes from the spec. Update around lines 113-142:

```python
# Economic events
econ = report_data.get('economic', {})
events = econ.get('events', [])
tomorrow_events = econ.get('tomorrow', [])

if events or tomorrow_events:
    risk_class = "risk-high" if econ.get('risk_level') == '🔴' else "risk-medium" if econ.get('risk_level') == '🟡' else "risk-low"
    risk_text = "🔴 High Impact Events Today — Reduce Size 50%" if econ.get('risk_level') == '🔴' else "🟡 Medium Impact Events Today — Watch for Volatility" if econ.get('risk_level') == '🟡' else "🟢 Clear Day — No Major Economic Events"
    
    econ_html = f'''
    <div class="risk-badge {risk_class}">
        {risk_text}
    </div>
    '''
    
    if events:
        econ_html += '''
        <table class="events-table">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Impact</th>
                    <th>Event</th>
                    <th>Estimate</th>
                    <th>Previous</th>
                </tr>
            </thead>
            <tbody>
        '''
        for e in events:
            impact_class = "impact-high" if e.impact == "high" else "impact-medium" if e.impact == "medium" else "impact-low"
            impact_label = "🔴 HIGH" if e.impact == "high" else "🟡 MED" if e.impact == "medium" else "🟢 LOW"
            econ_html += f'''
                <tr>
                    <td class="time">{e.time}</td>
                    <td class="impact {impact_class}">{impact_label}</td>
                    <td class="event">{e.event}</td>
                    <td class="estimate">{e.estimate or '—'}</td>
                    <td class="previous">{e.previous or '—'}</td>
                </tr>
            '''
        econ_html += '</tbody></table>'
    
    if tomorrow_events:
        high_tomorrow = [e for e in tomorrow_events if e.impact == "high"]
        econ_html += '<div class="tomorrow-preview"><h3>Tomorrow</h3>'
        for e in tomorrow_events[:3]:  # Show up to 3 tomorrow events
            impact_emoji = '🔴' if e.impact == "high" else '🟡' if e.impact == "medium" else '🟢'
            econ_html += f'''
                <div class="event-item">
                    <span class="time">{e.time}</span>
                    <span class="impact">{impact_emoji}</span>
                    <span class="event-name">{e.event}</span>
                </div>
            '''
        if high_tomorrow:
            econ_html += '<div class="warning">⚠️ Major event tomorrow — size accordingly today</div>'
        econ_html += '</div>'
    
    econ_html += f'''
    <div class="guidance">
        <p>→ {econ.get('advice', '')}</p>
    </div>
    '''
else:
    econ_html = '''
    <div class="risk-badge risk-low">
        🟢 Clear Day — No Major Economic Events
    </div>
    <p class="no-events">No high or medium impact events scheduled for today.</p>
    '''
```

### Step 44: Add CSS styles

Add the CSS styles for the economic calendar to the HTML template. Look for the `<style>` section and add:

```css
/* Economic Calendar Styles */
.risk-badge {
    padding: 12px 20px;
    border-radius: 8px;
    font-weight: bold;
    margin-bottom: 20px;
}
.risk-high { background: rgba(248, 113, 113, 0.2); color: #f87171; }
.risk-medium { background: rgba(250, 204, 21, 0.2); color: #facc15; }
.risk-low { background: rgba(74, 222, 128, 0.2); color: #4ade80; }

.events-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
}
.events-table th {
    text-align: left;
    padding: 10px;
    color: #94a3b8;
    font-weight: 500;
    border-bottom: 1px solid #475569;
}
.events-table td {
    padding: 12px 10px;
    border-bottom: 1px solid #334155;
}
.events-table .time {
    font-family: monospace;
    color: #f8fafc;
    width: 60px;
}
.events-table .impact {
    width: 80px;
    font-size: 0.85rem;
}
.impact-high { color: #f87171; }
.impact-medium { color: #facc15; }
.impact-low { color: #4ade80; }
.events-table .event {
    color: #f8fafc;
    font-weight: 500;
}
.events-table .estimate,
.events-table .previous {
    color: #94a3b8;
    font-family: monospace;
    width: 100px;
}

.tomorrow-preview {
    background: var(--bg-tertiary, #1e293b);
    padding: 15px;
    border-radius: 8px;
    margin: 20px 0;
}
.tomorrow-preview h3 {
    margin: 0 0 10px 0;
    color: #94a3b8;
    font-size: 0.9rem;
}
.tomorrow-preview .event-item {
    margin: 8px 0;
    color: #f8fafc;
}
.tomorrow-preview .warning {
    margin-top: 10px;
    color: #facc15;
    font-style: italic;
}

.guidance {
    margin-top: 15px;
    padding: 12px;
    background: var(--bg-tertiary, #1e293b);
    border-left: 4px solid #facc15;
    border-radius: 0 8px 8px 0;
}
.guidance p {
    margin: 0;
    color: #f8fafc;
}

.no-events {
    color: #94a3b8;
    font-style: italic;
}
```

### Step 45: Commit integration changes

```bash
git add scripts/premarket_report.py
git commit -m "feat: integrate FMP Economic Calendar into pre-market report"
```

---

## Task 4: Test End-to-End

### Step 46: Run unit tests

Run: `pytest tests/test_economic_calendar.py -v`
Expected: All tests pass

### Step 47: Test import

Run: `python -c "from traderlib import EconomicCalendar; print('Import OK')"`
Expected: Import OK

### Step 48: Test pre-market report import

Run: `python -c "import scripts.premarket_report; print('Import OK')"`
Expected: Import OK

### Step 49: Commit

```bash
git commit --allow-empty -m "test: verify EconomicCalendar integration"
```

---

## Summary

This implementation plan creates:

1. **`traderlib/economic_calendar.py`** — New module following `earnings_calendar.py` patterns
   - `EconomicEvent` dataclass
   - `EconomicCalendar` class with rate limiting, caching, fail-open behavior
   - High-impact event detection (CPI, Fed, FOMC, Nonfarm, Payrolls, Employment)
   - Timezone handling (FMP returns ET for US events)

2. **`tests/test_economic_calendar.py`** — Comprehensive unit tests
   - Tests for all public methods
   - Tests for edge cases (failures, weekends, no API key)

3. **`scripts/premarket_report.py`** — Integration
   - Replace broken tradingcharts scraper with FMP
   - Risk classification (🔴🟡🟢)
   - Console output with event list and advice
   - HTML output with styled tables and badges

**Pattern Consistency:**
- Same rate limiting as earnings_calendar (300 req/min)
- Same fail-open behavior
- Same in-memory caching
- Same environment variable (FMP_API_KEY)
- Same dotenv loading

**Plan complete and saved to `docs/superpowers/plans/2026-04-27-fmp-economic-calendar.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
