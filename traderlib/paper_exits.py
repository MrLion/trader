#!/usr/bin/env python3
"""Exit rule engine for paper trading - trailing stops and profit targets."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import warnings
from datetime import datetime
import yfinance as yf

# Add scripts directory for local imports
sys.path.insert(0, str(Path(__file__).parent))
from traderlib.trading_exceptions import TradingExceptionHandler

# Add parent directory to path for traderlib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from traderlib.risk_config import (
        RiskConfig, RiskConfigManager,
        calculate_position_size_with_constraints
    )
    from traderlib.stage2_utils import calculate_ma_support_stop
except ImportError:
    # Fallback if risk_config not available
    RiskConfig = None
    RiskConfigManager = None
    calculate_position_size_with_constraints = None
    calculate_ma_support_stop = None


@dataclass
class ExitSignal:
    """Represents an exit decision."""
    should_exit: bool
    reason: str
    exit_price: float
    r_multiple: float
    new_stop: Optional[float] = None
    new_stop_type: Optional[str] = None


class ExitEngine:
    """Manages exit rules: hard stops, trailing stops, and profit targets."""

    def __init__(self, risk_config: Optional[RiskConfig] = None, risk_profile: Optional[str] = None):
        self.price_cache = {}  # Cache for EMA calculations
        self.cache_timestamp = None

        # Load or use provided risk configuration
        if risk_config:
            self.risk_config = risk_config
        elif RiskConfigManager:
            manager = RiskConfigManager(profile=risk_profile)
            self.risk_config = manager.get_config()
        else:
            # Use defaults if risk_config module unavailable
            self.risk_config = None

    def _get_cached_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch and cache price data with configurable TTL."""
        now = datetime.now()

        # Get cache TTL from config (default 5 minutes = 300 seconds)
        cache_ttl = 300
        if self.risk_config:
            cache_ttl = self.risk_config.cache.ttl_seconds

        # Clear cache if older than TTL
        if self.cache_timestamp and (now - self.cache_timestamp).seconds > cache_ttl:
            self.price_cache = {}
            self.cache_timestamp = None

        if ticker not in self.price_cache:
            try:
                stock = yf.Ticker(ticker)
                # Get 60 days for EMA calculations
                hist = stock.history(period="60d", interval="1d")
                if len(hist) >= 50:
                    # Calculate EMAs using configured periods
                    ema_short = self.risk_config.profit_target.ema_short_period if self.risk_config else 10
                    ema_long = self.risk_config.profit_target.ema_long_period if self.risk_config else 21
                    hist['EMA10'] = hist['Close'].ewm(span=ema_short, adjust=False).mean()
                    hist['EMA21'] = hist['Close'].ewm(span=ema_long, adjust=False).mean()
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

    def _get_ema_values(self, ticker: str,
                        historical_data: Optional[pd.DataFrame] = None) -> Tuple[Optional[float], Optional[float]]:
        """Get current short and long EMA values.

        Args:
            ticker: Stock symbol
            historical_data: Optional DataFrame with OHLCV data. If provided,
                           calculates EMAs from this data. Otherwise uses yfinance.

        Returns:
            Tuple of (short_ema, long_ema) or (None, None) if data unavailable
        """
        if historical_data is not None:
            # Use injected data (for backtesting or Alpaca-only mode)
            ema_short = self.risk_config.profit_target.ema_short_period if self.risk_config else 10
            ema_long = self.risk_config.profit_target.ema_long_period if self.risk_config else 21

            if len(historical_data) < ema_long:
                return None, None

            # Calculate EMAs from injected data
            short_ema = historical_data['Close'].ewm(span=ema_short, adjust=False).mean().iloc[-1]
            long_ema = historical_data['Close'].ewm(span=ema_long, adjust=False).mean().iloc[-1]
            return short_ema, long_ema
        else:
            # Use yfinance (legacy behavior for reports/tools)
            hist = self._get_cached_data(ticker)
            ema_long = self.risk_config.profit_target.ema_long_period if self.risk_config else 21
            if hist is None or len(hist) < ema_long:
                return None, None

            return hist['EMA10'].iloc[-1], hist['EMA21'].iloc[-1]

    def evaluate_exit(self, position, current_price: float,
                      historical_data: Optional[pd.DataFrame] = None) -> ExitSignal:
        """
        Evaluate all exit conditions for a position.

        Exit hierarchy:
        1. Hard stop (initial 2xATR stop)
        2. Profit target (2R minimum)
        3. Trailing stops based on R multiple

        Args:
            position: Position object with ticker, entry_price, shares, stop_price
            current_price: Current market price
            historical_data: Optional DataFrame with OHLCV data for EMA calculation.
                           If provided, uses this data (enables backtesting/Alpaca-only).
                           If None, uses yfinance (legacy behavior).

        Returns:
            ExitSignal with exit decision
        """
        ticker = position.ticker
        entry_price = position.entry_price
        shares = position.shares
        current_stop = position.stop_price

        # FINDING-013: Use immutable initial_stop_price for accurate R-multiple
        # This prevents R-multiple drift when stop ratchets up (breakeven/EMA trailing)
        initial_stop = getattr(position, 'initial_stop_price', None)
        if initial_stop is None and position.stop_price > 0:
            # Migration: derive from current stop if initial not stored (legacy positions)
            initial_stop = position.stop_price

        if initial_stop and initial_stop > 0:
            r_multiple = self._calculate_r_multiple(current_price, entry_price,
                                                     initial_stop, shares)
        elif getattr(position, 'initial_risk', 0) > 0:
            # Fallback: use pre-calculated initial_risk
            r_multiple = ((current_price - entry_price) * shares) / position.initial_risk
        else:
            # Last resort: may have drift if stop has ratcheted
            r_multiple = self._calculate_r_multiple(current_price, entry_price,
                                                     current_stop, shares)

        # 1. Check hard stop (price hit stop level)
        if current_price <= current_stop:
            return ExitSignal(
                should_exit=True,
                reason=f"STOP_HIT",
                exit_price=current_price,
                r_multiple=r_multiple,
                new_stop=None,
                new_stop_type=None
            )

        # 2. Get EMA values for trailing logic
        ema10, ema21 = self._get_ema_values(ticker, historical_data)

        # 3. Trailing stop logic based on R multiple (using config if available)
        new_stop = current_stop
        new_stop_type = position.current_stop_type

        # Get R thresholds from config or use defaults
        if self.risk_config:
            breakeven_r = self.risk_config.profit_target.breakeven_at_r
            ema10_r = self.risk_config.profit_target.ema10_at_r
            ema21_r = self.risk_config.profit_target.ema21_at_r
        else:
            breakeven_r, ema10_r, ema21_r = 1.0, 1.5, 3.0

        if r_multiple >= ema21_r and ema21 is not None:
            # +3R: Trail 21 EMA
            if ema21 > current_stop:
                new_stop = ema21
                new_stop_type = "EMA21"

        elif r_multiple >= ema10_r and ema10 is not None:
            # +1.5R to +2R: Trail 10 EMA
            if ema10 > current_stop:
                new_stop = ema10
                new_stop_type = "EMA10"

        elif r_multiple >= breakeven_r:
            # +1R: Move to breakeven
            if entry_price > current_stop:
                new_stop = entry_price
                new_stop_type = "BREAKEVEN"

        # Compute stop update (no mutation — caller applies)
        stop_update = new_stop > current_stop

        # 4. Check profit target (target hit OR 2R minimum)
        target_price = position.target_price
        if current_price >= target_price or r_multiple >= 2.0:
            reason = f"TARGET_HIT_{r_multiple:.1f}R" if r_multiple >= 2.0 else "TARGET_HIT"
            return ExitSignal(
                should_exit=True,
                reason=reason,
                exit_price=current_price,
                r_multiple=r_multiple,
                new_stop=new_stop if stop_update else None,
                new_stop_type=new_stop_type if stop_update else None
            )

        # No exit signal
        return ExitSignal(
            should_exit=False,
            reason="HOLD",
            exit_price=current_price,
            r_multiple=r_multiple,
            new_stop=new_stop if stop_update else None,
            new_stop_type=new_stop_type if stop_update else None
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

    def calculate_initial_stop(
        self,
        ticker: str,
        entry_price: float,
        historical_data: Optional[pd.DataFrame] = None,
        s2_details: Optional[dict] = None
    ) -> float:
        """Calculate initial stop based on configured method.

        Supported methods:
        - atr_or_support: max(2xATR, recent low)
        - atr_or_ma_support: max(2xATR, recent low, MA support cluster)
        - atr: 2xATR below entry
        - percent: Fixed percentage below entry
        - pivot_based: Based on support levels

        When s2_details is provided and ma_support is enabled, computes an
        alternative MA support stop. The final stop is max(ATR stop, MA support stop)
        when a valid MA cluster exists.

        Args:
            ticker: Stock symbol (for logging/cache purposes)
            entry_price: Entry price for the position
            historical_data: Optional DataFrame with OHLCV data for ATR calculation.
                             If provided, uses this data (enables backtesting/Alpaca-only).
                             If None, falls back to yfinance (legacy behavior for reports/tools).
            s2_details: Optional Stage 2 details dict with MA values for MA support calculation.
                         When provided and ma_support is enabled, calculates dual risk stop.

        Returns:
            float: Calculated stop price
        """
        method = self.risk_config.stop_loss.method if self.risk_config else "atr_or_support"

        # Fixed percentage method - no historical data needed
        if method == "percent":
            pct = self.risk_config.stop_loss.fixed_pct if self.risk_config else 0.07
            return round(entry_price * (1 - pct), 2)

        # Validate historical_data columns before try block (fail fast on bad input)
        if historical_data is not None:
            required_cols = ['High', 'Low', 'Close']
            missing = [c for c in required_cols if c not in historical_data.columns]
            if missing:
                raise ValueError(f"historical_data missing required columns: {missing}")

        try:
            # ATR-based methods (atr, atr_or_support, atr_or_ma_support)
            if historical_data is not None:
                hist = historical_data
            else:
                # Use yfinance (legacy behavior for reports/tools)
                warnings.warn(
                    "yfinance fallback is deprecated for trading, use Alpaca data",
                    DeprecationWarning,
                    stacklevel=2
                )
                stock = yf.Ticker(ticker)
                hist = stock.history(period="60d", interval="1d")

            if len(hist) < 14:
                # Fallback to fixed percent
                fallback = self.risk_config.stop_loss.fallback_pct if self.risk_config else 0.07
                return round(entry_price * (1 - fallback), 2)

            # Calculate ATR
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)

            atr_period = self.risk_config.stop_loss.atr_period if self.risk_config else 14
            atr = true_range.rolling(atr_period).mean().iloc[-1]

            atr_mult = self.risk_config.stop_loss.atr_multiplier if self.risk_config else 2.0
            atr_stop = entry_price - (atr_mult * atr)

            # Apply method-specific logic
            recent_low = hist['Low'].tail(10).min()

            if method in ("atr_or_support", "atr_or_ma_support"):
                # Use max of ATR stop and recent low
                stop = max(atr_stop, recent_low)
            else:
                # Pure ATR stop
                stop = atr_stop

            # MA Support Stop calculation (when enabled and s2_details provided)
            ma_support_stop = None
            if s2_details and calculate_ma_support_stop:
                ma_config = self.risk_config.ma_support if self.risk_config else None
                if ma_config and ma_config.enabled:
                    ma_result = calculate_ma_support_stop(
                        entry_price,
                        s2_details,
                        buffer_pct=ma_config.buffer_pct,
                        cluster_spread_pct=ma_config.cluster_spread_pct,
                        min_cluster_size=ma_config.min_cluster_size
                    )
                    if ma_result:
                        ma_support_stop = ma_result['ma_support_stop']

            # If MA support stop is available, use the tighter of ATR stop and MA support
            # (higher stop price = tighter risk = less risk)
            if ma_support_stop:
                stop = max(stop, ma_support_stop)

            # Apply configured min/max bounds
            if self.risk_config:
                min_pct = self.risk_config.stop_loss.min_stop_distance_pct
                max_pct = self.risk_config.stop_loss.max_stop_distance_pct

                # Enforce minimum stop distance
                min_stop = entry_price * (1 - min_pct)
                if stop > min_stop:
                    stop = min_stop

                # Enforce maximum stop distance
                max_stop = entry_price * (1 - max_pct)
                if stop < max_stop:
                    stop = max_stop
            else:
                # Default bounds: 3-15%
                if stop > entry_price * 0.97:
                    stop = entry_price * 0.97
                elif stop < entry_price * 0.85:
                    stop = entry_price * 0.85

            return round(stop, 2)

        except Exception as e:
            TradingExceptionHandler.log_exception(
                "atr_stop_calculation", e,
                severity=TradingExceptionHandler.WARNING,
                ticker=ticker if 'ticker' in locals() else 'unknown'
            )
            # Fallback
            fallback = self.risk_config.stop_loss.fallback_pct if self.risk_config else 0.07
            return round(entry_price * (1 - fallback), 2)

    def calculate_target_price(self, entry_price: float, stop_price: float,
                                min_r: float = None) -> float:
        """Calculate profit target based on R multiple."""
        r_multiple = min_r if min_r else (
            self.risk_config.profit_target.min_r_multiple if self.risk_config else 2.0
        )

        risk = entry_price - stop_price
        if risk <= 0:
            # Fallback: configurable % above entry (default 10%)
            fallback_pct = self.risk_config.profit_target.fallback_target_pct if self.risk_config else 0.10
            return round(entry_price * (1 + fallback_pct), 2)

        target = entry_price + (risk * r_multiple)
        return round(target, 2)

    def calculate_position_size(self, equity: float, entry_price: float,
                                 stop_price: float, account_risk_pct: float = None,
                                 available_cash: float = None) -> int:
        """
        Calculate shares using triple-constraint risk system.

        Constraints:
        1. Account risk: Total $ risk <= account_risk_pct of equity
        2. Position size: Position value <= max_position_pct of equity
        3. Cash available: Position value <= available_cash (partial position)

        Returns number of shares, respecting all constraints.

        Args:
            equity: Total account equity
            entry_price: Entry price per share
            stop_price: Stop price per share
            account_risk_pct: Override risk per trade (uses config if None)
            available_cash: Cash available for new positions (enables partial positions)

        Returns:
            int: Number of shares to purchase (0 if rejected)
        """
        # Use new triple-constraint system if risk config available
        if self.risk_config and calculate_position_size_with_constraints:
            shares, metadata = calculate_position_size_with_constraints(
                equity, entry_price, stop_price, self.risk_config,
                available_cash=available_cash
            )
            self._last_position_calc = metadata  # Store for logging
            return shares

        # Fallback to original calculation
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            return 0

        risk_pct = account_risk_pct if account_risk_pct else 0.0075
        account_risk_dollars = equity * risk_pct
        shares = int(account_risk_dollars / risk_per_share)
        shares = (shares // 10) * 10
        return max(shares, 10)

    def get_last_position_calc(self) -> Optional[dict]:
        """Get metadata from last position size calculation."""
        return getattr(self, '_last_position_calc', None)


if __name__ == "__main__":
    # Quick test with mock data (avoids yfinance dependency)
    engine = ExitEngine()

    # Create sample historical data for testing
    import numpy as np
    np.random.seed(42)
    base_price = 150.0
    volatility = 0.02
    days = 60

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    closes = base_price + np.random.randn(days).cumsum() * volatility * base_price
    highs = closes * (1 + abs(np.random.randn(days) * 0.01))
    lows = closes * (1 - abs(np.random.randn(days) * 0.01))
    volumes = np.random.randint(1000000, 10000000, days)

    sample_data = pd.DataFrame({
        'Open': lows + (highs - lows) * np.random.rand(days),
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': volumes
    }, index=dates)

    # Test stop calculation with injected data
    stop = engine.calculate_initial_stop("AAPL", 150.0, historical_data=sample_data)
    print(f"Sample AAPL stop at $150: ${stop:.2f}")

    target = engine.calculate_target_price(150.0, stop)
    print(f"Sample target (2R): ${target:.2f}")

    shares = engine.calculate_position_size(100000, 150.0, stop)
    print(f"Position size (0.75% risk): {shares} shares")
