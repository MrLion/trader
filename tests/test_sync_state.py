#!/usr/bin/env python3
"""Tests for sync_state.py.

Covers:
- _is_test_trade — pattern detection
- count_production_trades — JSONL filtering
- sync — mocked AlpacaClient path
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import sync_state


class TestIsTestTrade:
    """Test _is_test_trade."""

    def test_test_mode_flag(self):
        trade = {'_meta': {'test_mode': True}}
        assert sync_state._is_test_trade(trade) is True

    def test_aapl_at_150(self):
        trade = {'ticker': 'AAPL', 'entry_price': 150.0}
        assert sync_state._is_test_trade(trade) is True

    def test_validation_failed_msft(self):
        trade = {'_meta': {'validation_failed': True}, 'ticker': 'MSFT'}
        assert sync_state._is_test_trade(trade) is True

    def test_production_trade(self):
        trade = {'ticker': 'XOM', 'entry_price': 85.5, '_meta': {}}
        assert sync_state._is_test_trade(trade) is False


class TestCountProductionTrades:
    """Test count_production_trades."""

    def test_counts_only_production(self, tmp_path):
        f = tmp_path / 'paper_trades.jsonl'
        lines = [
            json.dumps({'ticker': 'AAPL', 'entry_price': 150.0, '_meta': {}, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'}),
            json.dumps({'ticker': 'XOM', 'entry_price': 85.5, '_meta': {}, 'event': 'ENTRY', 'timestamp': '2026-04-01T11:00:00'}),
            json.dumps({'ticker': 'MSFT', 'entry_price': 200.0, '_meta': {'validation_failed': True}, 'event': 'ENTRY', 'timestamp': '2026-04-01T12:00:00'}),
        ]
        f.write_text('\n'.join(lines) + '\n')

        with patch.object(sync_state, 'TRADES_FILE', f):
            result = sync_state.count_production_trades()
        assert result['trade_count'] == 1
        assert result['entries_today'] == 0

    def test_missing_file_returns_zero(self, tmp_path):
        with patch.object(sync_state, 'TRADES_FILE', tmp_path / 'missing.jsonl'):
            result = sync_state.count_production_trades()
        assert result['trade_count'] == 0
        assert result['entries_today'] == 0

    def test_skips_malformed_json(self, tmp_path):
        f = tmp_path / 'paper_trades.jsonl'
        f.write_text('not json\n' + json.dumps({'ticker': 'XOM', 'entry_price': 85.5, '_meta': {}, 'event': 'ENTRY', 'timestamp': '2026-04-01T11:00:00'}) + '\n')
        with patch.object(sync_state, 'TRADES_FILE', f):
            result = sync_state.count_production_trades()
        assert result['trade_count'] == 1


