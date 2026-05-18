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

    def __init__(self, risk_config: Optional[RiskConfig] = None, profile: str = 'large_cap',
                 watchlist_tickers: Optional[List[str]] = None,
                 watchlist_df: Optional[pd.DataFrame] = None):
        self.risk_config = risk_config
        self.profile = profile
        self.exit_engine = ExitEngine(risk_config=risk_config)
        self.watchlist_tickers = watchlist_tickers or []
        self.watchlist_df = watchlist_df

        from traderlib.sector_resolver import SectorResolver
        self._sector_resolver = SectorResolver()

        # Load profile-specific parameters from config
        self._load_profile_params()

        # Rejection counters — accumulated across all simulation days
        self.rejection_counts: dict = {
            'scanned': 0,
            'already_holding': 0,
            'no_data': 0,
            'stage2': 0,
            'vcp': 0,
            'convergence': 0,
            'pivot': 0,
            'sizing': 0,
            'signals': 0,
        }
        # VCP sub-rejection buckets (from error_message prefix)
        self.vcp_rejection_reasons: dict = {}

    def get_rejection_summary(self) -> str:
        """Return a human-readable breakdown of entry filter rejections."""
        c = self.rejection_counts
        lines = [
            f"\n{'─'*50}",
            f"  Entry filter breakdown ({self.name})",
            f"{'─'*50}",
            f"  Ticker-days scanned:    {c['scanned']:>6}",
            f"  Already holding:        {c['already_holding']:>6}",
            f"  No data (dropped):      {c['no_data']:>6}",
            f"  Failed Stage 2 (< 6):   {c['stage2']:>6}",
            f"  Failed VCP pattern:     {c['vcp']:>6}",
        ]
        if self.vcp_rejection_reasons:
            top = sorted(self.vcp_rejection_reasons.items(), key=lambda x: -x[1])[:5]
            for reason, count in top:
                lines.append(f"    ↳ {reason[:42]:<42} {count:>5}")
        lines += [
            f"  Failed convergence:     {c['convergence']:>6}",
            f"  Failed pivot prox:      {c['pivot']:>6}",
            f"  Failed sizing:          {c['sizing']:>6}",
            f"  Signals generated:      {c['signals']:>6}",
            f"{'─'*50}",
        ]
        return '\n'.join(lines)

    def _load_profile_params(self):
        """Load VCP parameters — two-tier priority:
        1. config/strategies/vcp_{profile}.yaml  (authoritative)
        2. Hardcoded defaults                    (fallback)

        Note: Previously used risk_config.vcp as Tier 2, but this has been
        removed. All VCP parameters now come from per-strategy YAML files
        with hardcoded defaults as fallback.
        """
        # ── Tier 3: hardcoded defaults ────────────────────────────────────
        if self.profile == 'large_cap':
            defaults = {
                'min_dollar_volume':      80_000_000,
                'min_share_volume':        1_000_000,
                'contraction_ranges':     [(15, 25), (8, 12), (3, 8)],
                'volume_dry_up_threshold': 0.60,
                'breakout_volume_min':    1.4,
                'trail_ema_period':       20,
                'phase2_start_r':         2.0,
                'max_pivot_proximity_pct': 5.0,
                'min_convergence_score':  50,
            }
        else:  # high_octane
            defaults = {
                'min_dollar_volume':      20_000_000,
                'min_share_volume':          400_000,
                'contraction_ranges':     [(30, 35), (15, 15), (3, 6)],
                'volume_dry_up_threshold': 0.50,
                'breakout_volume_min':    2.0,
                'trail_ema_period':       10,
                'phase2_start_r':         2.0,
                'max_pivot_proximity_pct': 5.0,
                'min_convergence_score':  50,
            }
        profile_params = dict(defaults)

        # ── Tier 1: strategy YAML ─────────────────────────────────────────
        try:
            from traderlib.strategy_config import load_strategy_config, get_param
            _scfg = load_strategy_config(f'vcp_{self.profile}') or {}
            if _scfg:
                yaml_overrides = {
                    'min_dollar_volume':       get_param(_scfg, 'universe', 'min_dollar_volume'),
                    'min_share_volume':        get_param(_scfg, 'universe', 'min_share_volume'),
                    'volume_dry_up_threshold': get_param(_scfg, 'volume',   'dry_up_threshold'),
                    'breakout_volume_min':     get_param(_scfg, 'volume',   'breakout_volume_min'),
                    'trail_ema_period':        get_param(_scfg, 'exit',     'phase2_trail_ma'),
                    'phase2_start_r':          get_param(_scfg, 'exit',     'phase2_trigger_r'),
                    'max_pivot_proximity_pct': get_param(_scfg, 'entry',    'max_pivot_proximity_pct'),
                    'min_convergence_score':   get_param(_scfg, 'entry',    'min_convergence_score'),
                }
                # Only apply non-None values so missing YAML keys fall through
                profile_params.update({k: v for k, v in yaml_overrides.items() if v is not None})
        except Exception:
            pass  # YAML errors never crash the strategy

        self.params = profile_params

    def _get_watchlist_tickers(self, context: StrategyContext) -> List[str]:
        """Get tickers to scan for entries."""
        if self.watchlist_df is not None:
            if 'week_start' in self.watchlist_df.columns:
                week_start = pd.to_datetime(self.watchlist_df['week_start'])
                active = self.watchlist_df[
                    week_start <= pd.Timestamp(context.sim_date)
                ]
                active = active.sort_values('week_start').groupby('ticker').last().reset_index()
                col = 'ticker' if 'ticker' in active.columns else 'Ticker'
                return active[col].dropna().unique().tolist()
            else:
                col = 'Ticker' if 'Ticker' in self.watchlist_df.columns else 'ticker'
                return self.watchlist_df[col].dropna().unique().tolist()
        return self.watchlist_tickers

    def _get_sector(self, ticker: str) -> str:
        """Get sector for ticker via SectorResolver."""
        return self._sector_resolver.resolve(ticker)

    def _calculate_shares(self, context: StrategyContext, entry: float, stop: float) -> int:
        """Triple-constraint position sizing."""
        if self.risk_config:
            shares, _ = calculate_position_size_with_constraints(
                context.equity, entry, stop, self.risk_config,
                available_cash=context.cash
            )
            return shares
        return 0

    def _find_swing_lows(self, hist: pd.DataFrame, window: int = 3) -> List[float]:
        """Find local swing low prices using a rolling window.

        A swing low is a bar whose Low is ≤ all surrounding `window` bars on
        each side. Returns prices in chronological order (oldest first).
        """
        lows = hist['Low'].values
        n = len(lows)
        result = []
        for i in range(window, n - window):
            if (all(lows[i] <= lows[i - j] for j in range(1, window + 1)) and
                    all(lows[i] <= lows[i + j] for j in range(1, window + 1))):
                result.append(float(lows[i]))
        return result

    def _find_recent_higher_low(self, hist: pd.DataFrame,
                                current_stop: float,
                                current_price: float) -> Optional[float]:
        """Find the highest swing low that's above current_stop and below current price.

        Used in Phase 1 to ratchet the trailing stop up as the position moves
        in favour. Returns the highest qualifying swing low (tightest valid stop),
        or None if none qualifies.

        A 3% buffer below current price prevents setting the stop so close that
        normal intraday noise triggers an exit.
        """
        candidates = [
            p for p in self._find_swing_lows(hist.tail(40), window=3)
            if current_stop < p < current_price * 0.97
        ]
        return max(candidates) if candidates else None

    def _find_last_swing_low(self, hist: pd.DataFrame) -> Optional[float]:
        """Find the most recent significant swing low for Phase 2 trailing.

        Uses a wider window (5 bars each side) so only meaningful swing lows
        qualify — not every 3-bar dip. Returns None if no swing low found in
        the last 60 bars, in which case the caller falls back to EMA only.
        """
        swing_lows = self._find_swing_lows(hist.tail(60), window=5)
        return swing_lows[-1] if swing_lows else None

    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """VCP Exit Management — Two-Phase System (shared by all VCP profiles).

        Phase 1 (entry → phase2_trigger_r):
            Hold initial stop; ratchet up to confirmed swing lows.
            ExitAction carries metadata={'exit_phase': 'phase1'}.

        Phase 2 (phase2_trigger_r+):
            Trail with EMA + swing low, whichever is tighter.
            ExitAction carries metadata={'exit_phase': 'phase2'}.

        Stop enforcement fires first in both phases (bug-1 fix).
        Subclasses inherit this; profile-specific params come from self.params.
        """
        actions = []
        ema_period = self.params.get('trail_ema_period', 20)
        phase2_r   = self.params.get('phase2_start_r',  2.0)

        for ticker, position in context.positions.items():
            try:
                current = context.get_current_price(ticker)
            except Exception:
                continue
            if current is None:
                continue

            try:
                hist = context.get_bars(ticker, lookback_days=60)
            except Exception:
                continue
            if hist is None or len(hist) < max(ema_period, 20):
                continue

            # R-multiple relative to initial stop (needed for all branches)
            initial_risk = position.entry_price - position.stop_price
            current_gain = current - position.entry_price
            r_multiple   = current_gain / initial_risk if initial_risk > 0 else 0

            # ── Stop enforcement first (Phase 1 bug-fix) ──────────────────
            if current <= position.stop_price:
                actions.append(ExitAction(
                    ticker=ticker,
                    action=ExitActionType.EXIT,
                    reason='STOP_HIT',
                    exit_price=current,
                    r_multiple=r_multiple,
                    metadata={'exit_phase': getattr(position, 'exit_phase', 'phase1')},
                ))
                continue

            # ── Phase 1: below phase2_r — ratchet to swing lows ───────────
            if r_multiple < phase2_r:
                higher_low = self._find_recent_higher_low(
                    hist, position.stop_price, current
                )
                if higher_low:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.UPDATE_STOP,
                        reason='HIGHER_LOW',
                        new_stop_price=higher_low,
                        new_stop_type='TRAIL_VCP_HL',
                        r_multiple=r_multiple,
                        metadata={'exit_phase': 'phase1'},
                    ))
                else:
                    actions.append(ExitAction(
                        ticker=ticker,
                        action=ExitActionType.HOLD,
                        reason='PHASE1_WAITING',
                        r_multiple=r_multiple,
                        metadata={'exit_phase': 'phase1'},
                    ))
                continue

            # ── Phase 2: phase2_r+ — trail EMA + swing low ────────────────
            ema = hist['Close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
            swing_low = self._find_last_swing_low(hist)

            candidates = [ema, position.stop_price]
            if swing_low:
                candidates.append(swing_low)
            new_stop = max(candidates)

            if new_stop > position.stop_price:
                actions.append(ExitAction(
                    ticker=ticker,
                    action=ExitActionType.UPDATE_STOP,
                    reason=f'TRAIL_EMA{ema_period}',
                    new_stop_price=new_stop,
                    new_stop_type=f'TRAIL_EMA{ema_period}_R{r_multiple:.1f}',
                    r_multiple=r_multiple,
                    metadata={'exit_phase': 'phase2'},
                ))
            else:
                actions.append(ExitAction(
                    ticker=ticker,
                    action=ExitActionType.HOLD,
                    reason=f'TRAILING_R{r_multiple:.1f}',
                    r_multiple=r_multiple,
                    metadata={'exit_phase': 'phase2'},
                ))

        return actions


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

    def __init__(self, risk_config: Optional[RiskConfig] = None,
                 watchlist_tickers: Optional[List[str]] = None,
                 watchlist_df: Optional[pd.DataFrame] = None):
        super().__init__(risk_config=risk_config, profile='large_cap',
                         watchlist_tickers=watchlist_tickers, watchlist_df=watchlist_df)

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

        # VIX gate: block new entries when volatility exceeds configured max
        if context.vix_current is not None and self.risk_config:
            max_vix = getattr(self.risk_config.market, 'max_vix', None)
            if max_vix and context.vix_current > max_vix:
                return signals

        # Get candidate tickers
        tickers = self._get_watchlist_tickers(context)

        # If no watchlist, can't scan
        if not tickers:
            return signals

        self.rejection_counts['scanned'] += len(tickers)
        for ticker in tickers:
            # Skip if already holding
            if ticker in context.positions:
                self.rejection_counts['already_holding'] += 1
                continue

            try:
                hist = context.get_bars(ticker, lookback_days=200)
            except Exception:
                self.rejection_counts['no_data'] += 1
                continue
            if hist is None or len(hist) < 200:
                self.rejection_counts['no_data'] += 1
                continue

            try:
                current = context.get_current_price(ticker)
            except Exception:
                self.rejection_counts['no_data'] += 1
                continue
            if current is None:
                self.rejection_counts['no_data'] += 1
                continue

            # 1. Stage-2 check
            stage2_score = calculate_stage2_score(hist)
            if stage2_score < 6:
                self.rejection_counts['stage2'] += 1
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
                self.rejection_counts['vcp'] += 1
                reason = vcp.error_message.split(' —')[0][:50]
                self.vcp_rejection_reasons[reason] = self.vcp_rejection_reasons.get(reason, 0) + 1
                continue

            # 3. MA convergence score
            s2_details = get_stage2_details(hist)
            conv_score = calculate_convergence_score(current, s2_details)
            if conv_score['score'] < self.params.get('min_convergence_score', 50):
                self.rejection_counts['convergence'] += 1
                continue

            # 4. Proximity to pivot
            pivot = vcp.pivot_high
            proximity = (current - pivot) / pivot
            if proximity > self.params.get('max_pivot_proximity_pct', 5.0) / 100:
                self.rejection_counts['pivot'] += 1
                continue

            # Calculate position sizing
            stop_price = max(vcp.stop_low, conv_score.get('ma_support_stop', 0))
            shares = self._calculate_shares(context, current, stop_price)

            if shares <= 0:
                self.rejection_counts['sizing'] += 1
                continue

            self.rejection_counts['signals'] += 1
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

    # manage_exits() inherited from VCPBreakoutBase

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

    def __init__(self, risk_config: Optional[RiskConfig] = None,
                 watchlist_tickers: Optional[List[str]] = None,
                 watchlist_df: Optional[pd.DataFrame] = None):
        super().__init__(risk_config=risk_config, profile='high_octane',
                         watchlist_tickers=watchlist_tickers, watchlist_df=watchlist_df)

    @property
    def name(self) -> str:
        return "vcp_high_octane"

    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """Scan for high-octane VCP entries (same logic, different parameters)."""
        signals = []

        # VIX gate: block new entries when volatility exceeds configured max
        if context.vix_current is not None and self.risk_config:
            max_vix = getattr(self.risk_config.market, 'max_vix', None)
            if max_vix and context.vix_current > max_vix:
                return signals

        tickers = self._get_watchlist_tickers(context)
        if not tickers:
            return signals

        self.rejection_counts['scanned'] += len(tickers)
        for ticker in tickers:
            if ticker in context.positions:
                self.rejection_counts['already_holding'] += 1
                continue

            try:
                hist = context.get_bars(ticker, lookback_days=200)
            except Exception:
                self.rejection_counts['no_data'] += 1
                continue
            if hist is None or len(hist) < 200:
                self.rejection_counts['no_data'] += 1
                continue

            try:
                current = context.get_current_price(ticker)
            except Exception:
                self.rejection_counts['no_data'] += 1
                continue
            if current is None:
                self.rejection_counts['no_data'] += 1
                continue

            # Stage-2 check (same)
            stage2_score = calculate_stage2_score(hist)
            if stage2_score < 6:
                self.rejection_counts['stage2'] += 1
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
                self.rejection_counts['vcp'] += 1
                reason = vcp.error_message.split(' —')[0][:50]
                self.vcp_rejection_reasons[reason] = self.vcp_rejection_reasons.get(reason, 0) + 1
                continue

            # MA convergence
            s2_details = get_stage2_details(hist)
            conv_score = calculate_convergence_score(current, s2_details)
            if conv_score['score'] < self.params.get('min_convergence_score', 50):
                self.rejection_counts['convergence'] += 1
                continue

            # Proximity to pivot (same)
            pivot = vcp.pivot_high
            proximity = (current - pivot) / pivot
            if proximity > self.params.get('max_pivot_proximity_pct', 5.0) / 100:
                self.rejection_counts['pivot'] += 1
                continue

            # Position sizing
            stop_price = max(vcp.stop_low, conv_score.get('ma_support_stop', 0))
            shares = self._calculate_shares(context, current, stop_price)

            if shares <= 0:
                self.rejection_counts['sizing'] += 1
                continue

            self.rejection_counts['signals'] += 1
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

    # manage_exits() inherited from VCPBreakoutBase (uses trail_ema_period=10 from YAML/params)

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
