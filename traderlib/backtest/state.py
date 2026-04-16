"""Backtest state management.

Tracks positions, equity, and the simulation clock.
Never calls datetime.now() — all time is controlled by sim_date.
Never touches the filesystem — no save_state(), no _log_trade().
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from traderlib.paper_state import Position
from traderlib.backtest.data_provider import DataFrameProvider


# Sector position limits (same as production PaperState)
MAX_SECTOR_POSITIONS = 3


@dataclass
class TradeRecord:
    """Record of a completed trade in the backtest."""
    ticker: str
    side: str              # 'LONG' or 'SHORT'
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    exit_reason: str


@dataclass
class BacktestPosition:
    """A position in the backtest with side awareness.

    Extends Position with a `side` field for future short strategies.
    The engine stores BacktestPosition alongside Position for compatibility
    with ExitEngine (which expects Position objects).
    """
    position: Position       # The underlying Position (used by ExitEngine)
    side: str = 'LONG'       # 'LONG' or 'SHORT'
    entry_date: date = None  # Set from sim_date, never datetime.now()


class BacktestState:
    """Manages backtest state: positions, cash, and the simulation clock.

    Critical rules:
    - Never call datetime.now() — use sim_date
    - Never touch the filesystem
    - Always set initial_stop_price explicitly
    - Apply stop updates from ExitSignal (caller responsibility)
    - P&L is side-aware
    """

    def __init__(self, initial_capital: float, start_date: date,
                 risk_config=None, max_open_positions: int = 10):
        self.sim_date: date = start_date
        self.initial_capital: float = initial_capital
        self.cash: float = initial_capital
        self.positions: dict[str, BacktestPosition] = {}
        self.closed_trades: list[TradeRecord] = []
        self.equity_curve: list[tuple[date, float]] = []
        self.max_open_positions: int = max_open_positions
        self._risk_config = risk_config
        # Track SPY data for benchmark
        self._spy_prices: dict[date, float] = {}

    def set_date(self, d: date) -> None:
        """Advance the simulation clock."""
        self.sim_date = d

    @property
    def equity(self) -> float:
        """Total equity: cash + position values at current prices."""
        position_value = sum(
            bp.position.stop_price * bp.position.shares  # Conservative estimate
            for bp in self.positions.values()
        )
        # Use actual position value (entry price * shares) as approximation
        # mark_to_market() should be called daily for accurate equity
        position_value = sum(
            bp.position.entry_price * bp.position.shares
            for bp in self.positions.values()
        )
        return self.cash + position_value

    def can_enter_position(self, sector: str, position_value: float) -> tuple[bool, str]:
        """Check if entry is allowed based on risk rules.

        Checks:
        1. Max open positions
        2. Sector concentration limit
        3. Buying power
        """
        # Check max open positions
        if len(self.positions) >= self.max_open_positions:
            return False, f"Max positions reached ({self.max_open_positions})"

        # Check sector limit
        sector_counts: dict[str, int] = {}
        for bp in self.positions.values():
            sector_counts[bp.position.sector] = sector_counts.get(bp.position.sector, 0) + 1

        max_sector = MAX_SECTOR_POSITIONS
        if self._risk_config:
            max_sector = self._risk_config.account.max_sector_positions

        if sector_counts.get(sector, 0) >= max_sector:
            return False, f"Sector limit reached ({max_sector} in {sector})"

        # Check buying power
        if position_value > self.cash:
            return False, f"Insufficient cash (${self.cash:,.2f} < ${position_value:,.2f})"

        # Check position size limit
        if self._risk_config:
            max_pct = self._risk_config.position.max_position_pct
            if position_value > self.equity * max_pct:
                return False, (
                    f"Position size ${position_value:,.0f} exceeds "
                    f"{max_pct*100:.0f}% of equity"
                )

        return True, "OK"

    def enter_position(self, ticker: str, side: str, entry_price: float,
                       shares: int, stop_price: float, target_price: float,
                       sector: str, initial_stop_price: float) -> Position:
        """Open a new position.

        Args:
            ticker: Stock symbol
            side: 'LONG' or 'SHORT'
            entry_price: Fill price (after slippage)
            shares: Number of shares
            stop_price: Initial stop price
            target_price: Profit target price
            sector: Stock sector
            initial_stop_price: The immutable initial stop (for R-multiple calc)

        Returns:
            The Position object (compatible with ExitEngine)
        """
        position_value = entry_price * shares
        initial_risk = abs(entry_price - stop_price) * shares

        position = Position(
            ticker=ticker,
            status='OPEN',
            entry_date=self.sim_date.isoformat(),
            entry_price=entry_price,
            shares=shares,
            stop_price=stop_price,
            target_price=target_price,
            initial_risk=initial_risk,
            sector=sector,
            initial_stop_price=initial_stop_price,
        )

        self.positions[ticker] = BacktestPosition(
            position=position,
            side=side,
            entry_date=self.sim_date,
        )

        self.cash -= position_value
        return position

    def close_position(self, ticker: str, exit_price: float,
                       reason: str) -> TradeRecord:
        """Close a position and record the trade.

        P&L is side-aware:
        - LONG: (exit - entry) * shares
        - SHORT: (entry - exit) * shares

        Args:
            ticker: Stock symbol
            exit_price: Fill price (after slippage)
            reason: Exit reason string

        Returns:
            TradeRecord with P&L details
        """
        if ticker not in self.positions:
            raise ValueError(f"No position for {ticker}")

        bp = self.positions[ticker]
        pos = bp.position

        # Side-aware P&L
        if bp.side == 'LONG':
            pnl = (exit_price - pos.entry_price) * pos.shares
        else:  # SHORT
            pnl = (pos.entry_price - exit_price) * pos.shares

        trade = TradeRecord(
            ticker=ticker,
            side=bp.side,
            entry_date=bp.entry_date,
            exit_date=self.sim_date,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            shares=pos.shares,
            pnl=pnl,
            exit_reason=reason,
        )

        self.closed_trades.append(trade)
        self.cash += exit_price * pos.shares
        del self.positions[ticker]

        return trade

    def mark_to_market(self, data_provider: DataFrameProvider) -> float:
        """Update equity based on current market prices.

        Returns:
            Total equity at current prices
        """
        position_value = 0.0
        for bp in self.positions.values():
            price = data_provider.get_current_price(bp.position.ticker, self.sim_date)
            if price is not None:
                position_value += price * bp.position.shares
            else:
                # Fallback to entry price if no market price
                position_value += bp.position.entry_price * bp.position.shares

        total_equity = self.cash + position_value
        self.equity_curve.append((self.sim_date, total_equity))
        return total_equity