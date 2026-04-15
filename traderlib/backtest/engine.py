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
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from traderlib.backtest.data_provider import DataFrameProvider
from traderlib.backtest.execution import ExecutionModel, ExecutionConfig, FillResult
from traderlib.backtest.state import BacktestState, BacktestPosition, TradeRecord
from traderlib.backtest.strategy import Strategy, EntrySignal, ExitDecision
from traderlib.paper_exits import ExitEngine
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

        # Risk configuration
        self._risk_config: Optional[RiskConfig] = None
        try:
            manager = RiskConfigManager(profile=config.risk_profile)
            self._risk_config = manager.get_config()
        except Exception:
            pass

        # Execution model
        self._execution = ExecutionModel(config.execution_config or ExecutionConfig())

        # Pending signals (filled at T+1 open)
        self._pending_entries: list[EntrySignal] = []
        self._pending_exits: list[ExitDecision] = []

        # Gap rejections (entries rejected due to T+1 gap)
        self._gap_rejections: list[dict] = []

    def run(self) -> BacktestResult:
        """Execute the backtest day by day.

        Returns:
            BacktestResult with trades, equity curve, and final state
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
        if self.config.tickers:
            prefetch_tickers = list(self.config.tickers) + ['SPY']
            self.data_provider.prefetch(
                prefetch_tickers,
                start=self.config.start_date,
                end=self.config.end_date,
            )

        # Collect dropped tickers from provider
        tickers_dropped = []
        if hasattr(self.data_provider, 'tickers_dropped'):
            tickers_dropped = list(self.data_provider.tickers_dropped)

        # Previous day tracking for T+1 fills
        prev_date: Optional[date] = None

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

            # First, update stops via ExitEngine
            self._update_stops(state, sim_date)

            # Then, get exit decisions from strategy
            exit_decisions = self.strategy.evaluate_exits(
                sim_date, current_positions, self.data_provider,
                self._risk_config
            )

            # Step 3: Mark to market
            state.mark_to_market(self.data_provider)

            # Step 4: Evaluate entries (signals fill at T+1)
            entry_signals = self.strategy.evaluate_entries(
                sim_date, current_positions, self.data_provider,
                state.equity, self._risk_config
            )

            # Queue signals for T+1 execution
            self._pending_entries = entry_signals
            self._pending_exits = exit_decisions

            prev_date = sim_date

        # End of simulation: liquidate all positions at last close
        self._liquidate_positions(state, trading_days[-1])

        # Final mark to market
        state.mark_to_market(self.data_provider)

        # Fetch SPY benchmark data
        benchmark = self._get_benchmark(trading_days)

        return BacktestResult(
            trades=state.closed_trades,
            equity_curve=state.equity_curve,
            state=state,
            benchmark=benchmark,
            config=self.config,
            gap_rejections=self._gap_rejections,
            tickers_dropped=tickers_dropped,
        )

    def _resolve_pending_fills(self, state: BacktestState, sim_date: date):
        """Resolve yesterday's entry and exit signals at today's open.

        Entry fills: BUY at T+1 open + slippage
        Exit fills: SELL at T+1 open - slippage

        Gap rejection: Skip entry if T+1 open > stop price (risk/reward invalidated).
        """
        # Resolve exits first (free up capital for entries)
        for exit_decision in self._pending_exits:
            ticker = exit_decision.ticker
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
                ticker, fill.fill_price, exit_decision.reason,
                commission=fill.commission
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

    def _update_stops(self, state: BacktestState, sim_date: date):
        """Apply stop updates from ExitSignal to positions.

        ExitEngine.evaluate_exit() returns new_stop/new_stop_type via ExitSignal.
        The engine applies these — no position mutation inside evaluate_exit.
        """
        exit_engine = getattr(self.strategy, 'exit_engine', None)
        if exit_engine is None:
            return

        for ticker, bp in list(state.positions.items()):
            price = self.data_provider.get_current_price(ticker, sim_date)
            if price is None:
                continue

            try:
                hist = self.data_provider.get_bars(ticker, sim_date)
                signal = exit_engine.evaluate_exit(
                    bp.position, price, historical_data=hist
                )

                if signal.new_stop is not None:
                    bp.position.stop_price = signal.new_stop
                    bp.position.current_stop_type = signal.new_stop_type
            except Exception:
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
                ticker, fill.fill_price, 'LIQUIDATION',
                commission=fill.commission
            )

    def _get_benchmark(self, trading_days: list[date]) -> pd.DataFrame:
        """Fetch buy-and-hold SPY benchmark data."""
        try:
            spy_data = self.data_provider.get_bars(
                'SPY', trading_days[-1]
            )
            # Filter to trading days in our range
            start_ts = pd.Timestamp(trading_days[0])
            end_ts = pd.Timestamp(trading_days[-1])
            mask = (spy_data.index >= start_ts) & (spy_data.index <= end_ts)
            return spy_data.loc[mask]
        except Exception:
            return pd.DataFrame()

    def _load_watchlist(self, path: Path) -> list[str]:
        """Load tickers from a watchlist CSV."""
        if not path.exists():
            raise FileNotFoundError(f"Watchlist file not found: {path}")
        try:
            df = pd.read_csv(path)
            if 'Ticker' in df.columns:
                return df['Ticker'].dropna().unique().tolist()
            raise ValueError(f"'Ticker' column not found in {path}")
        except pd.errors.EmptyDataError:
            raise ValueError(f"Watchlist file is empty: {path}")
        except Exception as e:
            raise ValueError(f"Failed to load watchlist from {path}: {e}")