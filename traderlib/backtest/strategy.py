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


# Backward compatibility alias
ExitDecision = ExitAction  # Alias for tests using old name

# Re-export for backward compatibility
__all__ = [
    'BaseStrategy',
    'StrategyContext',
    'EntrySignal',
    'ExitAction',
    'ExitActionType',
    'ExitDecision',  # For backward compatibility
    'Stage2MomentumStrategy',
]


# Backtest-specific adapter context builder
class BacktestStrategyContext(StrategyContext):
    """Adapter: wraps backtest's data provider into unified context."""

    def __init__(self, data_provider: DataFrameProvider, sim_date: date,
                 positions: Dict[str, Position], equity: float, cash: float,
                 risk_config: Optional[RiskConfig] = None,
                 spy_data: Optional[pd.DataFrame] = None,
                 vix_current: Optional[float] = None):
        self._data_provider = data_provider
        self._sim_date = sim_date
        self.sim_date = sim_date
        self.positions = positions
        self.equity = equity
        self.cash = cash
        self.risk_config = risk_config
        self.spy_data = spy_data
        self.spy_current = None
        self.vix_current = vix_current
        self.day_pnl = 0.0

    def get_bars(self, ticker: str, lookback_days: int = 200) -> Optional[pd.DataFrame]:
        """Get historical bars for ticker."""
        return self._data_provider.get_bars(ticker, self._sim_date)

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current/latest price."""
        return self._data_provider.get_current_price(ticker, self._sim_date)


class Strategy(BaseStrategy):
    """Backtest-compatible Strategy base class using unified StrategyContext interface.

    All strategies must implement evaluate_entries(context) and manage_exits(context)
    using the unified StrategyContext interface.
    """

    @abstractmethod
    def evaluate_entries(self, context: StrategyContext) -> list[EntrySignal]:
        """Scan for entry opportunities using unified StrategyContext.

        Args:
            context: StrategyContext with data_provider, positions, equity, etc.

        Returns:
            List of EntrySignal for new positions
        """
        pass

    @abstractmethod
    def manage_exits(self, context: StrategyContext) -> list[ExitAction]:
        """Manage exits for current positions using unified StrategyContext.

        Args:
            context: StrategyContext with data_provider, positions, etc.

        Returns:
            List of ExitAction (EXIT, UPDATE_STOP, or HOLD per position)
        """
        pass

    def _build_context(self, sim_date: date, positions: dict[str, Position],
                      data_provider: DataFrameProvider, equity: float,
                      risk_config: Optional[RiskConfig] = None,
                      vix_current: Optional[float] = None) -> BacktestStrategyContext:
        """Build unified context from backtest parameters."""
        return BacktestStrategyContext(
            data_provider=data_provider,
            sim_date=sim_date,
            positions=positions,
            equity=equity,
            cash=equity,  # Approximation - backtest tracks cash separately
            risk_config=risk_config,
            vix_current=vix_current
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
        # Sector cache - populated from watchlist_df sector column or provided dict
        self._sector_cache: dict[str, str] = {}
        # Note: No yfinance imports - backtest must use provided sector data only

        # Load strategy-specific parameters from config/strategies/stage2_momentum.yaml.
        # Falls back to hardcoded defaults when file is absent.
        from traderlib.strategy_config import load_strategy_config, get_param
        _scfg = load_strategy_config('stage2_momentum') or {}
        self._strategy_params = {
            'min_stage2_score':      get_param(_scfg, 'entry', 'min_stage2_score',   default=6),
            'min_entry_score':       get_param(_scfg, 'entry', 'min_entry_score',     default=60),
            'atr_period':            get_param(_scfg, 'stop',  'atr_period',          default=14),
            'atr_multiplier':        get_param(_scfg, 'stop',  'atr_multiplier',      default=2.0),
            'use_recent_low':        get_param(_scfg, 'stop',  'use_recent_low',      default=True),
            'min_stop_distance_pct': get_param(_scfg, 'stop',  'min_stop_distance_pct', default=0.03),
            'max_stop_distance_pct': get_param(_scfg, 'stop',  'max_stop_distance_pct', default=0.15),
            'breakeven_at_r':        get_param(_scfg, 'exit',  'breakeven_at_r',      default=1.0),
            'trail_ema_period':      get_param(_scfg, 'exit',  'trail_ema_period',    default=20),
            'trail_start_r':         get_param(_scfg, 'exit',  'trail_start_r',       default=1.5),
        }

    @property
    def name(self) -> str:
        return "stage2_momentum"

    @property
    def side(self) -> str:
        return 'LONG'

    def _get_spy_return_from_context(self, context: StrategyContext,
                                       lookback_days: int = 130) -> float:
        """Get SPY 6-month return for relative strength calculation.

        Returns 0.0 if SPY data is unavailable.
        """
        as_of = context.sim_date
        if as_of in self._spy_return_cache:
            return self._spy_return_cache[as_of]

        try:
            spy_data = context.get_bars('SPY', lookback_days=lookback_days)
            if spy_data is not None and len(spy_data) >= lookback_days:
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
        """Get sector for ticker from watchlist_df or sector_dict.

        Note: Does NOT use yfinance - backtest must use provided sector data only.
        Returns 'Unknown' if sector not available.
        """
        if ticker in self._sector_cache:
            return self._sector_cache[ticker]

        # Try to get from watchlist_df sector column
        if self.watchlist_df is not None:
            try:
                active = self.watchlist_df[pd.to_datetime(self.watchlist_df['week_start']) <= pd.Timestamp(date.today())]
                active = active.sort_values('week_start').groupby('ticker').last().reset_index()
                ticker_row = active[active['ticker'] == ticker]
                if len(ticker_row) > 0 and 'sector' in ticker_row.columns:
                    sector = ticker_row['sector'].iloc[0]
                    if pd.notna(sector):
                        self._sector_cache[ticker] = str(sector)
                        return self._sector_cache[ticker]
            except Exception:
                pass

        # Default to Unknown if no sector data available
        self._sector_cache[ticker] = 'Unknown'
        return 'Unknown'

    def evaluate_entries(self, context: StrategyContext) -> list[EntrySignal]:
        """Evaluate entries using Stage 2 momentum criteria.

        Uses unified StrategyContext interface.
        """
        # Extract parameters from context
        sim_date = context.sim_date
        positions = context.positions
        equity = context.equity
        config = context.risk_config or self._risk_config

        # Get tickers to scan
        if self.watchlist_df is not None:
            if 'week_start' in self.watchlist_df.columns:
                # Date-aware filtering from historical watchlist (mcstock_scraper output)
                active = self.watchlist_df[pd.to_datetime(self.watchlist_df['week_start']) <= pd.Timestamp(sim_date)]
                active = active.sort_values('week_start').groupby('ticker').last().reset_index()
                ticker_col = 'ticker' if 'ticker' in active.columns else 'Ticker'
                tickers = active[ticker_col].dropna().unique().tolist()
            else:
                # Plain ticker list (trend screener output or simple watchlist)
                ticker_col = 'Ticker' if 'Ticker' in self.watchlist_df.columns else 'ticker'
                tickers = self.watchlist_df[ticker_col].dropna().unique().tolist()
        else:
            tickers = self.watchlist_tickers or []

        signals = []

        for ticker in tickers:
            # Skip if already holding
            if ticker in positions:
                continue

            try:
                hist = context.get_bars(ticker, lookback_days=200)
            except Exception:
                continue

            if hist is None or len(hist) < 30:
                continue

            current = float(hist['Close'].iloc[-1])
            if current <= 0:
                continue

            # Stage 2 score and MA flags
            s2_details = get_stage2_details(hist)
            stage2 = s2_details['score']
            below_50ma = not s2_details['criteria'].get('price_above_50ma', True)
            below_20ma = not s2_details['criteria'].get('price_above_20ema', False)

            # Minimum Stage 2 score — from stage2_momentum.yaml (default 6)
            if stage2 < self._strategy_params['min_stage2_score']:
                continue

            # Calculate ATR for stop — period/multiplier from stage2_momentum.yaml
            atr_period = self._strategy_params['atr_period']
            atr_mult   = self._strategy_params['atr_multiplier']
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = tr.rolling(window=atr_period, min_periods=1).mean().iloc[-1]
                if pd.isna(atr):
                    continue
            except Exception:
                continue

            atr_stop = current - (atr_mult * atr)
            recent_low = float(hist['Low'].tail(10).min())
            stop = max(atr_stop, recent_low) if self._strategy_params['use_recent_low'] else atr_stop

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

            # Enforce bounds — risk_config takes priority, strategy YAML is fallback
            if config:
                min_pct = config.stop_loss.min_stop_distance_pct
                max_pct = config.stop_loss.max_stop_distance_pct
            else:
                min_pct = self._strategy_params['min_stop_distance_pct']
                max_pct = self._strategy_params['max_stop_distance_pct']
            min_stop = current * (1 - min_pct)
            max_stop = current * (1 - max_pct)
            if stop > min_stop:
                stop = min_stop
            if stop < max_stop:
                stop = max_stop

            # Target price
            target = self.exit_engine.calculate_target_price(current, stop)

            # 6-month return
            ret_6m = 0.0
            if len(hist) >= 130:
                ret_6m = ((current / float(hist['Close'].iloc[-130])) - 1) * 100

            # Relative strength - fetch SPY data via context
            spy_return = self._get_spy_return_from_context(context)
            rs_6m = ret_6m - spy_return

            # Pivot proximity cannot be measured in a historical simulation without
            # live watchlist pivot data. Use dist_to_pivot = 0.0 to neutralise the
            # proximity component — every stock gets the same score, so the factor
            # does not bias selection.
            pivot = current
            dist_to_pivot = 0.0
            risk_pct = abs((stop - current) / current) * 100 if current > stop else 999

            # Entry score
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                           below_50ma=below_50ma, below_20ma=below_20ma)

            # Check minimum entry score — risk_config wins, strategy YAML is fallback
            min_score = self._strategy_params['min_entry_score']
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
                metadata={'pivot': pivot},
            ))

        return signals

    def manage_exits(self, context: StrategyContext) -> list[ExitAction]:
        """Evaluate exits for all held positions using unified StrategyContext.

        Uses ExitEngine.evaluate_exit_action() which returns ExitAction.
        The caller (BacktestEngine) applies actions: EXIT, UPDATE_STOP, or HOLD.
        """
        positions = context.positions

        actions = []

        for ticker, position in list(positions.items()):
            price = context.get_current_price(ticker)
            if price is None:
                continue

            hist = context.get_bars(ticker, lookback_days=50)
            action = self.exit_engine.evaluate_exit_action(
                position, price, historical_data=hist
            )
            actions.append(action)

        return actions
