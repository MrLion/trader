#!/usr/bin/env python3
"""Tests for cooldown state rebuild from trade log and daily reset fix."""

import json
import os
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(event, ticker, timestamp, realized_pnl=None,
                test_mode=False, entry_price=100.0, shares=10):
    """Create a trade record dict matching paper_trades.jsonl format."""
    trade = {
        'event': event,
        'timestamp': timestamp,
        'ticker': ticker,
        'entry_price': entry_price,
        'shares': shares,
    }
    if event == 'EXIT':
        trade['realized_pnl'] = realized_pnl
        trade['exit_price'] = entry_price + (realized_pnl / shares) if realized_pnl else entry_price
        trade['exit_reason'] = 'stop'
        trade['stop_type'] = 'HARD'
    trade['_meta'] = {
        'test_mode': test_mode,
        'data_dir': '/tmp/test_data',
        'source': 'paper_state',
    }
    if test_mode:
        trade['_meta']['validation_failed'] = True
    return trade


def _write_trades(trades_file, trades):
    """Write a list of trade dicts to a JSONL file."""
    with open(trades_file, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')


def _make_risk_config():
    """Create a mock risk config with cooldown settings."""
    mock_config = MagicMock()
    mock_config.cooldown.reentry_cooldown_minutes = 300
    mock_config.cooldown.max_cooldown_minutes = 240
    mock_config.cooldown.consecutive_loss_multiplier = 2.0
    mock_config.cooldown.min_loss_to_trigger_cooldown_pct = 0.0
    return mock_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def trades_file(tmp_path):
    """Return path to a trades file in a temp directory."""
    return tmp_path / 'paper_trades.jsonl'


@pytest.fixture
def cooldown_engine(trades_file):
    """Create a minimal engine with cooldown state and patched TRADES_FILE."""
    from scripts.paper_engine_alpaca import AlpacaPaperEngine
    import scripts.paper_engine_alpaca as engine_mod

    risk_config = _make_risk_config()

    # Use object.__new__ to skip __init__
    engine = object.__new__(AlpacaPaperEngine)
    engine.risk_config = risk_config
    engine.last_exit_time = {}
    engine.consecutive_losses = {}
    engine.signaled_tickers = set()
    engine.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

    # Mock state._is_test_trade to delegate to PaperState._is_test_trade
    from traderlib.paper_state import PaperState
    real_state = object.__new__(PaperState)
    real_state.initial_capital = 100000
    real_state.positions = {}
    engine.state = real_state

    # Patch TRADES_FILE in the module namespace so the method reads from our temp file
    with patch.object(engine_mod, 'TRADES_FILE', trades_file):
        yield engine, trades_file


# ---------------------------------------------------------------------------
# Test: Rebuild from trade log
# ---------------------------------------------------------------------------

class TestRebuildFromTradeLog:

    def test_rebuild_populates_dicts(self, cooldown_engine):
        """Recent EXIT events rebuild cooldown state correctly."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        trades = [
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=30)).isoformat(), realized_pnl=-50.0),
            _make_trade('EXIT', 'TSLA', (now - timedelta(minutes=60)).isoformat(), realized_pnl=20.0),
        ]
        _write_trades(trades_file, trades)

        engine._rebuild_cooldown_state()

        assert 'AAPL' in engine.last_exit_time
        assert 'TSLA' in engine.last_exit_time
        # AAPL had a loss
        assert engine.consecutive_losses.get('AAPL') == 1
        # TSLA had a profit - no consecutive losses
        assert 'TSLA' not in engine.consecutive_losses

    def test_rebuild_ignores_old_exits(self, cooldown_engine):
        """EXIT events outside max_cooldown_minutes window are skipped."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        # Exit 500 minutes ago (well beyond the 240min max_cooldown window)
        old_trade = _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=500)).isoformat(), realized_pnl=-100.0)
        # Recent exit within window
        recent_trade = _make_trade('EXIT', 'TSLA', (now - timedelta(minutes=30)).isoformat(), realized_pnl=-50.0)
        _write_trades(trades_file, [old_trade, recent_trade])

        engine._rebuild_cooldown_state()

        assert 'TSLA' in engine.last_exit_time
        assert 'AAPL' not in engine.last_exit_time

    def test_rebuild_ignores_test_trades(self, cooldown_engine):
        """Trades with _meta.test_mode: true are skipped."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        test_trade = _make_trade('EXIT', 'MSFT', (now - timedelta(minutes=30)).isoformat(),
                                 realized_pnl=-50.0, test_mode=True)
        real_trade = _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=60)).isoformat(),
                                 realized_pnl=-30.0, test_mode=False)
        _write_trades(trades_file, [test_trade, real_trade])

        engine._rebuild_cooldown_state()

        assert 'AAPL' in engine.last_exit_time
        assert 'MSFT' not in engine.last_exit_time

    def test_rebuild_profit_resets_losses(self, cooldown_engine):
        """Profit exit sets last_exit_time but resets consecutive_losses."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        trades = [
            # Earlier: loss
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=120)).isoformat(), realized_pnl=-50.0),
            # Most recent: profit
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=30)).isoformat(), realized_pnl=20.0),
        ]
        _write_trades(trades_file, trades)

        engine._rebuild_cooldown_state()

        assert 'AAPL' in engine.last_exit_time
        # Profit resets consecutive losses
        assert 'AAPL' not in engine.consecutive_losses

    def test_rebuild_consecutive_losses(self, cooldown_engine):
        """Three losses in a row gives consecutive_losses[ticker] == 3."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        trades = [
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=180)).isoformat(), realized_pnl=-10.0),
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=120)).isoformat(), realized_pnl=-20.0),
            _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=30)).isoformat(), realized_pnl=-30.0),
        ]
        _write_trades(trades_file, trades)

        engine._rebuild_cooldown_state()

        assert engine.consecutive_losses.get('AAPL') == 3

    def test_rebuild_missing_trade_log(self, cooldown_engine):
        """No crash when trade log file doesn't exist."""
        engine, trades_file = cooldown_engine
        # Don't write any trades file - it may or may not exist in tmp_path
        if trades_file.exists():
            trades_file.unlink()

        engine._rebuild_cooldown_state()
        assert len(engine.last_exit_time) == 0
        assert len(engine.consecutive_losses) == 0

    def test_rebuild_malformed_json(self, cooldown_engine):
        """Malformed JSON lines are skipped, not crashed on."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        good_trade = _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=30)).isoformat(), realized_pnl=-50.0)
        with open(trades_file, 'w') as f:
            f.write('this is not json\n')
            f.write('{"broken json\n')
            f.write(json.dumps(good_trade) + '\n')

        engine._rebuild_cooldown_state()

        assert 'AAPL' in engine.last_exit_time


# ---------------------------------------------------------------------------
# Test: Cooldown blocks after restart
# ---------------------------------------------------------------------------

class TestCooldownBlocksAfterRestart:

    def test_cooldown_blocks_after_restart(self, cooldown_engine):
        """After rebuilding state, _check_cooldown still blocks re-entry."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        # AAPL exited at a loss 30 minutes ago (cooldown = 300 min base)
        trade = _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=30)).isoformat(), realized_pnl=-50.0)
        _write_trades(trades_file, [trade])

        engine._rebuild_cooldown_state()

        can_enter, reason = engine._check_cooldown('AAPL')
        assert can_enter is False
        assert 'Cooldown' in reason

    def test_cooldown_allows_after_expiry(self, cooldown_engine):
        """After cooldown expires, re-entry is allowed."""
        engine, trades_file = cooldown_engine
        now = datetime.now()
        # AAPL exited at a loss 400 minutes ago (base cooldown = 300 min, so expired)
        trade = _make_trade('EXIT', 'AAPL', (now - timedelta(minutes=400)).isoformat(), realized_pnl=-50.0)
        _write_trades(trades_file, [trade])

        engine._rebuild_cooldown_state()

        can_enter, reason = engine._check_cooldown('AAPL')
        assert can_enter is True
        assert reason is None


# ---------------------------------------------------------------------------
# Test: Expired cooldown cleared on daily reset
# ---------------------------------------------------------------------------

class TestDailyResetPreservesActiveCooldowns:

    def test_expired_cooldown_cleared_on_daily_reset(self, cooldown_engine):
        """Expired cooldowns are removed, active ones preserved."""
        engine, _ = cooldown_engine
        now = datetime.now()

        # Set up cooldown state: one expired, one active
        engine.last_exit_time['EXPIRED'] = now - timedelta(minutes=400)
        engine.consecutive_losses['EXPIRED'] = 1

        engine.last_exit_time['ACTIVE'] = now - timedelta(minutes=30)
        engine.consecutive_losses['ACTIVE'] = 2

        # Set last_signal_reset to yesterday to trigger daily reset
        engine.last_signal_reset = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        engine._reset_daily_signals()

        # EXPIRED should be removed
        assert 'EXPIRED' not in engine.last_exit_time
        assert 'EXPIRED' not in engine.consecutive_losses

        # ACTIVE should be preserved
        assert 'ACTIVE' in engine.last_exit_time
        assert engine.consecutive_losses.get('ACTIVE') == 2

        # Signals should be cleared
        assert len(engine.signaled_tickers) == 0

    def test_all_expired_cleared(self, cooldown_engine):
        """When all cooldowns are expired, all are removed."""
        engine, _ = cooldown_engine
        now = datetime.now()

        engine.last_exit_time['OLD1'] = now - timedelta(minutes=400)
        engine.consecutive_losses['OLD1'] = 1
        engine.last_exit_time['OLD2'] = now - timedelta(minutes=500)
        engine.consecutive_losses['OLD2'] = 3

        engine.last_signal_reset = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        engine._reset_daily_signals()

        assert len(engine.last_exit_time) == 0
        assert len(engine.consecutive_losses) == 0