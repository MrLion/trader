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


# =============================================================================
# Sub-task 6: get_events method
# =============================================================================

class TestGetEvents:
    """Test get_events method with caching and fetching."""

    def test_cache_hit_returns_cached_events(self):
        ec = EconomicCalendar(api_key="key")
        cached_events = [
            EconomicEvent(date="2026-04-27", time="08:30", event="CPI", impact="high", estimate="0.3%", previous="0.2%")
        ]
        ec._cache["2026-04-27:2026-04-27"] = cached_events

        with patch("traderlib.economic_calendar.requests.get") as mock_get:
            result = ec.get_events(date(2026, 4, 27))

        assert result == cached_events
        mock_get.assert_not_called()

    def test_cache_miss_fetches_and_stores(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": "0.3%", "previous": "0.2%"}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
            result = ec.get_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "CPI"
        assert ec._cache["2026-04-27:2026-04-27"] == result
        mock_get.assert_called_once()

    def test_cache_miss_no_key_returns_empty_list(self):
        with patch.dict("os.environ", {}, clear=True):
            ec = EconomicCalendar()
            with patch("traderlib.economic_calendar.requests.get") as mock_get:
                result = ec.get_events(date(2026, 4, 27))
        assert result == []
        mock_get.assert_not_called()

    def test_fetch_failure_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        with patch("traderlib.economic_calendar.requests.get", side_effect=Exception("timeout")):
            result = ec.get_events(date(2026, 4, 27))
        assert result == []

    def test_fetch_malformed_record_is_skipped(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high"},  # missing estimate/previous
            {"invalid": "data"},  # malformed
            {"date": "2026-04-27", "time": "14:00", "event": "FOMC", "impact": "high", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27))

        assert len(result) == 2
        assert result[0].event == "CPI"
        assert result[1].event == "FOMC"

    def test_fetch_empty_list_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27))

        assert result == []

    def test_fetch_non_list_response_returns_empty_list(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad request"}
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27))

        assert result == []

    def test_weekend_returns_empty_list_no_api_call(self):
        ec = EconomicCalendar(api_key="key")
        with patch("traderlib.economic_calendar.requests.get") as mock_get:
            # Saturday
            result = ec.get_events(date(2026, 4, 25))
            assert result == []
            # Sunday
            result = ec.get_events(date(2026, 4, 26))
            assert result == []
        mock_get.assert_not_called()

    def test_weekday_does_make_api_call(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
            ec.get_events(date(2026, 4, 27))  # Monday

        mock_get.assert_called_once()

    def test_url_construction_correct(self):
        ec = EconomicCalendar(api_key="test_api_key_123")
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
        assert call_args[1]["params"]["apikey"] == "test_api_key_123"
        assert call_args[1]["timeout"] == 5

    def test_date_range_with_end_date(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-28", "time": "08:30", "event": "GDP", "impact": "high", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27), date(2026, 4, 28))

        assert len(result) == 2

    def test_default_end_date_equals_start(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
            ec.get_events(date(2026, 4, 27))  # No end date

        call_args = mock_get.call_args
        assert call_args[1]["params"]["from"] == "2026-04-27"
        assert call_args[1]["params"]["to"] == "2026-04-27"

    def test_events_sorted_by_date_and_time(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "14:00", "event": "FOMC", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-26", "time": "10:00", "event": "Retail", "impact": "low", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 26), date(2026, 4, 27))

        assert len(result) == 3
        assert result[0].event == "Retail"  # Apr 26
        assert result[1].event == "CPI"     # Apr 27, 08:30
        assert result[2].event == "FOMC"    # Apr 27, 14:00

    def test_response_with_missing_fields(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        # Some fields may be missing from FMP response
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high"}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].estimate is None
        assert result[0].previous is None


# =============================================================================
# Sub-task 7: Convenience methods
# =============================================================================

class TestConvenienceMethods:
    """Test convenience methods: get_today_events, get_tomorrow_events, get_high_impact_events."""

    def test_get_today_events_calls_get_events_with_today(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 27)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
                result = ec.get_today_events()

        assert len(result) == 1
        call_args = mock_get.call_args
        assert call_args[1]["params"]["from"] == "2026-04-27"
        assert call_args[1]["params"]["to"] == "2026-04-27"

    def test_get_tomorrow_events_calls_get_events_with_tomorrow(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-28", "time": "08:30", "event": "GDP", "impact": "high", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.date") as mock_date:
            mock_date.today.return_value = date(2026, 4, 27)
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            with patch("traderlib.economic_calendar.requests.get", return_value=mock_response) as mock_get:
                result = ec.get_tomorrow_events()

        assert len(result) == 1
        call_args = mock_get.call_args
        assert call_args[1]["params"]["from"] == "2026-04-28"
        assert call_args[1]["params"]["to"] == "2026-04-28"

    def test_get_high_impact_events_filters_low_and_medium(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-27", "time": "10:00", "event": "Retail Sales", "impact": "medium", "estimate": None, "previous": None},
            {"date": "2026-04-27", "time": "12:00", "event": "Factory Orders", "impact": "low", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_high_impact_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "CPI"

    def test_get_high_impact_events_detects_keywords(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "FOMC Statement", "impact": "medium", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_high_impact_events(date(2026, 4, 27))

        assert len(result) == 1
        assert result[0].event == "FOMC Statement"

    def test_get_high_impact_events_with_date_range(self):
        ec = EconomicCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-04-27", "time": "08:30", "event": "CPI", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-28", "time": "08:30", "event": "GDP", "impact": "high", "estimate": None, "previous": None},
            {"date": "2026-04-28", "time": "10:00", "event": "Retail", "impact": "low", "estimate": None, "previous": None}
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.economic_calendar.requests.get", return_value=mock_response):
            result = ec.get_high_impact_events(date(2026, 4, 27), date(2026, 4, 28))

        assert len(result) == 2
        assert result[0].event == "CPI"
        assert result[1].event == "GDP"

    def test_clear_cache_removes_all_entries(self):
        ec = EconomicCalendar(api_key="key")
        ec._cache["key1"] = []
        ec._cache["key2"] = []
        ec.clear_cache()
        assert ec._cache == {}

    def test_invalidate_removes_specific_range(self):
        ec = EconomicCalendar(api_key="key")
        ec._cache["2026-04-27:2026-04-27"] = []
        ec._cache["2026-04-28:2026-04-28"] = []
        ec.invalidate(date(2026, 4, 27))
        assert "2026-04-27:2026-04-27" not in ec._cache
        assert "2026-04-28:2026-04-28" in ec._cache
