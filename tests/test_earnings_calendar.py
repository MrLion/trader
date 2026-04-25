#!/usr/bin/env python3
"""Tests for earnings_calendar module.

Covers:
1. _prev_trading_day weekend skipping
2. EarningsCalendar initialization (API key, fail-open)
3. In-memory cache behavior (hit, miss, prefetch, invalidate)
4. Rate limiting (token bucket)
5. FMP fetch logic (success, empty, malformed, timeout, no key)
6. Blackout and force-exit date logic
"""

import logging
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from traderlib.earnings_calendar import EarningsCalendar, _prev_trading_day

# Fixed "today" for all fetch tests so mock dates are consistently in the future
_FAKE_TODAY = date(2026, 4, 1)


@pytest.fixture
def fixed_today():
    """Patch date.today() inside earnings_calendar to a fixed value."""
    with patch("traderlib.earnings_calendar.date") as mock_date:
        mock_date.today.return_value = _FAKE_TODAY
        mock_date.fromisoformat = date.fromisoformat
        yield mock_date


class TestPrevTradingDay:
    """Test _prev_trading_day helper."""

    def test_monday_returns_friday(self):
        monday = date(2024, 1, 8)
        assert _prev_trading_day(monday) == date(2024, 1, 5)

    def test_tuesday_returns_monday(self):
        tuesday = date(2024, 1, 9)
        assert _prev_trading_day(tuesday) == date(2024, 1, 8)

    def test_sunday_returns_friday(self):
        sunday = date(2024, 1, 7)
        assert _prev_trading_day(sunday) == date(2024, 1, 5)

    def test_saturday_returns_friday(self):
        saturday = date(2024, 1, 6)
        assert _prev_trading_day(saturday) == date(2024, 1, 5)

    def test_friday_returns_thursday(self):
        friday = date(2024, 1, 5)
        assert _prev_trading_day(friday) == date(2024, 1, 4)


class TestInit:
    """Test EarningsCalendar initialization."""

    def test_accepts_api_key_argument(self):
        ec = EarningsCalendar(api_key="test_key")
        assert ec._api_key == "test_key"

    def test_reads_api_key_from_env(self):
        with patch.dict("os.environ", {"FMP_API_KEY": "env_key"}, clear=True):
            ec = EarningsCalendar()
            assert ec._api_key == "env_key"

    def test_logs_warning_when_no_key(self, caplog):
        with patch.dict("os.environ", {}, clear=True):
            with caplog.at_level(logging.WARNING):
                ec = EarningsCalendar()
        assert ec._api_key is None
        assert "FMP_API_KEY not set" in caplog.text

    def test_cache_is_empty_on_init(self):
        ec = EarningsCalendar(api_key="key")
        assert ec._cache == {}

    def test_call_times_is_empty_on_init(self):
        ec = EarningsCalendar(api_key="key")
        assert ec._call_times == []


class TestGetNextEarnings:
    """Test get_next_earnings cache and fetch behavior."""

    def test_cache_hit_returns_cached_date(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        with patch("traderlib.earnings_calendar.requests.get") as mock_get:
            result = ec.get_next_earnings("AAPL")
        assert result == date(2026, 7, 25)
        mock_get.assert_not_called()

    def test_cache_miss_fetches_and_stores(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [{"date": "2026-07-25", "epsActual": None}]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response) as mock_get:
            result = ec.get_next_earnings("AAPL")

        assert result == date(2026, 7, 25)
        assert ec._cache["AAPL"] == date(2026, 7, 25)
        mock_get.assert_called_once()

    def test_cache_miss_no_key_returns_none(self):
        with patch.dict("os.environ", {}, clear=True):
            ec = EarningsCalendar()
            with patch("traderlib.earnings_calendar.requests.get") as mock_get:
                result = ec.get_next_earnings("AAPL")
        assert result is None
        mock_get.assert_not_called()

    def test_fetch_failure_returns_none(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        with patch("traderlib.earnings_calendar.requests.get", side_effect=Exception("timeout")):
            result = ec.get_next_earnings("AAPL")
        assert result is None

    def test_fetch_returns_none_for_past_earnings_only(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [{"date": "2020-01-15", "epsActual": None}]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response):
            result = ec.get_next_earnings("AAPL")

        assert result is None

    def test_fetch_filters_out_reported_earnings(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "2026-07-20", "epsActual": 1.5},
            {"date": "2026-07-25", "epsActual": None},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response):
            result = ec.get_next_earnings("AAPL")

        assert result == date(2026, 7, 25)

    def test_fetch_malformed_date_is_skipped(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"date": "not-a-date", "epsActual": None},
            {"date": "2026-07-25", "epsActual": None},
        ]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response):
            result = ec.get_next_earnings("AAPL")

        assert result == date(2026, 7, 25)

    def test_fetch_empty_list_returns_none(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response):
            result = ec.get_next_earnings("AAPL")

        assert result is None

    def test_fetch_non_list_response_returns_none(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad request"}
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response):
            result = ec.get_next_earnings("AAPL")

        assert result is None


class TestIsEarningsBlackout:
    """Test is_earnings_blackout."""

    def test_true_on_earnings_date(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        assert ec.is_earnings_blackout("AAPL", date(2026, 7, 25)) is True

    def test_false_when_no_earnings(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = None
        assert ec.is_earnings_blackout("AAPL", date(2026, 7, 25)) is False

    def test_false_on_different_date(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        assert ec.is_earnings_blackout("AAPL", date(2026, 7, 24)) is False


class TestShouldForceExit:
    """Test should_force_exit logic."""

    def test_true_day_before_earnings(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        assert ec.should_force_exit("AAPL", date(2026, 7, 24)) is True

    def test_true_friday_before_monday_earnings(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 27)  # Monday
        assert ec.should_force_exit("AAPL", date(2026, 7, 24)) is True  # Friday

    def test_false_on_earnings_date(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        assert ec.should_force_exit("AAPL", date(2026, 7, 25)) is False

    def test_false_when_no_earnings(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = None
        assert ec.should_force_exit("AAPL", date(2026, 7, 24)) is False

    def test_false_two_days_before(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        assert ec.should_force_exit("AAPL", date(2026, 7, 23)) is False


class TestPrefetch:
    """Test prefetch bulk cache warming."""

    def test_prefetch_fetches_uncached_tickers(self, fixed_today):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)

        mock_response = MagicMock()
        mock_response.json.return_value = [{"date": "2026-08-01", "epsActual": None}]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response) as mock_get:
            ec.prefetch(["AAPL", "MSFT"])

        assert ec._cache["MSFT"] == date(2026, 8, 1)
        assert mock_get.call_count == 1

    def test_prefetch_no_key_does_nothing(self):
        with patch.dict("os.environ", {}, clear=True):
            ec = EarningsCalendar()
            with patch("traderlib.earnings_calendar.requests.get") as mock_get:
                ec.prefetch(["AAPL", "MSFT"])
        mock_get.assert_not_called()


class TestInvalidate:
    """Test invalidate cache removal."""

    def test_invalidate_removes_ticker(self):
        ec = EarningsCalendar(api_key="key")
        ec._cache["AAPL"] = date(2026, 7, 25)
        ec.invalidate("AAPL")
        assert "AAPL" not in ec._cache

    def test_invalidate_unknown_ticker_no_error(self):
        ec = EarningsCalendar(api_key="key")
        ec.invalidate("UNKNOWN")
        assert "UNKNOWN" not in ec._cache


class TestRateLimit:
    """Test internal rate limiting."""

    def test_no_sleep_when_under_limit(self):
        ec = EarningsCalendar(api_key="key")
        ec._call_times = [100.0] * 299
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_not_called()
        assert len(ec._call_times) == 300

    def test_sleeps_when_at_limit(self):
        ec = EarningsCalendar(api_key="key")
        ec._call_times = [100.0] * 300
        with patch("time.monotonic", return_value=120.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_called_once()
        assert len(ec._call_times) == 301

    def test_prunes_old_calls(self):
        ec = EarningsCalendar(api_key="key")
        ec._call_times = [50.0] * 300 + [120.0] * 5
        with patch("time.monotonic", return_value=130.0):
            with patch("time.sleep") as mock_sleep:
                ec._rate_limit()
        mock_sleep.assert_not_called()

    def test_rate_limit_url_construction(self, fixed_today):
        ec = EarningsCalendar(api_key="key123")
        mock_response = MagicMock()
        mock_response.json.return_value = [{"date": "2026-07-25", "epsActual": None}]
        mock_response.raise_for_status.return_value = None

        with patch("traderlib.earnings_calendar.requests.get", return_value=mock_response) as mock_get:
            ec.get_next_earnings("AAPL")

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "financialmodelingprep.com/stable/earnings" in call_args[0][0]
        assert call_args[1]["params"]["symbol"] == "AAPL"
        assert call_args[1]["params"]["apikey"] == "key123"
