#!/usr/bin/env python3
"""Exit engine tests: trailing stops, breakeven, EMA trailing, profit targets.

Standard test position:
    entry=150, stop=140, risk/share=10, shares=100, initial_risk=1000
    target=170 (2R)

    R levels:
        +0.5R → 155.0
        +1R   → 160.0
        +1.5R → 165.0
        +2R   → 170.0  (= target)
        +3R   → 180.0
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.paper_exits import ExitEngine
from scripts.paper_state import Position
from traderlib.risk_config import RiskConfig, ProfitTargetConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(**overrides) -> Position:
    """Create a standard test position. Keyword args override defaults."""
    defaults = dict(
        ticker='TEST',
        status='OPEN',
        entry_date='2026-01-01',
        entry_price=150.0,
        shares=100,
        stop_price=140.0,
        target_price=170.0,
        initial_risk=1000.0,   # (150-140) * 100
        sector='Technology',
        current_stop_type='HARD',
    )
    defaults.update(overrides)
    return Position(**defaults)


def make_engine(ema10=None, ema21=None, risk_config=None) -> ExitEngine:
    """Create an ExitEngine with _get_ema_values mocked."""
    engine = ExitEngine(risk_config=risk_config)
    engine._get_ema_values = Mock(return_value=(ema10, ema21))
    return engine


# ---------------------------------------------------------------------------
# Group 1 — _calculate_r_multiple
# ---------------------------------------------------------------------------

class TestRMultipleCalculation(unittest.TestCase):

    def setUp(self):
        self.engine = ExitEngine()

    def test_at_entry_price_is_zero(self):
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(150.0, 150.0, 140.0, 100), 0.0
        )

    def test_at_plus_one_r(self):
        # price = entry + 1 * risk/share = 160
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(160.0, 150.0, 140.0, 100), 1.0
        )

    def test_at_minus_one_r(self):
        # price = stop = 140
        self.assertAlmostEqual(
            self.engine._calculate_r_multiple(140.0, 150.0, 140.0, 100), -1.0
        )

    def test_zero_initial_risk_returns_zero(self):
        # stop == entry → no risk → guard against division by zero
        result = self.engine._calculate_r_multiple(160.0, 150.0, 150.0, 100)
        self.assertEqual(result, 0.0)


# ---------------------------------------------------------------------------
# Group 2 — Hard stop boundaries
# ---------------------------------------------------------------------------

class TestHardStop(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine()
        self.pos = make_position()

    def test_price_below_stop_triggers_exit(self):
        signal = self.engine.evaluate_exit(self.pos, 139.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, 'STOP_HIT')

    def test_price_exactly_at_stop_triggers_exit(self):
        signal = self.engine.evaluate_exit(self.pos, 140.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, 'STOP_HIT')

    def test_price_one_cent_above_stop_is_hold(self):
        signal = self.engine.evaluate_exit(self.pos, 140.01)
        self.assertFalse(signal.should_exit)


# ---------------------------------------------------------------------------
# Group 3 — Breakeven ratchet (+1R)
# ---------------------------------------------------------------------------

class TestBreakevenRatchet(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine(ema10=None, ema21=None)

    def test_at_plus_1r_stop_moves_to_entry(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 161.0)  # just above +1R
        self.assertEqual(pos.stop_price, 150.0)

    def test_at_plus_1r_stop_type_becomes_breakeven(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

    def test_below_plus_1r_stop_does_not_move(self):
        pos = make_position()
        self.engine.evaluate_exit(pos, 159.0)  # 0.9R — below threshold
        self.assertEqual(pos.stop_price, 140.0)
        self.assertEqual(pos.current_stop_type, 'HARD')

    def test_already_at_breakeven_stop_does_not_go_down(self):
        # Stop already at entry — should not be moved downward
        pos = make_position(stop_price=150.0, current_stop_type='BREAKEVEN')
        self.engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.stop_price, 150.0)


# ---------------------------------------------------------------------------
# Group 4 — EMA10 trailing (+1.5R)
# ---------------------------------------------------------------------------

class TestEMA10Trailing(unittest.TestCase):

    def test_ema10_above_stop_moves_stop(self):
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)  # +1.5R
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_ema10_below_stop_does_not_move_stop(self):
        # EMA10 below current stop — ratchet must not go down
        engine = make_engine(ema10=135.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)
        self.assertEqual(pos.stop_price, 140.0)

    def test_ema10_none_falls_back_to_breakeven(self):
        # No EMA data at +1.5R — should still apply breakeven logic
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 165.0)
        # Breakeven fires as fallback (entry_price > current_stop)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')


# ---------------------------------------------------------------------------
# Group 5 — EMA21 trailing (+3R)
# ---------------------------------------------------------------------------

class TestEMA21Trailing(unittest.TestCase):

    def test_ema21_above_stop_moves_stop(self):
        engine = make_engine(ema10=155.0, ema21=165.0)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)  # +3R
        self.assertEqual(pos.stop_price, 165.0)
        self.assertEqual(pos.current_stop_type, 'EMA21')

    def test_ema21_below_stop_does_not_move_stop(self):
        engine = make_engine(ema10=155.0, ema21=135.0)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 140.0)

    def test_ema21_none_falls_back_to_ema10(self):
        # Gap 2 decision: at +3R with ema21=None, fall back to EMA10 trailing
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_ema21_and_ema10_none_falls_back_to_breakeven(self):
        # No EMA data at +3R — breakeven is the last resort
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()
        engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')


# ---------------------------------------------------------------------------
# Group 6 — Profit target exit
# ---------------------------------------------------------------------------

class TestProfitTargetExit(unittest.TestCase):

    def setUp(self):
        self.engine = make_engine()

    def test_price_at_target_triggers_exit(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 170.0)  # exactly at 2R target
        self.assertTrue(signal.should_exit)
        self.assertIn('TARGET_HIT', signal.reason)

    def test_price_above_target_triggers_exit(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 175.0)
        self.assertTrue(signal.should_exit)
        self.assertIn('TARGET_HIT', signal.reason)

    def test_r_multiple_2_without_reaching_target_triggers_exit(self):
        # target is 175 (above 2R=170) — 2R fires first
        pos = make_position(target_price=175.0)
        signal = self.engine.evaluate_exit(pos, 170.0)  # 2R exactly
        self.assertTrue(signal.should_exit)
        self.assertIn('2.0R', signal.reason)

    def test_below_target_and_below_2r_is_hold(self):
        pos = make_position()
        signal = self.engine.evaluate_exit(pos, 169.0)  # 1.9R, below target
        self.assertFalse(signal.should_exit)
        self.assertEqual(signal.reason, 'HOLD')


# ---------------------------------------------------------------------------
# Group 7 — Stop never goes down (ratchet invariant)
# ---------------------------------------------------------------------------

class TestStopNeverGoesDown(unittest.TestCase):

    def test_stop_does_not_retreat_when_price_falls_back(self):
        # Advance to +1.5R (EMA10 trailing), then price retreats to +1R
        engine = make_engine(ema10=155.0, ema21=None)
        pos = make_position()

        engine.evaluate_exit(pos, 165.0)  # stop moves to EMA10=155
        self.assertEqual(pos.stop_price, 155.0)

        engine._get_ema_values = Mock(return_value=(148.0, None))  # EMA drops
        engine.evaluate_exit(pos, 161.0)  # price retreats

        # Stop must not fall back below 155
        self.assertGreaterEqual(pos.stop_price, 155.0)

    def test_sequential_advances_only_ratchet_upward(self):
        # Three price advances — stop should only go up
        engine = make_engine(ema10=153.0, ema21=None)
        pos = make_position()
        stops = []

        for price in [161.0, 163.0, 165.0]:
            engine.evaluate_exit(pos, price)
            stops.append(pos.stop_price)

        for i in range(1, len(stops)):
            self.assertGreaterEqual(stops[i], stops[i - 1],
                msg=f"Stop went down from {stops[i-1]} to {stops[i]}")


# ---------------------------------------------------------------------------
# Group 8 — Custom risk config thresholds (Gap 3: inline RiskConfig, no YAML)
# ---------------------------------------------------------------------------

class TestCustomRiskConfigThresholds(unittest.TestCase):

    def _make_config(self, breakeven_at_r=1.0, ema10_at_r=1.5, ema21_at_r=3.0) -> RiskConfig:
        config = RiskConfig()
        config.profit_target.breakeven_at_r = breakeven_at_r
        config.profit_target.ema10_at_r = ema10_at_r
        config.profit_target.ema21_at_r = ema21_at_r
        return config

    def test_custom_breakeven_threshold_fires_early(self):
        # Configured to move to breakeven at only +0.5R
        config = self._make_config(breakeven_at_r=0.5)
        engine = make_engine(ema10=None, ema21=None, risk_config=config)
        pos = make_position()

        engine.evaluate_exit(pos, 155.0)  # exactly +0.5R
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

    def test_custom_ema10_threshold_fires_at_configured_r(self):
        # Configured EMA10 trailing at +2R instead of +1.5R
        config = self._make_config(ema10_at_r=2.0)
        engine = make_engine(ema10=155.0, ema21=None, risk_config=config)
        pos = make_position()

        # At +1.5R — should NOT trail EMA10 yet (threshold is +2R)
        engine.evaluate_exit(pos, 165.0)
        self.assertNotEqual(pos.current_stop_type, 'EMA10')

        # At +2R — should now trail EMA10
        pos2 = make_position()
        engine.evaluate_exit(pos2, 170.0)
        self.assertEqual(pos2.current_stop_type, 'EMA10')


# ---------------------------------------------------------------------------
# Gap 1 — Lifecycle: R multiples stay correct after stop ratchets
# ---------------------------------------------------------------------------

class TestLifecycle(unittest.TestCase):

    def test_r_multiple_correct_after_breakeven_ratchet(self):
        """Stop ratchet must not corrupt R multiple on subsequent calls.

        Bug: if initial_stop = position.stop_price and stop has moved to
        entry (breakeven), the next call computes risk/share = 0, returning
        r_multiple = 0.0 instead of the real value. This prevents EMA10
        trailing from ever activating after breakeven.
        """
        engine = make_engine(ema10=None, ema21=None)
        pos = make_position()

        # Call 1: price at +1R — stop ratchets to breakeven
        signal1 = engine.evaluate_exit(pos, 161.0)
        self.assertFalse(signal1.should_exit)
        self.assertEqual(pos.stop_price, 150.0, "stop should be at breakeven")

        # Call 2: price at +1.5R — EMA10 should trail (engine now has EMA data)
        engine._get_ema_values = Mock(return_value=(155.0, None))
        signal2 = engine.evaluate_exit(pos, 165.0)

        # If the bug exists, r_multiple would be 0.0 here and EMA10 wouldn't fire
        self.assertFalse(signal2.should_exit)
        self.assertEqual(pos.stop_price, 155.0,
            "EMA10 trailing should have fired — r_multiple was corrupted by stop ratchet if not")
        self.assertEqual(pos.current_stop_type, 'EMA10')

    def test_full_lifecycle_initial_stop_to_target(self):
        """Full position lifecycle: HARD → BREAKEVEN → EMA10 → EMA21 → exit."""
        pos = make_position()

        # Phase 1: hold below +1R
        engine = make_engine(ema10=None, ema21=None)
        s = engine.evaluate_exit(pos, 155.0)  # +0.5R
        self.assertFalse(s.should_exit)
        self.assertEqual(pos.current_stop_type, 'HARD')

        # Phase 2: breakeven at +1R
        s = engine.evaluate_exit(pos, 161.0)
        self.assertEqual(pos.stop_price, 150.0)
        self.assertEqual(pos.current_stop_type, 'BREAKEVEN')

        # Phase 3: EMA10 trailing at +1.5R
        engine._get_ema_values = Mock(return_value=(155.0, None))
        s = engine.evaluate_exit(pos, 165.0)
        self.assertEqual(pos.stop_price, 155.0)
        self.assertEqual(pos.current_stop_type, 'EMA10')

        # Phase 4: EMA21 trailing at +3R
        engine._get_ema_values = Mock(return_value=(162.0, 168.0))
        s = engine.evaluate_exit(pos, 180.0)
        self.assertEqual(pos.stop_price, 168.0)
        self.assertEqual(pos.current_stop_type, 'EMA21')

        # Phase 5: target exit
        s = engine.evaluate_exit(pos, 170.0)
        self.assertTrue(s.should_exit)
        self.assertIn('TARGET_HIT', s.reason)


if __name__ == '__main__':
    unittest.main()
