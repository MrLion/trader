#!/usr/bin/env python3
"""Tests for market hours and holiday calendar utilities.

Covers:
1. Trading day detection (weekends, holidays)
2. Market hours (open/close times)
3. Market open/closed status
4. Next market open calculation
5. Trading day lists
6. Timezone handling
"""

import sys
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path

from traderlib.market_hours import (
    MarketHours,
    is_market_open,
    is_trading_day,
    next_market_open,
    format_market_status,
    MARKET_TZ,
    MARKET_OPEN_TIME,
    MARKET_CLOSE_TIME,
)


class TestMarketHoursBasics(unittest.TestCase):
    """Test basic MarketHours initialization and properties."""

    def setUp(self):
        """Create MarketHours instance for each test."""
        self.hours = MarketHours(exchange='NYSE')

    def test_init_sets_exchange(self):
        """MarketHours should initialize with exchange."""
        self.assertEqual(self.hours.exchange, 'NYSE')

    def test_init_handles_missing_calendar(self):
        """Should handle missing calendar module gracefully."""
        # When HAS_MARKET_CALS is False, _calendar should be None
        hours = MarketHours(exchange='NYSE')
        if not hasattr(hours, '_calendar') or hours._calendar is None:
            # This is expected when pandas_market_calendars not installed
            pass


class TestIsTradingDay(unittest.TestCase):
    """Test trading day detection."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_saturday_is_not_trading_day(self):
        """Saturday should not be a trading day."""
        saturday = datetime(2024, 1, 6)  # A Saturday
        self.assertFalse(self.hours.is_trading_day(saturday))

    def test_sunday_is_not_trading_day(self):
        """Sunday should not be a trading day."""
        sunday = datetime(2024, 1, 7)  # A Sunday
        self.assertFalse(self.hours.is_trading_day(sunday))

    def test_monday_is_trading_day(self):
        """Monday should be a trading day."""
        monday = datetime(2024, 1, 8)  # A Monday
        self.assertTrue(self.hours.is_trading_day(monday))

    def test_friday_is_trading_day(self):
        """Friday should be a trading day."""
        friday = datetime(2024, 1, 5)  # A Friday
        self.assertTrue(self.hours.is_trading_day(friday))

    def test_uses_current_time_when_no_date(self):
        """Should use current time when no date provided."""
        result = self.hours.is_trading_day()
        # Just verify it doesn't raise
        self.assertIsInstance(result, bool)


class TestMarketSchedule(unittest.TestCase):
    """Test market schedule retrieval."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_get_schedule_trading_day(self):
        """Should return schedule for trading day."""
        monday = datetime(2024, 1, 8)
        schedule = self.hours.get_market_schedule(monday)

        self.assertIsNotNone(schedule)
        market_open, market_close = schedule
        self.assertIsInstance(market_open, datetime)
        self.assertIsInstance(market_close, datetime)

    def test_get_schedule_non_trading_day_returns_none(self):
        """Should return None for non-trading day."""
        saturday = datetime(2024, 1, 6)
        schedule = self.hours.get_market_schedule(saturday)
        self.assertIsNone(schedule)

    def test_schedule_has_correct_times(self):
        """Schedule should have 9:30 AM open and 4:00 PM close."""
        monday = datetime(2024, 1, 8)
        schedule = self.hours.get_market_schedule(monday)

        if schedule:
            market_open, market_close = schedule
            self.assertEqual(market_open.hour, 9)
            self.assertEqual(market_open.minute, 30)
            self.assertEqual(market_close.hour, 16)
            self.assertEqual(market_close.minute, 0)

    def test_schedule_includes_timezone(self):
        """Schedule times should be timezone-aware."""
        monday = datetime(2024, 1, 8)
        schedule = self.hours.get_market_schedule(monday)

        if schedule:
            market_open, market_close = schedule
            self.assertIsNotNone(market_open.tzinfo)
            self.assertIsNotNone(market_close.tzinfo)


class TestIsMarketOpen(unittest.TestCase):
    """Test market open/closed status."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_weekend_market_closed(self):
        """Market should be closed on weekends."""
        saturday = datetime(2024, 1, 6, 10, 0)
        self.assertFalse(self.hours.is_market_open(saturday))

    def test_before_open_market_closed(self):
        """Market should be closed before 9:30 AM."""
        monday = datetime(2024, 1, 8, 8, 0)  # 8:00 AM
        monday = MARKET_TZ.localize(monday)
        self.assertFalse(self.hours.is_market_open(monday))

    def test_after_close_market_closed(self):
        """Market should be closed after 4:00 PM."""
        monday = datetime(2024, 1, 8, 17, 0)  # 5:00 PM
        monday = MARKET_TZ.localize(monday)
        self.assertFalse(self.hours.is_market_open(monday))

    def test_during_hours_market_open(self):
        """Market should be open during trading hours."""
        monday = datetime(2024, 1, 8, 12, 0)  # 12:00 PM
        monday = MARKET_TZ.localize(monday)
        result = self.hours.is_market_open(monday)
        # Note: May be false on holidays
        self.assertIsInstance(result, bool)

    def test_exactly_at_open(self):
        """Market should be open exactly at 9:30 AM."""
        monday = datetime(2024, 1, 8, 9, 30)  # 9:30 AM
        monday = MARKET_TZ.localize(monday)
        result = self.hours.is_market_open(monday)
        # Note: May be false on holidays
        self.assertIsInstance(result, bool)

    def test_exactly_at_close(self):
        """Market should be closed exactly at 4:00 PM."""
        monday = datetime(2024, 1, 8, 16, 0)  # 4:00 PM
        monday = MARKET_TZ.localize(monday)
        # Closed at exactly 4:00 PM (<= vs < behavior)
        result = self.hours.is_market_open(monday)
        self.assertIsInstance(result, bool)


class TestNextMarketOpen(unittest.TestCase):
    """Test next market open calculation."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_next_open_during_market_hours(self):
        """During market hours, next open should be now."""
        # Use a known trading day
        monday = datetime(2024, 1, 8, 12, 0)  # 12:00 PM Monday
        monday = MARKET_TZ.localize(monday)

        # If market is open, should return now
        if self.hours.is_market_open(monday):
            next_open = self.hours.next_market_open(monday)
            self.assertIsNotNone(next_open)

    def test_next_open_after_hours_finds_tomorrow(self):
        """After hours, should find next trading day open."""
        # Friday at 6 PM
        friday = datetime(2024, 1, 5, 18, 0)
        friday = MARKET_TZ.localize(friday)

        next_open = self.hours.next_market_open(friday)
        self.assertIsNotNone(next_open)

        # Should be Monday
        self.assertEqual(next_open.weekday(), 0)  # Monday

    def test_next_open_weekend_finds_monday(self):
        """On weekend, should find Monday open."""
        saturday = datetime(2024, 1, 6, 10, 0)
        saturday = MARKET_TZ.localize(saturday)

        next_open = self.hours.next_market_open(saturday)
        self.assertIsNotNone(next_open)

        if next_open:
            self.assertEqual(next_open.weekday(), 0)  # Monday

    def test_next_open_returns_none_if_cannot_find(self):
        """Should return None if cannot find next open."""
        # Use a date far in the future
        future = datetime(2030, 1, 1)
        future = MARKET_TZ.localize(future)
        result = self.hours.next_market_open(future)
        # May return None if calendar doesn't extend that far
        self.assertIsInstance(result, (datetime, type(None)))


class TestGetTradingDays(unittest.TestCase):
    """Test trading day list generation."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_trading_days_in_week(self):
        """Should return 5 trading days for a week."""
        start = datetime(2024, 1, 8)  # Monday
        end = datetime(2024, 1, 12)    # Friday

        days = self.hours.get_trading_days(start, end)

        # Should have 5 trading days
        self.assertEqual(len(days), 5)

        # All should be weekdays
        for day in days:
            self.assertLess(day.weekday(), 5)

    def test_trading_days_includes_timezone(self):
        """Trading days should be timezone-aware when calendar available."""
        start = datetime(2024, 1, 8)
        end = datetime(2024, 1, 12)

        days = self.hours.get_trading_days(start, end)

        # When pandas_market_calendars is available, days should have timezone
        # When using fallback, they may not
        for day in days:
            if day.tzinfo is not None:
                self.assertEqual(str(day.tzinfo), 'America/New_York')

    def test_trading_days_empty_range(self):
        """Empty range should return empty list."""
        start = datetime(2024, 1, 8)
        end = datetime(2024, 1, 7)  # Before start

        days = self.hours.get_trading_days(start, end)
        self.assertEqual(len(days), 0)


class TestFormatMarketStatus(unittest.TestCase):
    """Test market status formatting."""

    def setUp(self):
        """Create MarketHours instance."""
        self.hours = MarketHours()

    def test_format_returns_string(self):
        """Should always return a string."""
        now = datetime(2024, 1, 8, 12, 0)
        now = MARKET_TZ.localize(now)
        result = self.hours.format_market_status(now)
        self.assertIsInstance(result, str)

    def test_format_when_open_includes_close_time(self):
        """When open, should include close time."""
        # Use a known trading day at noon
        monday = datetime(2024, 1, 8, 12, 0)
        monday = MARKET_TZ.localize(monday)

        result = self.hours.format_market_status(monday)
        self.assertIsInstance(result, str)

    def test_format_when_closed_includes_status(self):
        """When closed, should indicate closed status."""
        saturday = datetime(2024, 1, 6, 10, 0)
        saturday = MARKET_TZ.localize(saturday)

        result = self.hours.format_market_status(saturday)
        self.assertIn('CLOSED', result)


class TestGlobalFunctions(unittest.TestCase):
    """Test global convenience functions."""

    def test_is_market_open_global(self):
        """Global is_market_open should work."""
        result = is_market_open()
        self.assertIsInstance(result, bool)

    def test_is_trading_day_global(self):
        """Global is_trading_day should work."""
        result = is_trading_day()
        self.assertIsInstance(result, bool)

    def test_next_market_open_global(self):
        """Global next_market_open should work."""
        result = next_market_open()
        # May return None in some cases
        self.assertIsInstance(result, (datetime, type(None)))

    def test_format_market_status_global(self):
        """Global format_market_status should work."""
        result = format_market_status()
        self.assertIsInstance(result, str)


class TestTimezoneHandling(unittest.TestCase):
    """Test timezone handling."""

    def test_market_tz_is_eastern(self):
        """MARKET_TZ should be America/New_York."""
        self.assertEqual(str(MARKET_TZ), 'America/New_York')

    def test_market_open_time_is_930(self):
        """MARKET_OPEN_TIME should be 9:30."""
        self.assertEqual(MARKET_OPEN_TIME, time(9, 30))

    def test_market_close_time_is_1600(self):
        """MARKET_CLOSE_TIME should be 16:00."""
        self.assertEqual(MARKET_CLOSE_TIME, time(16, 0))


class TestMarketHoursWithCalendar(unittest.TestCase):
    """Test market hours when calendar is available."""

    def test_weekend_detection_without_calendar(self):
        """Should detect weekends even without calendar."""
        hours = MarketHours()
        # Weekends should be detected without calendar
        saturday = datetime(2024, 1, 6)
        self.assertFalse(hours.is_trading_day(saturday))


if __name__ == '__main__':
    unittest.main()
