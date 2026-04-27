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


# =============================================================================
# Sub-task 2: EconomicCalendar initialization
# =============================================================================

class TestEconomicCalendarInit:
    """Test EconomicCalendar initialization."""

    def test_accepts_api_key_argument(self):
        ec = EconomicCalendar(api_key="test_key")
        assert ec._api_key == "test_key"

    def test_reads_api_key_from_env(self):
        with patch.dict("os.environ", {"FMP_API_KEY": "env_key"}, clear=True):
            ec = EconomicCalendar()
            assert ec._api_key == "env_key"

    def test_prefers_argument_over_env(self):
        with patch.dict("os.environ", {"FMP_API_KEY": "env_key"}, clear=True):
            ec = EconomicCalendar(api_key="arg_key")
            assert ec._api_key == "arg_key"

    def test_logs_warning_when_no_key(self, caplog):
        with patch.dict("os.environ", {}, clear=True):
            with caplog.at_level(logging.WARNING):
                ec = EconomicCalendar()
        assert ec._api_key is None
        assert "FMP_API_KEY not set" in caplog.text
        assert "economic event gates disabled" in caplog.text

    def test_cache_is_empty_on_init(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._cache == {}

    def test_call_times_is_empty_on_init(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._call_times == []

    def test_high_impact_keywords_defined(self):
        ec = EconomicCalendar(api_key="key")
        expected_keywords = ["cpi", "ppi", "fed", "fomc", "nonfarm", "payrolls", "employment"]
        assert ec._HIGH_IMPACT_KEYWORDS == expected_keywords


# =============================================================================
# Sub-task 3: Rate limiting
# =============================================================================

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
        # Old calls (50.0) should be pruned, leaving only the 5 recent ones + new one
        assert len(ec._call_times) == 6

    def test_sleeps_correct_amount(self):
        ec = EconomicCalendar(api_key="key")
        ec._call_times = [100.0] * 300
        with patch("time.monotonic", return_value=159.0):  # 59 seconds after first call
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        # Should sleep for ~1.05 seconds (60 - 59 + 0.05)
        mock_sleep.assert_called_once()
        call_args = mock_sleep.call_args[0][0]
        assert 1.0 <= call_args <= 1.1

    def test_appends_new_call_time(self):
        ec = EconomicCalendar(api_key="key")
        ec._call_times = [100.0] * 299
        with patch("time.monotonic", return_value=200.0):
            ec._rate_limit()
        assert 200.0 in ec._call_times


# =============================================================================
# Sub-task 4: High-impact event detection
# =============================================================================

class TestIsHighImpactEvent:
    """Test _is_high_impact_event keyword detection."""

    def test_cpi_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("CPI MoM") is True
        assert ec._is_high_impact_event("Core CPI") is True

    def test_ppi_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("PPI MoM") is True
        assert ec._is_high_impact_event("Core PPI") is True

    def test_fed_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Fed Interest Rate Decision") is True

    def test_fomc_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("FOMC Statement") is True

    def test_nonfarm_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Nonfarm Payrolls") is True

    def test_payrolls_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("ADP Payrolls") is True

    def test_employment_is_high_impact(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Employment Report") is True

    def test_case_insensitive_matching(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("cpi mom") is True
        assert ec._is_high_impact_event("CPI MoM") is True
        assert ec._is_high_impact_event("Cpi Mom") is True
        assert ec._is_high_impact_event("FOMC STATEMENT") is True

    def test_low_impact_events_return_false(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("Retail Sales") is False
        assert ec._is_high_impact_event("Consumer Confidence") is False
        assert ec._is_high_impact_event("Durable Goods Orders") is False

    def test_empty_string_returns_false(self):
        ec = EconomicCalendar(api_key="key")
        assert ec._is_high_impact_event("") is False


# =============================================================================
# Sub-task 5: Impact classification
# =============================================================================

class TestClassifyImpact:
    """Test _classify_impact method."""

    def test_fmp_high_impact_returns_high(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="Some Event",
            impact="high",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "high"

    def test_keyword_high_impact_returns_high(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI Report",
            impact="medium",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "high"

    def test_fmp_medium_no_keyword_returns_medium(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="Retail Sales",
            impact="medium",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "medium"

    def test_fmp_low_no_keyword_returns_low(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="Factory Orders",
            impact="low",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "low"

    def test_high_impact_case_insensitive(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="FOMC Statement",
            impact="HIGH",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "high"

    def test_medium_impact_case_insensitive(self):
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="Some Event",
            impact="MEDIUM",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "medium"

    def test_combined_fmp_and_keyword_detection(self):
        """If FMP says high AND keywords indicate high, still return high."""
        ec = EconomicCalendar(api_key="key")
        event = EconomicEvent(
            date="2026-04-27",
            time="08:30",
            event="CPI MoM",
            impact="high",
            estimate=None,
            previous=None
        )
        assert ec._classify_impact(event) == "high"
