#!/usr/bin/env python3
"""Tests for market hours calendar — holiday detection, format_market_status, next_market_open.

Targets uncovered paths in traderlib/market_hours.py:
- Calendar-based trading day detection (holiday, weekday, weekend)
- get_market_schedule with calendar and fallback
- format_market_status branches (open, weekend, holiday, pre-market, after-hours)
- next_market_open edge cases (friday evening, pre-market same day, holiday boundary)
"""

import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytz
import pytest


from traderlib.market_hours import MarketHours, MARKET_TZ


ET = pytz.timezone('America/New_York')


def make_market_hours(with_calendar=True):
    """Create MarketHours instance with optional calendar mock."""
    mh = MarketHours.__new__(MarketHours)
    mh.exchange = 'NYSE'

    if with_calendar:
        mh._calendar = Mock()
    else:
        mh._calendar = None

    return mh


def et_dt(year, month, day, hour=0, minute=0, second=0):
    """Create timezone-aware datetime in Eastern Time."""
    return ET.localize(datetime(year, month, day, hour, minute, second))


class TestIsTradingDay:
    """Test is_trading_day with calendar and fallback."""

    def test_weekday_is_trading_day_no_calendar(self):
        """Regular weekday is a trading day (no calendar)."""
        mh = make_market_hours(with_calendar=False)
        # Monday April 8, 2024
        assert mh.is_trading_day(et_dt(2024, 4, 8)) is True

    def test_weekend_is_not_trading_day(self):
        """Weekend is never a trading day."""
        mh = make_market_hours(with_calendar=False)
        # Saturday
        assert mh.is_trading_day(et_dt(2024, 4, 6)) is False
        # Sunday
        assert mh.is_trading_day(et_dt(2024, 4, 7)) is False

    def test_holiday_is_not_trading_day_with_calendar(self):
        """Holiday returns False when calendar says no session."""
        mh = make_market_hours(with_calendar=True)
        # July 4th, 2024 is a holiday
        mock_schedule = MagicMock()
        mock_schedule.__len__ = Mock(return_value=0)
        mh._calendar.schedule.return_value = mock_schedule

        assert mh.is_trading_day(et_dt(2024, 7, 4)) is False

    def test_weekday_is_trading_day_with_calendar(self):
        """Regular weekday returns True when calendar says session exists."""
        mh = make_market_hours(with_calendar=True)
        mock_schedule = MagicMock()
        mock_schedule.__len__ = Mock(return_value=1)
        mh._calendar.schedule.return_value = mock_schedule

        assert mh.is_trading_day(et_dt(2024, 4, 8)) is True

    def test_default_uses_current_time(self):
        """No date argument uses current time."""
        mh = make_market_hours(with_calendar=False)
        # Should not raise
        result = mh.is_trading_day()
        assert isinstance(result, bool)


class TestGetMarketSchedule:
    """Test get_market_schedule with calendar and fallback."""

    def test_non_trading_day_returns_none(self):
        """Non-trading day returns None."""
        mh = make_market_hours(with_calendar=False)
        # Saturday
        result = mh.get_market_schedule(et_dt(2024, 4, 6))
        assert result is None

    def test_fallback_standard_hours(self):
        """Without calendar, returns standard 9:30-16:00 hours."""
        mh = make_market_hours(with_calendar=False)
        result = mh.get_market_schedule(et_dt(2024, 4, 8))  # Monday

        assert result is not None
        open_time, close_time = result
        assert open_time.tzinfo is not None
        assert close_time.tzinfo is not None
        # Verify times
        assert open_time.hour == 9 and open_time.minute == 30
        assert close_time.hour == 16 and close_time.minute == 0

    def test_calendar_returns_schedule(self):
        """With calendar, returns schedule from pandas_market_calendars."""
        mh = make_market_hours(with_calendar=True)

        open_time = et_dt(2024, 4, 8, 9, 30)
        close_time = et_dt(2024, 4, 8, 16, 0)

        mock_schedule = MagicMock()
        mock_schedule.__len__ = Mock(return_value=1)
        mock_schedule.iloc = [Mock()]
        mock_schedule.iloc[0].__getitem__ = Mock(side_effect=lambda key: {
            'market_open': open_time,
            'market_close': close_time,
        }[key])
        mh._calendar.schedule.return_value = mock_schedule

        result = mh.get_market_schedule(et_dt(2024, 4, 8))
        assert result is not None
        returned_open, returned_close = result
        assert returned_open.hour == 9
        assert returned_close.hour == 16

    def test_calendar_empty_schedule_returns_none(self):
        """Calendar returns None when schedule is empty (holiday)."""
        mh = make_market_hours(with_calendar=True)
        mock_schedule = MagicMock()
        mock_schedule.__len__ = Mock(return_value=0)
        mh._calendar.schedule.return_value = mock_schedule

        # July 4th is a holiday, is_trading_day returns False
        # so get_market_schedule should return None early
        result = mh.get_market_schedule(et_dt(2024, 7, 4))
        assert result is None

    def test_calendar_exception_falls_back_to_standard(self):
        """Calendar exception falls back to standard hours."""
        mh = make_market_hours(with_calendar=True)
        # Make calendar.schedule raise only on the get_market_schedule call,
        # not on is_trading_day. is_trading_day calls schedule with date args.
        # We need is_trading_day to return True (weekday), then get_market_schedule
        # to fail on the calendar path.
        call_count = [0]

        def schedule_side_effect(start_date, end_date):
            call_count[0] += 1
            if call_count[0] == 1:
                # is_trading_day call: return non-empty schedule (trading day)
                mock_schedule = MagicMock()
                mock_schedule.__len__ = Mock(return_value=1)
                return mock_schedule
            else:
                # get_market_schedule calendar path: raise exception
                raise Exception("Calendar error")

        mh._calendar.schedule.side_effect = schedule_side_effect

        result = mh.get_market_schedule(et_dt(2024, 4, 8))
        assert result is not None
        open_time, close_time = result
        assert open_time.hour == 9 and open_time.minute == 30


class TestIsMarketOpen:
    """Test is_market_open with various scenarios."""

    def test_market_hours_open(self):
        """During market hours, returns True."""
        mh = make_market_hours(with_calendar=False)
        # Monday at 10:00 AM
        assert mh.is_market_open(et_dt(2024, 4, 8, 10, 0)) is True

    def test_market_hours_after_close(self):
        """After market close, returns False."""
        mh = make_market_hours(with_calendar=False)
        # Monday at 5:00 PM
        assert mh.is_market_open(et_dt(2024, 4, 8, 17, 0)) is False

    def test_weekend_always_false(self):
        """Weekend is always False."""
        mh = make_market_hours(with_calendar=False)
        assert mh.is_market_open(et_dt(2024, 4, 6, 10, 0)) is False

    def test_naive_datetime_localized(self):
        """Naive datetime gets localized to ET."""
        mh = make_market_hours(with_calendar=False)
        naive = datetime(2024, 4, 8, 10, 0)
        result = mh.is_market_open(naive)
        assert isinstance(result, bool)

    def test_holiday_returns_false_with_calendar(self):
        """Holiday returns False."""
        mh = make_market_hours(with_calendar=True)
        mock_schedule = MagicMock()
        mock_schedule.__len__ = Mock(return_value=0)
        mh._calendar.schedule.return_value = mock_schedule

        assert mh.is_market_open(et_dt(2024, 7, 4, 10, 0)) is False


class TestFormatMarketStatus:
    """Test format_market_status branches."""

    def test_market_open_status(self):
        """During market hours, shows OPEN with close time."""
        mh = make_market_hours(with_calendar=False)
        result = mh.format_market_status(et_dt(2024, 4, 8, 10, 0))
        assert "OPEN" in result
        assert "16:00" in result

    def test_weekend_status(self):
        """Weekend shows CLOSED (Weekend) with next open."""
        mh = make_market_hours(with_calendar=False)
        result = mh.format_market_status(et_dt(2024, 4, 6, 10, 0))
        assert "CLOSED" in result
        assert "Weekend" in result

    def test_holiday_status_with_calendar(self):
        """Holiday shows CLOSED (Holiday) when calendar identifies non-trading weekday."""
        mh = make_market_hours(with_calendar=True)
        # July 4th is a Thursday (weekday), but calendar says no session.
        # July 5th (Friday) IS a trading day so next_market_open can find it.
        from datetime import date

        def schedule_side_effect(start_date, end_date):
            sd = start_date if isinstance(start_date, date) else date.fromisoformat(str(start_date))
            mock_schedule = MagicMock()
            # July 4th: no session (holiday)
            if sd == date(2024, 7, 4):
                mock_schedule.__len__ = Mock(return_value=0)
            else:
                # Other days: has session
                mock_schedule.__len__ = Mock(return_value=1)
                next_open = et_dt(sd.year, sd.month, sd.day, 9, 30)
                next_close = et_dt(sd.year, sd.month, sd.day, 16, 0)
                mock_schedule.iloc = [Mock()]
                mock_schedule.iloc[0].__getitem__ = Mock(side_effect=lambda key: {
                    'market_open': next_open,
                    'market_close': next_close,
                }[key])
            return mock_schedule

        mh._calendar.schedule.side_effect = schedule_side_effect

        result = mh.format_market_status(et_dt(2024, 7, 4, 10, 0))
        assert "CLOSED" in result
        assert "Holiday" in result

    def test_pre_market_status(self):
        """Before market open shows CLOSED with open time."""
        mh = make_market_hours(with_calendar=False)
        result = mh.format_market_status(et_dt(2024, 4, 8, 8, 0))
        assert "CLOSED" in result
        assert "09:30" in result

    def test_after_hours_status(self):
        """After market close shows CLOSED with next open."""
        mh = make_market_hours(with_calendar=False)
        result = mh.format_market_status(et_dt(2024, 4, 8, 17, 0))
        assert "CLOSED" in result

    def test_naive_datetime_handled(self):
        """Naive datetime is properly localized."""
        mh = make_market_hours(with_calendar=False)
        naive = datetime(2024, 4, 8, 10, 0)
        result = mh.format_market_status(naive)
        assert isinstance(result, str)
        assert len(result) > 0


class TestNextMarketOpen:
    """Test next_market_open edge cases."""

    def test_friday_evening_returns_monday(self):
        """Friday evening returns Monday open."""
        mh = make_market_hours(with_calendar=False)
        result = mh.next_market_open(et_dt(2024, 4, 5, 17, 0))  # Friday 5 PM
        assert result is not None
        assert result.weekday() == 0  # Monday
        assert result.hour == 9 and result.minute == 30

    def test_pre_market_same_day(self):
        """Before market open on trading day returns today's open."""
        mh = make_market_hours(with_calendar=False)
        result = mh.next_market_open(et_dt(2024, 4, 8, 8, 0))  # Monday 8 AM
        assert result is not None
        assert result.date() == datetime(2024, 4, 8).date()
        assert result.hour == 9 and result.minute == 30

    def test_during_market_returns_now(self):
        """During market hours returns current time."""
        mh = make_market_hours(with_calendar=False)
        now = et_dt(2024, 4, 8, 10, 0)
        result = mh.next_market_open(now)
        assert result is not None
        # Should return approximately now (the exact time)
        assert result.date() == now.date()

    def test_naive_datetime_handled(self):
        """Naive datetime is properly localized."""
        mh = make_market_hours(with_calendar=False)
        naive = datetime(2024, 4, 8, 8, 0)
        result = mh.next_market_open(naive)
        assert result is not None


class TestGetTradingDays:
    """Test get_trading_days with calendar and fallback."""

    def test_fallback_returns_weekdays(self):
        """Without calendar, returns all weekdays in range."""
        mh = make_market_hours(with_calendar=False)
        start = et_dt(2024, 4, 8)   # Monday
        end = et_dt(2024, 4, 12)    # Friday

        days = mh.get_trading_days(start, end)
        assert len(days) == 5  # Mon-Fri

    def test_excludes_weekends(self):
        """Weekends are excluded from trading days."""
        mh = make_market_hours(with_calendar=False)
        start = et_dt(2024, 4, 5)   # Friday
        end = et_dt(2024, 4, 8)     # Monday

        days = mh.get_trading_days(start, end)
        # Should include Friday and Monday, not Saturday/Sunday
        assert len(days) == 2

    def test_calendar_returns_schedule_dates(self):
        """With calendar, returns dates from schedule."""
        mh = make_market_hours(with_calendar=True)

        import pandas as pd
        mock_schedule = MagicMock()
        mock_schedule.index = pd.DatetimeIndex(['2024-04-08', '2024-04-09', '2024-04-10'])
        mh._calendar.schedule.return_value = mock_schedule

        start = et_dt(2024, 4, 8)
        end = et_dt(2024, 4, 10)

        days = mh.get_trading_days(start, end)
        assert len(days) == 3

    def test_calendar_exception_falls_back(self):
        """Calendar exception falls back to weekday calculation."""
        mh = make_market_hours(with_calendar=True)
        mh._calendar.schedule.side_effect = Exception("Calendar error")

        start = et_dt(2024, 4, 8)
        end = et_dt(2024, 4, 12)

        days = mh.get_trading_days(start, end)
        assert len(days) == 5  # Mon-Fri fallback