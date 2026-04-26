"""Trailing exit engine - implements all three trailing modes.

Supports:
- stage_based: Discrete stages at R-levels
- continuous: Smooth transitions between trailing methods
- hybrid: Stage-based with scale-out
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any

from traderlib.risk_config import ProfitTargetConfig, TrailingStageConfig


@dataclass
class TrailingResult:
    """Result of trailing exit evaluation.

    Actions:
    - "exit": Close the entire position (stop hit or target reached)
    - "update_stop": Move stop loss to new level (breakeven or EMA trail)
    - "scale_out": Sell partial position (hybrid mode). Caller should:
        1. Execute market order for shares_to_sell
        2. Reduce position.shares by shares_to_sell
        3. Call position.record_scale_out(trigger_r) to prevent repeats
        4. Continue holding remaining shares
    - "hold": No action needed
    """
    action: str  # "exit", "update_stop", "scale_out", "hold"
    reason: str
    new_stop: Optional[float] = None
    new_stop_type: Optional[str] = None
    scale_fraction: Optional[float] = None
    shares_to_sell: Optional[int] = None
    r_multiple: float = 0.0
    trigger_r: Optional[float] = None  # R-level that triggered this action


class TrailingExitEngine:
    """Engine for evaluating trailing stop rules.

    Supports ProfitTargetConfig.mode values:
    - target: Fixed R multiple exit (backward compatible)
    - trailing: Stage-based or continuous trailing (via trailing_mode)
    - hybrid: Stage-based with scale-out

    Note: trailing_mode selects between 'stage_based' and 'continuous'
    when mode is 'trailing'. Hybrid mode uses trailing_mode='stage_based'.
    """

    def __init__(self, config: ProfitTargetConfig):
        """Initialize with configuration.

        Args:
            config: ProfitTargetConfig with trailing settings
        """
        self.config = config

        # Validate mode
        if config.mode not in ('target', 'trailing', 'hybrid'):
            raise ValueError(f"Unknown mode: {config.mode}")

    def evaluate(self, position, current_price: float,
                 ema10: Optional[float] = None,
                 ema21: Optional[float] = None) -> TrailingResult:
        """Evaluate position against trailing rules.

        Args:
            position: Position object with entry_price, stop_price, etc.
            current_price: Current market price
            ema10: 10-period EMA value
            ema21: 21-period EMA value

        Returns:
            TrailingResult with action and updates

        Raises:
            NotImplementedError: If position is a short (entry_price < initial_stop)
            ValueError: If config.mode is invalid
        """
        # Check for short positions (use initial_stop if available)
        initial_stop = getattr(position, 'initial_stop_price', position.stop_price)
        if position.entry_price < initial_stop:
            raise NotImplementedError("Short positions not yet supported")

        # Check hard stop first
        if current_price <= position.stop_price:
            return TrailingResult(
                action='exit',
                reason='STOP_HIT',
                r_multiple=self._calculate_r_multiple(position, current_price)
            )

        if self.config.mode == 'target':
            return self._evaluate_target_mode(position, current_price)
        elif self.config.mode == 'trailing':
            if self.config.trailing_mode == 'stage_based':
                return self._evaluate_stage_based(position, current_price, ema10, ema21)
            else:  # continuous
                return self._evaluate_continuous(position, current_price, ema10, ema21)
        else:  # hybrid
            return self._evaluate_hybrid(position, current_price, ema10, ema21)

    def _calculate_r_multiple(self, position, current_price: float) -> float:
        """Calculate current R-multiple.

        R = (current_price - entry_price) * shares / initial_risk

        Args:
            position: Position with entry_price, initial_stop_price, shares
            current_price: Current market price

        Returns:
            R-multiple (can be negative for losses)
        """
        entry = position.entry_price
        initial_stop = getattr(position, 'initial_stop_price', position.stop_price)
        shares = position.shares

        risk_per_share = entry - initial_stop
        if risk_per_share <= 0:
            return 0.0

        current_gain = (current_price - entry) * shares
        initial_risk = risk_per_share * shares

        return current_gain / initial_risk if initial_risk > 0 else 0.0

    def _evaluate_target_mode(self, position, current_price: float) -> TrailingResult:
        """Original target mode - exit at fixed R target."""
        r_multiple = self._calculate_r_multiple(position, current_price)

        if r_multiple >= self.config.min_r_multiple:
            return TrailingResult(
                action='exit',
                reason=f'TARGET_HIT_{r_multiple:.1f}R',
                r_multiple=r_multiple
            )

        return TrailingResult(
            action='hold',
            reason=f'BELOW_TARGET_{self.config.min_r_multiple}R',
            r_multiple=r_multiple
        )

    def _evaluate_stage_based(self, position, current_price: float,
                              ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate stage-based trailing rules.

        Rules evaluated in order; highest triggered stage wins.
        Stop only moves up, never down.
        """
        r_multiple = self._calculate_r_multiple(position, current_price)

        # Find the highest triggered stage
        active_stage = None
        for stage in self.config.trailing_stages:
            if r_multiple >= stage.trigger_r:
                active_stage = stage

        if active_stage is None:
            return TrailingResult(action='hold', reason='BELOW_FIRST_STAGE', r_multiple=r_multiple)

        # Execute the active stage action
        if active_stage.action == 'breakeven':
            new_stop = position.entry_price
            if new_stop > position.stop_price:
                return TrailingResult(
                    action='update_stop',
                    reason=f'STAGE_{active_stage.trigger_r}R_BREAKEVEN',
                    new_stop=new_stop,
                    new_stop_type='BREAKEVEN',
                    r_multiple=r_multiple
                )

        elif active_stage.action == 'trail_ema':
            if active_stage.period is None:
                print(f"⚠️  Trailing stage at {active_stage.trigger_r}R missing required 'period' for trail_ema")
                return TrailingResult(action='hold', reason='NO_STOP_UPDATE_MISSING_PERIOD', r_multiple=r_multiple)
            new_stop = self._get_ema_for_period(active_stage.period, ema10, ema21)
            if new_stop is None:
                print(f"⚠️  EMA{active_stage.period} not available for {position.ticker}, skipping trail update")
            if new_stop and new_stop > position.stop_price:
                stop_type = f'EMA{active_stage.period}_TRAIL'
                return TrailingResult(
                    action='update_stop',
                    reason=f'STAGE_{active_stage.trigger_r}R_{stop_type}',
                    new_stop=new_stop,
                    new_stop_type=stop_type,
                    r_multiple=r_multiple
                )

        return TrailingResult(action='hold', reason='NO_STOP_UPDATE', r_multiple=r_multiple)

    def _evaluate_continuous(self, position, current_price: float,
                             ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate continuous trailing rules.

        Uses bands defined by R-multiple ranges.
        """
        r_multiple = self._calculate_r_multiple(position, current_price)

        # First, ensure breakeven if threshold reached
        if (r_multiple >= self.config.breakeven_at_r and
            position.stop_price < position.entry_price):
            return TrailingResult(
                action='update_stop',
                reason=f'BREAKEVEN_AT_{self.config.breakeven_at_r}R',
                new_stop=position.entry_price,
                new_stop_type='BREAKEVEN',
                r_multiple=r_multiple
            )

        # Find active band
        active_band = None
        for band in self.config.continuous_bands:
            from_r = band['from_r']
            to_r = band.get('to_r')

            if r_multiple >= from_r:
                if to_r is None or r_multiple < to_r:
                    active_band = band
                    break

        if active_band is None:
            return TrailingResult(action='hold', reason='NO_ACTIVE_BAND', r_multiple=r_multiple)

        # Calculate trailing stop based on band method
        method = active_band['method']
        if method == 'ema10':
            new_stop = ema10
            stop_type = 'EMA10_TRAIL'
        elif method == 'ema21':
            new_stop = ema21
            stop_type = 'EMA21_TRAIL'
        else:
            new_stop = None
            stop_type = 'UNKNOWN'

        if new_stop and new_stop > position.stop_price:
            return TrailingResult(
                action='update_stop',
                reason=f'BAND_{active_band["from_r"]}R_{stop_type}',
                new_stop=new_stop,
                new_stop_type=stop_type,
                r_multiple=r_multiple
            )

        return TrailingResult(action='hold', reason='NO_STOP_UPDATE', r_multiple=r_multiple)

    def _evaluate_hybrid(self, position, current_price: float,
                         ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate hybrid mode (stage-based + scale-out).

        Scale-out triggers are checked first, then trailing logic.
        Uses position.scale_out_history to track executed scale-outs.
        """
        r_multiple = self._calculate_r_multiple(position, current_price)

        # Check scale-out triggers first (but only if not already executed)
        if self.config.scale_out_steps:
            executed = set(position.scale_out_history) if position.scale_out_history else set()

            for step in self.config.scale_out_steps:
                if step.trigger_r not in executed and r_multiple >= step.trigger_r:
                    shares_to_sell = int(position.shares * step.fraction)
                    return TrailingResult(
                        action='scale_out',
                        reason=f'SCALE_OUT_{step.trigger_r}R_{int(step.fraction*100)}%',
                        scale_fraction=step.fraction,
                        shares_to_sell=shares_to_sell,
                        r_multiple=r_multiple,
                        trigger_r=step.trigger_r
                    )

        # Delegate to stage-based logic for trailing
        return self._evaluate_stage_based(position, current_price, ema10, ema21)

    def _get_ema_for_period(self, period: int, ema10: Optional[float],
                            ema21: Optional[float]) -> Optional[float]:
        """Get EMA value for the specified period.

        Args:
            period: EMA period (10, 21, etc.)
            ema10: 10-period EMA value
            ema21: 21-period EMA value

        Returns:
            EMA value or None if ema10/ema21 is None

        Raises:
            ValueError: If period is not 10 or 21
        """
        if period == 10:
            return ema10
        elif period == 21:
            return ema21
        else:
            raise ValueError(f"Unsupported EMA period: {period}. Only 10 and 21 are supported.")
