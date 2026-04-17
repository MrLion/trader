"""Backtest engine — day-by-day simulation with next-bar fill.

The engine drives the daily loop:
1. Advance clock
2. Resolve fills from yesterday's signals at today's open
3. Load sliced data (<= sim_date)
4. Evaluate exits (apply stop updates from ExitSignal)
5. Mark to market
6. Evaluate entries
7. Queue new signals for T+1 execution
8. Record equity

At end: liquidate, compute buy-and-hold SPY benchmark.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from traderlib.backtest.data_provider import DataFrameProvider
from traderlib.backtest.execution import ExecutionModel, ExecutionConfig, FillResult
from traderlib.backtest.state import BacktestState, BacktestPosition, TradeRecord
from traderlib.backtest.strategy import Strategy, EntrySignal, BacktestStrategyContext
from traderlib.paper_exits import ExitEngine, ExitAction, ExitActionType
from traderlib.paper_state import Position
from traderlib.risk_config import RiskConfig, RiskConfigManager


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    tickers: Optional[list[str]] = None
    watchlist_path: Optional[Path] = None
    risk_profile: str = "conservative"
    execution_config: Optional[ExecutionConfig] = None
    max_open_positions: int = 10
    on_progress: Optional[Callable] = None
    progress_interval: int = 1


@dataclass
class BacktestProgress:
    """Progress snapshot emitted during backtest simulation."""
    phase: str                      # "prefetch" or "simulation"
    current: int                    # Current iteration
    total: int                      # Total iterations
    sim_date: Optional[date] = None # Current simulation date (simulation only)
    positions: int = 0              # Open position count
    equity: float = 0.0            # Current equity
    trades: int = 0                # Closed trade count
    ticker: Optional[str] = None   # Current ticker (prefetch only)


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    trades: list[TradeRecord]
    equity_curve: list[tuple[date, float]]
    state: BacktestState
    benchmark: pd.DataFrame
    config: BacktestConfig
    gap_rejections: list[dict] = field(default_factory=list)
    tickers_dropped: list[dict] = field(default_factory=list)
    partial: bool = False  # True if run was interrupted


class BacktestEngine:
    """Drives the backtest simulation.

    The engine is the orchestrator — it connects data, strategy, state,
    and execution into a day-by-day loop. It does NOT contain trading logic.
    """

    def __init__(self, data_provider: DataFrameProvider,
                 strategy: Strategy, config: BacktestConfig):
        self.data_provider = data_provider
        self.strategy = strategy
        self.config = config

        # Risk configuration (quiet=True to avoid duplicate print — backtest.py already reports profile)
        self._risk_config: Optional[RiskConfig] = None
        try:
            manager = RiskConfigManager(profile=config.risk_profile, quiet=True)
            self._risk_config = manager.get_config()
        except Exception:
            pass

        # Execution model
        self._execution = ExecutionModel(config.execution_config or ExecutionConfig())

        # Pending signals (filled at T+1 open)
        self._pending_entries: list[EntrySignal] = []
        self._pending_exits: list[ExitAction] = []

        # Gap rejections (entries rejected due to T+1 gap)
        self._gap_rejections: list[dict] = []

    def run(self) -> BacktestResult:
        """Execute the backtest day by day.

        Returns:
            BacktestResult with trades, equity curve, and final state.
            If interrupted by Ctrl+C, returns a partial result with
            BacktestResult.partial=True.
        """
        # Initialize state
        state = BacktestState(
            initial_capital=self.config.initial_capital,
            start_date=self.config.start_date,
            risk_config=self._risk_config,
            max_open_positions=self.config.max_open_positions,
        )

        # Get trading days
        trading_days = self.data_provider.get_trading_days(
            self.config.start_date, self.config.end_date
        )

        if not trading_days:
            raise ValueError(
                f"No trading days between {self.config.start_date} and "
                f"{self.config.end_date}"
            )

        # Load watchlist tickers if path provided
        if self.config.watchlist_path and self.config.tickers is None:
            self.config.tickers = self._load_watchlist(self.config.watchlist_path)

        # Prefetch data for tickers
        # Extend start date by ~400 days to provide historical context for
        # indicators (130-day RS, 50-day MA, 14-day ATR) and satisfy the
        # data provider's 252-row min_lookback requirement
        was_interrupted = False
        if self.config.tickers:
            prefetch_tickers = list(self.config.tickers) + ['SPY']
            prefetch_start = self.config.start_date - timedelta(days=400)
            # Pass progress callback to prefetch if available
            prefetch_kwargs = dict(
                tickers=prefetch_tickers,
                start=prefetch_start,
                end=self.config.end_date,
            )
            if self.config.on_progress:
                def _prefetch_cb(current, total, ticker):
                    self.config.on_progress(BacktestProgress(
                        phase="prefetch", current=current, total=total, ticker=ticker,
                    ))
                prefetch_kwargs['on_progress'] = _prefetch_cb
            try:
                self.data_provider.prefetch(**prefetch_kwargs)
            except KeyboardInterrupt:
                cached = len(getattr(self.data_provider, '_cache', {}))
                print(f"\n  Interrupted during data fetch ({cached} tickers cached)")
                raise

        # Collect dropped tickers from provider
        tickers_dropped = []
        if hasattr(self.data_provider, 'tickers_dropped'):
            tickers_dropped = list(self.data_provider.tickers_dropped)

        # Previous day tracking for T+1 fills
        prev_date: Optional[date] = None

        try:
            for i, sim_date in enumerate(trading_days):
                state.set_date(sim_date)

                # Step 1: Resolve pending fills from yesterday's signals
                if prev_date is not None and i > 0:
                    self._resolve_pending_fills(state, sim_date)

                # Clear pending queues (they've been resolved)
                self._pending_entries = []
                self._pending_exits = []

                # Step 2: Evaluate exits for current positions
                current_positions = {
                    ticker: bp.position
                    for ticker, bp in state.positions.items()
                }

                # Get exit actions from strategy (unified: EXIT, UPDATE_STOP, or HOLD)
                exit_actions = self.strategy.evaluate_exits(
                    sim_date, current_positions, self.data_provider,
                    self._risk_config
                )

                # Apply exit actions: handle EXIT and UPDATE_STOP
                self._apply_exit_actions(state, exit_actions)

                # Step 3: Mark to market
                state.mark_to_market(self.data_provider)

                # Emit progress after mark_to_market (equity is accurate here)
                if self.config.on_progress and i % self.config.progress_interval == 0:
                    self.config.on_progress(BacktestProgress(
                        phase="simulation",
                        current=i + 1,
                        total=len(trading_days),
                        sim_date=sim_date,
                        positions=len(state.positions),
                        equity=state.equity,
                        trades=len(state.closed_trades),
                    ))

                # Step 4: Evaluate entries (signals fill at T+1)
                entry_signals = self.strategy.evaluate_entries(
                    sim_date, current_positions, self.data_provider,
                    state.equity, self._risk_config
                )

                # Queue signals for T+1 execution
                self._pending_entries = entry_signals
                self._pending_exits = [a for a in exit_actions if a.action == ExitActionType.EXIT]

                prev_date = sim_date

        except KeyboardInterrupt:
            was_interrupted = True

        # Liquidate remaining positions (always — normal completion or interrupt)
        if state.positions:
            last_date = state.sim_date or trading_days[-1]
            self._liquidate_positions(state, last_date)

        # Final mark to market
        state.mark_to_market(self.data_provider)

        # Fetch SPY benchmark data
        benchmark = self._get_benchmark(trading_days) if not was_interrupted else pd.DataFrame()

        return BacktestResult(
            trades=state.closed_trades,
            equity_curve=state.equity_curve,
            state=state,
            benchmark=benchmark,
            config=self.config,
            gap_rejections=self._gap_rejections,
            tickers_dropped=tickers_dropped,
            partial=was_interrupted,
        )

    def _resolve_pending_fills(self, state: BacktestState, sim_date: date):
        """Resolve yesterday's entry and exit signals at today's open.

        Entry fills: BUY at T+1 open + slippage
        Exit fills: SELL at T+1 open - slippage

        Gap rejection: Skip entry if T+1 open > stop price (risk/reward invalidated).
        """
        # Resolve exits first (free up capital for entries)
        for exit_action in self._pending_exits:
            ticker = exit_action.ticker
            if ticker not in state.positions:
                continue

            bp = state.positions[ticker]
            # Get T+1 open price
            exit_price = self.data_provider.get_current_price(ticker, sim_date)
            if exit_price is None:
                continue

            # Simulate fill with slippage
            fill = self._execution.simulate_fill(
                ticker, 'SELL', bp.position.shares, exit_price
            )

            state.close_position(
                ticker, fill.fill_price, exit_action.reason
            )

        # Resolve entries
        for signal in self._pending_entries:
            ticker = signal.ticker
            if ticker in state.positions:
                continue  # Already holding

            # Get T+1 open price
            open_price = self.data_provider.get_current_price(ticker, sim_date)
            if open_price is None:
                continue

            # Gap rejection: if T+1 open exceeds stop price, reject entry
            if open_price >= signal.stop_price and signal.side == 'LONG':
                # For long positions: if open price is above stop, the stop
                # is already invalidated. But more importantly, if the open
                # gapped down below stop, the stop would trigger immediately.
                # The real gap rejection: if T+1 open > signal.entry_price significantly,
                # the risk/reward is worse than planned.
                pass  # Normal case — proceed with entry

            # Check if T+1 open gapped below stop (stop would trigger immediately)
            if signal.side == 'LONG' and open_price <= signal.stop_price:
                self._gap_rejections.append({
                    'ticker': ticker,
                    'date': sim_date,
                    'signal_price': signal.entry_price,
                    'open_price': open_price,
                    'stop_price': signal.stop_price,
                    'reason': 'open_below_stop',
                })
                continue

            # Position value check
            position_value = open_price * signal.shares
            can_enter, reason = state.can_enter_position(
                signal.sector, position_value
            )
            if not can_enter:
                continue

            # Simulate fill
            fill = self._execution.simulate_fill(
                ticker, 'BUY', signal.shares, open_price
            )

            state.enter_position(
                ticker=ticker,
                side=signal.side,
                entry_price=fill.fill_price,
                shares=signal.shares,
                stop_price=signal.stop_price,
                target_price=signal.target_price,
                sector=signal.sector,
                initial_stop_price=signal.stop_price,
            )

    def _apply_exit_actions(self, state: BacktestState, actions: list[ExitAction]):
        """Apply exit actions to positions.

        Handles EXIT (queued for T+1), UPDATE_STOP (applied immediately),
        and HOLD (no action) actions atomically.
        """
        for action in actions:
            ticker = action.ticker
            if ticker not in state.positions:
                continue

            bp = state.positions[ticker]

            if action.action == ExitActionType.UPDATE_STOP:
                # Apply stop update immediately
                if action.new_stop_price is not None:
                    bp.position.stop_price = action.new_stop_price
                    bp.position.current_stop_type = action.new_stop_type or bp.position.current_stop_type

            elif action.action == ExitActionType.EXIT:
                # EXIT actions are queued for T+1 execution
                # (Handled by _pending_exits in main loop)
                pass

            elif action.action == ExitActionType.HOLD:
                # No action needed
                pass

    def _liquidate_positions(self, state: BacktestState, last_date: date):
        """Close all remaining positions at the last trading day's close."""
        for ticker in list(state.positions.keys()):
            bp = state.positions[ticker]
            price = self.data_provider.get_current_price(ticker, last_date)
            if price is None:
                # Fallback to entry price
                price = bp.position.entry_price

            fill = self._execution.simulate_fill(
                ticker, 'SELL', bp.position.shares, price
            )

            state.close_position(
                ticker, fill.fill_price, 'LIQUIDATION'
            )

    def _get_benchmark(self, trading_days: list[date]) -> pd.DataFrame:
        """Fetch buy-and-hold SPY benchmark data."""
        try:
            spy_data = self.data_provider.get_bars(
                'SPY', trading_days[-1]
            )
            # Strip timezone from index for date-only comparison
            spy_idx = spy_data.index.tz_localize(None) if spy_data.index.tz else spy_data.index
            # Normalize to midnight for date-level comparison
            spy_dates = spy_idx.normalize()
            start_d = pd.Timestamp(trading_days[0])
            end_d = pd.Timestamp(trading_days[-1])
            mask = (spy_dates >= start_d) & (spy_dates <= end_d)
            return spy_data.loc[mask]
        except Exception:
            return pd.DataFrame()

    def _build_context(self, sim_date: date, state: BacktestState) -> BacktestStrategyContext:
        """Build unified StrategyContext from backtest state.

        Enables strategies to use unified interface (evaluate_entries_unified,
        manage_exits) while maintaining backward compatibility.
        """
        current_positions = {
            ticker: bp.position
            for ticker, bp in state.positions.items()
        }

        return BacktestStrategyContext(
            data_provider=self.data_provider,
            sim_date=sim_date,
            positions=current_positions,
            equity=state.equity,
            cash=state.cash,
            risk_config=self._risk_config
        )

    def _load_watchlist(self, path: Path) -> list[str]:
        """Load tickers from a watchlist CSV."""
        if not path.exists():
            raise FileNotFoundError(f"Watchlist file not found: {path}")
        try:
            df = pd.read_csv(path)
            # Accept both 'Ticker' (regular watchlist) and 'ticker' (historical scraper)
            ticker_col = 'Ticker' if 'Ticker' in df.columns else 'ticker' if 'ticker' in df.columns else None
            if ticker_col:
                return df[ticker_col].dropna().unique().tolist()
            raise ValueError(f"'Ticker' or 'ticker' column not found in {path}")
        except pd.errors.EmptyDataError:
            raise ValueError(f"Watchlist file is empty: {path}")
        except Exception as e:
            raise ValueError(f"Failed to load watchlist from {path}: {e}")