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

    def record_scale_out(self, r_level: float):
        if r_level not in self.scale_out_history:
            self.scale_out_history.append(r_level)


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
