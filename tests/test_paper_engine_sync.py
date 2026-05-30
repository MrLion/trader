import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from traderlib.paper_state import PaperState, Position


class TestSyncMergePreservesImmutables(unittest.TestCase):
    INITIAL_CAPITAL = 100_000.0

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Patch module-level file paths to use temp directory
        patcher_data_dir = patch('traderlib.paper_state.DATA_DIR', self.temp_path)
        patcher_positions = patch('traderlib.paper_state.POSITIONS_FILE', self.temp_path / 'paper_positions.json')
        patcher_daily = patch('traderlib.paper_state.DAILY_TRACKER_FILE', self.temp_path / 'daily_tracker.json')
        patcher_trades = patch('traderlib.paper_state.TRADES_FILE', self.temp_path / 'paper_trades.jsonl')

        patcher_data_dir.start()
        patcher_positions.start()
        patcher_daily.start()
        patcher_trades.start()

        self.addCleanup(patcher_data_dir.stop)
        self.addCleanup(patcher_positions.stop)
        self.addCleanup(patcher_daily.stop)
        self.addCleanup(patcher_trades.stop)
        self.addCleanup(self.temp_dir.cleanup)

        # Create PaperState using patched paths (no data_dir so fallback is used)
        self.state = PaperState(initial_capital=self.INITIAL_CAPITAL)

        # Enter position for NXT
        self.state.enter_position(
            ticker='NXT',
            entry_price=125.68,
            shares=80,
            stop_price=122.71,
            target_price=131.63,
            sector='Technology',
            entry_min_r=2.0
        )

        # Capture original entry_date before any mutations
        self.original_entry_date = self.state.positions['NXT'].entry_date

    def simulate_sync_merge(self, state):
        """Simulate a sync merge by mutating mutable fields and saving state."""
        pos = state.positions['NXT']
        pos.shares = 26
        pos.scale_out_history = [3.0]
        pos.stop_price = 125.68
        state.save_state()

    def test_sync_merge_preserves_mutable_and_immutable_fields(self):
        """Reload state into a new PaperState and verify fields survived."""
        self.simulate_sync_merge(self.state)

        new_state = PaperState(initial_capital=self.INITIAL_CAPITAL)

        self.assertIn('NXT', new_state.positions)
        pos = new_state.positions['NXT']

        # Immutable fields should survive the save/load cycle
        self.assertEqual(pos.initial_stop_price, 122.71)
        self.assertEqual(pos.entry_date, self.original_entry_date)
        self.assertEqual(pos.entry_price, 125.68)
        self.assertEqual(pos.target_price, 131.63)
        self.assertEqual(pos.sector, 'Technology')
        self.assertEqual(pos.entry_min_r, 2.0)

        # Mutable fields should reflect the updated values
        self.assertEqual(pos.shares, 26)
        self.assertEqual(pos.scale_out_history, [3.0])
        self.assertEqual(pos.stop_price, 125.68)


if __name__ == '__main__':
    unittest.main()
