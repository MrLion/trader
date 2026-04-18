"""Unified strategy architecture for backtest, paper, and live trading.

Provides a single Strategy ABC that works across all execution modes,
with auto-discovery registry for pluggable strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Type, Any, Protocol

import pandas as pd


# ============ Exit Action Types ============

class ExitActionType(Enum):
    """Exit action types for type-safe exit handling.

    Used with ExitAction for atomic exit decisions.
    """
    EXIT = "exit"              # Full position exit
    UPDATE_STOP = "update_stop"  # Stop loss update only
    HOLD = "hold"              # No action


# ============ Signal Dataclasses ============

@dataclass(frozen=True)
class EntrySignal:
    """Signal to enter a position.

    Attributes:
        ticker: Stock symbol
        side: 'LONG' or 'SHORT'
        entry_price: Intended entry price
        stop_price: Initial stop price
        target_price: Profit target (may be trailed)
        shares: Number of shares to buy
        sector: Stock sector for concentration limits
        entry_score: Entry attractiveness (0-100)
        stage2_score: Stage 2 compliance (0-10)
        metadata: Strategy-specific data (VCP data, convergence, etc.)
    """
    ticker: str
    side: str = 'LONG'
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    shares: int = 0
    sector: str = 'Unknown'
    entry_score: int = 0
    stage2_score: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExitAction:
    """Unified exit action — atomic exit decision.

    Single method returns one action: EXIT, UPDATE_STOP, or HOLD.
    Replaces ambiguous should_exit flag pattern.

    Attributes:
        ticker: Stock symbol
        action: ExitActionType enum (EXIT, UPDATE_STOP, or HOLD)
        reason: Human-readable reason for the action
        exit_price: Price for EXIT actions
        r_multiple: Current R multiple (for trailing logic)
        new_stop_price: New stop price for UPDATE_STOP actions
        new_stop_type: Type of stop (e.g., 'TRAIL_EMA10', 'BREAKEVEN')
        metadata: Strategy-specific additional data
    """
    ticker: str
    action: ExitActionType
    reason: str
    exit_price: Optional[float] = None
    r_multiple: float = 0.0
    new_stop_price: Optional[float] = None
    new_stop_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============ Data Provider Protocol ============

class DataFrameProvider(Protocol):
    """Protocol for data providers - implemented by backtest and paper engines."""

    def get_bars(self, ticker: str, as_of: date, min_rows: int = 30) -> Optional[pd.DataFrame]:
        """Get historical bars for ticker up to as_of date."""
        ...

    def get_current_price(self, ticker: str, as_of: date) -> Optional[float]:
        """Get current/latest price for ticker as of date."""
        ...


# ============ Strategy Context ============

@dataclass
class StrategyContext:
    """All data and dependencies a strategy needs, injected by engine.

    Designed for:
    - Backtest compatibility (sim_date, data_provider)
    - Paper/live compatibility (current prices, real portfolio)
    - Easy testing (mock context with minimal data)

    Note: Uses DataFrameProvider protocol for data access — does not
    duplicate raw data. Backtest uses AlpacaDataProvider; paper uses
    PaperDataProvider adapter wrapping AlpacaClient.
    """
    # Data provider (authoritative source for all market data)
    data_provider: DataFrameProvider

    # Market data (cached convenience fields — prefer data_provider for freshness)
    sim_date: date                          # Backtest: simulation date; Paper: today
    spy_data: Optional[pd.DataFrame] = None  # SPY history for RS calculations
    spy_current: Optional[float] = None     # Current SPY price
    vix_current: Optional[float] = None     # Current VIX (if available)

    # Portfolio state
    positions: Dict[str, Any] = field(default_factory=dict)  # ticker -> Position
    cash: float = 0.0
    equity: float = 0.0
    day_pnl: float = 0.0

    # Risk configuration
    risk_config: Optional[Any] = None
    execution_config: Optional[Any] = None

    # Helpers (delegated to data_provider)
    def get_bars(self, ticker: str, lookback_days: int = 200) -> Optional[pd.DataFrame]:
        """Get historical bars for ticker up to sim_date."""
        return self.data_provider.get_bars(ticker, self.sim_date, min_rows=lookback_days)

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current/latest price for ticker."""
        return self.data_provider.get_current_price(ticker, self.sim_date)


# ============ Strategy ABC ============

class Strategy(ABC):
    """Abstract base class for all trading strategies.

    One interface for:
    - Backtesting (deterministic, historical)
    - Paper trading (real-time, simulated execution)
    - Live trading (real-time, real execution)

    Implement evaluate_entries() to find opportunities and
    manage_exits() to handle position management with atomic actions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (e.g., 'vcp_breakout', 'stage2_momentum')."""
        pass

    @abstractmethod
    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """Scan for entry opportunities.

        Args:
            context: All market data, portfolio state, helpers

        Returns:
            List of EntrySignal for new positions
        """
        pass

    @abstractmethod
    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """Manage exits for all open positions.

        Called once per cycle. Returns atomic actions for each position.

        Args:
            context: Contains positions dict, current prices, helpers

        Returns:
            List of ExitAction (EXIT, UPDATE_STOP, or HOLD per position)
        """
        pass

    # ============ Optional Lifecycle Hooks (override as needed) ============

    def on_day_start(self, context: StrategyContext):
        """Called at start of each trading day."""
        pass

    def on_day_end(self, context: StrategyContext):
        """Called at end of trading day (after market close)."""
        pass

    def on_market_regime_change(self, old_regime: str, new_regime: str,
                                context: StrategyContext):
        """Called when market regime changes (e.g., BULL → BEAR)."""
        pass

    def on_position_opened(self, position: Any, context: StrategyContext):
        """Called when a position is opened (fill confirmed)."""
        pass

    def on_position_closed(self, position: Any, pnl: float,
                           context: StrategyContext):
        """Called when a position is closed."""
        pass

    @property
    def side(self) -> str:
        """Default side for this strategy. Override for short strategies."""
        return 'LONG'


# ============ Strategy Registry (Auto-Discovery) ============

STRATEGY_REGISTRY: Dict[str, Type[Strategy]] = {}


def register_strategy(name: str):
    """Decorator to auto-register strategy classes.

    Usage:
        @register_strategy('vcp_large_cap')
        class VCPBreakoutStrategy(Strategy):
            ...
    """
    def decorator(cls: Type[Strategy]) -> Type[Strategy]:
        STRATEGY_REGISTRY[name] = cls
        return cls
    return decorator


def get_strategy(name: str, **kwargs) -> Optional[Strategy]:
    """Get strategy instance by name with constructor args."""
    cls = STRATEGY_REGISTRY.get(name)
    if cls:
        return cls(**kwargs)
    return None


def list_strategies() -> List[str]:
    """List all registered strategy names."""
    return list(STRATEGY_REGISTRY.keys())


# Re-export ExitAction for backward compatibility with paper_exits
from traderlib.paper_exits import ExitAction as PaperExitAction

# Verify ExitAction compatibility
assert ExitAction is not None, "ExitAction must be defined"

# Import and register strategy implementations
# These imports trigger the @register_strategy decorators
from traderlib.strategies import vcp_breakout  # noqa: F401,E402
from traderlib.strategies import composite   # noqa: F401,E402
