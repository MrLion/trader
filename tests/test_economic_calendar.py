#!/usr/bin/env python3
"""Tests for economic_calendar module.

Covers:
1. EconomicEvent dataclass
2. EconomicCalendar initialization (API key, fail-open)
3. Rate limiting (token bucket)
4. High-impact event detection
5. Impact classification
6. get_events with caching and fetching
7. Convenience methods (today, tomorrow, high-impact)
"""

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from traderlib.economic_calendar import EconomicCalendar, EconomicEvent


# =============================================================================
# Sub-task 1: EconomicEvent dataclass
# =============================================================================

class TestEconomicEvent:
    """Test EconomicEvent dataclass."""

    def test_create_event_with_all_fields(self):
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        assert event.date == "2026-04-27"
        assert event.time == "08:30"
        assert event.event == "CPI MoM"
        assert event.impact == "high"
        assert event.estimate == "0.3%"
        assert event.previous == "0.2%"

    def test_create_event_with_optional_fields_none(self):
        event = EconomicEvent(
            date="2026-04-27",
            time="09:45",
            event="Manufacturing PMI",
            impact="medium",
            estimate=None,
            previous=None
        )
        assert event.date == "2026-04-27"
        assert event.time == "09:45"
        assert event.event == "Manufacturing PMI"
        assert event.impact == "medium"
        assert event.estimate is None
        assert event.previous is None

    def test_event_is_immutable(self):
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        with pytest.raises(AttributeError):
            event.event = "PPI MoM"

    def test_event_equality(self):
        event1 = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        event2 = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        event3 = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="PPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        assert event1 == event2
        assert event1 != event3

    def test_event_repr(self):
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate="0.3%",
            previous="0.2%"
        )
        repr_str = repr(event)
        assert "EconomicEvent" in repr_str
        assert "CPI MoM" in repr_str
