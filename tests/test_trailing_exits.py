"""Tests for trailing exit engine (all modes)."""

import unittest
from unittest.mock import Mock, patch
from dataclasses import dataclass

from traderlib.trailing_exits import TrailingExitEngine, TrailingResult
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

    def test_zero_risk(self):
        """Handle zero risk (entry == stop)."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)

        pos = MockPosition(entry_price=150.0, stop_price=150.0, initial_stop_price=150.0, shares=100)
        r = engine._calculate_r_multiple(pos, current_price=170.0)

        self.assertEqual(r, 0.0)  # Undefined, return 0


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

        self.assertEqual(result.action, 'exit')
        self.assertEqual(result.reason, 'STOP_HIT')

    def test_hold_below_first_stage(self):
        """Hold when below first stage trigger."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=155.0)  # 0.5R

        self.assertEqual(result.action, 'hold')

    def test_breakeven_stage(self):
        """At 2R, move stop to breakeven."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=170.0, ema10=165.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 150.0)  # breakeven
        self.assertEqual(result.reason, 'STAGE_2.0R_BREAKEVEN')

    def test_ema_trail_stage(self):
        """At 3R, trail with EMA10."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 175.0)  # EMA10

    def test_ema21_stage(self):
        """At 5R, switch to EMA21."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, initial_stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=200.0, ema10=195.0, ema21=190.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 190.0)  # EMA21

    def test_stop_only_moves_up(self):
        """Stop never moves lower."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, initial_stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=170.0)  # EMA below stop

        self.assertEqual(result.action, 'hold')  # No update

    def test_missing_ema_fallback(self):
        """Hold when EMA data unavailable."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        result = self.engine.evaluate(pos, current_price=180.0, ema10=None, ema21=None)

        self.assertEqual(result.action, 'hold')  # Can't trail without EMA


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
                {"from_r": 4.0, "to_r": 6.0, "method": "ema21"},
            ]
        )
        self.engine = TrailingExitEngine(self.config)

    def test_breakeven_trigger(self):
        """Move to breakeven at configured R."""
        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = self.engine.evaluate(pos, current_price=170.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 150.0)

    def test_ema10_band(self):
        """Trail EMA10 in first band."""
        pos = MockPosition(entry_price=150.0, stop_price=150.0, shares=100)
        # At 3R: 150 + 30 = 180
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0, ema21=170.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 175.0)  # EMA10

    def test_ema21_band(self):
        """Trail EMA21 in second band."""
        pos = MockPosition(entry_price=150.0, stop_price=175.0, initial_stop_price=140.0, shares=100)
        # At 5R: 150 + 50 = 200
        result = self.engine.evaluate(pos, current_price=200.0, ema10=190.0, ema21=195.0)

        self.assertEqual(result.action, 'update_stop')
        self.assertEqual(result.new_stop, 195.0)  # EMA21


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

        self.assertEqual(result.action, 'scale_out')
        self.assertEqual(result.scale_fraction, 0.33)
        self.assertEqual(result.shares_to_sell, 33)

    def test_scale_out_not_repeated(self):
        """Scale-out only triggers once."""
        pos = MockPosition(
            entry_price=150.0,
            stop_price=150.0,
            shares=67,  # After first scale-out
            scale_out_history=[3.0]  # 3R already executed
        )
        result = self.engine.evaluate(pos, current_price=180.0, ema10=175.0)

        self.assertNotEqual(result.action, 'scale_out')  # Should trail instead

    def test_second_scale_out(self):
        """Second scale-out at 4R."""
        pos = MockPosition(
            entry_price=150.0,
            stop_price=175.0,
            initial_stop_price=140.0,
            shares=67,
            scale_out_history=[3.0]
        )
        # At 4R: 150 + 40 = 190
        result = self.engine.evaluate(pos, current_price=190.0, ema10=185.0)

        self.assertEqual(result.action, 'scale_out')
        self.assertEqual(result.scale_fraction, 0.50)
        self.assertEqual(result.shares_to_sell, 33)  # 50% of remaining 67


class TestTargetMode(unittest.TestCase):
    """Test original target mode (backward compatibility)."""

    def test_target_mode_exits_at_r(self):
        """Original mode exits at fixed R target."""
        config = ProfitTargetConfig(mode="target", min_r_multiple=2.0)
        engine = TrailingExitEngine(config)

        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = engine.evaluate(pos, current_price=170.0)  # 2R

        self.assertEqual(result.action, 'exit')
        self.assertIn('TARGET_HIT', result.reason)

    def test_target_mode_holds_below(self):
        """Original mode holds below target."""
        config = ProfitTargetConfig(mode="target", min_r_multiple=2.0)
        engine = TrailingExitEngine(config)

        pos = MockPosition(entry_price=150.0, stop_price=140.0, shares=100)
        result = engine.evaluate(pos, current_price=160.0)  # 1R

        self.assertEqual(result.action, 'hold')


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def test_short_position_not_supported(self):
        """Short positions raise clear error."""
        config = ProfitTargetConfig(mode="trailing", trailing_mode="stage_based")
        engine = TrailingExitEngine(config)

        # Short position: initial stop above entry
        pos = MockPosition(entry_price=150.0, stop_price=160.0, initial_stop_price=160.0, shares=100)

        with self.assertRaises(NotImplementedError) as cm:
            engine.evaluate(pos, current_price=150.0)

        self.assertIn("short", str(cm.exception).lower())

    def test_invalid_mode(self):
        """Invalid mode raises error."""
        with self.assertRaises(ValueError) as cm:
            TrailingExitEngine(ProfitTargetConfig(mode="invalid"))
        self.assertIn("mode", str(cm.exception).lower())


if __name__ == '__main__':
    unittest.main()
