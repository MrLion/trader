#!/usr/bin/env python3
"""Exit rule engine for paper trading - trailing stops and profit targets."""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime
import yfinance as yf
import pandas as pd


@dataclass
class ExitSignal:
    """Represents an exit decision."""
    should_exit: bool
    reason: str
    exit_price: float
    r_multiple: float


class ExitEngine:
    """Manages exit rules: hard stops, trailing stops, and profit targets."""

    def __init__(self):
        self.price_cache = {}  # Cache for EMA calculations
        self.cache_timestamp = None

    def _get_cached_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch and cache price data with 5-minute TTL."""
        now = datetime.now()

        # Clear cache if older than 5 minutes
        if self.cache_timestamp and (now - self.cache_timestamp).seconds > 300:
            self.price_cache = {}
            self.cache_timestamp = None

        if ticker not in self.price_cache:
            try:
                stock = yf.Ticker(ticker)
                # Get 60 days for EMA calculations
                hist = stock.history(period="60d", interval="1d")
                if len(hist) >= 50:
                    # Calculate EMAs
                    hist['EMA10'] = hist['Close'].ewm(span=10, adjust=False).mean()
                    hist['EMA21'] = hist['Close'].ewm(span=21, adjust=False).mean()
                    self.price_cache[ticker] = hist
                    self.cache_timestamp = now
                else:
                    return None
            except Exception:
                return None

        return self.price_cache.get(ticker)

    def _calculate_r_multiple(self, current_price: float, entry_price: float,
                               initial_stop: float, shares: int) -> float:
        """Calculate current R multiple based on initial risk."""
        initial_risk_per_share = entry_price - initial_stop
        if initial_risk_per_share <= 0:
            return 0.0

        current_pnl = (current_price - entry_price) * shares
        total_initial_risk = initial_risk_per_share * shares

        return current_pnl / total_initial_risk if total_initial_risk > 0 else 0.0

    def _get_ema_values(self, ticker: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current EMA10 and EMA21 values."""
        hist = self._get_cached_data(ticker)
        if hist is None or len(hist) < 21:
            return None, None

        return hist['EMA10'].iloc[-1], hist['EMA21'].iloc[-1]

    def evaluate_exit(self, position, current_price: float) -> ExitSignal:
        """
        Evaluate all exit conditions for a position.

        Exit hierarchy:
        1. Hard stop (initial 2xATR stop)
        2. Profit target (2R minimum)
        3. Trailing stops based on R multiple
        """
        ticker = position.ticker
        entry_price = position.entry_price
        shares = position.shares
        current_stop = position.stop_price
        initial_stop = position.stop_price  # Track original stop

        # Calculate current R multiple
        r_multiple = self._calculate_r_multiple(current_price, entry_price,
                                                 initial_stop, shares)

        # 1. Check hard stop (price hit stop level)
        if current_price <= current_stop:
            return ExitSignal(
                should_exit=True,
                reason=f"STOP_HIT",
                exit_price=current_price,
                r_multiple=r_multiple
            )

        # 2. Get EMA values for trailing logic
        ema10, ema21 = self._get_ema_values(ticker)

        # 3. Trailing stop logic based on R multiple
        new_stop = current_stop
        new_stop_type = position.current_stop_type

        if r_multiple >= 3.0 and ema21 is not None:
            # +3R: Trail 21 EMA
            if ema21 > current_stop:
                new_stop = ema21
                new_stop_type = "EMA21"

        elif r_multiple >= 1.5 and ema10 is not None:
            # +1.5R to +2R: Trail 10 EMA
            if ema10 > current_stop:
                new_stop = ema10
                new_stop_type = "EMA10"

        elif r_multiple >= 1.0:
            # +1R: Move to breakeven
            if entry_price > current_stop:
                new_stop = entry_price
                new_stop_type = "BREAKEVEN"

        # Update stop if improved
        if new_stop > current_stop:
            position.stop_price = new_stop
            position.current_stop_type = new_stop_type

        # 4. Check profit target (target hit OR 2R minimum)
        target_price = position.target_price
        if current_price >= target_price or r_multiple >= 2.0:
            reason = f"TARGET_HIT_{r_multiple:.1f}R" if r_multiple >= 2.0 else "TARGET_HIT"
            return ExitSignal(
                should_exit=True,
                reason=reason,
                exit_price=current_price,
                r_multiple=r_multiple
            )

        # No exit signal
        return ExitSignal(
            should_exit=False,
            reason="HOLD",
            exit_price=current_price,
            r_multiple=r_multiple
        )

    def get_position_summary(self, position, current_price: float) -> dict:
        """Generate summary stats for a position."""
        entry_price = position.entry_price
        shares = position.shares
        initial_stop = position.stop_price

        unrealized_pnl = (current_price - entry_price) * shares
        r_multiple = self._calculate_r_multiple(current_price, entry_price,
                                                 initial_stop, shares)

        # Distance to stop
        pct_to_stop = ((current_price - position.stop_price) / current_price) * 100

        return {
            'ticker': position.ticker,
            'current_price': round(current_price, 2),
            'entry_price': entry_price,
            'shares': shares,
            'stop_price': position.stop_price,
            'stop_type': position.current_stop_type,
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_pct': round(((current_price / entry_price) - 1) * 100, 2),
            'r_multiple': round(r_multiple, 2),
            'pct_to_stop': round(pct_to_stop, 2)
        }

    def calculate_initial_stop(self, ticker: str, entry_price: float) -> float:
        """Calculate initial 2xATR stop for entry."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="60d", interval="1d")

            if len(hist) < 14:
                # Fallback: 7% below entry
                return entry_price * 0.93

            # Calculate ATR
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            # Recent low for additional support
            recent_low = hist['Low'].tail(10).min()

            # 2xATR below entry
            atr_stop = entry_price - (2 * atr)

            # Use max of ATR stop and recent low
            stop = max(atr_stop, recent_low)

            # Sanity check: stop should be 3-15% below entry
            if stop > entry_price * 0.97:
                stop = entry_price * 0.97
            elif stop < entry_price * 0.85:
                stop = entry_price * 0.85

            return round(stop, 2)

        except Exception:
            # Fallback: 7% below entry
            return round(entry_price * 0.93, 2)

    def calculate_target_price(self, entry_price: float, stop_price: float,
                                min_r: float = 2.0) -> float:
        """Calculate profit target based on R multiple."""
        risk = entry_price - stop_price
        if risk <= 0:
            # Fallback: 10% above entry
            return round(entry_price * 1.10, 2)

        target = entry_price + (risk * min_r)
        return round(target, 2)

    def calculate_position_size(self, equity: float, entry_price: float,
                                 stop_price: float, account_risk_pct: float = 0.0075) -> int:
        """
        Calculate shares based on account risk (default 0.75%).

        Formula: shares = (equity * account_risk_pct) / (entry_price - stop_price)
        """
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        account_risk_dollars = equity * account_risk_pct
        shares = int(account_risk_dollars / risk_per_share)

        # Round down to nearest 10 for cleaner numbers
        shares = (shares // 10) * 10

        # Ensure at least 10 shares
        return max(shares, 10)


if __name__ == "__main__":
    # Quick test
    engine = ExitEngine()

    # Test stop calculation
    stop = engine.calculate_initial_stop("AAPL", 150.0)
    print(f"Sample AAPL stop at $150: ${stop:.2f}")

    target = engine.calculate_target_price(150.0, stop)
    print(f"Sample target (2R): ${target:.2f}")

    shares = engine.calculate_position_size(100000, 150.0, stop)
    print(f"Position size (0.75% risk): {shares} shares")
