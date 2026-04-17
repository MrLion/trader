"""Strategy abstraction for backtesting.

This module now re-exports from traderlib.strategies for unified interface.
Backtest-specific implementations (Stage2MomentumStrategy) remain here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

from traderlib.backtest.data_provider import DataFrameProvider
from traderlib.backtest.execution import ExecutionModel, ExecutionConfig
from traderlib.paper_exits import ExitEngine
from traderlib.paper_state import Position
from traderlib.stage2_utils import calculate_stage2_score, get_entry_score, get_stage2_details, calculate_ma_support_stop
from traderlib.risk_config import RiskConfig, calculate_position_size_with_constraints

# Import unified strategy types
from traderlib.strategies import (
    Strategy as BaseStrategy,
    StrategyContext,
    EntrySignal,
    ExitAction,
    ExitActionType,
)


# Re-export for backward compatibility
__all__ = [
    'BaseStrategy',
    'StrategyContext',
    'EntrySignal',
    'ExitAction',
    'ExitActionType',
    'Stage2MomentumStrategy',
]


# Backtest-specific adapter context builder
class BacktestStrategyContext(StrategyContext):
    """Adapter: wraps backtest's data provider into unified context."""

    def __init__(self, data_provider: DataFrameProvider, sim_date: date,
                 positions: Dict[str, Position], equity: float, cash: float,
                 risk_config: Optional[RiskConfig] = None,
                 spy_data: Optional[pd.DataFrame] = None):
        self._data_provider = data_provider
        self._sim_date = sim_date
        self.sim_date = sim_date
        self.positions = positions
        self.equity = equity
        self.cash = cash
        self.risk_config = risk_config
        self.spy_data = spy_data
        self.spy_current = None
        self.vix_current = None
        self.day_pnl = 0.0

    def get_bars(self, ticker: str, lookback_days: int = 200) -> Optional[pd.DataFrame]:
        """Get historical bars for ticker."""
        return self._data_provider.get_bars(ticker, self._sim_date)

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current/latest price."""
        return self._data_provider.get_current_price(ticker, self._sim_date)


class Strategy(BaseStrategy):
    """Backtest-compatible Strategy base class.

    Maintains backward compatibility with existing backtest code while
    supporting the unified StrategyContext interface.

    New strategies should inherit from BaseStrategy (traderlib.strategies.Strategy)
    directly for cleaner interface.
    """

    @abstractmethod
    def evaluate_entries(self, sim_date: date, positions: dict[str, Position],
                        data_provider: DataFrameProvider, equity: float,
                        risk_config: Optional[RiskConfig] = None) -> list[EntrySignal]:
        """Scan for entry opportunities (legacy interface).

        Override this for backtest compatibility, or use evaluate_entries()
        with StrategyContext for unified interface.
        """
        pass

    @abstractmethod
    def evaluate_exits(self, sim_date: date, positions: dict[str, Position],
                       data_provider: DataFrameProvider,
                       risk_config: Optional[RiskConfig] = None) -> list[ExitAction]:
        """Evaluate exits for current positions (legacy interface).

        Returns list[ExitAction] for unified handling.
        """
        pass

    def _build_context(self, sim_date: date, positions: dict[str, Position],
                      data_provider: DataFrameProvider, equity: float,
                      risk_config: Optional[RiskConfig] = None) -> BacktestStrategyContext:
        """Build unified context from backtest parameters."""
        return BacktestStrategyContext(
            data_provider=data_provider,
            sim_date=sim_date,
            positions=positions,
            equity=equity,
            cash=equity,  # Approximation - backtest tracks cash separately
            risk_config=risk_config
        )


class Stage2MomentumStrategy(Strategy):
    """Stage 2 momentum strategy — mirrors paper engine entry/exit logic.

    Entry: Replicates _analyze_ticker() with injected data (no Alpaca calls).
    Exit: Delegates to ExitEngine.evaluate_exit_action() which returns ExitAction.
    """

    def __init__(self, exit_engine: ExitEngine, watchlist_tickers: Optional[list[str]] = None,
                 risk_config: Optional[RiskConfig] = None,
                 execution_config: Optional[ExecutionConfig] = None,
                 watchlist_df: Optional[pd.DataFrame] = None):
        """Initialize with dependencies.

        Args:
            exit_engine: ExitEngine instance for exit evaluation
            watchlist_tickers: Tickers to scan for entries (None = use data_provider)
            risk_config: Risk configuration for position sizing
            execution_config: Execution config for slippage calculations
            watchlist_df: Historical watchlist DataFrame with week_start column
                          for date-aware ticker filtering
        """
        self.exit_engine = exit_engine
        self.watchlist_tickers = watchlist_tickers
        self.watchlist_df = watchlist_df
        self._risk_config = risk_config
        self._execution_model = ExecutionModel(execution_config or ExecutionConfig())
        # SPY return cache for RS calculation
        self._spy_return_cache: dict[date, float] = {}
        # Sector cache to avoid repeated yfinance lookups
        self._sector_cache: dict[str, str] = {}
        self._sector_cache_path = Path("data/ticker_sectors_cache.json")

    @property
    def name(self) -> str:
        return "stage2_momentum"

    @property
    def side(self) -> str:
        return 'LONG'

    def _get_spy_return(self, data_provider: DataFrameProvider,
                        as_of: date, lookback_days: int = 130) -> float:
        """Get SPY 6-month return for relative strength calculation.

        Returns 0.0 if SPY data is unavailable.
        """
        if as_of in self._spy_return_cache:
            return self._spy_return_cache[as_of]

        try:
            spy_data = data_provider.get_bars('SPY', as_of)
            if len(spy_data) >= lookback_days:
                current = float(spy_data['Close'].iloc[-1])
                past = float(spy_data['Close'].iloc[-lookback_days])
                ret = ((current / past) - 1) * 100
                self._spy_return_cache[as_of] = ret
                return ret
        except Exception:
            pass

        self._spy_return_cache[as_of] = 0.0
        return 0.0

    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker using yfinance, with caching."""
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # Try to load from cache file
        if self._sector_cache_path.exists():
            try:
                import json
                with open(self._sector_cache_path) as f:
                    self._sector_cache = json.load(f)
                if ticker in self._sector_cache:
                    return self._sector_cache[ticker]
            except Exception:
                pass

        # Fallback to yfinance lookup
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            sector = info.get('sector', 'Unknown')
            self._sector_cache[ticker] = sector

            # Save cache
            try:
                import json
                with open(self._sector_cache_path, 'w') as f:
                    json.dump(self._sector_cache, f)
            except Exception:
                pass

            return sector
        except Exception:
            return 'Unknown'

    def evaluate_entries(self, sim_date: date, positions: dict[str, Position],
                        data_provider: DataFrameProvider, equity: float,
                        risk_config: Optional[RiskConfig] = None) -> list[EntrySignal]:
        """Evaluate entries using Stage 2 momentum criteria."""
        # Use provided config or instance config
        config = risk_config or self._risk_config

        # Get tickers to scan
        if self.watchlist_df is not None:
            # Date-aware filtering from historical watchlist
            active = self.watchlist_df[self.watchlist_df['week_start'] <= pd.Timestamp(sim_date)]
            active = active.sort_values('week_start').groupby('ticker').last().reset_index()
            ticker_col = 'ticker' if 'ticker' in active.columns else 'Ticker'
            tickers = active[ticker_col].dropna().unique().tolist()
        else:
            tickers = self.watchlist_tickers or []

        signals = []

        for ticker in tickers:
            # Skip if already holding
            if ticker in positions:
                continue

            try:
                hist = data_provider.get_bars(ticker, sim_date)
            except Exception:
                continue

            if len(hist) < 30:
                continue

            current = float(hist['Close'].iloc[-1])
            if current <= 0:
                continue

            # Stage 2 score and MA flags
            s2_details = get_stage2_details(hist)
            stage2 = s2_details['score']
            below_50ma = not s2_details['criteria'].get('price_above_50ma', True)
            below_20ma = not s2_details['criteria'].get('price_above_20ema', False)

            # Minimum Stage 2 score
            min_stage2 = 5
            if stage2 < min_stage2:
                continue

            # Calculate ATR for stop
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = tr.rolling(window=14, min_periods=1).mean().iloc[-1]
                if pd.isna(atr):
                    continue
            except Exception:
                continue

            atr_stop = current - (2 * atr)
            recent_low = float(hist['Low'].tail(10).min())
            stop = max(atr_stop, recent_low)

            # MA Support Stop calculation
            if config and config.ma_support.enabled:
                ma_result = calculate_ma_support_stop(
                    current,
                    s2_details,
                    buffer_pct=config.ma_support.buffer_pct,
                    cluster_spread_pct=config.ma_support.cluster_spread_pct,
                    min_cluster_size=config.ma_support.min_cluster_size
                )
                if ma_result:
                    ma_support_stop = ma_result['ma_support_stop']
                    # Use tighter stop (higher = less risk)
                    stop = max(stop, ma_support_stop)

            # Enforce bounds: 3-15% below entry
            if config:
                min_pct = config.stop_loss.min_stop_distance_pct
                max_pct = config.stop_loss.max_stop_distance_pct
                min_stop = current * (1 - min_pct)
                max_stop = current * (1 - max_pct)
                if stop > min_stop:
                    stop = min_stop
                if stop < max_stop:
                    stop = max_stop
            else:
                if stop > current * 0.97:
                    stop = current * 0.97
                elif stop < current * 0.85:
                    stop = current * 0.85

            # Target price
            target = self.exit_engine.calculate_target_price(current, stop)

            # 6-month return
            ret_6m = 0.0
            if len(hist) >= 130:
                ret_6m = ((current / float(hist['Close'].iloc[-130])) - 1) * 100

            # Relative strength
            spy_return = self._get_spy_return(data_provider, sim_date)
            rs_6m = ret_6m - spy_return

            # Distance to pivot (use current price as default pivot)
            # In production, pivot comes from watchlist data
            pivot = current
            dist_to_pivot = 0.0  # At pivot = 0%
            risk_pct = abs((stop - pivot) / pivot) * 100 if pivot > stop else 999

            # Entry score
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                           below_50ma=below_50ma, below_20ma=below_20ma)

            # Check minimum entry score
            min_score = 60
            if config:
                min_score = config.entry.min_entry_score
            if entry_score < min_score:
                continue

            # Position sizing
            if config:
                shares, _ = calculate_position_size_with_constraints(
                    equity, current, stop, config
                )
            else:
                shares = self.exit_engine.calculate_position_size(equity, current, stop)

            if shares <= 0:
                continue

            # Sector lookup via yfinance with caching
            sector = self._get_sector(ticker)

            # Initial stop price (immutable for R-multiple calculation)
            initial_stop_price = stop

            signals.append(EntrySignal(
                ticker=ticker,
                side='LONG',
                entry_price=current,
                stop_price=stop,
                target_price=target,
                shares=shares,
                sector=sector,
                entry_score=entry_score,
                stage2_score=stage2,
            ))

        return signals

    def evaluate_exits(self, sim_date: date, positions: dict[str, Position],
                       data_provider: DataFrameProvider,
                       risk_config: Optional[RiskConfig] = None) -> list[ExitAction]:
        """Evaluate exits for all held positions.

        Uses ExitEngine.evaluate_exit_action() which returns ExitAction.
        The caller (BacktestEngine) applies actions: EXIT, UPDATE_STOP, or HOLD.
        """
        actions = []

        for ticker, position in list(positions.items()):
            price = data_provider.get_current_price(ticker, sim_date)
            if price is None:
                continue

            hist = data_provider.get_bars(ticker, sim_date)
            action = self.exit_engine.evaluate_exit_action(
                position, price, historical_data=hist
            )
            actions.append(action)

        return actions

    # Implement unified interface using context adapter
    def manage_exits(self, context: StrategyContext) -> list[ExitAction]:
        """Unified exit management using StrategyContext."""
        return self.evaluate_exits(
            context.sim_date,
            context.positions,
            context.data_provider,
            context.risk_config
        )

    def evaluate_entries_unified(self, context: StrategyContext) -> list[EntrySignal]:
        """Unified entry evaluation using StrategyContext."""
        return self.evaluate_entries(
            context.sim_date,
            context.positions,
            context.data_provider,
            context.equity,
            context.risk_config
        )
