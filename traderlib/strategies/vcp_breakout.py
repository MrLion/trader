"""VCP Breakout Strategy Plugin.

Implements VCP (Volatility Contraction Pattern) breakout strategy
with large-cap and high-octane profiles.

Usage:
    python3 scripts/paper_engine_alpaca.py --strategy vcp_large_cap
    python3 scripts/paper_engine_alpaca.py --strategy vcp_high_octane
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from traderlib.strategies import Strategy, StrategyContext, EntrySignal, ExitAction, ExitActionType, register_strategy
from traderlib.stage2_utils import (
    calculate_stage2_score,
    get_stage2_details,
    calculate_convergence_score,
    calculate_volume_metrics,
)
from traderlib.vcp_utils import detect_vcp_pattern, VCPPattern
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfig, calculate_position_size_with_constraints


class VCPBreakoutBase(Strategy):
    """Base class for VCP breakout strategies."""

    def __init__(self, risk_config: Optional[RiskConfig] = None, profile: str = 'large_cap'):
        self.risk_config = risk_config
        self.profile = profile
        self.exit_engine = ExitEngine(risk_config=risk_config)

        # Load profile-specific parameters from config
        self._load_profile_params()

    def _load_profile_params(self):
        """Load VCP parameters from risk_config."""
        if self.risk_config and hasattr(self.risk_config, 'vcp'):
            profile_params = self.risk_config.vcp.get(self.profile, {})
        else:
            # Defaults
            if self.profile == 'large_cap':
                profile_params = {
                    'min_dollar_volume': 80000000,
                    'min_share_volume': 1000000,
                    'contraction_ranges': [(15, 25), (8, 12), (3, 8)],
                    'volume_dry_up_threshold': 0.60,
                    'breakout_volume_min': 1.4,
                    'trail_ema_period': 20,
                    'phase2_start_r': 2.0,
                    'max_pivot_proximity_pct': 5.0,
                    'min_convergence_score': 50,
                }
            else:  # high_octane
                profile_params = {
                    'min_dollar_volume': 20000000,
                    'min_share_volume': 400000,
                    'contraction_ranges': [(30, 35), (15, 15), (3, 6)],
                    'volume_dry_up_threshold': 0.50,
                    'breakout_volume_min': 2.0,
                    'trail_ema_period': 10,
                    'phase2_start_r': 2.0,
                    'max_pivot_proximity_pct': 5.0,
                    'min_convergence_score': 50,
                }

        self.params = profile_params

    def _get_watchlist_tickers(self, context: StrategyContext) -> List[str]:
        """Get tickers to scan for entries."""
        # In full implementation, would load from watchlist
        # For now, scan context positions or use default
        return []

    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker (cached)."""
        # Would implement sector lookup
        return 'Unknown'

    def _calculate_shares(self, context: StrategyContext, entry: float, stop: float) -> int:
        """Triple-constraint position sizing."""
        if self.risk_config:
            shares, _ = calculate_position_size_with_constraints(
                context.equity, entry, stop, self.risk_config,
                available_cash=context.cash
            )
            return shares
        return 0

    def _find_recent_higher_low(self, hist: pd.DataFrame, entry_price: float) -> Optional[float]:
        """Find most recent higher low above entry."""
        if len(hist) < 10:
            return None

        # Simple implementation: find highest low in last 20 bars
        recent_lows = hist['Low'].tail(20)
        return float(recent_lows.max())

    def _find_last_swing_low(self, hist: pd.DataFrame) -> float:
        """Find last significant swing low."""
        if len(hist) < 10:
            return hist['Low'].iloc[-1]

        # Return lowest low of last 10 days
        return float(hist['Low'].tail(10).min())


@register_strategy('vcp_large_cap')
class VCPBreakoutLargeCap(VCPBreakoutBase):
    """
    VCP Breakout Strategy — Large-Cap Profile.

    Characteristics:
    - $80M+ avg daily dollar volume
    - 15-25% → 8-12% → 3-8% contractions (shallower, smoother)
    - 20-day EMA trailing after 2-3R
    - Hold as long as it works (no hard profit target)
    """

    def __init__(self, risk_config: Optional[RiskConfig] = None):
        super().__init__(risk_config=risk_config, profile='large_cap')

    @property
    def name(self) -> str:
        return "vcp_large_cap"

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """
        Scan for VCP breakout entries.

        Entry criteria:
        1. Stage-2 uptrend (score >= 5)
        2. VCP pattern detected (2+ contractions)
        3. Volume confirmation (dry-up in base)
        4. MA convergence score >= 50
        5. Within 5% of pivot
        """
        signals = []

        # Get candidate tickers
        tickers = self._get_watchlist_tickers(context)

        # If no watchlist, can't scan
        if not tickers:
            return signals

        for ticker in tickers:
            # Skip if already holding
            if ticker in context.positions:
                continue

            hist = context.get_bars(ticker, lookback_days=200)
            if hist is None or len(hist) < 200:
                continue

            current = context.get_current_price(ticker)
            if current is None:
                continue

            # 1. Stage-2 check
            stage2_score = calculate_stage2_score(hist)
            if stage2_score < 5:
                continue

            # 2. VCP pattern detection
            vcp = detect_vcp_pattern(
                hist,
                min_contractions=2,
                reversal_threshold=0.05,
                require_volume_dry_up=True,
                volume_dry_up_threshold=self.params.get('volume_dry_up_threshold', 0.60)
            )
            if not vcp.valid:
                continue

            # 3. Volume confirmation
            vol_metrics = calculate_volume_metrics(hist)
            if vol_metrics['volume_ratio'] < self.params.get('breakout_volume_min', 1.4):
                continue

            # 4. MA convergence score
            s2_details = get_stage2_details(hist)
            conv_score = calculate_convergence_score(current, s2_details)
            if conv_score['score'] < self.params.get('min_convergence_score', 50):
                continue

            # 5. Proximity to pivot
            pivot = vcp.pivot_high
            proximity = (current - pivot) / pivot
            if proximity > self.params.get('max_pivot_proximity_pct', 5.0) / 100:
                continue

            # Calculate position sizing
            stop_price = max(vcp.stop_low, conv_score.get('ma_support_stop', 0))
            shares = self._calculate_shares(context, current, stop_price)

            if shares <= 0:
                continue

            signals.append(EntrySignal(
                ticker=ticker,
                side='LONG',
                entry_price=current,
                stop_price=stop_price,
                target_price=current * 1.10,  # Will be trailed
                shares=shares,
                sector=self._get_sector(ticker),
                entry_score=conv_score['score'],
                stage2_score=stage2_score,
                metadata={
                    'vcp_data': {
                        'num_contractions': len(vcp.contractions),
                        'pivot_high': vcp.pivot_high,
                        'stop_low': vcp.stop_low,
                        'volume_declining': vcp.volume_declining,
                    },
                    'convergence': conv_score,
                    'pivot': pivot
                }
            ))

        return signals

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """
        VCP Exit Management — Two-Phase System.

        Phase 1 (Until ~2R): Hold initial stop (last contraction low)
        Phase 2 (Once up 2-3R): Trail with 20-day EMA or swing low
        """
        actions = []

        for ticker, position in context.positions.items():
            current = context.get_current_price(ticker)
            if current is None:
                continue

            hist = context.get_bars(ticker, lookback_days=60)
            if hist is None or len(hist) < 20:
                continue

            # Calculate R-multiple
            initial_risk = position.entry_price - position.stop_price
            current_gain = current - position.entry_price
            r_multiple = current_gain / initial_risk if initial_risk > 0 else 0

            # Phase 1: Below 2R — hold initial stop (or update to higher low)
            if r_multiple < self.params.get('phase2_start_r', 2.0):
                higher_low = self._find_recent_higher_low(hist, position.entry_price)
                if higher_low and higher_low > position.stop_price:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.UPDATE_STOP,
                        reason='HIGHER_LOW',
                        new_stop_price=higher_low,
                        new_stop_type='TRAIL_VCP_HL',
                        r_multiple=r_multiple
                    ))
                else:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.HOLD,
                        reason='PHASE1_WAITING',
                        r_multiple=r_multiple
                    ))
                continue

            # Phase 2: At 2R+ — trail with 20-day EMA (large-cap)
            ema20 = hist['Close'].ewm(span=self.params.get('trail_ema_period', 20), adjust=False).mean().iloc[-1]
            swing_low = self._find_last_swing_low(hist)

            # Use tighter of EMA or swing low (never below initial)
            new_stop = max(ema20, swing_low, position.stop_price)

            if new_stop > position.stop_price:
                actions.append(ExitAction(
                    ticker=ticker,
                    action=ExitActionType.UPDATE_STOP,
                    reason='TRAIL_EMA20',
                    new_stop_price=new_stop,
                    new_stop_type=f'TRAIL_EMA20_R{r_multiple:.1f}',
                    r_multiple=r_multiple
                ))
            else:
                # Check if stop hit
                if current <= position.stop_price:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.EXIT,
                        reason='STOP_HIT',
                        exit_price=current,
                        r_multiple=r_multiple
                    ))
                else:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.HOLD,
                        reason=f'TRAILING_R{r_multiple:.1f}',
                        r_multiple=r_multiple
                    ))

        return actions

    # Lifecycle hooks
    def on_market_regime_change(self, old_regime: str, new_regime: str, context: StrategyContext):
        """React to regime changes."""
        if new_regime == 'BEAR':
            print(f"  🚨 {self.name}: Regime changed to BEAR — tightening risk")

    def on_position_opened(self, position: Any, context: StrategyContext):
        """Log position opening."""
        print(f"  📈 {self.name}: Opened {position.ticker} @ ${position.entry_price:.2f}")

    def on_position_closed(self, position: Any, pnl: float, context: StrategyContext):
        """Log position closing."""
        emoji = "🎯" if pnl > 0 else "🛑"
        print(f"  {emoji} {self.name}: Closed {position.ticker} — P&L ${pnl:,.2f}")


@register_strategy('vcp_high_octane')
class VCPBreakoutHighOctane(VCPBreakoutBase):
    """
    VCP Breakout Strategy — High-Octane Profile.

    Characteristics:
    - $20M+ avg daily dollar volume (lower threshold)
    - 30-35% → 15% → 3-6% contractions (deeper first leg)
    - 10-day EMA trailing after 2-3R (tighter for volatile names)
    - Hold as long as it works (no hard profit target)
    """

    def __init__(self, risk_config: Optional[RiskConfig] = None):
        super().__init__(risk_config=risk_config, profile='high_octane')

    @property
    def name(self) -> str:
        return "vcp_high_octane"

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """Scan for high-octane VCP entries (same logic, different parameters)."""
        signals = []

        tickers = self._get_watchlist_tickers(context)
        if not tickers:
            return signals

        for ticker in tickers:
            if ticker in context.positions:
                continue

            hist = context.get_bars(ticker, lookback_days=200)
            if hist is None or len(hist) < 200:
                continue

            current = context.get_current_price(ticker)
            if current is None:
                continue

            # Stage-2 check (same)
            stage2_score = calculate_stage2_score(hist)
            if stage2_score < 5:
                continue

            # VCP pattern (stricter volume for thin names)
            vcp = detect_vcp_pattern(
                hist,
                min_contractions=2,
                reversal_threshold=0.05,
                require_volume_dry_up=True,
                volume_dry_up_threshold=self.params.get('volume_dry_up_threshold', 0.50)
            )
            if not vcp.valid:
                continue

            # Volume confirmation (stricter for high-octane)
            vol_metrics = calculate_volume_metrics(hist)
            if vol_metrics['volume_ratio'] < self.params.get('breakout_volume_min', 2.0):
                continue

            # MA convergence (same)
            s2_details = get_stage2_details(hist)
            conv_score = calculate_convergence_score(current, s2_details)
            if conv_score['score'] < self.params.get('min_convergence_score', 50):
                continue

            # Proximity to pivot (same)
            pivot = vcp.pivot_high
            proximity = (current - pivot) / pivot
            if proximity > self.params.get('max_pivot_proximity_pct', 5.0) / 100:
                continue

            # Position sizing
            stop_price = max(vcp.stop_low, conv_score.get('ma_support_stop', 0))
            shares = self._calculate_shares(context, current, stop_price)

            if shares <= 0:
                continue

            signals.append(EntrySignal(
                ticker=ticker,
                side='LONG',
                entry_price=current,
                stop_price=stop_price,
                target_price=current * 1.10,
                shares=shares,
                sector=self._get_sector(ticker),
                entry_score=conv_score['score'],
                stage2_score=stage2_score,
                metadata={
                    'vcp_data': {
                        'num_contractions': len(vcp.contractions),
                        'pivot_high': vcp.pivot_high,
                        'stop_low': vcp.stop_low,
                        'volume_declining': vcp.volume_declining,
                        'profile': 'high_octane'
                    },
                    'convergence': conv_score,
                    'pivot': pivot
                }
            ))

        return signals

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """
        High-Octane Exit Management.

        Same two-phase system but trails with 10-day EMA (tighter)
        instead of 20-day EMA for more volatile names.
        """
        actions = []

        for ticker, position in context.positions.items():
            current = context.get_current_price(ticker)
            if current is None:
                continue

            hist = context.get_bars(ticker, lookback_days=60)
            if hist is None or len(hist) < 10:
                continue

            initial_risk = position.entry_price - position.stop_price
            current_gain = current - position.entry_price
            r_multiple = current_gain / initial_risk if initial_risk > 0 else 0

            # Phase 1: Below 2R
            if r_multiple < self.params.get('phase2_start_r', 2.0):
                higher_low = self._find_recent_higher_low(hist, position.entry_price)
                if higher_low and higher_low > position.stop_price:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.UPDATE_STOP,
                        reason='HIGHER_LOW',
                        new_stop_price=higher_low,
                        new_stop_type='TRAIL_VCP_HL',
                        r_multiple=r_multiple
                    ))
                else:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.HOLD,
                        reason='PHASE1_WAITING',
                        r_multiple=r_multiple
                    ))
                continue

            # Phase 2: At 2R+ — trail with 10-day EMA (tighter for high-octane)
            ema10 = hist['Close'].ewm(span=self.params.get('trail_ema_period', 10), adjust=False).mean().iloc[-1]
            swing_low = self._find_last_swing_low(hist)

            new_stop = max(ema10, swing_low, position.stop_price)

            if new_stop > position.stop_price:
                actions.append(ExitAction(
                    ticker=ticker,
                    action=ExitActionType.UPDATE_STOP,
                    reason='TRAIL_EMA10',
                    new_stop_price=new_stop,
                    new_stop_type=f'TRAIL_EMA10_R{r_multiple:.1f}',
                    r_multiple=r_multiple
                ))
            else:
                if current <= position.stop_price:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.EXIT,
                        reason='STOP_HIT',
                        exit_price=current,
                        r_multiple=r_multiple
                    ))
                else:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.HOLD,
                        reason=f'TRAILING_R{r_multiple:.1f}',
                        r_multiple=r_multiple
                    ))

        return actions

    def on_market_regime_change(self, old_regime: str, new_regime: str, context: StrategyContext):
        """React to regime changes."""
        if new_regime == 'BEAR':
            print(f"  🚨 {self.name}: Regime changed to BEAR — consider closing positions")

    def on_position_opened(self, position: Any, context: StrategyContext):
        """Log position opening."""
        print(f"  📈 {self.name}: Opened {position.ticker} @ ${position.entry_price:.2f}")

    def on_position_closed(self, position: Any, pnl: float, context: StrategyContext):
        """Log position closing."""
        emoji = "🎯" if pnl > 0 else "🛑"
        print(f"  {emoji} {self.name}: Closed {position.ticker} — P&L ${pnl:,.2f}")
