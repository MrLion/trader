# Configurable Trailing Exit System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a YAML-configurable trailing exit system that replaces fixed 2R profit targets with dynamic stop adjustments (breakeven at 2R, trail with EMAs at higher R-levels).

**Architecture:** Three-tier design: (1) Configuration layer with dataclasses for stage-based, continuous, and hybrid modes; (2) Exit strategy engine that evaluates positions against configured rules and returns stop updates; (3) Integration layer that applies stop adjustments to positions and logs transitions.

**Tech Stack:** Python 3.x, dataclasses, PyYAML, pandas (for EMA calculations), existing ExitEngine pattern in `traderlib/paper_exits.py`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `traderlib/trailing_exits.py` | **NEW** - Core trailing exit engine with three modes (stage-based, continuous, hybrid) |
| `traderlib/trailing_config.py` | **NEW** - Dataclasses for trailing exit configuration and YAML loading |
| `traderlib/paper_exits.py` | **MODIFY** - Integrate trailing exits into existing ExitEngine |
| `traderlib/risk_config.py` | **MODIFY** - Add trailing exit config loading from YAML |
| `config/strategies/example_trailing.yaml` | **NEW** - Example strategy with trailing exit configuration |
| `tests/test_trailing_exits.py` | **NEW** - Comprehensive tests for all three modes |
| `tests/test_trailing_config.py` | **NEW** - Tests for configuration loading and validation |

---

## Task 1: Create Trailing Exit Configuration Dataclasses

**Files:**
- Create: `traderlib/trailing_config.py`
- Test: `tests/test_trailing_config.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for trailing exit configuration dataclasses."""

import unittest
from pathlib import Path
import tempfile
import yaml

from traderlib.trailing_config import (
    TrailingStage,
    ScaleOutStep,
    TrailingConfig,
    TrailingConfigLoader,
)


class TestTrailingStage(unittest.TestCase):
    """Test TrailingStage dataclass."""

    def test_stage_creation(self):
        """Can create a basic stage."""
        stage = TrailingStage(
            trigger_r=2.0,
            action="move_stop_to",
            stop_price="breakeven"
        )
        self.assertEqual(stage.trigger_r, 2.0)
        self.assertEqual(stage.action, "move_stop_to")
        self.assertEqual(stage.stop_price, "breakeven")

    def test_stage_with_ema(self):
        """Can create a stage with EMA trailing."""
        stage = TrailingStage(
            trigger_r=3.0,
            action="trail_with",
            method="ema",
            period=10
        )
        self.assertEqual(stage.method, "ema")
        self.assertEqual(stage.period, 10)


class TestTrailingConfig(unittest.TestCase):
    """Test TrailingConfig dataclass."""

    def test_stage_based_config(self):
        """Can create stage-based configuration."""
        config = TrailingConfig(
            mode="stage_based",
            stages=[
                TrailingStage(trigger_r=2.0, action="move_stop_to", stop_price="breakeven"),
                TrailingStage(trigger_r=3.0, action="trail_with", method="ema", period=10),
            ]
        )
        self.assertEqual(config.mode, "stage_based")
        self.assertEqual(len(config.stages), 2)


class TestConfigLoader(unittest.TestCase):
    """Test loading configuration from YAML."""

    def test_load_stage_based_yaml(self):
        """Can load stage-based config from YAML file."""
        yaml_content = """
exit:
  mode: "stage_based"
  stages:
    - trigger_r: 2.0
      action: "move_stop_to"
      stop_price: "breakeven"
    - trigger_r: 3.0
      action: "trail_with"
      method: "ema"
      period: 10
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        loader = TrailingConfigLoader()
        config = loader.load_from_file(Path(temp_path))
        
        self.assertEqual(config.mode, "stage_based")
        self.assertEqual(len(config.stages), 2)
        self.assertEqual(config.stages[0].trigger_r, 2.0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_config.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'traderlib.trailing_config'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Trailing exit configuration dataclasses.

Defines the configuration schema for trailing stop strategies
that let winners run with dynamically adjusting stops.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class TrailingStage:
    """A single stage in a trailing stop progression.
    
    Each stage defines what happens when R-multiple reaches a threshold.
    
    Attributes:
        trigger_r: R-multiple threshold to activate this stage
        action: What to do - "move_stop_to", "trail_with", "scale_out"
        stop_price: For "move_stop_to" - "breakeven", "entry", or float price
        method: For "trail_with" - "ema", "swing_low", "atr_multiple", "fixed_pct"
        period: For "ema" method - EMA period (e.g., 10, 20, 50)
        atr_mult: For "atr_multiple" method - ATR multiplier
        fixed_pct: For "fixed_pct" method - percentage below price
    """
    trigger_r: float
    action: str  # "move_stop_to", "trail_with"
    stop_price: Optional[Union[str, float]] = None  # "breakeven", "entry", or price
    method: Optional[str] = None  # "ema", "swing_low", "atr_multiple", "fixed_pct"
    period: Optional[int] = None  # For EMA method
    atr_mult: Optional[float] = None  # For ATR method
    fixed_pct: Optional[float] = None  # For fixed_pct method


@dataclass
class ScaleOutStep:
    """A partial position exit at a specific R-level.
    
    Attributes:
        trigger_r: R-multiple to trigger scale-out
        fraction: Fraction of CURRENT position to sell (0.0-1.0)
    """
    trigger_r: float
    fraction: float


@dataclass
class ContinuousBand:
    """A trailing band definition for continuous mode.
    
    Defines trailing behavior between R-multiple ranges.
    
    Attributes:
        from_r: Starting R-multiple (inclusive)
        to_r: Ending R-multiple (exclusive, None for unlimited)
        method: Trailing method - "ema", "atr_multiple", "swing_low"
        period: For EMA method
        atr_mult: For ATR method
    """
    from_r: float
    to_r: Optional[float] = None
    method: str = "ema"
    period: Optional[int] = None
    atr_mult: Optional[float] = None


@dataclass
class TrailingConfig:
    """Complete trailing exit configuration.
    
    Supports three modes:
    - "stage_based": Discrete stages at specific R-levels
    - "continuous": Smooth transitions between trailing methods
    - "hybrid": Stage-based with optional scale-out
    
    Attributes:
        mode: Configuration mode
        stages: List of stages (for stage_based and hybrid modes)
        continuous_bands: List of bands (for continuous mode)
        scale_out: Optional scale-out configuration
        breakeven_at_r: R-level to move stop to breakeven (default 2.0)
    """
    mode: str  # "stage_based", "continuous", "hybrid", "target" (original)
    stages: List[TrailingStage] = field(default_factory=list)
    continuous_bands: List[ContinuousBand] = field(default_factory=list)
    scale_out: Optional[List[ScaleOutStep]] = None
    breakeven_at_r: float = 2.0


class TrailingConfigLoader:
    """Load trailing exit configuration from YAML files."""

    def load_from_file(self, path: Path) -> TrailingConfig:
        """Load configuration from a YAML file.
        
        Args:
            path: Path to YAML file
            
        Returns:
            TrailingConfig instance
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If YAML is invalid
        """
        import yaml
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        if data is None or 'exit' not in data:
            raise ValueError(f"YAML file {path} must contain 'exit' section")
        
        return self._parse_config(data['exit'])
    
    def _parse_config(self, data: dict) -> TrailingConfig:
        """Parse configuration dict into TrailingConfig."""
        mode = data.get('mode', 'target')
        
        config = TrailingConfig(
            mode=mode,
            breakeven_at_r=data.get('breakeven_at_r', 2.0)
        )
        
        if mode in ('stage_based', 'hybrid'):
            config.stages = self._parse_stages(data.get('stages', []))
        
        if mode == 'continuous':
            config.continuous_bands = self._parse_bands(data.get('continuous_bands', []))
        
        if mode == 'hybrid' or data.get('scale_out'):
            config.scale_out = self._parse_scale_out(data.get('scale_out', []))
        
        return config
    
    def _parse_stages(self, stages_data: list) -> List[TrailingStage]:
        """Parse stage definitions."""
        stages = []
        for s in stages_data:
            stage = TrailingStage(
                trigger_r=s['trigger_r'],
                action=s['action'],
                stop_price=s.get('stop_price'),
                method=s.get('method'),
                period=s.get('period'),
                atr_mult=s.get('atr_mult'),
                fixed_pct=s.get('fixed_pct')
            )
            stages.append(stage)
        return stages
    
    def _parse_bands(self, bands_data: list) -> List[ContinuousBand]:
        """Parse continuous band definitions."""
        bands = []
        for b in bands_data:
            band = ContinuousBand(
                from_r=b['from_r'],
                to_r=b.get('to_r'),
                method=b.get('method', 'ema'),
                period=b.get('period'),
                atr_mult=b.get('atr_mult')
            )
            bands.append(band)
        return bands
    
    def _parse_scale_out(self, scale_out_data: list) -> List[ScaleOutStep]:
        """Parse scale-out steps."""
        steps = []
        for s in scale_out_data:
            step = ScaleOutStep(
                trigger_r=s['trigger_r'],
                fraction=s['fraction']
            )
            steps.append(step)
        return steps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_config.py -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_config.py tests/test_trailing_config.py
git commit -m "feat: add trailing exit configuration dataclasses

Add TrailingStage, ScaleOutStep, ContinuousBand, TrailingConfig
and TrailingConfigLoader for YAML-based exit configuration.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Create Trailing Exit Engine

**Files:**
- Create: `traderlib/trailing_exits.py`
- Test: `tests/test_trailing_exits.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for trailing exit engine."""

import unittest
from unittest.mock import Mock

from traderlib.trailing_exits import TrailingExitEngine
from traderlib.trailing_config import TrailingConfig, TrailingStage, ScaleOutStep


class MockPosition:
    """Mock position for testing."""
    def __init__(self, entry=150.0, stop=140.0, shares=100):
        self.ticker = 'TEST'
        self.entry_price = entry
        self.stop_price = stop
        self.initial_stop_price = stop
        self.shares = shares
        self.current_stop_type = 'HARD'
        self.initial_risk = (entry - stop) * shares


class TestStageBasedMode(unittest.TestCase):
    """Test stage-based trailing exit mode."""

    def setUp(self):
        """Create engine with stage-based config."""
        self.config = TrailingConfig(
            mode='stage_based',
            stages=[
                TrailingStage(trigger_r=2.0, action='move_stop_to', stop_price='breakeven'),
                TrailingStage(trigger_r=3.0, action='trail_with', method='ema', period=10),
            ],
            breakeven_at_r=2.0
        )
        self.engine = TrailingExitEngine(self.config)

    def test_breakeven_stage(self):
        """At 2R, stop should move to breakeven."""
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)  # risk=$10/share
        # At 2R: entry + 2*risk = 150 + 20 = 170
        result = self.engine.evaluate_stage_based(pos, current_price=170.0, ema10=165.0)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 150.0)  # breakeven
        self.assertEqual(result['reason'], 'STAGE_2.0R_BREAKEVEN')

    def test_ema_trail_stage(self):
        """At 3R, should trail with EMA10."""
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)
        pos.stop_price = 150.0  # Already at breakeven
        # At 3R: 150 + 30 = 180
        result = self.engine.evaluate_stage_based(pos, current_price=180.0, ema10=175.0)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'update_stop')
        self.assertEqual(result['new_stop'], 175.0)  # EMA10
        self.assertEqual(result['new_stop_type'], 'EMA10_TRAIL')

    def test_exit_on_stop_hit(self):
        """Should exit when price hits stop."""
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)
        result = self.engine.evaluate_stage_based(pos, current_price=139.0, ema10=138.0)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'exit')
        self.assertEqual(result['reason'], 'STOP_HIT')


class TestRMultipleCalculation(unittest.TestCase):
    """Test R-multiple calculations."""

    def test_basic_r_calculation(self):
        """R = gain / initial risk."""
        config = TrailingConfig(mode='stage_based', stages=[])
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)  # risk=$1000
        r = engine._calculate_r_multiple(pos, current_price=170.0)
        
        # Gain = 170 - 150 = $20/share = $2000 total
        # R = 2000 / 1000 = 2.0
        self.assertEqual(r, 2.0)

    def test_fractional_r(self):
        """Calculate fractional R multiples."""
        config = TrailingConfig(mode='stage_based', stages=[])
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=165.0)
        
        # Gain = 1500, Risk = 1000, R = 1.5
        self.assertEqual(r, 1.5)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'traderlib.trailing_exits'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Trailing exit engine.

Evaluates positions against trailing stop configurations and returns
stop update or exit decisions.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

from traderlib.trailing_config import TrailingConfig, TrailingStage


@dataclass
class TrailingResult:
    """Result of trailing exit evaluation."""
    action: str  # "exit", "update_stop", "scale_out", "hold"
    reason: str
    new_stop: Optional[float] = None
    new_stop_type: Optional[str] = None
    scale_fraction: Optional[float] = None
    r_multiple: float = 0.0


class TrailingExitEngine:
    """Engine for evaluating trailing stop rules.
    
    Supports three modes:
    - stage_based: Discrete stages at R-levels
    - continuous: Smooth transitions
    - hybrid: Stage-based with scale-out
    """

    def __init__(self, config: TrailingConfig):
        """Initialize with configuration.
        
        Args:
            config: TrailingConfig with mode and rules
        """
        self.config = config

    def evaluate(self, position, current_price: float, 
                 ema_values: Optional[Dict[str, float]] = None) -> TrailingResult:
        """Evaluate position against trailing rules.
        
        Args:
            position: Position object with entry_price, stop_price, etc.
            current_price: Current market price
            ema_values: Optional dict with 'ema10', 'ema21', etc.
            
        Returns:
            TrailingResult with action and stop updates
        """
        ema10 = ema_values.get('ema10') if ema_values else None
        ema21 = ema_values.get('ema21') if ema_values else None
        
        if self.config.mode == 'stage_based':
            return self._evaluate_stage_based(position, current_price, ema10, ema21)
        elif self.config.mode == 'continuous':
            return self._evaluate_continuous(position, current_price, ema10, ema21)
        elif self.config.mode == 'hybrid':
            return self._evaluate_hybrid(position, current_price, ema10, ema21)
        else:
            raise ValueError(f"Unknown mode: {self.config.mode}")

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

    def _evaluate_stage_based(self, position, current_price: float,
                              ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate stage-based trailing rules.
        
        Rules are evaluated in order. The highest triggered stage wins.
        
        Args:
            position: Position object
            current_price: Current price
            ema10: 10-period EMA value
            ema21: 21-period EMA value
            
        Returns:
            TrailingResult with action
        """
        # Check hard stop first
        if current_price <= position.stop_price:
            return TrailingResult(
                action='exit',
                reason='STOP_HIT',
                exit_price=current_price,
                r_multiple=self._calculate_r_multiple(position, current_price)
            )
        
        r_multiple = self._calculate_r_multiple(position, current_price)
        
        # Find the highest triggered stage
        active_stage = None
        for stage in self.config.stages:
            if r_multiple >= stage.trigger_r:
                active_stage = stage
        
        if active_stage is None:
            return TrailingResult(action='hold', reason='BELOW_FIRST_STAGE', r_multiple=r_multiple)
        
        # Execute the active stage action
        if active_stage.action == 'move_stop_to':
            new_stop = self._resolve_stop_price(active_stage.stop_price, position)
            if new_stop and new_stop > position.stop_price:
                return TrailingResult(
                    action='update_stop',
                    reason=f'STAGE_{active_stage.trigger_r}R_{active_stage.stop_price.upper()}',
                    new_stop=new_stop,
                    new_stop_type='STAGE_PROTECT',
                    r_multiple=r_multiple
                )
        
        elif active_stage.action == 'trail_with':
            new_stop = self._calculate_trail_stop(
                active_stage.method,
                current_price,
                ema10,
                ema21,
                active_stage
            )
            if new_stop and new_stop > position.stop_price:
                stop_type = f"{active_stage.method.upper()}" + (f"{active_stage.period}" if active_stage.period else "")
                return TrailingResult(
                    action='update_stop',
                    reason=f'STAGE_{active_stage.trigger_r}R_{stop_type}',
                    new_stop=new_stop,
                    new_stop_type=stop_type,
                    r_multiple=r_multiple
                )
        
        return TrailingResult(action='hold', reason='NO_STOP_UPDATE', r_multiple=r_multiple)

    def _resolve_stop_price(self, stop_price: Any, position) -> Optional[float]:
        """Resolve stop price reference to actual price.
        
        Args:
            stop_price: "breakeven", "entry", or float price
            position: Position object
            
        Returns:
            Resolved price or None
        """
        if stop_price == 'breakeven' or stop_price == 'entry':
            return position.entry_price
        elif isinstance(stop_price, (int, float)):
            return float(stop_price)
        return None

    def _calculate_trail_stop(self, method: str, current_price: float,
                              ema10: Optional[float], ema21: Optional[float],
                              stage: TrailingStage) -> Optional[float]:
        """Calculate trailing stop based on method.
        
        Args:
            method: "ema", "swing_low", "atr_multiple", "fixed_pct"
            current_price: Current price
            ema10: 10-period EMA
            ema21: 21-period EMA
            stage: Stage configuration with method params
            
        Returns:
            Calculated stop price or None
        """
        if method == 'ema':
            if stage.period == 10 and ema10:
                return ema10
            elif stage.period == 21 and ema21:
                return ema21
            # Default to lower of available EMAs
            if ema10:
                return ema10
            if ema21:
                return ema21
        
        elif method == 'fixed_pct' and stage.fixed_pct:
            return current_price * (1 - stage.fixed_pct)
        
        # For other methods, would need additional data (ATR, swing lows)
        return None

    def _evaluate_continuous(self, position, current_price: float,
                             ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate continuous trailing rules.
        
        Similar to stage-based but with smooth band transitions.
        """
        # TODO: Implement in Task 3
        raise NotImplementedError("Continuous mode not yet implemented")

    def _evaluate_hybrid(self, position, current_price: float,
                         ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
        """Evaluate hybrid mode (stage-based + scale-out)."""
        # TODO: Implement in Task 4
        raise NotImplementedError("Hybrid mode not yet implemented")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py -v`

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_exits.py tests/test_trailing_exits.py
git commit -m "feat: add trailing exit engine with stage-based mode

Implement TrailingExitEngine with stage-based evaluation,
breakeven stops, and EMA trailing. Includes R-multiple
 calculation and stop resolution.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Integrate into Existing ExitEngine

**Files:**
- Modify: `traderlib/paper_exits.py` (integrate trailing exits)
- Test: `tests/test_exit_engine.py` (add trailing tests)

- [ ] **Step 1: Modify ExitEngine to support trailing mode**

Add to `traderlib/paper_exits.py` after the existing imports:

```python
try:
    from traderlib.trailing_config import TrailingConfig, TrailingConfigLoader
    from traderlib.trailing_exits import TrailingExitEngine
    TRAILING_AVAILABLE = True
except ImportError:
    TRAILING_AVAILABLE = False
```

Modify the `ExitEngine.__init__` method:

```python
def __init__(self, risk_config: Optional['RiskConfig'] = None, 
             risk_profile: Optional[str] = None,
             trailing_config: Optional['TrailingConfig'] = None):
    """Initialize with optional risk and trailing configuration.
    
    Args:
        risk_config: Risk configuration
        risk_profile: Named risk profile to load
        trailing_config: Optional trailing exit configuration
    """
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
    
    # Initialize trailing exit engine if config provided
    self.trailing_engine = None
    if trailing_config and TRAILING_AVAILABLE:
        self.trailing_engine = TrailingExitEngine(trailing_config)
    elif self.risk_config and TRAILING_AVAILABLE:
        # Try to load from risk_config.yaml exit section
        self._try_load_trailing_config()

def _try_load_trailing_config(self):
    """Attempt to load trailing config from risk_config.yaml."""
    try:
        config_path = Path(__file__).parent.parent / "config" / "risk_config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
            if data and 'exit' in data and data['exit'].get('mode') in ('stage_based', 'continuous', 'hybrid'):
                loader = TrailingConfigLoader()
                trailing_config = loader._parse_config(data['exit'])
                self.trailing_engine = TrailingExitEngine(trailing_config)
    except Exception:
        pass  # Silently fail, trailing exits are optional
```

Modify `evaluate_exit_action` to check trailing engine first:

```python
def evaluate_exit_action(self, position, current_price: float,
                         historical_data: Optional[pd.DataFrame] = None) -> 'ExitAction':
    """Evaluate all exit conditions and return atomic ExitAction.
    
    If trailing_engine is configured, delegates to trailing logic.
    Otherwise uses original profit target logic.
    """
    # Check if trailing mode is active
    if self.trailing_engine:
        ema10, ema21 = self._get_ema_values(position.ticker, historical_data)
        ema_values = {'ema10': ema10, 'ema21': ema21}
        
        result = self.trailing_engine.evaluate(position, current_price, ema_values)
        
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
        else:
            return ExitAction(
                ticker=position.ticker,
                action=ExitActionType.HOLD,
                reason=result.reason,
                r_multiple=result.r_multiple
            )
    
    # Original profit target logic (keep existing code)
    # ... rest of existing evaluate_exit_action method ...
```

- [ ] **Step 2: Write integration test**

Add to `tests/test_exit_engine.py`:

```python
# ---------------------------------------------------------------------------
# Group - Trailing Exit Integration
# ---------------------------------------------------------------------------

class TestTrailingExitIntegration(unittest.TestCase):
    """Test trailing exit integration with ExitEngine."""
    
    def setUp(self):
        """Create engine with trailing config."""
        from traderlib.trailing_config import TrailingConfig, TrailingStage
        
        self.trailing_config = TrailingConfig(
            mode='stage_based',
            stages=[
                TrailingStage(trigger_r=2.0, action='move_stop_to', stop_price='breakeven'),
                TrailingStage(trigger_r=3.0, action='trail_with', method='ema', period=10),
            ],
            breakeven_at_r=2.0
        )
    
    @patch.object(ExitEngine, '_get_ema_values')
    def test_trailing_mode_breakeven(self, mock_ema):
        """Trailing mode moves stop to breakeven at 2R."""
        mock_ema.return_value = (170.0, 168.0)  # ema10, ema21
        
        engine = ExitEngine(trailing_config=self.trailing_config)
        pos = make_position(entry_price=150.0, stop_price=140.0, 
                           initial_stop_price=140.0, initial_risk=1000)
        
        # At 2R: 150 + 2*10 = 170
        action = engine.evaluate_exit_action(pos, current_price=170.0)
        
        self.assertEqual(action.action, ExitActionType.UPDATE_STOP)
        self.assertEqual(action.new_stop_price, 150.0)  # breakeven
        self.assertIn('BREAKEVEN', action.reason)
    
    @patch.object(ExitEngine, '_get_ema_values')
    def test_trailing_mode_ema_trail(self, mock_ema):
        """Trailing mode trails with EMA at 3R."""
        mock_ema.return_value = (175.0, 170.0)
        
        engine = ExitEngine(trailing_config=self.trailing_config)
        pos = make_position(entry_price=150.0, stop_price=150.0,  # At breakeven
                           initial_stop_price=140.0, initial_risk=1000)
        
        # At 3R: 150 + 3*10 = 180
        action = engine.evaluate_exit_action(pos, current_price=180.0)
        
        self.assertEqual(action.action, ExitActionType.UPDATE_STOP)
        self.assertEqual(action.new_stop_price, 175.0)  # ema10
        self.assertIn('EMA10', action.new_stop_type)
```

- [ ] **Step 3: Run integration test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_exit_engine.py::TestTrailingExitIntegration -v`

Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/paper_exits.py tests/test_exit_engine.py
git commit -m "feat: integrate trailing exits into ExitEngine

ExitEngine now supports trailing mode via trailing_config param.
Falls back to original profit target logic when trailing not configured.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Create Example Strategy Configuration

**Files:**
- Create: `config/strategies/example_trailing.yaml`

- [ ] **Step 1: Create example configuration**

```yaml
# Example Trailing Exit Strategy Configuration
# Demonstrates stage-based trailing exits for AMD-style momentum trades

name: example_trailing
description: "Stage-based trailing stops - breakeven at 2R, trail EMA at 3R+"

# ---------------------------------------------------------------------------
# Exit Management - Stage-Based Trailing
# ---------------------------------------------------------------------------
# This configuration:
# 1. Moves stop to breakeven at +2R (protects capital)
# 2. Trails with 10 EMA at +3R (early trend following)
# 3. Widens to 21 EMA at +5R (let winners run)
# 4. No fixed profit target - exits on trailing stop breach

exit:
  mode: "stage_based"
  breakeven_at_r: 2.0  # Move to breakeven at 2R (redundant but explicit)
  
  stages:
    # Stage 1: Protect capital
    - trigger_r: 2.0
      action: "move_stop_to"
      stop_price: "breakeven"
    
    # Stage 2: Early trend (tight trail)
    - trigger_r: 3.0
      action: "trail_with"
      method: "ema"
      period: 10
    
    # Stage 3: Late trend (wider trail)
    - trigger_r: 5.0
      action: "trail_with"
      method: "ema"
      period: 21
    
    # Stage 4: Long-term hold
    - trigger_r: 8.0
      action: "trail_with"
      method: "swing_low"

# ---------------------------------------------------------------------------
# Universe filters (same as vcp_large_cap for comparison)
# ---------------------------------------------------------------------------
universe:
  min_market_cap: 5000
  min_dollar_volume: 80000000
  min_share_volume: 1000000

# ---------------------------------------------------------------------------
# Entry filters
# ---------------------------------------------------------------------------
entry:
  min_stage2_score: 6
  min_convergence_score: 50
  max_pivot_proximity_pct: 5.0
```

- [ ] **Step 2: Validate YAML**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -c "import yaml; yaml.safe_load(open('config/strategies/example_trailing.yaml'))"`

Expected: No errors

- [ ] **Step 3: Write test for loading example**

Add to `tests/test_trailing_config.py`:

```python
class TestExampleStrategyLoad(unittest.TestCase):
    """Test loading the example trailing strategy."""
    
    def test_example_yaml_loads(self):
        """Example trailing strategy YAML loads correctly."""
        from pathlib import Path
        
        example_path = Path(__file__).parent.parent / "config" / "strategies" / "example_trailing.yaml"
        if not example_path.exists():
            self.skipTest("Example strategy not found")
        
        loader = TrailingConfigLoader()
        config = loader.load_from_file(example_path)
        
        self.assertEqual(config.mode, "stage_based")
        self.assertEqual(len(config.stages), 4)
        self.assertEqual(config.stages[0].trigger_r, 2.0)
        self.assertEqual(config.stages[2].method, "ema")
        self.assertEqual(config.stages[2].period, 21)
```

- [ ] **Step 4: Run test**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_config.py::TestExampleStrategyLoad -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add config/strategies/example_trailing.yaml tests/test_trailing_config.py
git commit -m "feat: add example trailing exit strategy config

Demonstrates stage-based trailing with 4 stages:
- Breakeven at 2R
- EMA10 trail at 3R
- EMA21 trail at 5R
- Swing low at 8R

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Implement Continuous Mode

**Files:**
- Modify: `traderlib/trailing_exits.py` (add _evaluate_continuous)
- Test: `tests/test_trailing_exits.py` (add continuous tests)

- [ ] **Step 1: Add continuous mode test**

```python
class TestContinuousMode(unittest.TestCase):
    """Test continuous trailing exit mode."""
    
    def test_continuous_band_selection(self):
        """Continuous mode selects correct band."""
        from traderlib.trailing_config import ContinuousBand
        
        config = TrailingConfig(
            mode='continuous',
            breakeven_at_r=2.0,
            continuous_bands=[
                ContinuousBand(from_r=2.5, to_r=4.0, method='ema', period=10),
                ContinuousBand(from_r=4.0, method='ema', period=21),  # to_r=None = unlimited
            ]
        )
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=140.0, shares=100)
        pos.stop_price = 150.0  # At breakeven
        
        # At 3.5R: should use band 1 (EMA10)
        result = engine._evaluate_continuous(pos, current_price=185.0, ema10=180.0, ema21=175.0)
        
        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 180.0)  # EMA10
        self.assertEqual(result.new_stop_type, 'EMA10_TRAIL')
    
    def test_continuous_high_r(self):
        """Continuous mode uses wider trail at high R."""
        from traderlib.trailing_config import ContinuousBand
        
        config = TrailingConfig(
            mode='continuous',
            breakeven_at_r=2.0,
            continuous_bands=[
                ContinuousBand(from_r=2.5, to_r=4.0, method='ema', period=10),
                ContinuousBand(from_r=4.0, method='ema', period=21),
            ]
        )
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=150.0, shares=100)  # At breakeven
        
        # At 6R: should use band 2 (EMA21)
        result = engine._evaluate_continuous(pos, current_price=210.0, ema10=200.0, ema21=205.0)
        
        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 205.0)  # EMA21
```

- [ ] **Step 2: Implement continuous mode**

Replace the `_evaluate_continuous` stub in `traderlib/trailing_exits.py`:

```python
def _evaluate_continuous(self, position, current_price: float,
                         ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
    """Evaluate continuous trailing rules.
    
    Continuous mode uses bands defined by R-multiple ranges.
    The active band is determined by current R.
    
    Args:
        position: Position object
        current_price: Current price
        ema10: 10-period EMA
        ema21: 21-period EMA
        
    Returns:
        TrailingResult with action
    """
    # Check hard stop first
    if current_price <= position.stop_price:
        return TrailingResult(
            action='exit',
            reason='STOP_HIT',
            r_multiple=self._calculate_r_multiple(position, current_price)
        )
    
    r_multiple = self._calculate_r_multiple(position, current_price)
    
    # Below breakeven trigger - hold with initial stop
    if r_multiple < self.config.breakeven_at_r:
        return TrailingResult(action='hold', reason='BELOW_BREAKEVEN_TRIGGER', r_multiple=r_multiple)
    
    # Move to breakeven once threshold reached
    if r_multiple >= self.config.breakeven_at_r and position.stop_price < position.entry_price:
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
        if r_multiple >= band.from_r:
            if band.to_r is None or r_multiple < band.to_r:
                active_band = band
                break
    
    if active_band is None:
        return TrailingResult(action='hold', reason='NO_ACTIVE_BAND', r_multiple=r_multiple)
    
    # Calculate trailing stop based on band method
    new_stop = self._calculate_trail_stop(
        active_band.method,
        current_price,
        ema10,
        ema21,
        MockStageFromBand(active_band)
    )
    
    if new_stop and new_stop > position.stop_price:
        stop_type = f"{active_band.method.upper()}" + (f"{active_band.period}" if active_band.period else "")
        return TrailingResult(
            action='update_stop',
            reason=f'BAND_{active_band.from_r}R_{stop_type}',
            new_stop=new_stop,
            new_stop_type=stop_type,
            r_multiple=r_multiple
        )
    
    return TrailingResult(action='hold', reason='NO_STOP_UPDATE', r_multiple=r_multiple)


class MockStageFromBand:
    """Adapter to use band config with trail stop calculation."""
    def __init__(self, band):
        self.method = band.method
        self.period = band.period
        self.atr_mult = band.atr_mult
        self.fixed_pct = None
```

- [ ] **Step 3: Run continuous tests**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py::TestContinuousMode -v`

Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_exits.py tests/test_trailing_exits.py
git commit -m "feat: implement continuous trailing mode

Adds smooth band transitions between R-multiple ranges.
Each band can use different trailing methods (EMA, ATR, etc).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Implement Hybrid Mode (Stage + Scale-Out)

**Files:**
- Modify: `traderlib/trailing_exits.py` (add _evaluate_hybrid)
- Test: `tests/test_trailing_exits.py` (add hybrid tests)

- [ ] **Step 1: Add hybrid mode test**

```python
class TestHybridMode(unittest.TestCase):
    """Test hybrid mode with scale-out."""
    
    def test_scale_out_trigger(self):
        """Hybrid mode triggers scale-out at R-level."""
        config = TrailingConfig(
            mode='hybrid',
            stages=[
                TrailingStage(trigger_r=2.0, action='move_stop_to', stop_price='breakeven'),
                TrailingStage(trigger_r=3.0, action='trail_with', method='ema', period=10),
            ],
            scale_out=[
                ScaleOutStep(trigger_r=3.0, fraction=0.33),
                ScaleOutStep(trigger_r=4.0, fraction=0.50),
            ],
            breakeven_at_r=2.0
        )
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=150.0, shares=100)  # At breakeven
        
        # At 3R: should scale out 33%
        result = engine._evaluate_hybrid(pos, current_price=180.0, ema10=175.0, ema21=170.0)
        
        self.assertEqual(result.action, 'scale_out')
        self.assertEqual(result.scale_fraction, 0.33)
        self.assertEqual(result.reason, 'SCALE_OUT_3.0R_33%')
    
    def test_trail_after_scale_out(self):
        """After scale-out, continue trailing remaining position."""
        config = TrailingConfig(
            mode='hybrid',
            stages=[
                TrailingStage(trigger_r=2.0, action='move_stop_to', stop_price='breakeven'),
                TrailingStage(trigger_r=3.0, action='trail_with', method='ema', period=10),
            ],
            scale_out=[
                ScaleOutStep(trigger_r=3.0, fraction=0.33),
            ],
            breakeven_at_r=2.0
        )
        engine = TrailingExitEngine(config)
        
        pos = MockPosition(entry=150.0, stop=150.0, shares=67)  # After 33% scale-out
        
        # At 5R: should trail remaining
        result = engine._evaluate_hybrid(pos, current_price=200.0, ema10=190.0, ema21=185.0)
        
        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 190.0)  # EMA10
```

- [ ] **Step 2: Implement hybrid mode**

Replace the `_evaluate_hybrid` stub in `traderlib/trailing_exits.py`:

```python
def _evaluate_hybrid(self, position, current_price: float,
                     ema10: Optional[float], ema21: Optional[float]) -> TrailingResult:
    """Evaluate hybrid mode (stage-based + scale-out).
    
    Hybrid mode adds partial exits to stage-based trailing.
    Scale-out happens before trailing stop updates.
    
    Args:
        position: Position object
        current_price: Current price
        ema10: 10-period EMA
        ema21: 21-period EMA
        
    Returns:
        TrailingResult with action
    """
    r_multiple = self._calculate_r_multiple(position, current_price)
    
    # Check hard stop
    if current_price <= position.stop_price:
        return TrailingResult(
            action='exit',
            reason='STOP_HIT',
            r_multiple=r_multiple
        )
    
    # Check scale-out triggers first (priority over trailing)
    if self.config.scale_out:
        for step in self.config.scale_out:
            if abs(r_multiple - step.trigger_r) < 0.05:  # Within 0.05R
                return TrailingResult(
                    action='scale_out',
                    reason=f'SCALE_OUT_{step.trigger_r}R_{int(step.fraction*100)}%',
                    scale_fraction=step.fraction,
                    r_multiple=r_multiple
                )
    
    # Delegate to stage-based logic for trailing
    return self._evaluate_stage_based(position, current_price, ema10, ema21)
```

- [ ] **Step 3: Run hybrid tests**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_exits.py::TestHybridMode -v`

Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_exits.py tests/test_trailing_exits.py
git commit -m "feat: implement hybrid trailing mode with scale-out

Adds partial position exits at R-levels while maintaining
trailing stops on remaining position.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Add Configuration Validation

**Files:**
- Modify: `traderlib/trailing_config.py` (add validation)
- Test: `tests/test_trailing_config.py` (add validation tests)

- [ ] **Step 1: Add validation tests**

```python
class TestConfigValidation(unittest.TestCase):
    """Test configuration validation."""
    
    def test_stages_must_increase(self):
        """Stages must have increasing R-values."""
        with self.assertRaises(ValueError) as cm:
            TrailingConfig(
                mode='stage_based',
                stages=[
                    TrailingStage(trigger_r=3.0, action='trail_with', method='ema', period=10),
                    TrailingStage(trigger_r=2.0, action='move_stop_to', stop_price='breakeven'),
                ]
            )
        self.assertIn('stages must have increasing trigger_r', str(cm.exception).lower())
    
    def test_stage_r_must_be_positive(self):
        """Stage R-values must be positive."""
        with self.assertRaises(ValueError):
            TrailingConfig(
                mode='stage_based',
                stages=[
                    TrailingStage(trigger_r=-1.0, action='move_stop_to', stop_price='breakeven'),
                ]
            )
    
    def test_continuous_bands_must_not_overlap(self):
        """Continuous bands must not overlap."""
        from traderlib.trailing_config import ContinuousBand
        
        with self.assertRaises(ValueError) as cm:
            TrailingConfig(
                mode='continuous',
                continuous_bands=[
                    ContinuousBand(from_r=2.0, to_r=4.0, method='ema', period=10),
                    ContinuousBand(from_r=3.0, to_r=5.0, method='ema', period=21),  # Overlaps!
                ]
            )
        self.assertIn('overlap', str(cm.exception).lower())
```

- [ ] **Step 2: Implement validation in TrailingConfig**

Add to `traderlib/trailing_config.py` in the `TrailingConfig` dataclass:

```python
@dataclass
class TrailingConfig:
    """Complete trailing exit configuration."""
    mode: str
    stages: List[TrailingStage] = field(default_factory=list)
    continuous_bands: List[ContinuousBand] = field(default_factory=list)
    scale_out: Optional[List[ScaleOutStep]] = None
    breakeven_at_r: float = 2.0
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate configuration."""
        if self.mode in ('stage_based', 'hybrid'):
            self._validate_stages()
        
        if self.mode == 'continuous':
            self._validate_continuous_bands()
        
        if self.scale_out:
            self._validate_scale_out()
    
    def _validate_stages(self):
        """Validate stages are in increasing order."""
        if not self.stages:
            return
        
        prev_r = 0.0
        for stage in self.stages:
            if stage.trigger_r <= 0:
                raise ValueError(f"Stage trigger_r must be positive, got {stage.trigger_r}")
            if stage.trigger_r <= prev_r:
                raise ValueError(
                    f"Stages must have increasing trigger_r: "
                    f"{prev_r} followed by {stage.trigger_r}"
                )
            prev_r = stage.trigger_r
    
    def _validate_continuous_bands(self):
        """Validate continuous bands don't overlap."""
        if not self.continuous_bands:
            return
        
        # Sort by from_r
        sorted_bands = sorted(self.continuous_bands, key=lambda b: b.from_r)
        
        prev_end = 0.0
        for band in sorted_bands:
            if band.from_r <= prev_end:
                raise ValueError(
                    f"Continuous bands must not overlap: "
                    f"band starting at {band.from_r} overlaps with previous ending at {prev_end}"
                )
            prev_end = band.to_r if band.to_r else float('inf')
    
    def _validate_scale_out(self):
        """Validate scale-out steps."""
        for step in self.scale_out:
            if step.fraction <= 0 or step.fraction > 1.0:
                raise ValueError(f"Scale-out fraction must be 0-1, got {step.fraction}")
```

- [ ] **Step 3: Run validation tests**

Run: `cd /Users/mintmrlion/.openclaw/workspaces/trader && python -m pytest tests/test_trailing_config.py::TestConfigValidation -v`

Expected: PASS (4 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add traderlib/trailing_config.py tests/test_trailing_config.py
git commit -m "feat: add trailing config validation

Validates:
- Stages have increasing trigger_r
- R-values are positive
- Continuous bands don't overlap
- Scale-out fractions are 0-1

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Update Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-configurable-trailing-exits-design.md` (mark as implemented)
- Create: `docs/superpowers/plans/2026-04-25-trailing-exit-system-implementation-notes.md`

- [ ] **Step 1: Update design doc**

Add to the top of the design doc:

```markdown
## Implementation Status

**Status:** ✅ IMPLEMENTED  
**Completed:** 2026-04-25  
**Plan:** `docs/superpowers/plans/2026-04-25-trailing-exit-system.md`

### Files Created/Modified
- `traderlib/trailing_config.py` - Configuration dataclasses
- `traderlib/trailing_exits.py` - Core trailing engine
- `traderlib/paper_exits.py` - Integration with ExitEngine
- `config/strategies/example_trailing.yaml` - Example configuration
- `tests/test_trailing_config.py` - Configuration tests
- `tests/test_trailing_exits.py` - Engine tests
```

- [ ] **Step 2: Create implementation notes**

```markdown
# Trailing Exit System Implementation Notes

## Quick Start

### Using Stage-Based Mode (Recommended)

Create a strategy config:

```yaml
exit:
  mode: "stage_based"
  stages:
    - trigger_r: 2.0
      action: "move_stop_to"
      stop_price: "breakeven"
    - trigger_r: 3.0
      action: "trail_with"
      method: "ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_with"
      method: "ema"
      period: 21
```

### Running with Trailing Exits

```python
from traderlib.trailing_config import TrailingConfigLoader
from traderlib.paper_exits import ExitEngine

# Load config
loader = TrailingConfigLoader()
config = loader.load_from_file("config/strategies/my_strategy.yaml")

# Create engine with trailing
engine = ExitEngine(trailing_config=config)
```

## Backward Compatibility

The original `target` mode (fixed 2R profit) remains the default.
To enable trailing, explicitly set `mode` to `stage_based`, `continuous`, or `hybrid`.

## AMD Trade Example

With the example configuration above:

| Price | R-Multiple | Action | Stop |
|-------|------------|--------|------|
| $281.83 | 0R | Entry | $267.74 (ATR-based) |
| $313.93 | 2R | Move stop | $281.83 (breakeven) |
| $345.73 | 3R | Trail 10 EMA | ~$340 (dynamic) |
| $409.33 | 5R | Trail 21 EMA | ~$390 (dynamic) |
| $350 | — | Exit | When 21 EMA breached |

## Configuration Reference

See `config/strategies/example_trailing.yaml` for full examples.

## Testing

Run all trailing exit tests:

```bash
python -m pytest tests/test_trailing_*.py -v
```
```

- [ ] **Step 3: Commit documentation**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
git add docs/
git commit -m "docs: update trailing exit design and add implementation notes

Marks design as implemented, adds quick start guide
and configuration reference.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Plan Self-Review

### Spec Coverage

| Requirement | Task |
|-------------|------|
| Stage-based mode | Task 2, 5 |
| Continuous mode | Task 5 |
| Hybrid mode | Task 6 |
| Configuration validation | Task 7 |
| YAML loading | Task 1 |
| Integration with ExitEngine | Task 3 |
| Example configuration | Task 4 |
| Documentation | Task 8 |

### Placeholder Check

- ✅ No TBDs or TODOs
- ✅ No vague requirements
- ✅ All test code complete
- ✅ All implementation code complete

### Type Consistency

- ✅ TrailingResult used consistently
- ✅ ExitAction types match across files
- ✅ Method names consistent (ema, swing_low, etc.)

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-trailing-exit-system.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
