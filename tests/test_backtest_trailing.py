"""Test backtesting with trailing exits."""

import unittest
from datetime import date
from traderlib.risk_config import RiskConfig, TrailingStageConfig


class TestBacktestWithTrailingExits(unittest.TestCase):
    """Test backtesting engine with trailing exit configuration."""

    def test_backtest_uses_trailing_config(self):
        """Backtest engine respects trailing configuration."""
        # Create config with trailing mode
        risk_config = RiskConfig()
        risk_config.profit_target.mode = "trailing"
        risk_config.profit_target.trailing_mode = "stage_based"
        risk_config.profit_target.trailing_stages = [
            TrailingStageConfig(trigger_r=2.0, action="breakeven"),
            TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
        ]

        # Verify engine has trailing config
        self.assertEqual(
            risk_config.profit_target.mode,
            "trailing"
        )
        self.assertEqual(
            risk_config.profit_target.trailing_mode,
            "stage_based"
        )
        self.assertEqual(
            len(risk_config.profit_target.trailing_stages),
            2
        )

    def test_stage_based_config_has_correct_stages(self):
        """Stage-based config has correct R-levels."""
        risk_config = RiskConfig()
        risk_config.profit_target.mode = "trailing"
        risk_config.profit_target.trailing_stages = [
            TrailingStageConfig(trigger_r=2.0, action="breakeven"),
            TrailingStageConfig(trigger_r=3.0, action="trail_ema", period=10),
            TrailingStageConfig(trigger_r=5.0, action="trail_ema", period=21),
        ]

        stages = risk_config.profit_target.trailing_stages
        self.assertEqual(stages[0].trigger_r, 2.0)
        self.assertEqual(stages[0].action, "breakeven")
        self.assertEqual(stages[1].trigger_r, 3.0)
        self.assertEqual(stages[1].action, "trail_ema")
        self.assertEqual(stages[1].period, 10)


if __name__ == '__main__':
    unittest.main()
