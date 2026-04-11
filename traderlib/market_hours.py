#!/usr/bin/env python3
"""Market hours and holiday calendar utilities.

FINDING-007: Weekend/holiday market hours — Integrate pandas_market_calendars
"""

from datetime import datetime, time, timedelta
from typing import Optional, Tuple, List
import pytz

try:
    import pandas_market_calendars as mcal
    HAS_MARKET_CALS = True
except ImportError:
    HAS_MARKET_CALS = False

# Market timezone (US Equity)
MARKET_TZ = pytz.timezone('America/New_York')

# Market hours (9:30 AM - 4:00 PM ET)
MARKET_OPEN_TIME = time(9, 30)
MARKET_CLOSE_TIME = time(16, 0)

# Early close times (1:00 PM ET)
EARLY_CLOSE_TIME = time(13, 0)


class MarketHours:
    """Manages US equity market hours and holidays."""

    def __init__(self, exchange: str = 'NYSE'):
        """Initialize market hours for an exchange.

        Args:
            exchange: Exchange calendar (default: NYSE)
        """
        self.exchange = exchange
        self._calendar = None

        if HAS_MARKET_CALS:
            try:
                self._calendar = mcal.get_calendar(exchange)
            except Exception:
                pass

    def is_trading_day(self, date: Optional[datetime] = None) -> bool:
        """Check if the given date is a trading day.

        Args:
            date: Date to check (default: today in market timezone)

        Returns:
            True if trading day, False if weekend or holiday
        """
        if date is None:
            date = datetime.now(MARKET_TZ)

        # Check if weekend (Saturday=5, Sunday=6)
        if date.weekday() >= 5:
            return False

        # Check market calendar if available
        if self._calendar:
            schedule = self._calendar.schedule(start_date=date.date(), end_date=date.date())
            return len(schedule) > 0

        # Fallback: assume weekday is trading day
        return True

    def get_market_schedule(self, date: datetime) -> Optional[Tuple[datetime, datetime]]:
        """Get market open and close times for a specific date.

        Args:
            date: Date to get schedule for

        Returns:
            Tuple of (market_open, market_close) in market timezone,
            or None if not a trading day
        """
        if not self.is_trading_day(date):
            return None

        if self._calendar:
            try:
                schedule = self._calendar.schedule(
                    start_date=date.date(),
                    end_date=date.date()
                )
                if len(schedule) == 0:
                    return None

                open_time = schedule.iloc[0]['market_open']
                close_time = schedule.iloc[0]['market_close']

                # Convert to market timezone
                if open_time.tzinfo is None:
                    open_time = MARKET_TZ.localize(open_time)
                if close_time.tzinfo is None:
                    close_time = MARKET_TZ.localize(close_time)

                return (open_time, close_time)
            except Exception:
                pass

        # Fallback: standard market hours
        market_open = datetime.combine(date.date(), MARKET_OPEN_TIME)
        market_close = datetime.combine(date.date(), MARKET_CLOSE_TIME)
        return (MARKET_TZ.localize(market_open), MARKET_TZ.localize(market_close))

    def is_market_open(self, now: Optional[datetime] = None) -> bool:
        """Check if the market is currently open.

        Args:
            now: Current time (default: now in market timezone)

        Returns:
            True if market is open for trading
        """
        if now is None:
            now = datetime.now(MARKET_TZ)
        else:
            # Ensure timezone-aware
            if now.tzinfo is None:
                now = MARKET_TZ.localize(now)
            else:
                now = now.astimezone(MARKET_TZ)

        # Check if trading day
        if not self.is_trading_day(now):
            return False

        # Get schedule for today
        schedule = self.get_market_schedule(now)
        if schedule is None:
            return False

        market_open, market_close = schedule
        return market_open <= now <= market_close

    def next_market_open(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Get the next market open time.

        Args:
            now: Current time (default: now in market timezone)

        Returns:
            Next market open datetime, or None if cannot determine
        """
        if now is None:
            now = datetime.now(MARKET_TZ)
        else:
            if now.tzinfo is None:
                now = MARKET_TZ.localize(now)
            else:
                now = now.astimezone(MARKET_TZ)

        # Check if market is currently open
        if self.is_market_open(now):
            return now

        # Check if today is a trading day and market hasn't opened yet
        if self.is_trading_day(now):
            schedule = self.get_market_schedule(now)
            if schedule:
                market_open, _ = schedule
                if now < market_open:
                    return market_open

        # Find next trading day
        next_day = now + timedelta(days=1)
        for _ in range(10):  # Look ahead up to 10 days
            if self.is_trading_day(next_day):
                schedule = self.get_market_schedule(next_day)
                if schedule:
                    return schedule[0]  # Return market open time
            next_day += timedelta(days=1)

        return None

    def get_trading_days(self, start: datetime, end: datetime) -> List[datetime]:
        """Get list of trading days between start and end dates.

        Args:
            start: Start date
            end: End date

        Returns:
            List of trading days (as datetimes at midnight)
        """
        if self._calendar:
            try:
                schedule = self._calendar.schedule(
                    start_date=start.date(),
                    end_date=end.date()
                )
                return [MARKET_TZ.localize(datetime.combine(d, time(0, 0)))
                        for d in schedule.index]
            except Exception:
                pass

        # Fallback: return weekdays
        trading_days = []
        current = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end.date()

        while current.date() <= end_date:
            if current.weekday() < 5:  # Monday=0 to Friday=4
                trading_days.append(current)
            current += timedelta(days=1)

        return trading_days

    def format_market_status(self, now: Optional[datetime] = None) -> str:
        """Format a human-readable market status message.

        Args:
            now: Current time (default: now in market timezone)

        Returns:
            Status message with market state and next open info
        """
        if now is None:
            now = datetime.now(MARKET_TZ)
        else:
            if now.tzinfo is None:
                now = MARKET_TZ.localize(now)
            else:
                now = now.astimezone(MARKET_TZ)

        if self.is_market_open(now):
            schedule = self.get_market_schedule(now)
            if schedule:
                _, close = schedule
                close_str = close.strftime('%H:%M')
                return f"Market OPEN - Closes at {close_str} ET"
            return "Market OPEN"

        if not self.is_trading_day(now):
            next_open = self.next_market_open(now)
            if next_open:
                if now.weekday() >= 5:  # Weekend
                    return f"Market CLOSED (Weekend) - Opens {next_open.strftime('%A at %H:%M')} ET"
                else:
                    return f"Market CLOSED (Holiday) - Opens {next_open.strftime('%A at %H:%M')} ET"
            return "Market CLOSED"

        # Trading day but market closed
        schedule = self.get_market_schedule(now)
        if schedule:
            open_time, close_time = schedule
            if now < open_time:
                return f"Market CLOSED - Opens {open_time.strftime('%H:%M')} ET"
            else:
                next_open = self.next_market_open(now)
                if next_open:
                    return f"Market CLOSED - Opens {next_open.strftime('%A at %H:%M')} ET"

        return "Market CLOSED"


# Global market hours instance
market_hours = MarketHours()


# Convenience functions
def is_market_open(now: Optional[datetime] = None) -> bool:
    """Check if market is currently open."""
    return market_hours.is_market_open(now)


def is_trading_day(date: Optional[datetime] = None) -> bool:
    """Check if date is a trading day."""
    return market_hours.is_trading_day(date)


def next_market_open(now: Optional[datetime] = None) -> Optional[datetime]:
    """Get next market open time."""
    return market_hours.next_market_open(now)


def format_market_status(now: Optional[datetime] = None) -> str:
    """Format market status message."""
    return market_hours.format_market_status(now)


if __name__ == "__main__":
    # Test market hours
    print("Market Hours Test")
    print("=" * 60)
    print()

    now = datetime.now(MARKET_TZ)
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()

    print(f"Is trading day: {is_trading_day()}")
    print(f"Is market open: {is_market_open()}")
    print(f"Status: {format_market_status()}")
    print()

    next_open = next_market_open()
    if next_open:
        print(f"Next market open: {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    else:
        print("Could not determine next market open")
    print()

    # Test schedule lookup
    schedule = market_hours.get_market_schedule(now)
    if schedule:
        open_time, close_time = schedule
        print(f"Today's hours: {open_time.strftime('%H:%M')} - {close_time.strftime('%H:%M')} ET")
    else:
        print("No trading hours for today")
