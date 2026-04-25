#!/usr/bin/env python3
"""Tests for risk management circuit breakers in PaperState.

Covers:
1. can_enter_position rejection paths (daily limit, cash, loss, sector, combined)
2. Position.from_dict Alpaca migration paths (missing fields, field mapping, list format)
3. update_stop and _log_trade validation (stop changes, initial stop preservation, validation failures)
"""

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# Add project root to path

from traderlib.paper_state import PaperState, Position, VALIDATION
from traderlib.risk_config import RiskConfig


@contextmanager
def paper_state_ctx(initial_capital=100000.0):
    """Context manager that creates a PaperState with patched file paths.

    All patches remain active for the duration of the context, ensuring
    that save_state, _log_trade, etc. use the temp directory.
    """
    tmpdir = Path(tempfile.mkdtemp())
    positions_file = tmpdir / 'paper_positions.json'
    positions_file.write_text('{}')

    # Use today's date so PaperState does not reset day_pnl/entries_today counters
    today = datetime.now().strftime('%Y-%m-%d')
    daily_tracker = tmpdir / 'daily_tracker.json'
    daily_tracker.write_text(json.dumps({'last_entry_reset': today}))

    trades_file = tmpdir / 'paper_trades.jsonl'
    trades_file.write_text('')

    with patch('traderlib.paper_state.DATA_DIR', tmpdir):
        with patch('traderlib.paper_state.POSITIONS_FILE', positions_file):
            with patch('traderlib.paper_state.DAILY_TRACKER_FILE', daily_tracker):
                with patch('traderlib.paper_state.TRADES_FILE', trades_file):
                    state = PaperState(initial_capital=initial_capital)
                    yield state, tmpdir, trades_file


# ---------------------------------------------------------------------------
# 1.1  can_enter_position rejection paths
# ---------------------------------------------------------------------------
class TestCanEnterPositionRejections(unittest.TestCase):
    """Test can_enter_position rejection paths."""

    def test_daily_entry_limit_blocks_entry(self):
        """Entering max_entries_per_day positions blocks further entries."""
        risk_config = RiskConfig()
        risk_config.account.max_entries_per_day = 3

        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Enter 3 positions to reach the daily limit
            for i, ticker in enumerate(['TSLA', 'NVDA', 'META']):
                state.enter_position(
                    ticker=ticker,
                    entry_price=200.0 + i * 10,
                    shares=10,
                    stop_price=190.0 + i * 10,
                    target_price=220.0 + i * 10,
                    sector='Technology',
                )

            # 4th entry should be blocked
            can_enter, reason = state.can_enter_position(
                sector='Technology',
                position_value=1000.0,
                risk_config=risk_config,
            )

            self.assertFalse(can_enter)
            self.assertIn('Daily entry limit', reason)

    def test_insufficient_cash_blocks_entry(self):
        """Insufficient cash blocks entry.

        We need existing positions so that equity > cash, otherwise the
        position-size check (which runs first) blocks with "exceeds X% of
        equity" before the cash check is reached.
        """
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Enter a position so equity > cash
            state.enter_position(
                ticker='NVDA', entry_price=400.0, shares=50,
                stop_price=380.0, target_price=440.0, sector='Technology',
            )
            # Cash = 100000 - 20000 = 80000, equity = 80000 + 20000 = 100000

            # Manually lower cash to simulate an API-reported cash shortfall
            state.cash = 500.0
            # Equity = 500 + 20000 = 20500
            # position_value=1000 <= 20500 * 0.20 = 4100 (passes size check)
            # 1000 > 500 (fails cash check)

            can_enter, reason = state.can_enter_position(
                sector='Healthcare',
                position_value=1000.0,
            )

            self.assertFalse(can_enter)
            self.assertTrue(
                'Insufficient cash' in reason or 'buying power' in reason,
                f"Expected cash/buying power in reason, got: {reason}",
            )

    def test_daily_loss_limit_blocks_entry(self):
        """Daily loss exceeding limit blocks entry."""
        risk_config = RiskConfig()
        # daily_loss_limit_pct default is 0.02 (2%), so limit is $2000 for 100k capital

        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Set day_pnl to -3% of initial_capital (exceeds 2% limit)
            state.day_pnl = -3000.0

            can_enter, reason = state.can_enter_position(
                sector='Healthcare',
                position_value=1000.0,
                risk_config=risk_config,
            )

            self.assertFalse(can_enter)
            self.assertIn('Daily loss limit', reason)

    def test_sector_limit_with_risk_config(self):
        """Sector position limit blocks entry when exceeded."""
        risk_config = RiskConfig()
        risk_config.account.max_sector_positions = 3

        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Enter 3 positions in Technology sector
            for i, ticker in enumerate(['TSLA', 'NVDA', 'META']):
                state.enter_position(
                    ticker=ticker,
                    entry_price=200.0 + i * 10,
                    shares=10,
                    stop_price=190.0 + i * 10,
                    target_price=220.0 + i * 10,
                    sector='Technology',
                )

            # 4th Technology entry should be blocked by sector limit
            can_enter, reason = state.can_enter_position(
                sector='Technology',
                position_value=1000.0,
                risk_config=risk_config,
            )

            self.assertFalse(can_enter)
            self.assertIn('Sector limit', reason)
            self.assertIn('Technology', reason)

    def test_combined_limits_first_applicable_reported(self):
        """When multiple limits are hit, the first applicable limit is reported.

        Order of checks in can_enter_position:
        1. Daily entry limit
        2. Sector limit
        3. Position size limit
        4. Buying power (insufficient cash)
        5. Daily loss limit
        """
        risk_config = RiskConfig()
        risk_config.account.max_entries_per_day = 3
        risk_config.account.daily_loss_limit_pct = 0.02

        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Set up multiple limit conditions simultaneously
            state.entries_today = 3  # Hit daily entry limit
            state.day_pnl = -3000.0  # Also hit daily loss limit (-3% > -2%)

            # Daily entry limit should be reported first (it's checked first)
            can_enter, reason = state.can_enter_position(
                sector='Technology',
                position_value=1000.0,
                risk_config=risk_config,
            )

            self.assertFalse(can_enter)
            self.assertIn('Daily entry limit', reason)


# ---------------------------------------------------------------------------
# 1.2  Position.from_dict Alpaca migration paths
# ---------------------------------------------------------------------------
class TestPositionFromDictAlpacaMigration(unittest.TestCase):
    """Test Position.from_dict handling of missing/Alpaca fields."""

    def test_from_dict_missing_stop_price_marks_unsynced(self):
        """Missing stop_price sets stop_price=0.0 and current_stop_type='UNSYNCED'."""
        data = {
            'ticker': 'AAPL',
            'status': 'OPEN',
            'entry_date': '2024-04-01',
            'entry_price': 150.0,
            'shares': 100,
        }

        pos = Position.from_dict(data)

        self.assertEqual(pos.stop_price, 0.0)
        self.assertEqual(pos.current_stop_type, 'UNSYNCED')

    def test_from_dict_missing_target_price_calculates_from_risk(self):
        """Missing target_price is calculated as entry + 2*risk when stop is valid."""
        data = {
            'ticker': 'AAPL',
            'status': 'OPEN',
            'entry_date': '2024-04-01',
            'entry_price': 150.0,
            'stop_price': 140.0,
            'shares': 100,
            'sector': 'Technology',
        }

        pos = Position.from_dict(data)

        # risk = 150 - 140 = 10, target = 150 + 10*2 = 170.0
        self.assertEqual(pos.target_price, 170.0)

    def test_from_dict_missing_initial_risk_recalculates(self):
        """Missing initial_risk is recalculated as (entry - stop) * shares."""
        data = {
            'ticker': 'AAPL',
            'status': 'OPEN',
            'entry_date': '2024-04-01',
            'entry_price': 150.0,
            'stop_price': 140.0,
            'shares': 100,
            'sector': 'Technology',
        }

        pos = Position.from_dict(data)

        # initial_risk = (150 - 140) * 100 = 1000.0
        self.assertEqual(pos.initial_risk, 1000.0)

    def test_from_dict_alpaca_field_names(self):
        """Alpaca field names (qty, avg_entry_price, symbol) are mapped correctly."""
        data = {
            'symbol': 'AAPL',
            'qty': 100,
            'avg_entry_price': 150.0,
            'stop_price': 140.0,
            'sector': 'Technology',
        }

        pos = Position.from_dict(data)

        self.assertEqual(pos.ticker, 'AAPL')        # symbol -> ticker
        self.assertEqual(pos.shares, 100)             # qty -> shares
        self.assertEqual(pos.entry_price, 150.0)     # avg_entry_price -> entry_price

    def test_from_dict_list_format_in_state_file(self):
        """Positions file as JSON list (Alpaca format) is loaded correctly."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Overwrite positions file with list format (Alpaca-style)
            positions_file = tmpdir / 'paper_positions.json'
            positions_file.write_text(json.dumps([
                {
                    'symbol': 'TSLA',
                    'status': 'OPEN',
                    'entry_date': '2024-04-01',
                    'entry_price': 200.0,
                    'qty': 50,
                    'stop_price': 185.0,
                    'target_price': 220.0,
                    'initial_risk': 750.0,
                    'sector': 'Automotive',
                }
            ]))

            # Create a new PaperState to load from the list-format file
            state2 = PaperState(initial_capital=100000.0)

            self.assertIn('TSLA', state2.positions)
            self.assertEqual(state2.positions['TSLA'].shares, 50)
            self.assertEqual(state2.positions['TSLA'].entry_price, 200.0)


# ---------------------------------------------------------------------------
# 1.3  update_stop and _log_trade validation
# ---------------------------------------------------------------------------
class TestUpdateStopAndLogTradeValidation(unittest.TestCase):
    """Test update_stop behavior and _log_trade validation."""

    def test_update_stop_changes_stop_price_and_type(self):
        """update_stop changes both stop_price and current_stop_type."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            state.enter_position(
                ticker='XYZ',
                entry_price=200.0,
                shares=50,
                stop_price=190.0,
                target_price=220.0,
                sector='Technology',
            )

            state.update_stop('XYZ', 195.0, 'EMA_10')

            self.assertEqual(state.positions['XYZ'].stop_price, 195.0)
            self.assertEqual(state.positions['XYZ'].current_stop_type, 'EMA_10')

    def test_update_stop_preserves_initial_stop(self):
        """update_stop does not change initial_stop_price (FINDING-013)."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            state.enter_position(
                ticker='XYZ',
                entry_price=200.0,
                shares=50,
                stop_price=140.0,
                target_price=220.0,
                sector='Technology',
            )

            # Verify initial_stop_price was set at entry
            self.assertEqual(state.positions['XYZ'].initial_stop_price, 140.0)

            state.update_stop('XYZ', 145.0, 'BREAKEVEN')

            # stop_price moved, but initial_stop_price preserved
            self.assertEqual(state.positions['XYZ'].stop_price, 145.0)
            self.assertEqual(state.positions['XYZ'].initial_stop_price, 140.0)

    def test_validate_trade_rejects_over_max_shares(self):
        """Trade with shares > MAX_SHARES is logged with validation_failed metadata."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            # Patch VALIDATION to guarantee known thresholds regardless of env vars
            validation = {
                'MAX_ENTRY_PRICE': 5000.0,
                'MAX_SHARES': 500,
                'MAX_POSITION_VALUE': 50000.0,
                'MAX_PNL_ABS': 10000.0,
                'SKIP_VALIDATION': False,
            }
            with patch('traderlib.paper_state.VALIDATION', validation):
                # Enter position with shares exceeding MAX_SHARES (500)
                # Keep position_value under MAX_POSITION_VALUE (50000)
                state.enter_position(
                    ticker='XYZ',
                    entry_price=50.0,
                    shares=600,       # > MAX_SHARES (500)
                    stop_price=45.0,
                    target_price=55.0,
                    sector='Technology',
                )

                # Read the trade log
                trades_content = trades_file.read_text().strip()
                self.assertTrue(trades_content, "Trade log should not be empty")

                trade_line = trades_content.split('\n')[-1]
                trade = json.loads(trade_line)

                # Verify validation_failed metadata
                self.assertTrue(
                    trade.get('_meta', {}).get('validation_failed', False),
                    "validation_failed should be True in trade metadata",
                )
                self.assertIn(
                    'shares',
                    trade.get('_meta', {}).get('validation_reason', ''),
                    "validation_reason should mention 'shares'",
                )

    def test_validate_trade_rejects_over_max_entry_price(self):
        """Trade with entry_price > MAX_ENTRY_PRICE is logged with validation_failed metadata."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            validation = {
                'MAX_ENTRY_PRICE': 5000.0,
                'MAX_SHARES': 500,
                'MAX_POSITION_VALUE': 50000.0,
                'MAX_PNL_ABS': 10000.0,
                'SKIP_VALIDATION': False,
            }
            with patch('traderlib.paper_state.VALIDATION', validation):
                # Enter position with entry_price exceeding MAX_ENTRY_PRICE (5000)
                state.enter_position(
                    ticker='XYZ',
                    entry_price=5500.0,  # > MAX_ENTRY_PRICE (5000)
                    shares=5,
                    stop_price=5400.0,
                    target_price=5600.0,
                    sector='Finance',
                )

                # Read the trade log
                trades_content = trades_file.read_text().strip()
                self.assertTrue(trades_content, "Trade log should not be empty")

                trade_line = trades_content.split('\n')[-1]
                trade = json.loads(trade_line)

                self.assertTrue(
                    trade.get('_meta', {}).get('validation_failed', False),
                    "validation_failed should be True in trade metadata",
                )
                self.assertIn(
                    'entry_price',
                    trade.get('_meta', {}).get('validation_reason', ''),
                    "validation_reason should mention 'entry_price'",
                )

    def test_log_trade_validation_failure_still_records(self):
        """After validation failure, a line is still written to the trade log file."""
        with paper_state_ctx(initial_capital=100000.0) as (state, tmpdir, trades_file):
            validation = {
                'MAX_ENTRY_PRICE': 5000.0,
                'MAX_SHARES': 500,
                'MAX_POSITION_VALUE': 50000.0,
                'MAX_PNL_ABS': 10000.0,
                'SKIP_VALIDATION': False,
            }
            with patch('traderlib.paper_state.VALIDATION', validation):
                # Enter a position that will fail validation (shares > MAX_SHARES)
                state.enter_position(
                    ticker='XYZ',
                    entry_price=50.0,
                    shares=600,
                    stop_price=45.0,
                    target_price=55.0,
                    sector='Technology',
                )

                # Verify trade log file has at least one line
                trades_content = trades_file.read_text().strip()
                self.assertTrue(
                    len(trades_content) > 0,
                    "Trade log should not be empty after validation failure",
                )

                # Verify the line is valid JSON with expected fields
                lines = [line for line in trades_content.split('\n') if line.strip()]
                self.assertGreaterEqual(len(lines), 1, "At least one trade should be logged")

                trade = json.loads(lines[-1])
                self.assertEqual(trade.get('event'), 'ENTRY')
                self.assertEqual(trade.get('ticker'), 'XYZ')
                self.assertTrue(
                    trade.get('_meta', {}).get('validation_failed', False),
                    "validation_failed should be True",
                )


if __name__ == '__main__':
    unittest.main()