"""Tests for backtest state management."""

import unittest
from datetime import date

from traderlib.backtest.state import BacktestState, TradeRecord, BacktestPosition
from traderlib.paper_state import Position


def make_position(**overrides) -> Position:
    """Create a test Position with sensible defaults."""
    defaults = dict(
        ticker='AAPL',
        status='OPEN',
        entry_date='2024-01-15',
        entry_price=150.0,
        shares=100,
        stop_price=140.0,
        target_price=170.0,
        initial_risk=1000.0,
        sector='Technology',
        current_stop_type='HARD',
        initial_stop_price=140.0,
    )
    defaults.update(overrides)
    return Position(**defaults)


class TestTradeRecord(unittest.TestCase):
    """Tests for TradeRecord dataclass."""

    def test_fields(self):
        record = TradeRecord(
            ticker='AAPL', side='LONG',
            entry_date=date(2024, 1, 15), exit_date=date(2024, 2, 15),
            entry_price=150.0, exit_price=160.0,
            shares=100, pnl=1000.0,
            exit_reason='TARGET_HIT', commissions=1.0,
        )
        self.assertEqual(record.ticker, 'AAPL')
        self.assertEqual(record.side, 'LONG')
        self.assertEqual(record.pnl, 1000.0)


class TestBacktestPosition(unittest.TestCase):
    """Tests for BacktestPosition wrapper."""

    def test_default_side_is_long(self):
        pos = make_position()
        bp = BacktestPosition(position=pos, entry_date=date(2024, 1, 15))
        self.assertEqual(bp.side, 'LONG')

    def test_short_side(self):
        pos = make_position()
        bp = BacktestPosition(position=pos, side='SHORT', entry_date=date(2024, 1, 15))
        self.assertEqual(bp.side, 'SHORT')


class TestBacktestState(unittest.TestCase):
    """Tests for BacktestState."""

    def setUp(self):
        self.state = BacktestState(
            initial_capital=100_000,
            start_date=date(2024, 1, 1),
        )

    def test_initial_state(self):
        self.assertEqual(self.state.cash, 100_000)
        self.assertEqual(self.state.sim_date, date(2024, 1, 1))
        self.assertEqual(len(self.state.positions), 0)
        self.assertEqual(len(self.state.closed_trades), 0)

    def test_set_date(self):
        self.state.set_date(date(2024, 3, 15))
        self.assertEqual(self.state.sim_date, date(2024, 3, 15))

    def test_equity_no_positions(self):
        self.assertEqual(self.state.equity, 100_000)

    def test_enter_position(self):
        pos = self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=150.0, shares=100,
            stop_price=140.0, target_price=170.0,
            sector='Technology', initial_stop_price=140.0,
        )
        self.assertEqual(pos.ticker, 'AAPL')
        self.assertEqual(pos.shares, 100)
        self.assertEqual(pos.initial_stop_price, 140.0)
        self.assertAlmostEqual(self.state.cash, 100_000 - 15000)

    def test_close_position_long_pnl(self):
        """LONG P&L: (exit - entry) * shares - commission."""
        self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=150.0, shares=100,
            stop_price=140.0, target_price=170.0,
            sector='Technology', initial_stop_price=140.0,
        )
        trade = self.state.close_position('AAPL', 160.0, 'TARGET_HIT', commission=1.0)
        # P&L = (160 - 150) * 100 - 1.0 = 999.0
        self.assertAlmostEqual(trade.pnl, 999.0)
        self.assertEqual(trade.side, 'LONG')

    def test_close_position_short_pnl(self):
        """SHORT P&L: (entry - exit) * shares - commission."""
        self.state.enter_position(
            ticker='AAPL', side='SHORT',
            entry_price=150.0, shares=100,
            stop_price=160.0, target_price=130.0,
            sector='Technology', initial_stop_price=160.0,
        )
        trade = self.state.close_position('AAPL', 140.0, 'TARGET_HIT', commission=1.0)
        # P&L = (150 - 140) * 100 - 1.0 = 999.0
        self.assertAlmostEqual(trade.pnl, 999.0)
        self.assertEqual(trade.side, 'SHORT')

    def test_close_position_removes_from_positions(self):
        self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=150.0, shares=100,
            stop_price=140.0, target_price=170.0,
            sector='Technology', initial_stop_price=140.0,
        )
        self.assertIn('AAPL', self.state.positions)
        self.state.close_position('AAPL', 160.0, 'EXIT', commission=0.5)
        self.assertNotIn('AAPL', self.state.positions)

    def test_close_position_unknown_ticker_raises(self):
        with self.assertRaises(ValueError):
            self.state.close_position('UNKNOWN', 100.0, 'EXIT')

    def test_max_open_positions(self):
        """Cannot exceed max_open_positions."""
        state = BacktestState(
            initial_capital=1_000_000,
            start_date=date(2024, 1, 1),
            max_open_positions=3,
        )
        for i in range(3):
            state.enter_position(
                ticker=f'TICK{i}', side='LONG',
                entry_price=100.0, shares=10,
                stop_price=90.0, target_price=110.0,
                sector='Technology', initial_stop_price=90.0,
            )
        self.assertEqual(len(state.positions), 3)

    def test_can_enter_position_max_positions(self):
        state = BacktestState(
            initial_capital=1_000_000,
            start_date=date(2024, 1, 1),
            max_open_positions=2,
        )
        state.enter_position('A', 'LONG', 100.0, 10, 90.0, 110.0, 'Tech', 90.0)
        state.enter_position('B', 'LONG', 100.0, 10, 90.0, 110.0, 'Tech', 90.0)
        ok, reason = state.can_enter_position('Tech', 1000.0)
        self.assertFalse(ok)
        self.assertIn('Max positions', reason)

    def test_can_enter_position_insufficient_cash(self):
        ok, reason = self.state.can_enter_position('Tech', 200_000.0)
        self.assertFalse(ok)
        self.assertIn('Insufficient', reason)

    def test_can_enter_position_sector_limit(self):
        """Sector limit blocks excess concentration."""
        for i in range(3):
            self.state.enter_position(
                ticker=f'TICK{i}', side='LONG',
                entry_price=100.0, shares=10,
                stop_price=90.0, target_price=110.0,
                sector='Technology', initial_stop_price=90.0,
            )
        ok, reason = self.state.can_enter_position('Technology', 1000.0)
        self.assertFalse(ok)
        self.assertIn('Sector limit', reason)

    def test_initial_stop_price_always_set(self):
        """BacktestState always sets initial_stop_price explicitly."""
        pos = self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=150.0, shares=100,
            stop_price=140.0, target_price=170.0,
            sector='Technology', initial_stop_price=140.0,
        )
        self.assertEqual(pos.initial_stop_price, 140.0)

    def test_no_datetime_now_in_state(self):
        """BacktestState never calls datetime.now() in code."""
        import traderlib.backtest.state as state_module
        import re
        source = open(state_module.__file__).read()
        # Remove docstrings and comments
        source_no_strings = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
        source_no_strings = re.sub(r"'''.*?'''", '', source_no_strings, flags=re.DOTALL)
        source_no_strings = re.sub(r"'[^']*'", '', source_no_strings)
        source_no_strings = re.sub(r'"[^"]*"', '', source_no_strings)
        source_no_strings = re.sub(r'#.*$', '', source_no_strings, flags=re.MULTILINE)
        self.assertNotIn('datetime.now()', source_no_strings)

    def test_no_file_io_in_state(self):
        """BacktestState has no save_state or file I/O."""
        import inspect
        members = [name for name, _ in inspect.getmembers(BacktestState)]
        self.assertNotIn('save_state', members)
        self.assertNotIn('_log_trade', members)

    def test_side_aware_long_exit(self):
        """Long position exits correctly."""
        self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=100.0, shares=50,
            stop_price=90.0, target_price=120.0,
            sector='Tech', initial_stop_price=90.0,
        )
        trade = self.state.close_position('AAPL', 110.0, 'STOP_HIT')
        # P&L = (110 - 100) * 50 = 500
        self.assertAlmostEqual(trade.pnl, 500.0)

    def test_side_aware_short_exit(self):
        """Short position exits correctly: (entry - exit) * shares."""
        self.state.enter_position(
            ticker='AAPL', side='SHORT',
            entry_price=100.0, shares=50,
            stop_price=110.0, target_price=80.0,
            sector='Tech', initial_stop_price=110.0,
        )
        trade = self.state.close_position('AAPL', 85.0, 'TARGET_HIT')
        # P&L = (100 - 85) * 50 = 750
        self.assertAlmostEqual(trade.pnl, 750.0)

    def test_cash_tracking_after_entry_exit(self):
        """Cash decreases on entry, increases on exit."""
        initial_cash = self.state.cash
        self.state.enter_position(
            ticker='AAPL', side='LONG',
            entry_price=100.0, shares=50,
            stop_price=90.0, target_price=120.0,
            sector='Tech', initial_stop_price=90.0,
        )
        self.assertEqual(self.state.cash, initial_cash - 5000)

        self.state.close_position('AAPL', 110.0, 'EXIT')
        # Cash = initial - 5000 + 5500 = initial + 500
        self.assertEqual(self.state.cash, initial_cash + 500)


if __name__ == '__main__':
    unittest.main()