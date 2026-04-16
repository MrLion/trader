#!/usr/bin/env python3
"""Tests for backtest gap rejection logic.

Targets uncovered paths in traderlib/backtest/engine.py:
- Gap rejection: T+1 open below stop → entry signal rejected
- Gap acceptance: T+1 open above stop → entry proceeds
- Position blocking: risk rules prevent entry after gap check
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from traderlib.backtest.engine import BacktestEngine, BacktestConfig
from traderlib.backtest.state import BacktestState
from traderlib.backtest.strategy import EntrySignal
from traderlib.paper_exits import ExitEngine
from traderlib.risk_config import RiskConfigManager


class TestGapRejection:
    """Test gap rejection in _resolve_pending_fills."""

    def _make_engine(self):
        """Create a minimal engine with mocked dependencies."""
        config = BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            initial_capital=100000,
            tickers=['AAPL'],
        )

        data_provider = Mock()
        strategy = Mock()

        engine = BacktestEngine(data_provider, strategy, config)
        return engine, config

    def test_gap_below_stops_records_rejection(self):
        """T+1 open below stop → gap rejection recorded, no entry."""
        engine, config = self._make_engine()
        state = BacktestState(initial_capital=100000, start_date=date(2024, 1, 2))

        signal = EntrySignal(
            ticker='AAPL',
            side='LONG',
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector='Technology',
            entry_score=80,
            stage2_score=7,
        )
        engine._pending_entries = [signal]

        # Mock data provider to return T+1 open price BELOW stop
        engine.data_provider.get_current_price = Mock(return_value=135.0)

        # Mock can_enter_position to allow entry
        state.can_enter_position = Mock(return_value=(True, 'OK'))

        engine._resolve_pending_fills(state, date(2024, 1, 3))

        # Should have recorded a gap rejection
        assert len(engine._gap_rejections) == 1
        assert engine._gap_rejections[0]['ticker'] == 'AAPL'
        assert engine._gap_rejections[0]['reason'] == 'open_below_stop'
        assert engine._gap_rejections[0]['open_price'] == 135.0

        # No position created
        assert 'AAPL' not in state.positions

    def test_gap_above_entry_allows_entry(self):
        """T+1 open above stop → entry proceeds at open price."""
        engine, config = self._make_engine()
        state = BacktestState(initial_capital=100000, start_date=date(2024, 1, 2))

        signal = EntrySignal(
            ticker='AAPL',
            side='LONG',
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector='Technology',
            entry_score=80,
            stage2_score=7,
        )
        engine._pending_entries = [signal]

        # T+1 open above stop (normal case)
        engine.data_provider.get_current_price = Mock(return_value=148.0)

        # Mock can_enter_position to allow entry
        state.can_enter_position = Mock(return_value=(True, 'OK'))

        # Mock execution to simulate fill
        engine._execution = Mock()
        fill = Mock()
        fill.fill_price = 148.0
        fill.shares = 100
        fill.slippage = 0.0
        engine._execution.simulate_fill = Mock(return_value=fill)

        engine._resolve_pending_fills(state, date(2024, 1, 3))

        # No gap rejection
        assert len(engine._gap_rejections) == 0

        # Entry should have been attempted (simulate_fill called)
        engine._execution.simulate_fill.assert_called_once()

    def test_gap_partially_below_stop(self):
        """T+1 open between stop and entry → entry still allowed."""
        engine, config = self._make_engine()
        state = BacktestState(initial_capital=100000, start_date=date(2024, 1, 2))

        signal = EntrySignal(
            ticker='AAPL',
            side='LONG',
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector='Technology',
            entry_score=80,
            stage2_score=7,
        )
        engine._pending_entries = [signal]

        # Open at $145 (between stop=140 and entry=150)
        engine.data_provider.get_current_price = Mock(return_value=145.0)

        state.can_enter_position = Mock(return_value=(True, 'OK'))

        engine._execution = Mock()
        fill = Mock()
        fill.fill_price = 145.0
        fill.shares = 100
        fill.slippage = 0.0
        engine._execution.simulate_fill = Mock(return_value=fill)

        engine._resolve_pending_fills(state, date(2024, 1, 3))

        # No gap rejection (open > stop)
        assert len(engine._gap_rejections) == 0
        engine._execution.simulate_fill.assert_called_once()

    def test_position_blocked_by_risk_rules(self):
        """Entry blocked by can_enter_position after gap check passes."""
        engine, config = self._make_engine()
        state = BacktestState(initial_capital=100000, start_date=date(2024, 1, 2))

        signal = EntrySignal(
            ticker='AAPL',
            side='LONG',
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector='Technology',
            entry_score=80,
            stage2_score=7,
        )
        engine._pending_entries = [signal]

        engine.data_provider.get_current_price = Mock(return_value=148.0)

        # Risk rules block the entry
        state.can_enter_position = Mock(return_value=(False, 'Sector limit reached'))

        engine._resolve_pending_fills(state, date(2024, 1, 3))

        # No gap rejection (gap check passed)
        assert len(engine._gap_rejections) == 0

        # But no position created (risk blocked)
        assert 'AAPL' not in state.positions

    def test_missing_price_skips_entry(self):
        """Missing T+1 price → entry skipped."""
        engine, config = self._make_engine()
        state = BacktestState(initial_capital=100000, start_date=date(2024, 1, 2))

        signal = EntrySignal(
            ticker='AAPL',
            side='LONG',
            entry_price=150.0,
            stop_price=140.0,
            target_price=170.0,
            shares=100,
            sector='Technology',
            entry_score=80,
            stage2_score=7,
        )
        engine._pending_entries = [signal]

        engine.data_provider.get_current_price = Mock(return_value=None)

        engine._resolve_pending_fills(state, date(2024, 1, 3))

        assert 'AAPL' not in state.positions
        assert len(engine._gap_rejections) == 0  # No rejection, just skip