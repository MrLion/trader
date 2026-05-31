#!/usr/bin/env python3
"""Tests for operational state logging.

Covers:
1. STATE_LOAD logs on successful load
2. STATE_LOAD_EMPTY logs when file is missing
3. INTEGRITY_TRADE_LOG flags missing positions
4. STATE_SAVE_VERIFY logs after save
"""

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.paper_state import PaperState


class PaperStateTestMixin:
    """Mixin providing helper to create a PaperState with patched file paths."""

    def _create_paper_state(self, tmpdir, positions='{}', trades='', daily_reset='2024-04-08'):
        data_dir = Path(tmpdir)
        positions_file = data_dir / 'paper_positions.json'
        if positions is not None:
            positions_file.write_text(positions)
        daily_tracker = data_dir / 'daily_tracker.json'
        daily_tracker.write_text(json.dumps({'last_entry_reset': daily_reset}))
        trades_file = data_dir / 'paper_trades.jsonl'
        trades_file.write_text(trades)

        with ExitStack() as stack:
            stack.enter_context(patch('traderlib.paper_state.DATA_DIR', data_dir))
            stack.enter_context(patch('traderlib.paper_state.POSITIONS_FILE', positions_file))
            stack.enter_context(patch('traderlib.paper_state.DAILY_TRACKER_FILE', daily_tracker))
            stack.enter_context(patch('traderlib.paper_state.TRADES_FILE', trades_file))
            return PaperState(initial_capital=100000.0)


class TestStateLoadLogging(unittest.TestCase, PaperStateTestMixin):
    """Test that _load_state emits operational logs."""

    def test_state_load_empty_file(self):
        """Empty positions file should load without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertLogs('trading', level='INFO') as cm:
                state = self._create_paper_state(tmpdir, positions='{}')
            self.assertTrue(
                any('STATE_LOAD' in msg for msg in cm.output),
                f"Expected STATE_LOAD in logs, got: {cm.output}"
            )
            self.assertEqual(len(state.positions), 0)

    def test_state_load_with_positions(self):
        """Positions file with data should load correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertLogs('trading', level='INFO') as cm:
                state = self._create_paper_state(
                    tmpdir,
                    positions=json.dumps({
                        'AAPL': {
                            'ticker': 'AAPL',
                            'status': 'OPEN',
                            'entry_date': '2024-04-01',
                            'entry_price': 150.0,
                            'shares': 100,
                            'stop_price': 140.0,
                            'target_price': 165.0,
                            'initial_risk': 1000.0,
                            'sector': 'Technology',
                            'initial_stop_price': 140.0,
                            'entry_min_r': 2.0,
                        }
                    })
                )
            self.assertTrue(
                any('STATE_LOAD' in msg for msg in cm.output),
                f"Expected STATE_LOAD in logs, got: {cm.output}"
            )
            self.assertIn('AAPL', state.positions)
            self.assertEqual(state.positions['AAPL'].shares, 100)

    def test_state_load_missing_file(self):
        """Missing positions file should log STATE_LOAD_EMPTY."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertLogs('trading', level='INFO') as cm:
                state = self._create_paper_state(tmpdir, positions=None)
            self.assertTrue(
                any('STATE_LOAD_EMPTY' in msg for msg in cm.output),
                f"Expected STATE_LOAD_EMPTY in logs, got: {cm.output}"
            )
            self.assertEqual(len(state.positions), 0)


class TestIntegrityTradeLog(unittest.TestCase, PaperStateTestMixin):
    """Test trade log integrity checks."""

    def test_integrity_flags_missing_position(self):
        """Trade log ENTRY with no position should trigger integrity warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertLogs('trading', level='WARNING') as cm:
                state = self._create_paper_state(
                    tmpdir,
                    positions='{}',
                    trades=json.dumps({
                        'event': 'ENTRY',
                        'timestamp': '2024-04-08T10:00:00',
                        'ticker': 'GHOST',
                        'entry_price': 100.0,
                        'shares': 10,
                    }) + '\n'
                )
            self.assertTrue(
                any('INTEGRITY_TRADE_LOG' in msg for msg in cm.output),
                f"Expected INTEGRITY_TRADE_LOG in logs, got: {cm.output}"
            )
            self.assertNotIn('GHOST', state.positions)

    def test_integrity_no_false_positive_for_closed_position(self):
        """Trade log with matching ENTRY and EXIT should not trigger warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = self._create_paper_state(
                tmpdir,
                positions='{}',
                trades=(
                    json.dumps({'event': 'ENTRY', 'timestamp': '2024-04-08T10:00:00', 'ticker': 'CLOSED', 'entry_price': 100.0, 'shares': 10}) + '\n' +
                    json.dumps({'event': 'EXIT', 'timestamp': '2024-04-08T11:00:00', 'ticker': 'CLOSED', 'exit_price': 110.0, 'shares': 10, 'realized_pnl': 100.0}) + '\n'
                )
            )
            self.assertNotIn('CLOSED', state.positions)


class TestStateSaveVerify(unittest.TestCase, PaperStateTestMixin):
    """Test post-save verification."""

    def test_save_verify_succeeds(self):
        """Normal save should pass verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = self._create_paper_state(tmpdir, positions='{}')
            with self.assertLogs('trading', level='INFO') as cm:
                state.enter_position(
                    ticker='TEST',
                    entry_price=100.0,
                    shares=10,
                    stop_price=90.0,
                    target_price=110.0,
                    sector='Technology',
                )
            self.assertTrue(
                any('STATE_SAVE_VERIFY' in msg for msg in cm.output),
                f"Expected STATE_SAVE_VERIFY in logs, got: {cm.output}"
            )
            # Verify file was written
            self.assertTrue(state.positions_file.exists())
            data = json.loads(state.positions_file.read_text())
            self.assertIn('TEST', data)


if __name__ == '__main__':
    unittest.main()
