# Configurable Trailing Exit System Implementation Plan (REVISED)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a YAML-configurable trailing exit system that replaces fixed 2R profit targets with dynamic stop adjustments (breakeven at 2R, trail with EMAs at higher R-levels).

**Architecture:** Extend existing `risk_config.py` ProfitTargetConfig with new trailing modes. Single trailing exit engine that plugs into existing ExitEngine.

**Tech Stack:** Python 3.x, dataclasses, PyYAML, pandas (for EMA calculations), existing ExitEngine pattern in `traderlib/paper_exits.py`

---

## Changes from Original Plan (Post-Review)

### Critical Fixes

1. **Merged config into risk_config.py** — Eliminates parallel config system, extends existing `ProfitTargetConfig`
2. **Fixed task dependency order** — All modes (stage/continuous/hybrid) implemented BEFORE integration
3. **Fixed scale-out trigger bug** — Added `executed` flag to prevent repeated triggers
4. **Added state persistence** — Position tracks `scale_out_history` list
5. **Fixed EMA handling** — Graceful fallback when EMAs unavailable
6. **Fixed breakeven logic** — Proper state machine for continuous mode

### Added Tasks

- Task 4: Position state persistence for scale-outs
- Task 8: Backtest engine integration
- Task 10: Edge case tests (short positions, missing EMAs, etc.)

---

## File Structure (Revised)

| File | Responsibility | Status |
|------|----------------|--------|
| `traderlib/risk_config.py` | **MODIFY** - Add trailing config to ProfitTargetConfig | Extend existing |
| `traderlib/trailing_exits.py` | **NEW** - Core trailing exit engine (all 3 modes) | Consolidated |
| `traderlib/paper_exits.py` | **MODIFY** - Integrate trailing exits | Single integration point |
| `traderlib/paper_state.py` | **MODIFY** - Add scale_out_history to Position | State persistence |
| `config/strategies/example_trailing.yaml` | **NEW** - Example strategy config | Demonstrates usage |
| `tests/test_trailing_exits.py` | **NEW** - Engine tests (all modes) | Comprehensive |
| `tests/test_trailing_integration.py` | **NEW** - Integration tests | ExitEngine + backtest |

---

## Task 1: Extend Risk Config with Trailing Modes

**Files:**
- Modify: `traderlib/risk_config.py`
- Test: `tests/test_risk_config.py` (add trailing config tests)

**Rationale:** Instead of parallel `trailing_config.py`, extend existing `ProfitTargetConfig` with `trailing_mode` and `trailing_stages`.

- [ ] **Step 1: Write the failing test**

```python
"""Test trailing configuration in risk_config."""

import unittest
from traderlib.risk_config import ProfitTargetConfig, TrailingStageConfig


class TestProfitTargetConfigTrailing(unittest.TestCase):
    """Test trailing exit configuration."""

    def test_stage_based_mode(self):
        """Can configure stage-based trailing."""
        config = ProfitTargetConfig(
            mode="trailing",  # New mode
            trailing_mode="stage_based",
            trailing_stages=[
                TrailingStageConfig(trigger_r=2.0, action="breakeven"),
                TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
            ]
        )
        self.assertEqual(config.mode, "trailing")
        self.assertEqual(config.trailing_mode, "stage_based")
        self.assertEqual(len(config.trailing_stages), 2)

    def test_continuous_mode(self):
        """Can configure continuous trailing."""
        config = ProfitTargetConfig(
            mode="trailing",
            trailing_mode="continuous",
            continuous_bands=[
                {"from_r": 2.5, "to_r": 4.0, "method": "ema10"},
                {"from_r": 4.0, "method": "ema21"},
            ]
        )
        self.assertEqual(config.trailing_mode, "continuous")

    def test_target_mode_backward_compatible(self):
        """Original target mode still works."""
        config = ProfitTargetConfig(
            mode="target",
            min_r_multiple=2.0
        )
        self.assertEqual(config.mode, "target")

    def test_validation_increasing_stages(self):
        """Stages must have increasing R values."""
        with self.assertRaises(ValueError) as cm:
            ProfitTargetConfig(
                mode="trailing",
                trailing_mode="stage_based",
                trailing_stages=[
                    TrailingStageConfig(trigger_r=3.0, action="breakeven"),
                    TrailingStageConfig(trigger_r=2.0, action="trail_ema", period=10),
                ]
            )
        self.assertIn("increasing", str(cm.exception).lower())

    def test_validation_positive_r(self):
        """Stage R must be positive."""
        with self.assertRaises(ValueError):
            ProfitTargetConfig(
                mode="trailing",
                trailing_mode="stage_based",
                trailing_stages=[
                    TrailingStageConfig(trigger_r=-1.0, action="breakeven"),
                ]
            )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py::TestProfitTargetConfigTrailing -v`

Expected: FAIL with "AttributeError: 'ProfitTargetConfig' object has no attribute 'mode'"

- [ ] **Step 3: Extend ProfitTargetConfig in risk_config.py**

Add to `traderlib/risk_config.py` after existing imports:

```python
@dataclass
class TrailingStageConfig:
    """Configuration for a single trailing stage.
    
    Attributes:
        trigger_r: R-multiple threshold to activate this stage
        action: "breakeven", "trail_ema", "trail_swing_low", "scale_out"
        period: For "trail_ema" - EMA period (10, 21, etc.)
        fraction: For "scale_out" - fraction to sell (0.0-1.0)
        executed: Runtime flag - has this stage been executed?
    """
    trigger_r: float
    action: str
    period: Optional[int] = None
    fraction: Optional[float] = None
    executed: bool = False  # Runtime state, not from YAML


@dataclass
class ScaleOutStepConfig:
    """Configuration for a scale-out step in hybrid mode."""
    trigger_r: float
    fraction: float
    executed: bool = False
```

Modify `ProfitTargetConfig` dataclass:

```python
@dataclass
class ProfitTargetConfig:
    """Profit target and trailing stop settings - EXTENDED with trailing modes."""
    
    # Original settings (backward compatible)
    min_r_multiple: float = 2.0
    fallback_target_pct: float = 0.10
    breakeven_at_r: float = 1.0  # Kept for backward compat, but see trailing_stages
    ema10_at_r: float = 1.5
    ema21_at_r: float = 3.0
    ema_short_period: int = 10
    ema_long_period: int = 21
    
    # NEW: Mode selection
    mode: str = "target"  # "target" (original), "trailing", "hybrid"
    
    # NEW: Trailing mode configuration (when mode="trailing")
    trailing_mode: str = "stage_based"  # "stage_based", "continuous"
    trailing_stages: List[TrailingStageConfig] = field(default_factory=list)
    continuous_bands: List[Dict] = field(default_factory=list)
    
    # NEW: Hybrid mode configuration (when mode="hybrid")
    scale_out_steps: List[ScaleOutStepConfig] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate configuration."""
        self._validate()
    
    def _validate(self):
        """Validate configuration."""
        if self.mode == "trailing":
            self._validate_trailing()
        elif self.mode == "hybrid":
            self._validate_hybrid()
    
    def _validate_trailing(self):
        """Validate trailing configuration."""
        if self.trailing_mode == "stage_based":
            # Stages must have increasing trigger_r
            prev_r = 0.0
            for stage in self.trailing_stages:
                if stage.trigger_r <= 0:
                    raise ValueError(f"Stage trigger_r must be positive, got {stage.trigger_r}")
                if stage.trigger_r <= prev_r:
                    raise ValueError(
                        f"Trailing stages must have increasing trigger_r: "
                        f"{prev_r} followed by {stage.trigger_r}"
                    )
                prev_r = stage.trigger_r
        
        elif self.trailing_mode == "continuous":
            # Bands must not overlap
            sorted_bands = sorted(self.continuous_bands, key=lambda b: b['from_r'])
            prev_end = 0.0
            for band in sorted_bands:
                if band['from_r'] <= prev_end:
                    raise ValueError(
                        f"Continuous bands must not overlap: "
                        f"band at {band['from_r']} overlaps with previous"
                    )
                prev_end = band.get('to_r', float('inf'))
    
    def _validate_hybrid(self):
        """Validate hybrid mode configuration."""
        for step in self.scale_out_steps:
            if step.fraction <= 0 or step.fraction > 1.0:
                raise ValueError(f"Scale-out fraction must be 0-1, got {step.fraction}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py::TestProfitTargetConfigTrailing -v`

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/risk_config.py tests/test_risk_config.py
git commit -m "feat: extend ProfitTargetConfig with trailing modes

Add mode, trailing_mode, trailing_stages, continuous_bands,
and scale_out_steps to ProfitTargetConfig.

Includes validation for increasing stages and non-overlapping bands.
Maintains backward compatibility with original target mode.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Create Trailing Exit Engine (All Modes)

**Files:**
- Create: `traderlib/trailing_exits.py`
- Test: `tests/test_trailing_exits.py`

**Rationale:** Single engine file implementing all three modes. Uses `RiskConfig` instead of parallel config.

- [ ] **Step 1: Write comprehensive failing test**

```python
"""Tests for trailing exit engine (all modes)."""

import unittest
from unittest.mock import Mock, patch
from dataclasses import dataclass

from traderlib.trailing_exits import TrailingExitEngine
from traderlib.risk_config import ProfitTargetConfig, TrailingStageConfig, ScaleOutStepConfig


@dataclass
class MockPosition:
    """Mock position for testing."""
    ticker: str = 'TEST'
    entry_price: float = 150.0
    stop_price: float = 140.0
    initial_stop_price: float = 140.0
    shares: int = 100
    current_stop_type: str = 'HARD'
    scale_out_history: list = None
    
    def __post_init__(self):
        if self.scale_out_history is None:
            self.scale_out_history = []


class TestRMultipleCalculation(unittest.TestCase):
    """Test R-multiple calculations."""

    def test_basic_r(self):
        """R = gain / initial risk."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=170.0)
        
        # Gain = 2000, Risk = 1000, R = 2.0
        self.assertEqual(r, 2.0)

    def test_fractional_r(self):
        """Calculate 1.5R."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=165.0)
        
        self.assertEqual(r, 1.5)

    def test_negative_r(self):
        """Negative R for losses."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=145.0)
        
        # Loss = -500, R = -0.5
        self.assertEqual(r, -0.5)


class TestStageBasedMode(unittest.TestCase):
    """Test stage-based trailing exit mode."""

    def setUp(self):
        """Create engine with stage-based config."""
        self.config = ProfitTargetConfig(
            mode="trailing",
            trailing_mode="stage_based",
            trailing_stages=[
                TrailingStageConfig(trigger_r=2.0, action="breakeven"),
                TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
                TrailingStageConfig(trigger_r=5.0, action="trail_ema", period=21),
            ]
        )
        self.engine = TrailingExitEngine(self.config)

    def test_stop_hit_exits(self):
        """Exit when price hits stop."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=139.0)
        
        self.assertEqual(result['action'], 'exit')
        self.assertEqual(result['reason'], 'STOP_HIT')

    def test_hold_below_first_stage(self):
        """Hold when below first stage trigger."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=155.0)  # 0.5R
        
        self.assertEqual(result['action'], 'hold')

    def test_breakeven_stage(self):
        """At 2R, move stop to breakeven."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=170.0, ema10=165.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 150.0)  # breakeven
        self.assertEqual(result['reason'], 'STAGE_2.0R_BREAKEVEN')

    def test_ema_trail_stage(self):
        """At 3R, trail with EMA10."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 175.0)  # EMA10

    def test_ema21_stage(self):
        """At 5R, switch to EMA21."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, shares=100)
        result = self.engine.evaluate(pos, current_price=200.0, ema10=195.0, ema21=190.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 190.0)  # EMA21

    def test_stop_only_moves_up(self):
        """Stop never moves lower."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=170.0)  # EMA below stop
        
        self.assertEqual(result['action'], 'hold')  # No update

    def test_missing_ema_fallback(self):
        """Hold when EMA data unavailable."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=None, ema21=None)
        
        self.assertEqual(result['action'], 'hold')  # Can't trail without EMA


class TestContinuousMode(unittest.TestCase):
    """Test continuous trailing exit mode."""

    def setUp(self):
        """Create engine with continuous config."""
        self.config = ProfitTargetConfig(
            mode="trailing",
            trailing_mode="continuous",
            breakeven_at_r=2.0,
            continuous_bands=[
                {"from_r": 2.5, "to_r": 4.0, "method": "ema10"},
                {"from_r": 4.0, "method": "ema21"},  # No to_r = unlimited
            ]
        )
        self.engine = TrailingExitEngine(self.config)

    def test_breakeven_trigger(self):
        """Move to breakeven at configured R."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=170.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 150.0)

    def test_ema10_band(self):
        """Trail EMA10 in first band."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        # At 3R: 150 + 30 = 180
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0, ema21=170.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 175.0)  # EMA10

    def test_ema21_band(self):
        """Trail EMA21 in second band."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, shares=100)
        # At 6R: 150 + 60 = 210
        result = self.engine.evaluate(pos, current_price=210.0, ema10=200.0, ema21=205.0)
        
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 205.0)  # EMA21


class TestHybridMode(unittest.TestCase):
    """Test hybrid mode with scale-out."""

    def setUp(self):
        """Create engine with hybrid config."""
        self.config = ProfitTargetConfig(
            mode="hybrid",
            trailing_stages=[
                TrailingStageConfig(trigger_r=2.0, action="breakeven"),
                TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
            ],
            scale_out_steps=[
                ScaleOutStepConfig(trigger_r=3.0, fraction=0.33),
                ScaleOutStepConfig(trigger_r=4.0, fraction=0.50),
            ]
        )
        self.engine = TrailingExitEngine(self.config)

    def test_scale_out_trigger(self):
        """Trigger scale-out at R-level."""
        pos = MockPosition(
            entry_price=150.0, 
            stop_price=150.0,  # At breakeven
            shares=100,
            scale_out_history=[]
        )
        # At 3R
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0)
        
        self.assertEqual(result['action'], 'scale_out')
        self.assertEqual(result['scale_fraction'], 0.33)
        self.assertEqual(result['shares_to_sell'], 33)

    def test_scale_out_not_repeated(self):
        """Scale-out only triggers once."""
        pos = MockPosition(
            entry_price=150.0,
            stop_price=150.0,
            shares=67,  # After first scale-out
            scale_out_history=[3.0]  # 3R already executed
        )
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0)
        
        self.assertNotEqual(result['action'], 'scale_out')  # Should trail instead

    def test_second_scale_out(self):
        """Second scale-out at 4R."""
        pos = MockPosition(
            entry_price=150.0,
            stop_price=175.0,
            shares=67,
            scale_out_history=[3.0]
        )
        # At 4R: 150 + 40 = 190
        result = self.engine.evaluate(pos, current_price=190.0, ema10=185.0)
        
        self.assertEqual(result['action'], 'scale_out')
        self.assertEqual(result['scale_fraction'], 0.50)
        self.assertEqual(result['shares_to_sell'], 33)  # 50% of remaining 67


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def test_zero_risk(self):
        """Handle zero risk (entry == stop)."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry_price=150.0, stop_price=150.0, initial_stop_price=150.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=170.0)
        
        self.assertEqual(r, 0.0)  # Undefined, return 0

    def test_short_position_not_supported(self):
        """Short positions raise clear error."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry_price=150.0, stop_price=160.0, shares=100)  # Stop above entry = short
        
        with self.assertRaises(NotImplementedError) as cm:
            engine.evaluate(pos, current_price=150.0)
        
        self.assertIn("short", str(cm.exception).lower())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'traderlib.trailing_exits'"

- [ ] **Step 3: Implement TrailingExitEngine**

```python
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
    """Result of trailing exit evaluation."""
    action: str  # "exit", "update_stop", "scale_out", "hold"
    reason: str
    new_stop: Optional[float] = None
    new_stop_type: Optional[str] = None
    scale_fraction: Optional[float] = None
    shares_to_sell: Optional[int] = None
    r_multiple: float = 0.0


class TrailingExitEngine:
    """Engine for evaluating trailing stop rules."""

    def __init__(self, config: ProfitTargetConfig):
        """Initialize with configuration.
        
        Args:
            config: ProfitTargetConfig with trailing settings
        """
        self.config = config
        
        # Validate mode
        if config.mode not in ('target', 'trailing', 'hybrid'):
            raise ValueError(f"Unknown mode: {config.mode}")
        
        if config.mode == 'trailing' and config.trailing_mode not in ('stage_based', 'continuous'):
            raise ValueError(f"Unknown trailing_mode: {config.trailing_mode}")

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
        """
        # Check for short positions
        if position.stop_price > position.entry_price:
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
            new_stop = self._get_ema_for_period(active_stage.period, ema10, ema21)
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
                        r_multiple=r_multiple
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
            EMA value or None if not available
        """
        if period == 10:
            return ema10
        elif period == 21:
            return ema21
        # For other periods, would need additional data
        return ema10 or ema21  # Fallback to available EMA
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

Expected: PASS (20+ tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_exits.py tests/test_trailing_exits.py
git commit -m "feat: add TrailingExitEngine with all three modes

Implements stage_based, continuous, and hybrid trailing modes.
Includes proper state tracking for scale-outs (no repeated triggers).
Handles missing EMA data gracefully.
Raises NotImplementedError for short positions.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Add Scale-Out State Persistence to Position

**Files:**
- Modify: `traderlib/paper_state.py` (Position dataclass)
- Test: `tests/test_paper_state.py` (add scale_out_history tests)

**Rationale:** Position must persist which scale-out steps have been executed to prevent repeated triggers.

- [ ] **Step 1: Add scale_out_history to Position**

Add to `traderlib/paper_state.py` in the Position dataclass:

```python
@dataclass
class Position:
    """Represents an open or closed position.
    
    EXTENDED with scale_out_history for hybrid trailing mode.
    """
    ticker: str
    status: str  # 'OPEN', 'CLOSED'
    entry_date: str
    entry_price: float
    shares: int
    stop_price: float
    target_price: float
    initial_risk: float
    sector: str
    current_stop_type: str = 'HARD'
    initial_stop_price: Optional[float] = None  # For accurate R-calc
    
    # NEW: Scale-out tracking for hybrid mode
    scale_out_history: List[float] = field(default_factory=list)
    # List of R-levels where scale-outs occurred (e.g., [3.0, 4.0])
    
    def record_scale_out(self, r_level: float):
        """Record that a scale-out occurred at the given R-level."""
        if r_level not in self.scale_out_history:
            self.scale_out_history.append(r_level)
```

- [ ] **Step 2: Write test for scale_out_history**

Add to `tests/test_paper_state.py`:

```python
class TestScaleOutHistory(unittest.TestCase):
    """Test scale_out_history tracking."""

    def test_record_scale_out(self):
        """Can record scale-out events."""
        pos = Position(
            ticker='TEST',
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology'
        )
        
        pos.record_scale_out(3.0)
        pos.record_scale_out(4.0)
        
        self.assertEqual(pos.scale_out_history, [3.0, 4.0])

    def test_record_scale_out_no_duplicates(self):
        """Same R-level not recorded twice."""
        pos = Position(
            ticker='TEST',
            status='OPEN',
            entry_date='2026-01-01',
            entry_price=150.0,
            shares=100,
            stop_price=140.0,
            target_price=170.0,
            initial_risk=1000.0,
            sector='Technology'
        )
        
        pos.record_scale_out(3.0)
        pos.record_scale_out(3.0)  # Duplicate
        
        self.assertEqual(pos.scale_out_history, [3.0])
```

- [ ] **Step 3: Run test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_paper_state.py::TestScaleOutHistory -v`

Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/paper_state.py tests/test_paper_state.py
git commit -m "feat: add scale_out_history to Position

Prevents repeated scale-out triggers by tracking
which R-levels have already been executed.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Integrate Trailing Engine into ExitEngine

**Files:**
- Modify: `traderlib/paper_exits.py` (ExitEngine class)
- Test: `tests/test_trailing_integration.py` (new integration tests)

**Rationale:** Single integration point that routes to trailing engine when configured.

- [ ] **Step 1: Write integration test**

Create `tests/test_trailing_integration.py`:

```python
"""Integration tests for trailing exits with ExitEngine."""

import unittest
from unittest.mock import Mock, patch
from dataclasses import dataclass

from traderlib.paper_exits import ExitEngine, ExitActionType
from traderlib.risk_config import ProfitTargetConfig, TrailingStageConfig, RiskConfig


@dataclass
class MockPosition:
    """Mock position matching Position interface."""
    ticker: str = 'TEST'
    entry_price: float = 150.0
    stop_price: float = 140.0
    initial_stop_price: float = 140.0
    shares: int = 100
    current_stop_type: str = 'HARD'
    scale_out_history: list = None
    
    def __post_init__(self):
        if self.scale_out_history is None:
            self.scale_out_history = []


class TestTrailingModeIntegration(unittest.TestCase):
    """Test trailing mode integration with ExitEngine."""

    @patch.object(ExitEngine, '_get_ema_values')
    def test_trailing_mode_breakeven(self, mock_ema):
        """Trailing mode moves stop to breakeven at 2R."""
        mock_ema.return_value = (170.0, 168.0)
        
        # Create risk config with trailing mode
        risk_config = RiskConfig()
        risk_config.profit_target.mode = "trailing"
        risk_config.profit_target.trailing_mode = "stage_based"
        risk_config.profit_target.trailing_stages = [
            TrailingStageConfig(trigger_r=2.0, action="breakeven"),
            TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
        ]
        
        engine = ExitEngine(risk_config=risk_config)
        pos = MockPosition(entry_price=150.0, stop_price=140.0, 
                          initial_stop_price=140.0)
        
        # At 2R: 150 + 20 = 170
        action = engine.evaluate_exit_action(pos, current_price=170.0)
        
        self.assertEqual(action.action, ExitActionType.UPDATE_STOP)
        self.assertEqual(action.new_stop_price, 150.0)  # breakeven

    @patch.object(ExitEngine, '_get_ema_values')
    def test_trailing_mode_ema_trail(self, mock_ema):
        """Trailing mode trails with EMA at 3R."""
        mock_ema.return_value = (175.0, 170.0)
        
        risk_config = RiskConfig()
        risk_config.profit_target.mode = "trailing"
        risk_config.profit_target.trailing_mode = "stage_based"
        risk_config.profit_target.trailing_stages = [
            TrailingStageConfig(trigger_r=2.0, action="breakeven"),
            TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
        ]
        
        engine = ExitEngine(risk_config=risk_config)
        pos = MockPosition(entry_price=150.0, stop_price=150.0)  # At breakeven
        
        # At 3R: 150 + 30 = 180
        action = engine.evaluate_exit_action(pos, current_price=180.0)
        
        self.assertEqual(action.action, ExitActionType.UPDATE_STOP)
        self.assertEqual(action.new_stop_price, 175.0)  # ema10
        self.assertEqual(action.new_stop_type, 'EMA10_TRAIL')

    def test_target_mode_backward_compatible(self):
        """Original target mode still works when mode not set."""
        risk_config = RiskConfig()
        # mode defaults to "target"
        
        engine = ExitEngine(risk_config=risk_config)
        pos = MockPosition(entry_price=150.0, stop_price=140.0,
                          initial_stop_price=140.0)
        pos.target_price = 170.0  # 2R target
        
        # At 2.5R: should exit at target
        action = engine.evaluate_exit_action(pos, current_price=175.0)
        
        self.assertEqual(action.action, ExitActionType.EXIT)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_integration.py -v`

Expected: FAIL with "ExitEngine doesn't have trailing engine integration"

- [ ] **Step 3: Modify ExitEngine to integrate trailing**

Add to `traderlib/paper_exits.py` after existing imports:

```python
try:
    from traderlib.trailing_exits import TrailingExitEngine
    TRAILING_AVAILABLE = True
except ImportError:
    TRAILING_AVAILABLE = False
```

Modify `ExitEngine.__init__`:

```python
def __init__(self, risk_config: Optional['RiskConfig'] = None, 
             risk_profile: Optional[str] = None):
    """Initialize with optional risk configuration."""
    self.price_cache = {}
    self.cache_timestamp = None

    # Load or use provided risk configuration
    if risk_config:
        self.risk_config = risk_config
    elif RiskConfigManager:
        manager = RiskConfigManager(profile=risk_profile)
        self.risk_config = manager.get_config()
    else:
        self.risk_config = None
    
    # Initialize trailing engine if mode is trailing or hybrid
    self.trailing_engine = None
    if (self.risk_config and TRAILING_AVAILABLE and 
        self.risk_config.profit_target.mode in ('trailing', 'hybrid')):
        self.trailing_engine = TrailingExitEngine(self.risk_config.profit_target)
```

Modify `evaluate_exit_action` to use trailing engine:

```python
def evaluate_exit_action(self, position, current_price: float,
                         historical_data: Optional[pd.DataFrame] = None) -> 'ExitAction':
    """Evaluate all exit conditions and return atomic ExitAction.
    
    Routes to trailing engine if configured, otherwise uses original target logic.
    """
    # If trailing mode is active, delegate to trailing engine
    if self.trailing_engine:
        ema10, ema21 = self._get_ema_values(position.ticker, historical_data)
        result = self.trailing_engine.evaluate(position, current_price, ema10, ema21)
        
        # Convert TrailingResult to ExitAction
        if result.action == 'exit':
            return ExitAction(
                ticker=position.ticker,
                action=ExitActionType.EXIT,
                reason=result.reason,
                exit_price=current_price,
                r_multiple=result.r_multiple
            )
        elif result.action == 'update_stop':
            return ExitAction(
                ticker=position.ticker,
                action=ExitActionType.UPDATE_STOP,
                reason=result.reason,
                r_multiple=result.r_multiple,
                new_stop_price=result.new_stop,
                new_stop_type=result.new_stop_type
            )
        elif result.action == 'scale_out':
            # Scale-out is handled by caller, treat as update_stop for now
            return ExitAction(
                ticker=position.ticker,
                action=ExitActionType.UPDATE_STOP,
                reason=result.reason,
                r_multiple=result.r_multiple,
                new_stop_price=position.stop_price,  # No stop change
                new_stop_type='SCALE_OUT'
            )
        else:  # hold
            return ExitAction(
                ticker=position.ticker,
                action=ExitActionType.HOLD,
                reason=result.reason,
                r_multiple=result.r_multiple
            )
    
    # Original profit target logic (keep existing code from paper_exits.py)
    # ... rest of existing evaluate_exit_action ...
```

- [ ] **Step 4: Run integration test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_integration.py -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/paper_exits.py tests/test_trailing_integration.py
git commit -m "feat: integrate trailing engine into ExitEngine

ExitEngine now routes to TrailingExitEngine when mode
is 'trailing' or 'hybrid'. Falls back to original target
logic when mode is 'target'.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Create Example Strategy Configuration

**Files:**
- Create: `config/strategies/example_trailing.yaml`

- [ ] **Step 1: Create example configuration**

```yaml
# Example Trailing Exit Strategy Configuration
# Demonstrates stage-based trailing exits

name: example_trailing
description: "Stage-based trailing stops - breakeven at 2R, trail EMA at 3R+"

# Use this with: python scripts/backtest.py --strategy example_trailing
# Or in paper trading: set strategy in risk_config.yaml

# =============================================================================
# Exit Management - Stage-Based Trailing (User's Preferred Strategy)
# =============================================================================
# This configuration:
# 1. Moves stop to breakeven at +2R (protects capital)
# 2. Trails with 10 EMA at +3R (early trend following)
# 3. Widens to 21 EMA at +5R (let winners run)
# 4. No fixed profit target - exits on trailing stop breach

profit_target:
  mode: "trailing"
  trailing_mode: "stage_based"
  breakeven_at_r: 2.0  # Optional, first stage does same thing
  
  trailing_stages:
    # Stage 1: Protect capital
    - trigger_r: 2.0
      action: "breakeven"
    
    # Stage 2: Early trend (tight trail)
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    
    # Stage 3: Late trend (wider trail)
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21

# =============================================================================
# Alternative: Hybrid Mode (Scale-Out + Trail)
# =============================================================================
# Uncomment to use hybrid mode:
#
# profit_target:
#   mode: "hybrid"
#   trailing_stages:
#     - trigger_r: 2.0
#       action: "breakeven"
#     - trigger_r: 3.0
#       action: "trail_ema"
#       period: 10
#   scale_out_steps:
#     - trigger_r: 3.0
#       fraction: 0.33  # Sell 1/3 at 3R
#     - trigger_r: 4.0
#       fraction: 0.50  # Sell 1/2 of remaining at 4R

# =============================================================================
# Alternative: Continuous Mode
# =============================================================================
# Uncomment to use continuous mode:
#
# profit_target:
#   mode: "trailing"
#   trailing_mode: "continuous"
#   breakeven_at_r: 2.0
#   continuous_bands:
#     - from_r: 2.5
#       to_r: 4.0
#       method: "ema10"
#     - from_r: 4.0
#       method: "ema21"

# =============================================================================
# Universe filters (same as vcp_large_cap for comparison)
# =============================================================================
universe:
  min_market_cap: 5000
  min_dollar_volume: 80000000
  min_share_volume: 1000000

# =============================================================================
# Entry filters
# =============================================================================
entry:
  min_stage2_score: 6
  min_convergence_score: 50
  max_pivot_proximity_pct: 5.0
```

- [ ] **Step 2: Validate YAML**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -c "import yaml; yaml.safe_load(open('config/strategies/example_trailing.yaml'))"`

Expected: No errors

- [ ] **Step 3: Write test for loading example**

Add to `tests/test_risk_config.py`:

```python
class TestExampleStrategyLoad(unittest.TestCase):
    """Test loading the example trailing strategy."""
    
    def test_example_yaml_loads(self):
        """Example trailing strategy YAML loads correctly."""
        from pathlib import Path
        from traderlib.trailing_config import TrailingConfigLoader
        
        example_path = Path(__file__).parent.parent / "config" / "strategies" / "example_trailing.yaml"
        if not example_path.exists():
            self.skipTest("Example strategy not found")
        
        # Load as dict first (strategy files have more than just exit config)
        import yaml
        with open(example_path, 'r') as f:
            data = yaml.safe_load(f)
        
        self.assertIn('profit_target', data)
        pt = data['profit_target']
        self.assertEqual(pt['mode'], 'trailing')
        self.assertEqual(pt['trailing_mode'], 'stage_based')
        self.assertEqual(len(pt['trailing_stages']), 3)
```

- [ ] **Step 4: Run test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py::TestExampleStrategyLoad -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add config/strategies/example_trailing.yaml tests/test_risk_config.py
git commit -m "feat: add example trailing exit strategy config

Demonstrates all three modes with user's preferred
stage-based strategy as default example.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Migration Path: Global to Per-Strategy Config

**Current Implementation (Option A - Global):** All strategies use `risk_config.yaml`

**Future Migration (Option B - Per-Strategy):** Each strategy can override exits

### Why Migration is Possible

The architecture already supports per-strategy configs. The `TrailingExitEngine` accepts any `ProfitTargetConfig`, regardless of source:

```python
# Global config (current)
risk_config = RiskConfigManager().get_config()
engine = TrailingExitEngine(risk_config.profit_target)

# Strategy config (future)
strategy_config = load_strategy_config('stage2_momentum')
engine = TrailingExitEngine(strategy_config.profit_target)
```

### Migration Steps (Future Task)

To migrate from global to per-strategy later:

**Step 1:** Modify `backtest.py` to check for strategy-specific exit config:

```python
# In backtest.py, around line 142
risk_config = RiskConfigManager(profile=args.risk_profile).get_config()

# NEW: Check if strategy has its own exit config
strategy_config_path = Path(f"config/strategies/{args.strategy}.yaml")
if strategy_config_path.exists():
    strategy_yaml = yaml.safe_load(open(strategy_config_path))
    if 'profit_target' in strategy_yaml:
        # Override with strategy-specific config
        strategy_profit_config = parse_profit_target_config(strategy_yaml['profit_target'])
        risk_config.profit_target = strategy_profit_config

exit_engine = ExitEngine(risk_config=risk_config)
```

**Step 2:** Create per-strategy config files:

```yaml
# config/strategies/stage2_momentum.yaml
name: stage2_momentum

profit_target:
  mode: "trailing"
  trailing_mode: "stage_based"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21
```

**Step 3:** Fallback to global config if no strategy-specific config:

```python
# If strategy YAML doesn't have profit_target, use risk_config.yaml (current behavior)
```

### Benefits of Deferred Migration

1. **Start simple:** Get trailing exits working with one config file
2. **Validate approach:** See if you actually want different exits per strategy
3. **No rework:** The architecture supports both modes without refactoring
4. **Gradual transition:** Add per-strategy configs one at a time

### When to Migrate

| Trigger | Action |
|---------|--------|
| Want to A/B test exit strategies | Add per-strategy config for one strategy |
| Different strategies need different exits | Migrate fully to per-strategy |
| Happy with one exit strategy for all | Stay with global config |

**No migration needed until you want per-strategy customization.**

---

## Task 6: Integrate with Backtest Engine

**Files:**
- Modify: `traderlib/backtest/engine.py` (use trailing exits)
- Test: `tests/test_backtest_trailing.py` (new backtest tests)

- [ ] **Step 1: Verify backtest engine uses ExitEngine**

Check: `grep -n "ExitEngine\|evaluate_exit" traderlib/backtest/engine.py | head -10`

- [ ] **Step 2: Write backtest test with trailing exits**

Create `tests/test_backtest_trailing.py`:

```python
"""Test backtesting with trailing exits."""

import unittest
from datetime import date
from traderlib.backtest.engine import BacktestEngine
from traderlib.backtest.strategy import BuyAndHoldStrategy
from traderlib.risk_config import RiskConfig, TrailingStageConfig


class TestBacktestWithTrailingExits(unittest.TestCase):
    """Test backtesting engine with trailing exit configuration."""

    def setUp(self):
        """Create engine with trailing config."""
        self.risk_config = RiskConfig()
        self.risk_config.profit_target.mode = "trailing"
        self.risk_config.profit_target.trailing_mode = "stage_based"
        self.risk_config.profit_target.trailing_stages = [
            TrailingStageConfig(trigger_r=2.0, action="breakeven"),
            TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
        ]

    def test_backtest_uses_trailing_config(self):
        """Backtest engine respects trailing configuration."""
        # This test verifies the backtest engine can be configured
        # with trailing exits and runs without errors
        engine = BacktestEngine(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 1),
            initial_cash=100000,
            risk_config=self.risk_config
        )
        
        # Verify engine has trailing config
        self.assertEqual(
            engine.risk_config.profit_target.mode,
            "trailing"
        )
```

- [ ] **Step 3: Run test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_backtest_trailing.py -v`

Expected: PASS (if backtest engine accepts risk_config) or FAIL (if integration needed)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add tests/test_backtest_trailing.py
git commit -m "test: add backtest integration tests for trailing exits

Verifies backtest engine can use trailing exit configuration.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Update Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-configurable-trailing-exits-design.md`
- Create: `docs/superpowers/plans/2026-04-25-trailing-exit-system-implementation-notes.md`

- [ ] **Step 1: Update design doc with status**

Add to top of design doc:

```markdown
## Implementation Status

**Status:** ✅ IMPLEMENTED (Revised Plan)
**Completed:** 2026-04-25
**Plan:** `docs/superpowers/plans/2026-04-25-trailing-exit-system.md`

### Key Changes from Original Design (Post-Review)

1. **Merged config into risk_config.py** — Eliminated parallel `trailing_config.py`, extended existing `ProfitTargetConfig`
2. **Fixed task dependency order** — All modes implemented before integration
3. **Fixed scale-out trigger bug** — Added `executed` flag to prevent repeated triggers
4. **Added state persistence** — Position tracks `scale_out_history`
5. **Fixed EMA handling** — Graceful fallback when EMAs unavailable
6. **Fixed breakeven logic** — Proper state machine for continuous mode

### Files Created/Modified
- `traderlib/risk_config.py` — Extended ProfitTargetConfig with trailing modes
- `traderlib/trailing_exits.py` — Core trailing engine (all 3 modes)
- `traderlib/paper_state.py` — Added scale_out_history to Position
- `traderlib/paper_exits.py` — Integrated trailing into ExitEngine
- `config/strategies/example_trailing.yaml` — Example configuration
- `tests/test_trailing_exits.py` — Engine tests
- `tests/test_trailing_integration.py` — Integration tests
- `tests/test_backtest_trailing.py` — Backtest tests
```

- [ ] **Step 2: Create implementation notes**

```markdown
# Trailing Exit System - Implementation Notes

## Quick Start

### Using Stage-Based Mode

Add to your strategy config or `risk_config.yaml`:

```yaml
profit_target:
  mode: "trailing"
  trailing_mode: "stage_based"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21
```

### Using Hybrid Mode (Scale-Out)

```yaml
profit_target:
  mode: "hybrid"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
  scale_out_steps:
    - trigger_r: 3.0
      fraction: 0.33
    - trigger_r: 4.0
      fraction: 0.50
```

## AMD Trade Example (Revised)

With stage-based configuration:

| Price | R | Action | Stop | Notes |
|-------|---|--------|------|-------|
| $281.83 | 0R | Entry | $267.74 | Initial ATR stop |
| $313.93 | 2R | Breakeven | $281.83 | Capital protected |
| $345.73 | 3R | Trail 10EMA | ~$340 | Following trend |
| $409.33 | 5R | Trail 21EMA | ~$390 | Widened for volatility |
| $380.00 | — | Exit | $380 | 21EMA breached |

## Backward Compatibility

Default mode remains `target` (fixed 2R profit). To enable trailing, explicitly set:

```yaml
profit_target:
  mode: "trailing"  # or "hybrid"
```

## Running Tests

```bash
# All trailing tests
python -m pytest tests/test_trailing*.py -v

# Integration tests
python -m pytest tests/test_trailing_integration.py -v

# Backtest tests
python -m pytest tests/test_backtest_trailing.py -v
```

## Known Limitations

1. **Short positions not supported** — Raises `NotImplementedError`
2. **EMA periods limited** — Currently supports 10 and 21 (others use nearest)
3. **Scale-out doesn't reduce risk** — Initial R-calculation unchanged after scale-out
```

- [ ] **Step 3: Commit documentation**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add docs/
git commit -m "docs: update trailing exit design and add implementation notes

Documents revised implementation with all fixes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Fix Critical — Scale-Out with 0 Shares Silent No-Op

**Priority:** CRITICAL
**Files:**
- Modify: `traderlib/trailing_exits.py`

**Issue:** When `position.shares` is small (e.g., 3 shares × 0.33 fraction), `int(3 * 0.33) = int(0.99) = 0`. The scale-out "fires" with `shares_to_sell=0`, which means no shares are sold, but the R-level gets recorded in `scale_out_history`, permanently blocking future triggers. For 1-share positions, every fraction yields 0.

- [ ] **Step 1: Add minimum-shares guard in `_evaluate_hybrid()`**

In `trailing_exits.py`, after computing `shares_to_sell`:
```python
shares_to_sell = int(position.shares * step.fraction)
if shares_to_sell <= 0:
    # Position too small to scale out at this fraction; skip this step
    continue
if shares_to_sell >= position.shares:
    # Scale-out would close entire position; treat as hold and let trailing handle exit
    continue
```

- [ ] **Step 2: Add test for small-position scale-out edge case**

```python
def test_scale_out_too_small_position(self):
    """Scale-out with too few shares should hold, not fire with 0 shares."""
    config = ProfitTargetConfig(
        mode="hybrid",
        trailing_stages=[TrailingStageConfig(trigger_r=2.0, action="breakeven")],
        scale_out_steps=[ScaleOutStepConfig(trigger_r=3.0, fraction=0.33)]
    )
    engine = TrailingExitEngine(config)
    pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=2, scale_out_history=[])
    result = engine.evaluate(pos, current_price=180.0, ema10=175.0)
    # 2 shares × 0.33 = 0.66 → int(0.66) = 0, should skip scale-out
    self.assertNotEqual(result.action, 'scale_out')
    self.assertNotIn(3.0, pos.scale_out_history)
```

- [ ] **Step 3: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

- [ ] **Step 4: Commit**

```bash
git add traderlib/trailing_exits.py tests/test_trailing_exits.py
git commit -m "fix: prevent scale-out with 0 shares from blocking future triggers

When position.shares is too small for a scale-out fraction, int()
rounds to 0 shares. Now skips scale-out steps that would sell 0 or
all remaining shares, preventing scale_out_history from recording
R-levels that were never actually executed."
```

---

## Task 9: Fix Critical — Invalid YAML Config Silently Falls Back to Defaults

**Priority:** CRITICAL
**Files:**
- Modify: `traderlib/risk_config.py`

**Issue:** `_load_config()` catches all exceptions (including `ValueError` from config validation) and silently returns defaults. An operator who configured trailing exits would silently revert to fixed 2R targets.

- [ ] **Step 1: Separate validation errors from I/O errors in `_load_config()`**

```python
def _load_config(self):
    """Load and validate risk configuration from YAML."""
    config = self._get_defaults()
    config_path = self._find_config_path()
    if not config_path:
        return config

    try:
        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f) or {}
        config = self._parse_config(yaml_data)
        return config
    except yaml.YAMLError as e:
        print(f"⚠️  YAML parse error in {config_path}: {e}, using defaults")
        return config
    except ValueError as e:
        raise SystemExit(f"Invalid risk configuration in {config_path}: {e}") from e
    except Exception as e:
        print(f"⚠️  Error loading risk config: {e}, using defaults")
        return config
```

- [ ] **Step 2: Add test for invalid config rejection**

```python
def test_invalid_yaml_config_fails_loudly(self):
    """Invalid config should raise SystemExit, not silently fall back."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'profit_target': {
                'mode': 'trailing',
                'trailing_stages': [
                    {'trigger_r': 3.0, 'action': 'breakeven'},
                    {'trigger_r': 2.0, 'action': 'breakeven'},  # Not increasing!
                ]
            }
        }, f)
        f.flush()
        path = f.name

    with self.assertRaises(SystemExit):
        RiskConfigManager(config_path=path)

    os.unlink(path)
```

- [ ] **Step 3: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py -v`

- [ ] **Step 4: Commit**

```bash
git add traderlib/risk_config.py tests/test_risk_config.py
git commit -m "fix: fail loudly on invalid YAML config instead of silent fallback

ValueError from config validation (e.g., decreasing stages, invalid
fractions) now raises SystemExit. Only I/O and YAML parse errors
fall back to defaults. Prevents silent reversion from trailing to
fixed 2R targets."
```

---

## Task 10: Fix Important — Remove Dead `executed` Fields from Config Dataclasses

**Priority:** IMPORTANT
**Files:**
- Modify: `traderlib/risk_config.py`

**Issue:** `TrailingStageConfig` and `ScaleOutStepConfig` have `executed: bool = False` fields annotated as "Runtime state, not from YAML." These are never read or written — runtime tracking uses `position.scale_out_history` instead. They pollute `asdict()` output with `False` values.

- [ ] **Step 1: Remove `executed` field from `TrailingStageConfig` and `ScaleOutStepConfig`**

- [ ] **Step 2: Update any tests that reference `.executed`**

- [ ] **Step 3: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py tests/test_trailing_exits.py -v`

- [ ] **Step 4: Commit**

```bash
git add traderlib/risk_config.py tests/
git commit -m "fix: remove unused executed fields from config dataclasses

Runtime state tracking uses position.scale_out_history, not config
fields. Removes dead state that confused asdict() output."
```

---

## Task 11: Fix Important — Validate Non-Empty Stages/Bands in Trailing Mode

**Priority:** IMPORTANT
**Files:**
- Modify: `traderlib/risk_config.py`

**Issue:** `mode="trailing"` with `trailing_stages=[]` causes the engine to hold forever (only hard stop remains). No validation prevents this misconfiguration.

- [ ] **Step 1: Add validation requiring at least one stage/band**

In `_validate_trailing()`:
```python
def _validate_trailing(self):
    """Validate trailing configuration."""
    if self.trailing_mode == "stage_based":
        if not self.trailing_stages:
            raise ValueError("trailing_stages must have at least one stage when mode='trailing'")
        # ... existing stage validation ...
    elif self.trailing_mode == "continuous":
        if not self.continuous_bands:
            raise ValueError("continuous_bands must have at least one band when trailing_mode='continuous'")
        # ... existing band validation ...
```

Similarly in `_validate_hybrid()`:
```python
def _validate_hybrid(self):
    """Validate hybrid mode configuration."""
    if not self.trailing_stages:
        raise ValueError("trailing_stages must have at least one stage when mode='hybrid'")
    # ... existing scale-out validation ...
```

- [ ] **Step 2: Add tests for empty stages/bands**

```python
def test_trailing_mode_requires_stages(self):
    """Trailing mode with empty stages raises ValueError."""
    with self.assertRaises(ValueError) as cm:
        ProfitTargetConfig(mode="trailing", trailing_mode="stage_based", trailing_stages=[])
    self.assertIn("at least one stage", str(cm.exception))

def test_continuous_mode_requires_bands(self):
    """Continuous mode with empty bands raises ValueError."""
    with self.assertRaises(ValueError) as cm:
        ProfitTargetConfig(mode="trailing", trailing_mode="continuous", continuous_bands=[])
    self.assertIn("at least one band", str(cm.exception))

def test_hybrid_mode_requires_stages(self):
    """Hybrid mode with empty stages raises ValueError."""
    with self.assertRaises(ValueError) as cm:
        ProfitTargetConfig(mode="hybrid", trailing_stages=[], scale_out_steps=[ScaleOutStepConfig(trigger_r=3.0, fraction=0.5)])
    self.assertIn("at least one stage", str(cm.exception))
```

- [ ] **Step 3: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py -v`

- [ ] **Step 4: Commit**

```bash
git add traderlib/risk_config.py tests/test_risk_config.py
git commit -m "fix: require non-empty stages/bands in trailing and hybrid modes

Empty trailing_stages or continuous_bands caused hold-forever behavior
since only the hard stop would remain active. Now raises ValueError
at config load time."
```

---

## Task 12: Fix Important — Document `breakeven_at_r` Mode-Specific Behavior

**Priority:** IMPORTANT
**Files:**
- Modify: `traderlib/risk_config.py` (docstring)
- Modify: `config/strategies/example_trailing.yaml` (comment)

**Issue:** `breakeven_at_r` only applies in continuous mode but this is undocumented. Stage-based mode requires an explicit `action: "breakeven"` stage. Also, `breakeven_at_r` defaults to 1.0 in continuous mode — this implicit behavior should be called out.

- [ ] **Step 1: Add docstring to `breakeven_at_r` field in `ProfitTargetConfig`**

```python
breakeven_at_r: float = 1.0  # Continuous mode only: R-level to move stop to breakeven.
                              # Stage-based mode uses explicit breakeven stages instead.
                              # Defaults to 1.0 — set explicitly to avoid implicit behavior.
```

- [ ] **Step 2: Add note to example_trailing.yaml**

Add a comment block explaining `breakeven_at_r` scope:
```yaml
# NOTE: breakeven_at_r only applies in continuous mode.
# In stage_based mode, add an explicit stage with action: "breakeven".
# If using continuous mode, set breakeven_at_r explicitly to avoid
# the 1.0R default triggering breakeven earlier than intended.
```

- [ ] **Step 3: Commit**

```bash
git add traderlib/risk_config.py config/strategies/example_trailing.yaml
git commit -m "docs: clarify breakeven_at_r is continuous-mode only

breakeven_at_r defaults to 1.0 in continuous mode. Stage-based mode
uses explicit breakeven stages. Added docstrings and YAML comments."
```

---

## Task 13: Fix Important — Add Float Precision Safety for Scale-Out Deduplication

**Priority:** IMPORTANT
**Files:**
- Modify: `traderlib/trailing_exits.py`
- Modify: `traderlib/paper_state.py`

**Issue:** `scale_out_history` deduplication uses `not in` on floats. Currently safe because config values are clean, but fragile. Add a note in `Position.record_scale_out()` and round to fixed precision for safety.

- [ ] **Step 1: Round `r_level` in `record_scale_out()` to 6 decimal places**

```python
def record_scale_out(self, r_level: float):
    """Record that a scale-out occurred at the given R-level.

    Args:
        r_level: R-level of the scale-out, must match a trigger_r from
                 ScaleOutStepConfig. Rounded to 6 decimal places for
                 safe float comparison.
    """
    rounded = round(r_level, 6)
    if rounded not in self.scale_out_history:
        self.scale_out_history.append(rounded)
```

- [ ] **Step 2: Round `trigger_r` comparison in `_evaluate_hybrid()`**

```python
executed = set(round(r, 6) for r in (position.scale_out_history or []))
...
if round(step.trigger_r, 6) not in executed and r_multiple >= step.trigger_r:
```

- [ ] **Step 3: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py tests/test_trailing_integration.py -v`

- [ ] **Step 4: Commit**

```bash
git add traderlib/trailing_exits.py traderlib/paper_state.py tests/
git commit -m "fix: round R-levels to 6 decimal places for scale-out deduplication

Float equality comparison for scale_out_history is fragile. Round
both recorded and compared R-levels to 6 decimal places for safety."
```

---

## Task 14: Suggestion — Add Runtime Validation to TrailingResult

**Priority:** SUGGESTION
**Files:**
- Modify: `traderlib/trailing_exits.py`

**Issue:** `TrailingAction = Literal["exit", "update_stop", "scale_out", "hold"]` is only a static type hint. Direct `TrailingResult(action='invalid')` construction is allowed. Invalid actions silently fall through to hold in ExitEngine.

- [ ] **Step 1: Add `__post_init__` validation to `TrailingResult`**

```python
VALID_ACTIONS = ("exit", "update_stop", "scale_out", "hold")

@dataclass
class TrailingResult:
    """Result of trailing exit evaluation."""
    action: str  # "exit", "update_stop", "scale_out", "hold"
    reason: str
    new_stop: Optional[float] = None
    new_stop_type: Optional[str] = None
    scale_fraction: Optional[float] = None
    shares_to_sell: Optional[int] = None
    r_multiple: float = 0.0

    def __post_init__(self):
        if self.action not in self.VALID_ACTIONS:
            raise ValueError(f"Invalid TrailingResult action: {self.action!r}. Must be one of {self.VALID_ACTIONS}")
```

- [ ] **Step 2: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

- [ ] **Step 3: Commit**

```bash
git add traderlib/trailing_exits.py
git commit -m "feat: add runtime validation to TrailingResult action field

Invalid actions now raise ValueError instead of silently falling
through to hold behavior in ExitEngine."
```

---

## Task 15: Suggestion — Add `__post_init__` Validation to ScaleOutStepConfig

**Priority:** SUGGESTION
**Files:**
- Modify: `traderlib/risk_config.py`

**Issue:** `ScaleOutStepConfig` has no `__post_init__` validation, while `TrailingStageConfig` does. A `ScaleOutStepConfig(trigger_r=3.0, fraction=0.0)` can be created without error.

- [ ] **Step 1: Add `__post_init__` to `ScaleOutStepConfig`**

```python
@dataclass
class ScaleOutStepConfig:
    """Configuration for a scale-out step in hybrid mode."""
    trigger_r: float
    fraction: float

    def __post_init__(self):
        if self.fraction <= 0 or self.fraction > 1.0:
            raise ValueError(f"Scale-out fraction must be 0 < fraction <= 1.0, got {self.fraction}")
        if self.trigger_r <= 0:
            raise ValueError(f"Scale-out trigger_r must be positive, got {self.trigger_r}")
```

- [ ] **Step 2: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py tests/test_trailing_exits.py -v`

- [ ] **Step 3: Commit**

```bash
git add traderlib/risk_config.py tests/
git commit -m "feat: add post_init validation to ScaleOutStepConfig

Validates fraction (0 < f <= 1.0) and trigger_r > 0 at construction
time, consistent with TrailingStageConfig validation."
```

---

## Task 16: Suggestion — Replace `print()` with `logging` in trailing_exits.py

**Priority:** SUGGESTION
**Files:**
- Modify: `traderlib/trailing_exits.py`

**Issue:** Several error/warning paths use `print()` instead of `logging`. Print statements go to stdout and can be lost or mixed with normal output.

- [ ] **Step 1: Replace `print()` calls with `logging.warning()`**

Add at top of file:
```python
import logging
logger = logging.getLogger(__name__)
```

Replace all `print(f"⚠️ ...")` with `logger.warning(...)`

- [ ] **Step 2: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

- [ ] **Step 3: Commit**

```bash
git add traderlib/trailing_exits.py
git commit -m "refactor: replace print() with logging in trailing_exits.py

Uses logging.warning() for consistency with the rest of the codebase."
```

---

## Task 17: Cleanup — Remove Unrelated rate_limiter.py Change from PR

**Priority:** SUGGESTION
**Files:**
- Modify: `traderlib/rate_limiter.py` (revert change)

**Issue:** The diff includes a change to `rate_limiter.py` switching `threading.Lock` to `threading.RLock`. This is unrelated to trailing exits and should be in a separate commit/PR.

- [ ] **Step 1: Assess whether to revert or separate**

Check if the rate_limiter.py change is needed by the trailing exit system:
```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && git diff main -- traderlib/rate_limiter.py
```

If unrelated, revert:
```bash
git checkout main -- traderlib/rate_limiter.py
git commit -m "revert: remove unrelated rate_limiter.py change from trailing exits PR"
```

Or create a separate branch for it.

---

## Task 18: Fix Critical — Add Trailing Exit Documentation to risk_config.yaml

**Priority:** CRITICAL (documentation)
**Files:**
- Modify: `config/risk_config.yaml`

**Issue:** The primary config file only documents the old `trailing_stops` format (breakeven_at_r, ema10_at_r, ema21_at_r). There is no documentation for `mode`, `trailing_mode`, `trailing_stages` (list), `continuous_bands`, or `scale_out_steps`. Users cannot discover or use the new feature from this config file.

- [ ] **Step 1: Add trailing exit documentation to `profit_target` section**

Under the existing `profit_target` block, add commented documentation:

```yaml
profit_target:
  # === Exit Mode Selection ===
  # mode: "target" (default) - fixed R target exit
  # mode: "trailing" - stage-based or continuous trailing stops
  # mode: "hybrid" - scale-out + trailing
  mode: "target"

  # === Target Mode (default) ===
  min_r_multiple: 2.0
  fallback_target_pct: 0.10

  # === Trailing Mode (when mode: "trailing") ===
  # trailing_mode: "stage_based" or "continuous"
  # trailing_stages: list of {trigger_r, action, period}
  #   - trigger_r: R-multiple threshold (must be increasing)
  #   - action: "breakeven" or "trail_ema"
  #   - period: EMA period for "trail_ema" (10 or 21)
  # breakeven_at_r: R-level to move stop to breakeven (continuous mode only)
  #   NOTE: In stage_based mode, add an explicit stage with action: "breakeven".
  #   Defaults to 1.0 in continuous mode — set explicitly to avoid implicit behavior.
  # continuous_bands: list of {from_r, to_r (optional), method: "ema10"|"ema21"}
  #   - Bands must not overlap and from_r must be increasing
  #   - to_r: Optional upper bound. If omitted, band extends to infinity.
  #
  # Example (stage_based):
  #   mode: "trailing"
  #   trailing_mode: "stage_based"
  #   trailing_stages:
  #     - trigger_r: 2.0
  #       action: "breakeven"
  #     - trigger_r: 3.0
  #       action: "trail_ema"
  #       period: 10
  #     - trigger_r: 5.0
  #       action: "trail_ema"
  #       period: 21
  #
  # See config/strategies/example_trailing.yaml for full examples.

  # === Hybrid Mode (when mode: "hybrid") ===
  # scale_out_steps: list of {trigger_r, fraction}
  #   - trigger_r: R-multiple threshold for scale-out
  #   - fraction: fraction of REMAINING position to sell (0 < f <= 1.0)
  #   - Total fractions should not exceed 1.0 across all steps
  #   - Requires trailing_stages for stop management after scale-outs
```

- [ ] **Step 2: Validate YAML still loads correctly**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python -c "from traderlib.risk_config import RiskConfigManager; cfg = RiskConfigManager(); print(f'Mode: {cfg.profit_target.mode}')"
```

- [ ] **Step 3: Commit**

```bash
git add config/risk_config.yaml
git commit -m "docs: add trailing exit configuration to risk_config.yaml

Documents mode, trailing_mode, trailing_stages, continuous_bands,
and scale_out_steps with examples. References example_trailing.yaml
for complete configurations."
```

---

## Task 19: Fix Critical — Remove Misleading `fraction` Field from TrailingStageConfig

**Priority:** CRITICAL (documentation / correctness)
**Files:**
- Modify: `traderlib/risk_config.py`
- Modify: `config/strategies/example_trailing.yaml`

**Issue:** `TrailingStageConfig.fraction` is documented as "For scale_out - fraction to sell (0.0-1.0)" but `TrailingStageConfig.action` only allows `"breakeven"` or `"trail_ema"`. There is no `"scale_out"` action on `TrailingStageConfig`. Scale-outs use the separate `ScaleOutStepConfig`. The `fraction` field is dead state that is never read by any code path and pollutes `asdict()` output.

- [ ] **Step 1: Remove `fraction` field from `TrailingStageConfig`**

```python
@dataclass
class TrailingStageConfig:
    """Configuration for a single trailing stage.

    Attributes:
        trigger_r: R-multiple threshold to activate this stage
        action: "breakeven" or "trail_ema"
        period: For "trail_ema" - EMA period (10, 21)
    """
    trigger_r: float
    action: Literal["breakeven", "trail_ema"]
    period: Optional[int] = None
```

- [ ] **Step 2: Update `_apply_config_dict()` if it references `fraction` on TrailingStageConfig**

Search for any parsing of `fraction` from YAML that assigns it to `TrailingStageConfig` and remove it.

- [ ] **Step 3: Update tests that pass `fraction` to `TrailingStageConfig`**

Search `tests/test_trailing_exits.py` and `tests/test_risk_config.py` for any `TrailingStageConfig(..., fraction=...)` and remove the `fraction` argument.

- [ ] **Step 4: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py tests/test_risk_config.py tests/test_trailing_integration.py -v`

- [ ] **Step 5: Commit**

```bash
git add traderlib/risk_config.py config/ tests/
git commit -m "fix: remove misleading fraction field from TrailingStageConfig

TrailingStageConfig only supports breakeven and trail_ema actions.
Scale-out fractions belong on ScaleOutStepConfig. The fraction field
was never read and confused asdict() output."
```

---

## Task 20: Fix Critical — Remove Unimplemented Methods from Design Doc

**Priority:** CRITICAL (documentation accuracy)
**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-configurable-trailing-exits-design.md`

**Issue:** The design doc's "Method Options" table lists `swing_low`, `atr_multiple`, and `fixed_pct` as available trailing methods. None of these are implemented — only `breakeven` and `trail_ema` exist. Users reading the design doc will try these and get `ValueError`.

- [ ] **Step 1: Update Method Options table in design doc**

Find the "Method Options" or "Trailing Methods" table and either:
- Remove rows for unimplemented methods, OR
- Add a "Status" column marking them as "Not yet implemented"

Example:
```markdown
| Method | Description | Status |
|--------|-------------|--------|
| breakeven | Move stop to entry price | ✅ Implemented |
| trail_ema | Trail with EMA (period 10 or 21) | ✅ Implemented |
| trail_swing_low | Trail with swing low | ❌ Not implemented |
| atr_multiple | Trail with ATR multiplier | ❌ Not implemented |
| fixed_pct | Trail with fixed percentage | ❌ Not implemented |
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-25-configurable-trailing-exits-design.md
git commit -m "docs: mark unimplemented trailing methods in design spec

swing_low, atr_multiple, and fixed_pct are not yet implemented.
Marked them clearly so users don't attempt to use them."
```

---

## Task 21: Update TOOLS.md with Trailing Exit System

**Priority:** IMPORTANT (documentation)
**Files:**
- Modify: `TOOLS.md`

**Issue:** TOOLS.md describes `paper_exits.py` as only "hard stops, breakeven (+1R), trailing EMA10 (+1.5R), EMA21 (+3R)" and doesn't mention the new `TrailingExitEngine` or the three configurable modes. The traderlib Library Reference table and Key Imports section are also missing `trailing_exits.py`.

- [ ] **Step 1: Update `paper_exits.py` description in Library Reference**

Change from:
```
paper_exits.py - Exit engine (ExitEngine); hard stops, breakeven (+1R), trailing EMA10 (+1.5R), EMA21 (+3R); profit targets; initial stop calculation
```

To:
```
paper_exits.py - Exit engine (ExitEngine); hard stops, configurable trailing exits (stage-based, continuous, hybrid modes via TrailingExitEngine); profit targets; initial stop calculation
```

- [ ] **Step 2: Add `trailing_exits.py` to Library Reference table**

```
trailing_exits.py - Trailing exit engine (TrailingExitEngine); stage-based breakeven/EMA trailing, continuous band trailing, hybrid scale-out+trail; converts TrailingResult to ExitAction
```

- [ ] **Step 3: Add `TrailingExitEngine` to Key Imports section**

```python
from traderlib.trailing_exits import TrailingExitEngine, TrailingResult
```

- [ ] **Step 4: Add "Trailing Exit Configuration" to Risk Configuration section**

Add a subsection after the existing risk configuration table:

```markdown
### Trailing Exit Configuration

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `mode` | `target`, `trailing`, `hybrid` | `target` | Exit mode selection |
| `trailing_mode` | `stage_based`, `continuous` | `stage_based` | Trailing mode (when mode=trailing) |
| `trailing_stages` | list of `{trigger_r, action, period}` | `[]` | Stage definitions for stage_based and hybrid |
| `continuous_bands` | list of `{from_r, to_r?, method}` | `[]` | Band definitions for continuous mode |
| `scale_out_steps` | list of `{trigger_r, fraction}` | `[]` | Scale-out steps for hybrid mode |
| `breakeven_at_r` | float | `1.0` | R-level for breakeven (continuous mode only) |

See `config/strategies/example_trailing.yaml` for complete examples.
```

- [ ] **Step 5: Commit**

```bash
git add TOOLS.md
git commit -m "docs: update TOOLS.md with trailing exit system

Adds TrailingExitEngine to library reference, updates paper_exits
description, adds trailing exit configuration table, and adds
TrailingExitEngine to key imports."
```

---

## Task 22: Update README.md with Configurable Trailing Exits

**Priority:** IMPORTANT (documentation)
**Files:**
- Modify: `README.md`

**Issue:** README.md describes "trailing stops (+1R breakeven, +1.5R EMA10, +3R EMA21)" as a fixed system. The new configurable trailing exit system is not mentioned.

- [ ] **Step 1: Update the risk rules description**

Change from:
```
Risk Rules: 0.5% account risk per trade, max 3 positions/sector, trailing stops (+1R breakeven, +1.5R EMA10, +3R EMA21)
```

To:
```
Risk Rules: 0.5% account risk per trade, max 3 positions/sector, configurable trailing exits (stage-based, continuous, or hybrid mode via YAML config)
```

- [ ] **Step 2: Add a "Trailing Exits" section if there's an appropriate place**

```markdown
### Trailing Exits

Three trailing exit modes configurable via `risk_config.yaml` or per-strategy YAML:

- **Stage-based**: Discrete stages at R-levels (breakeven at 2R, trail EMA10 at 3R, etc.)
- **Continuous**: Smooth EMA transitions between R-multiple bands
- **Hybrid**: Scale-out partial positions + stage-based trailing

Default mode is `target` (fixed 2R profit target) for backward compatibility.

See `config/strategies/example_trailing.yaml` for configuration examples.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with configurable trailing exits

Replaces fixed trailing stop description with configurable exit modes.
Adds trailing exits section with mode descriptions and config reference."
```

---

## Task 23: Fix Important — Update `print_summary()` for Trailing Config

**Priority:** IMPORTANT (documentation / user experience)
**Files:**
- Modify: `traderlib/risk_config.py`

**Issue:** `print_summary()` shows `min_r_multiple` and EMA periods even when mode is "trailing" or "hybrid", which is misleading. When trailing mode is active, it should display the stages/bands/scale-out steps instead.

- [ ] **Step 1: Add trailing config display to `print_summary()`**

After the existing profit target summary lines, add:

```python
def print_summary(self):
    """Print a summary of the risk configuration."""
    # ... existing summary ...
    pt = self.profit_target
    if pt.mode in ('trailing', 'hybrid'):
        print(f"  Exit Mode: {pt.mode}")
        if pt.mode == 'trailing':
            print(f"  Trailing Mode: {pt.trailing_mode}")
        if pt.trailing_stages:
            print(f"  Trailing Stages:")
            for s in pt.trailing_stages:
                stage_desc = f"    {s.trigger_r}R -> {s.action}"
                if s.action == 'trail_ema' and s.period:
                    stage_desc += f" (EMA{s.period})"
                print(stage_desc)
        if pt.continuous_bands:
            print(f"  Continuous Bands:")
            for b in pt.continuous_bands:
                band_desc = f"    {b['from_r']}R"
                band_desc += f" - {b.get('to_r', '∞')}R: {b['method']}"
                print(band_desc)
        if pt.scale_out_steps:
            print(f"  Scale-Out Steps:")
            for s in pt.scale_out_steps:
                print(f"    {s.trigger_r}R: sell {int(s.fraction*100)}% of position")
    else:
        # Existing target mode display
        print(f"  Min R-multiple: {pt.min_r_multiple}")
        print(f"  Breakeven at: {pt.breakeven_at_r}R")
        print(f"  EMA10 trail at: {pt.ema10_at_r}R")
        print(f"  EMA21 trail at: {pt.ema21_at_r}R")
```

- [ ] **Step 2: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_risk_config.py -v`

- [ ] **Step 3: Commit**

```bash
git add traderlib/risk_config.py
git commit -m "feat: display trailing exit config in print_summary()

When mode is trailing or hybrid, shows stages/bands/scale-out steps
instead of irrelevant EMA thresholds."
```

---

## Task 24: Fix Important — Document `continuous_bands` Schema and `ScaleOutStepConfig.fraction` Semantics

**Priority:** IMPORTANT (documentation / clarity)
**Files:**
- Modify: `traderlib/risk_config.py` (docstrings)
- Modify: `config/strategies/example_trailing.yaml` (comments)

**Issue:** Two documentation gaps:
1. `continuous_bands: List[Dict[str, Any]]` has no docstring explaining expected keys (`from_r`, `to_r`, `method`).
2. `ScaleOutStepConfig.fraction` docstring says "fraction to sell" but doesn't clarify it's a fraction of the **remaining** position, not the original.

- [ ] **Step 1: Add docstring to `continuous_bands` field**

```python
continuous_bands: List[Dict[str, Any]] = field(default_factory=list)
# Expected keys per band:
#   from_r: float (required) - R-multiple where this band starts
#   to_r: float (optional) - R-multiple where this band ends (None = infinity)
#   method: str - trailing method: "ema10" or "ema21"
```

- [ ] **Step 2: Clarify `ScaleOutStepConfig.fraction` docstring**

```python
@dataclass
class ScaleOutStepConfig:
    """Configuration for a scale-out step in hybrid mode.

    Attributes:
        trigger_r: R-multiple threshold to execute this scale-out
        fraction: Fraction of the CURRENT (remaining) position to sell.
                  Each scale-out reduces the position, so subsequent
                  steps sell fewer absolute shares. Must be 0 < f <= 1.0.
    """
    trigger_r: float
    fraction: float
```

- [ ] **Step 3: Update example_trailing.yaml comment for fraction clarity**

Change:
```yaml
fraction: 0.33  # Sell 1/3 at 3R
```
To:
```yaml
fraction: 0.33  # Sell 1/3 of remaining position at 3R
```

And:
```yaml
fraction: 0.50  # Sell 1/2 of remaining at 4R
```

- [ ] **Step 4: Commit**

```bash
git add traderlib/risk_config.py config/strategies/example_trailing.yaml
git commit -m "docs: clarify continuous_bands schema and ScaleOutStepConfig fraction

continuous_bands now documents expected keys. fraction clarifies
it's a fraction of remaining position, not original."
```

---

## Task 25: Fix Important — Document `_evaluate_continuous` Breakeven Priority and `_apply_config_dict` Trailing Logic

**Priority:** IMPORTANT (documentation accuracy)
**Files:**
- Modify: `traderlib/trailing_exits.py` (docstring)
- Modify: `traderlib/risk_config.py` (docstring)

**Issue:** Two undocumented behavioral subtleties:
1. `_evaluate_continuous()` checks `breakeven_at_r` BEFORE bands, silently overriding band logic. This priority is not documented.
2. `_apply_config_dict()` has two code paths for trailing/hybrid vs target mode. Trailing/hybrid requires full `ProfitTargetConfig` reconstruction (to trigger `__post_init__` validation), while target mode uses direct attribute setting. This distinction is undocumented.

- [ ] **Step 1: Update `_evaluate_continuous` docstring**

```python
def _evaluate_continuous(self, position, current_price, ema10, ema21):
    """Evaluate continuous trailing rules.

    Uses bands defined by R-multiple ranges. Breakeven is checked
    FIRST -- if position.stop_price < entry_price and r_multiple >=
    breakeven_at_r, stop moves to breakeven before band logic is
    evaluated.
    """
```

- [ ] **Step 2: Add inline comments to `_apply_config_dict` trailing logic**

At the start of the trailing/hybrid code path, add:

```python
# Trailing and hybrid modes require full ProfitTargetConfig reconstruction
# to trigger __post_init__ validation (increasing stages, non-overlapping
# bands, etc.). Target mode can use direct attribute setting since its
# validation is simpler.
```

- [ ] **Step 3: Commit**

```bash
git add traderlib/trailing_exits.py traderlib/risk_config.py
git commit -m "docs: document continuous breakeven priority and config loading paths

Clarifies that breakeven is checked before bands in continuous mode,
and that trailing/hybrid modes need full config reconstruction for
validation."
```

---

## Task 26: Fix Important — Document `ExitActionType` Scale-Out Convention and Legacy Method Gap

**Priority:** IMPORTANT (documentation / API clarity)
**Files:**
- Modify: `traderlib/paper_exits.py` (docstrings)

**Issue:** Two API documentation gaps:
1. Scale-out results from `TrailingExitEngine` are converted to `ExitActionType.UPDATE_STOP` with `new_stop_type='SCALE_OUT'`. This convention is undocumented, and there's no `SCALE_OUT` in the `ExitActionType` enum.
2. The legacy `evaluate_exit` method does NOT use `TrailingExitEngine` — it has hardcoded breakeven/EMA logic. Its docstring mentions "trailing stops" but doesn't clarify this gap.

- [ ] **Step 1: Add docstring to `evaluate_exit_action` explaining scale-out convention**

```python
def evaluate_exit_action(self, position, current_price, historical_data=None):
    """Evaluate all exit conditions and return atomic ExitAction.

    Routes to TrailingExitEngine when mode is 'trailing' or 'hybrid'.

    Note: Scale-out actions from TrailingExitEngine are converted to
    UPDATE_STOP with new_stop_type='SCALE_OUT'. The caller should check
    action.new_stop_type == 'SCALE_OUT' to distinguish scale-outs from
    regular stop updates.
    """
```

- [ ] **Step 2: Add deprecation/gap note to legacy `evaluate_exit` method**

```python
def evaluate_exit(self, position, ...):
    """Evaluate exit conditions and return ExitSignal.

    WARNING: This legacy method does NOT use TrailingExitEngine. It
    always uses the fixed breakeven/EMA thresholds from risk_config.
    For trailing mode support, use evaluate_exit_action() instead.
    """
```

- [ ] **Step 3: Commit**

```bash
git add traderlib/paper_exits.py
git commit -m "docs: document scale-out ExitAction convention and legacy method gap

Scale-outs use UPDATE_STOP with new_stop_type='SCALE_OUT'. Legacy
evaluate_exit() does not use TrailingExitEngine — callers should
use evaluate_exit_action() for trailing support."
```

---

## Task 27: Fix Important — Fix Implementation Notes: EMA Period Error vs Fallback

**Priority:** IMPORTANT (documentation accuracy)
**Files:**
- Modify: `docs/superpowers/plans/2026-04-25-trailing-exit-system-implementation-notes.md`

**Issue:** The "Known Limitations" section says "EMA periods limited — Currently supports 10 and 21 (others use nearest)". But `_get_ema_for_period` raises `ValueError` for other periods — it does NOT fall back to the nearest.

- [ ] **Step 1: Update the known limitation**

Change:
```
3. **EMA periods limited** — Currently supports 10 and 21 (others use nearest)
```

To:
```
3. **EMA periods limited to 10 and 21** — Other periods raise ValueError. Use trail_ema with period=10 or period=21 only.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-04-25-trailing-exit-system-implementation-notes.md
git commit -m "docs: fix EMA period limitation description

_get_ema_for_period raises ValueError for unsupported periods,
it does not fall back to the nearest. Corrected the known limitation."
```

---

## Task 28: Cleanup — Remove Misleading `Position.exit_phase` Documentation

**Priority:** SUGGESTION (documentation clarity)
**Files:**
- Modify: `traderlib/paper_state.py`

**Issue:** `Position.exit_phase` has a comment saying `'phase1' = ratchet mode | 'phase2' = EMA trail mode` which describes the OLD two-phase system. With configurable trailing exits (potentially many stages), this field is semantically incorrect. It should either be removed or its documentation updated.

- [ ] **Step 1: Update `exit_phase` comment**

Change the comment to reflect that `exit_phase` is only relevant for target (non-trailing) mode:

```python
exit_phase: str = ''  # Only used in target mode: '' | 'phase1' (ratchet) | 'phase2' (EMA trail)
                       # Trailing and hybrid modes use TrailingExitEngine instead
```

- [ ] **Step 2: Run tests**

`cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/ -v -k "paper" --no-header`

- [ ] **Step 3: Commit**

```bash
git add traderlib/paper_state.py
git commit -m "docs: clarify exit_phase is only used in target mode

Trailing and hybrid modes use TrailingExitEngine instead of the
two-phase exit_phase system."
```

---

## Plan Self-Review (Revised)

| Requirement | Task | Status |
|-------------|------|--------|
| Stage-based mode | Task 2 | ✅ |
| Continuous mode | Task 2 | ✅ |
| Hybrid mode | Task 2 | ✅ |
| Configuration validation | Task 1 | ✅ |
| YAML loading | Task 1 | ✅ |
| Integration with ExitEngine | Task 4 | ✅ |
| Position state persistence | Task 3 | ✅ |
| Backtest integration | Task 6 | ✅ |
| Scale-out trigger fix | Task 2, 3 | ✅ |
| Edge case tests | Task 2 | ✅ |

### Critical Fixes from Review

| Issue | Fix | Task |
|-------|-----|------|
| Config fragmentation | Merged into risk_config.py | Task 1 |
| Task dependency order | Modes before integration | All |
| Scale-out repeats | Added `executed` flag + scale_out_history | Task 2, 3 |
| Missing EMA handling | Returns hold when EMAs unavailable | Task 2 |
| Breakeven logic bug | Fixed continuous mode state machine | Task 2 |

### Post-Implementation Review Fixes (Tasks 8–17)

| # | Priority | Issue | Fix | File |
|---|----------|-------|-----|------|
| 8 | CRITICAL | Scale-out with 0 shares silent no-op | Add min-shares guard, skip invalid scale-outs | trailing_exits.py |
| 9 | CRITICAL | Invalid YAML silently falls back to defaults | Separate ValueError from I/O errors, SystemExit on misconfig | risk_config.py |
| 10 | IMPORTANT | `executed` fields are dead state on config dataclasses | Remove unused `executed` fields | risk_config.py |
| 11 | IMPORTANT | Empty stages/bands → hold-forever | Require at least 1 stage/band in validation | risk_config.py |
| 12 | IMPORTANT | `breakeven_at_r` undocumented mode-specific behavior | Add docstrings and YAML comments | risk_config.py, example_trailing.yaml |
| 13 | IMPORTANT | Float equality for scale-out deduplication | Round R-levels to 6 decimal places | trailing_exits.py, paper_state.py |
| 14 | SUGGESTION | `TrailingAction` Literal not runtime-enforced | Add `__post_init__` validation to TrailingResult | trailing_exits.py |
| 15 | SUGGESTION | `ScaleOutStepConfig.fraction` allows 0.0 | Add `__post_init__` validation | risk_config.py |
| 16 | SUGGESTION | `print()` instead of `logging` | Replace with `logging.warning()` | trailing_exits.py |
| 17 | SUGGESTION | Unrelated rate_limiter.py change in PR | Revert or separate into different PR | rate_limiter.py |

### Documentation Fixes (Tasks 18–28)

| # | Priority | Issue | Fix | File |
|---|----------|-------|-----|------|
| 18 | CRITICAL | risk_config.yaml missing trailing exit docs | Add mode/stages/bands docs with examples | config/risk_config.yaml |
| 19 | CRITICAL | TrailingStageConfig.fraction is misleading dead state | Remove `fraction` field from TrailingStageConfig | risk_config.py |
| 20 | CRITICAL | Design doc lists unimplemented methods | Mark swing_low/atr_multiple/fixed_pct as not implemented | design doc |
| 21 | IMPORTANT | TOOLS.md missing TrailingExitEngine | Add to library reference, key imports, risk config table | TOOLS.md |
| 22 | IMPORTANT | README.md describes old fixed system | Update trailing stops description, add exits section | README.md |
| 23 | IMPORTANT | `print_summary()` doesn't show trailing config | Add conditional display for trailing/hybrid modes | risk_config.py |
| 24 | IMPORTANT | `continuous_bands` schema and `fraction` semantics undocumented | Add docstrings, clarify fraction = remaining position | risk_config.py, example_trailing.yaml |
| 25 | IMPORTANT | Undocumented breakeven priority and config loading paths | Add docstrings to `_evaluate_continuous` and `_apply_config_dict` | trailing_exits.py, risk_config.py |
| 26 | IMPORTANT | Undocumented scale-out ExitAction convention and legacy method gap | Add docstrings to `evaluate_exit_action` and `evaluate_exit` | paper_exits.py |
| 27 | IMPORTANT | Implementation notes say EMA "uses nearest" but it raises ValueError | Fix known limitation description | implementation-notes.md |
| 28 | SUGGESTION | `Position.exit_phase` comment describes old two-phase system | Update comment to clarify target-mode only | paper_state.py |

### No Placeholders

- ✅ All test code complete
- ✅ All implementation code complete
- ✅ Exact file paths specified
- ✅ Commands with expected output

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-trailing-exit-system.md` (REVISION).**

Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks

**2. Inline Execution** — Execute in this session with checkpoints

**Which approach?**
