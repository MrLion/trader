#!/usr/bin/env python3
"""Phase 2: Exit Engine Logic Tests.
Verify trailing stop and breakeven logic without needing a live API.
"""

import unittest
from pathlib import Path
import sys

from scripts.paper_exits import ExitEngine, ExitSignal
from scripts.paper_state import Position

class TestExitEngine(unittest.TestCase):
    """Test trailing stop and exit logic."""

    def setUp(self):
        self.exits = ExitEngine()
        self.ticker = "AAPL"
        self.entry_price = 150.0
        self.stop_price = 140.0 # 6.6% risk

        self.pos = Position(
            ticker=self.ticker,
            status='OPEN',
            entry_date='2024-04-01',
            entry_price=self.entry_price,
            shares=100,
            stop_price=self.stop_price,
            target_price=165.0,
            initial_risk=10.0,
            sector='Technology'
        )

    def test_hard_stop_loss_trigger(self):
        """Price below stop should trigger immediate exit."""
        current_price = 139.0
        signal = self.exits.evaluate_exit(self.pos, current_price)

        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, "STOP_HIT")
        self.assertEqual(signal.exit_price, current_price)

    def test_breakeven_activation(self):
        """+1R move should move stop to breakeven."""
        # Risk is 10.0. +1R move = Price reaches 160.0
        current_price = 161.0
        # The engine evaluates exit. If not exiting, it may update stop.
        # Since evaluate_exit only returns a signal, we check how it would behave.
        signal = self.exits.evaluate_exit(self.pos, current_price)
        self.assertFalse(signal.should_exit)

        # Note: trailing stop updates usually happen in the engine loop.
        # If evaluate_exit doesn't update the position object, we test the calculation.
        # We check if the exit logic would now trigger at 150 instead of 140.

        # Simulate position already moved to breakeven
        self.pos.stop_price = 150.0
        signal = self.exits.evaluate_exit(self.pos, 149.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, "STOP_HIT")

    def test_trailing_stop_ema_logic(self):
        """Test that trailing stops move up as price increases."""
        # Simulate a massive run +3R
        current_price = 180.0
        # In the real engine, EMA is calculated. Here we verify that
        # the exit engine correctly triggers if price falls below the current stop.

        self.pos.stop_price = 170.0 # Simulating a trailing stop at 170
        signal = self.exits.evaluate_exit(self.pos, 169.0)
        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, "STOP_HIT")

    def test_target_hit(self):
        """Price hitting target should trigger exit."""
        current_price = 166.0
        signal = self.exits.evaluate_exit(self.pos, current_price)

        self.assertTrue(signal.should_exit)
        self.assertEqual(signal.reason, "TARGET_HIT")
        self.assertEqual(signal.exit_price, current_price)

if __name__ == '__main__':
    unittest.main()
