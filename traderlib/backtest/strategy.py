"""Strategy abstraction for backtesting.

Defines the Strategy ABC and Stage2MomentumStrategy implementation.
Entry/exit signals are dataclasses, not mutations of global state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from traderlib.backtest.data_provider import DataFrameProvider
from traderlib.backtest.execution import ExecutionModel, ExecutionConfig
from traderlib.backtest.state import BacktestState
from traderlib.paper_exits import ExitEngine, ExitSignal
from traderlib.paper_state import Position
from traderlib.stage2_utils import calculate_stage2_score, get_entry_score
from traderlib.risk_config import RiskConfig, calculate_position_size_with_constraints


@dataclass(frozen=True)
class EntrySignal:
    """Signal to enter a position."""
    ticker: str
    side: str = 'LONG'             # 'LONG' or 'SHORT' — enables future strategies
    entry_price: float = 0.0       # Intended entry price (T+1 open)
    stop_price: float = 0.0        # Initial stop price
    target_price: float = 0.0      # Profit target
    shares: int = 0                # Number of shares
    sector: str = 'Unknown'
    entry_score: int = 0           # Entry attractiveness score (0-100)
    stage2_score: int = 0         # Stage 2 compliance score (0-8)


@dataclass(frozen=True)
class ExitDecision:
    """Decision to exit a position."""
    ticker: str
    reason: str


class Strategy(ABC):
    """Abstract base class for trading strategies."""

    @abstractmethod
    def evaluate_entries(self, sim_date: date, positions: dict[str, Position],
                        data_provider: DataFrameProvider, equity: float,
                        risk_config: Optional[RiskConfig] = None) -> list[EntrySignal]:
        """Scan for entry opportunities.

        Args:
            sim_date: Current simulation date
            positions: Currently held positions (ticker -> Position)
            data_provider: Historical data provider (sliced to sim_date)
            equity: Current account equity
            risk_config: Optional risk configuration

        Returns:
            List of EntrySignal for new positions to enter
        """
        ...

    @abstractmethod
    def evaluate_exits(self, sim_date: date, positions: dict[str, Position],
                       data_provider: DataFrameProvider,
                       risk_config: Optional[RiskConfig] = None) -> list[ExitDecision]:
        """Evaluate exits for current positions.

        Args:
            sim_date: Current simulation date
            positions: Currently held positions (ticker -> Position)
            data_provider: Historical data provider (sliced to sim_date)
            risk_config: Optional risk configuration

        Returns:
            List of ExitDecision for positions to close
        """
        ...

    @property
    def side(self) -> str:
        """Default side for this strategy. Override for short strategies."""
        return 'LONG'


class Stage2MomentumStrategy(Strategy):
    """Stage 2 momentum strategy — mirrors paper engine entry/exit logic.

    Entry: Replicates _analyze_ticker() with injected data (no Alpaca calls).
    Exit: Delegates to ExitEngine.evaluate_exit() which returns ExitSignal
    with stop updates (no position mutation).
    """

    def __init__(self, exit_engine: ExitEngine, watchlist_tickers: Optional[list[str]] = None,
                 risk_config: Optional[RiskConfig] = None,
                 execution_config: Optional[ExecutionConfig] = None):
        """Initialize with dependencies.

        Args:
            exit_engine: ExitEngine instance for exit evaluation
            watchlist_tickers: Tickers to scan for entries (None = use data_provider)
            risk_config: Risk configuration for position sizing
            execution_config: Execution config for slippage calculations
        """
        self.exit_engine = exit_engine
        self.watchlist_tickers = watchlist_tickers
        self._risk_config = risk_config
        self._execution_model = ExecutionModel(execution_config or ExecutionConfig())
        # SPY return cache for RS calculation
        self._spy_return_cache: dict[date, float] = {}

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

    def evaluate_entries(self, sim_date: date, positions: dict[str, Position],
                        data_provider: DataFrameProvider, equity: float,
                        risk_config: Optional[RiskConfig] = None) -> list[EntrySignal]:
        """Scan watchlist for Stage 2 entry signals.

        Replicates the paper engine's _analyze_ticker() with injected data.
        """
        config = risk_config or self._risk_config
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

            # Stage 2 score
            stage2 = calculate_stage2_score(hist)

            # Calculate ATR and stop
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                ranges = pd.concat([high_low, high_close, low_close], axis=1)
                true_range = ranges.max(axis=1)
                atr = true_range.rolling(14).mean().iloc[-1]

                if pd.isna(atr):
                    continue
            except Exception:
                continue

            atr_stop = current - (2 * atr)
            recent_low = float(hist['Low'].tail(10).min())
            stop = max(atr_stop, recent_low)

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
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)

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

            # Sector (from watchlist data or default Unknown)
            sector = 'Unknown'

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
                       risk_config: Optional[RiskConfig] = None) -> list[ExitDecision]:
        """Evaluate exits for all held positions.

        Uses ExitEngine.evaluate_exit() which returns stop updates via ExitSignal.
        The caller (BacktestEngine) applies stop updates to positions.
        """
        decisions = []

        for ticker, position in list(positions.items()):
            price = data_provider.get_current_price(ticker, sim_date)
            if price is None:
                continue

            hist = data_provider.get_bars(ticker, sim_date)
            signal = self.exit_engine.evaluate_exit(
                position, price, historical_data=hist
            )

            # NOTE: stop updates are returned via signal.new_stop/new_stop_type
            # The engine applies these — we don't mutate here
            if signal.should_exit:
                decisions.append(ExitDecision(
                    ticker=ticker,
                    reason=signal.reason,
                ))

        return decisions