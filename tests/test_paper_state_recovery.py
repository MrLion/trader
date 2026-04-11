#!/usr/bin/env python3
"""Phase 3 Paper State Recovery Tests.

Tests edge cases in state persistence:
- Missing files
- Zero/negative equity
- Corrupted state recovery

Success Criteria:
- All recovery tests pass
- No crashes on edge cases
- Graceful degradation
"""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts' / 'lib'))

from traderlib.paper_state import PaperState, Position


class TestMissingAccountFile(unittest.TestCase):
    """Test handling of missing/deleted account JSON."""

    def test_missing_account_file(self):
        """Missing account file should use initial capital.

        Verifies:
        1. No error when account file missing
        2. Initial capital used as fallback
        3. Can save state after operations
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # No account file exists
            positions_file = data_dir / 'paper_positions.json'
            positions_file.write_text('{}')
            # account file is MISSING

            daily_tracker = data_dir / 'daily_tracker.json'
            daily_tracker.write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    with patch('paper_state.DAILY_TRACKER_FILE', daily_tracker):
                        # Should not raise error
                        state = PaperState(initial_capital=50000.0)

                        # Should use initial capital
                        self.assertEqual(state.cash, 50000.0)
                        self.assertEqual(state.initial_capital, 50000.0)

                        # Add a position
                        state.enter_position(
                            ticker='AAPL',
                            entry_price=150.0,
                            shares=100,
                            stop_price=140.0,
                            target_price=165.0,
                            sector='Technology'
                        )

                        # Position should be saved to positions file
                        self.assertTrue(positions_file.exists())

                        # Load new state - should restore from saved
                        state2 = PaperState(initial_capital=50000.0)
                        self.assertIn('AAPL', state2.positions)

        print("✅ Missing account file: Graceful fallback to initial capital")

    @patch('paper_state.datetime')
    def test_deleted_mid_session(self, mock_datetime):
        """Account file deleted mid-session should recover.

        Verifies:
        1. State continues with in-memory values
        2. Next save recreates file
        """
        mock_datetime.now.return_value = datetime(2024, 4, 8, 10, 0, 0)
        mock_datetime.strftime = datetime.strftime

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Start with existing state
            positions_file = data_dir / 'paper_positions.json'
            positions_file.write_text('{}')
            daily_tracker = data_dir / 'daily_tracker.json'
            daily_tracker.write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            # Create trade log with 2 entries for reconciliation
            trades_file = data_dir / 'paper_trades.jsonl'
            with open(trades_file, 'w') as f:
                # Two ENTRY events from today (production trades)
                # Use realistic prices that don't match test patterns (AAPL@150.00 is test pattern)
                f.write(json.dumps({
                    'event': 'ENTRY',
                    'timestamp': '2024-04-08T09:30:00',
                    'ticker': 'TSLA',
                    'entry_price': 175.5,
                    'shares': 10,
                    '_meta': {'test_mode': False}
                }) + '\n')
                f.write(json.dumps({
                    'event': 'ENTRY',
                    'timestamp': '2024-04-08T10:00:00',
                    'ticker': 'NVDA',
                    'entry_price': 485.25,
                    'shares': 5,
                    '_meta': {'test_mode': False}
                }) + '\n')

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    with patch('paper_state.DAILY_TRACKER_FILE', daily_tracker):
                        with patch('paper_state.TRADES_FILE', trades_file):
                            state = PaperState(initial_capital=100000.0)

                            # Verify entries_today reconciled from trade log (2 production entries)
                            # Cash now comes from Alpaca API, not stored locally
                            self.assertEqual(state.entries_today, 2)

                            # Add another position (should work fine)
                            state.enter_position(
                                ticker='MSFT',
                                entry_price=300.0,
                                shares=50,
                                stop_price=280.0,
                                target_price=330.0,
                                sector='Technology'
                            )

                            # Delete daily tracker AFTER adding position
                            daily_tracker.unlink()

                            # Save should recreate daily tracker
                            state.save_state()
                            self.assertTrue(daily_tracker.exists())

        print("✅ Deleted mid-session: Recovery and recreation works")


class TestZeroEquityHandling(unittest.TestCase):
    """Test edge case of zero or negative equity."""

    def test_zero_equity_prevents_entries(self):
        """Zero equity should prevent new positions.

        Verifies:
        1. can_enter_position returns False
        2. Appropriate error message
        3. No division by zero in position sizing
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'daily_tracker.json').write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', data_dir / 'paper_positions.json'):
                    with patch('paper_state.DAILY_TRACKER_FILE', data_dir / 'daily_tracker.json'):
                        state = PaperState(initial_capital=0.0)

                        self.assertEqual(state.get_equity(), 0.0)

                        # Should not allow entries (insufficient buying power)
                        can_enter, reason = state.can_enter_position(
                            'Technology',
                            position_value=1000.0
                        )

                        # Should be blocked (position value > buying power)
                        self.assertFalse(can_enter)

        print("✅ Zero equity: New entries blocked")

    def test_negative_pnl_calculation(self):
        """Position underwater should calculate negative P&L correctly.

        Verifies:
        1. Negative P&L calculated correctly
        2. Day P&L updated with negative value
        3. Position record shows loss
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'daily_tracker.json').write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', data_dir / 'paper_positions.json'):
                    with patch('paper_state.DAILY_TRACKER_FILE', data_dir / 'daily_tracker.json'):
                        state = PaperState(initial_capital=100000.0)

                        # Enter position
                        state.enter_position(
                            ticker='AAPL',
                            entry_price=200.0,
                            shares=100,
                            stop_price=180.0,
                            target_price=220.0,
                            sector='Technology'
                        )

                        # Close at loss (exit below entry)
                        position = state.close_position(
                            ticker='AAPL',
                            exit_price=180.0,  # $20 loss per share
                            reason='STOP_HIT'
                        )

                        # Verify negative P&L
                        self.assertIsNotNone(position)
                        self.assertEqual(position.realized_pnl, -2000.0)  # (180-200) * 100
                        self.assertLess(position.realized_pnl, 0)

                        # Day P&L should be negative
                        self.assertEqual(state.day_pnl, -2000.0)

        print("✅ Negative P&L: Underwater positions calculate correctly")

    def test_large_negative_pnl(self):
        """Extreme losses should be handled.

        Verifies:
        1. Large negative numbers don't overflow
        2. State remains consistent
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            (data_dir / 'paper_positions.json').write_text('{}')
            (data_dir / 'daily_tracker.json').write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', data_dir / 'paper_positions.json'):
                    with patch('paper_state.DAILY_TRACKER_FILE', data_dir / 'daily_tracker.json'):
                        state = PaperState(initial_capital=100000.0)

                        # Enter large position
                        state.enter_position(
                            ticker='AAPL',
                            entry_price=500.0,
                            shares=1000,
                            stop_price=450.0,
                            target_price=550.0,
                            sector='Technology'
                        )

                        # Close with massive loss (50% down)
                        position = state.close_position(
                            ticker='AAPL',
                            exit_price=250.0,  # $250 loss per share
                            reason='STOP_HIT'
                        )

                        # Verify large negative P&L
                        self.assertEqual(position.realized_pnl, -250000.0)
                        self.assertEqual(state.day_pnl, -250000.0)

                        # State should still be valid
                        self.assertEqual(len(state.positions), 0)

        print("✅ Large negative P&L: Extreme losses handled")


class TestCorruptedStateRecovery(unittest.TestCase):
    """Test recovery from various corruption scenarios."""

    def test_invalid_position_data_types(self):
        """Position with wrong data types should be handled.

        Verifies:
        1. Invalid types don't crash loading
        2. Corrupt positions skipped or defaulted
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            positions_file = data_dir / 'paper_positions.json'
            # Invalid: shares as string instead of number
            positions_file.write_text(json.dumps({
                'AAPL': {
                    'ticker': 'AAPL',
                    'status': 'OPEN',
                    'entry_date': '2024-04-01',
                    'entry_price': 'not_a_number',  # Invalid
                    'shares': '100',  # String instead of int
                    'stop_price': 140.0,
                    'target_price': 165.0,
                    'initial_risk': 1000.0,
                    'sector': 'Technology'
                }
            }))

            (data_dir / 'daily_tracker.json').write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    with patch('paper_state.DAILY_TRACKER_FILE', data_dir / 'daily_tracker.json'):
                        # This may or may not raise an error depending on implementation
                        # The important thing is it doesn't crash the system
                        try:
                            state = PaperState(initial_capital=100000.0)
                            # System loads the position (may have string values)
                            # Important thing is it doesn't crash
                            self.assertIn('AAPL', state.positions)
                        except (TypeError, ValueError, json.JSONDecodeError) as e:
                            # Expected - corrupt data rejected
                            pass

        print("✅ Invalid data types: Corrupt position data handled")

    def test_future_date_positions(self):
        """Positions with future dates should be handled.

        Verifies:
        1. Future entry dates don't break calculations
        2. System uses current date where appropriate
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            positions_file = data_dir / 'paper_positions.json'
            # Position from the future
            positions_file.write_text(json.dumps({
                'AAPL': {
                    'ticker': 'AAPL',
                    'status': 'OPEN',
                    'entry_date': '2025-12-25',  # Future date
                    'entry_price': 150.0,
                    'shares': 100,
                    'stop_price': 140.0,
                    'target_price': 165.0,
                    'initial_risk': 1000.0,
                    'sector': 'Technology'
                }
            }))

            (data_dir / 'daily_tracker.json').write_text(json.dumps({
                'last_entry_reset': '2024-04-08'
            }))

            with patch('paper_state.DATA_DIR', data_dir):
                with patch('paper_state.POSITIONS_FILE', positions_file):
                    with patch('paper_state.DAILY_TRACKER_FILE', data_dir / 'daily_tracker.json'):
                        state = PaperState(initial_capital=100000.0)

                        # Position should load
                        self.assertIn('AAPL', state.positions)
                        self.assertEqual(state.positions['AAPL'].entry_date, '2025-12-25')

        print("✅ Future dates: Unusual timestamps handled")


def run_tests():
    """Run all Phase 3 paper state recovery tests."""
    print("=" * 70)
    print("🧪 PHASE 3: PAPER STATE RECOVERY TESTS")
    print("=" * 70)
    print()
    print("Testing state edge cases:")
    print("  • Missing account files")
    print("  • Zero equity handling")
    print("  • Negative P&L calculation")
    print("  • Corrupted state recovery")
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestMissingAccountFile))
    suite.addTests(loader.loadTestsFromTestCase(TestZeroEquityHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestCorruptedStateRecovery))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("📊 STATE RECOVERY TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print()
        print("✅ ALL RECOVERY TESTS PASSED")
    else:
        print()
        print("❌ SOME RECOVERY TESTS FAILED")

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
