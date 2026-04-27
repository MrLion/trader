#!/usr/bin/env python3
"""Tests for clean_test_trades.py.

Covers pure logic functions:
- is_test_entry — pattern detection
- analyze_trades — duplicate detection, split
- load_trades — JSONL parsing, malformed lines, missing file
- save_trades — round-trip
- create_backup — backup creation
- main — argparse, dry-run, auto mode
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import clean_test_trades as ctt


class TestIsTestEntry:
    """Test is_test_entry detection logic."""

    def test_test_mode_flag(self):
        trade = {'_meta': {'test_mode': True}, 'ticker': 'AAPL', 'entry_price': 100}
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason == 'test_mode_flag'

    def test_aapl_at_150(self):
        trade = {'ticker': 'AAPL', 'entry_price': 150.0}
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason == 'test_pattern_aapl_150'

    def test_validation_failed_test_tickers(self):
        trade = {'_meta': {'validation_failed': True}, 'ticker': 'MSFT', 'entry_price': 100}
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'validation_failed_test' in reason

    def test_missing_required_field(self):
        trade = {'ticker': 'AAPL', 'entry_price': 100}  # missing 'event', 'timestamp', 'shares'
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason.startswith('missing_')

    def test_known_test_ticker_exact_price(self):
        trade = {
            'ticker': 'AAPL', 'entry_price': 200.0, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'known_test_ticker' in reason

    def test_stock_pattern(self):
        trade = {
            'ticker': 'STOCK7', 'entry_price': 100, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'test_stock_pattern' in reason

    def test_old_date_2024(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 100, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2024-06-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason == 'old_date_2024'

    def test_old_date_2025(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 100, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2025-06-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason == 'old_date_2025'

    def test_known_pattern_500_1000(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 500.0, 'shares': 1000,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert reason == 'known_test_pattern_500_1000'

    def test_unrealistic_price(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 9999.0, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'unrealistic_price' in reason

    def test_unrealistic_shares(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 100, 'shares': 1000,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'unrealistic_shares' in reason

    def test_unrealistic_value(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 1000, 'shares': 100,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is True
        assert 'unrealistic_value' in reason

    def test_strict_mode_synthetic_timestamp(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 100, 'shares': 10,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00.000000'
        }
        is_test, reason = ctt.is_test_entry(trade, strict=True)
        assert is_test is True
        assert reason == 'synthetic_timestamp'

    def test_strict_mode_unrealistic_pnl(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 100, 'shares': 10,
            'event': 'EXIT', 'timestamp': '2026-04-01T10:00:00',
            'realized_pnl': 50000
        }
        is_test, reason = ctt.is_test_entry(trade, strict=True)
        assert is_test is True
        assert 'unrealistic_pnl' in reason

    def test_production_entry_passes(self):
        trade = {
            'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50,
            'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'
        }
        is_test, reason = ctt.is_test_entry(trade)
        assert is_test is False
        assert reason == ""


class TestAnalyzeTrades:
    """Test analyze_trades."""

    def test_splits_production_and_test(self):
        trades = [
            {'ticker': 'AAPL', 'entry_price': 150.0, 'shares': 100, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'},
            {'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50, 'event': 'ENTRY', 'timestamp': '2026-04-01T11:00:00'},
        ]
        prod, test, stats = ctt.analyze_trades(trades)
        assert len(prod) == 1
        assert len(test) == 1
        assert stats['total'] == 2
        assert prod[0]['ticker'] == 'XOM'
        assert test[0]['ticker'] == 'AAPL'

    def test_detects_duplicates(self):
        trades = [
            {'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'},
            {'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'},
        ]
        prod, test, stats = ctt.analyze_trades(trades)
        assert len(prod) == 1
        assert len(test) == 1
        assert stats['reasons']['duplicate'] == 1

    def test_empty_list(self):
        prod, test, stats = ctt.analyze_trades([])
        assert prod == []
        assert test == []
        assert stats['total'] == 0


class TestLoadTrades:
    """Test load_trades."""

    def test_loads_valid_jsonl(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text(json.dumps({'ticker': 'AAPL'}) + '\n' + json.dumps({'ticker': 'MSFT'}) + '\n')
        trades = ctt.load_trades(f)
        assert len(trades) == 2
        assert trades[0]['ticker'] == 'AAPL'

    def test_skips_malformed_lines(self, tmp_path, capsys):
        f = tmp_path / 'trades.jsonl'
        f.write_text(json.dumps({'ticker': 'AAPL'}) + '\nnot json\n')
        trades = ctt.load_trades(f)
        assert len(trades) == 1

    def test_missing_file_returns_empty(self, tmp_path, capsys):
        trades = ctt.load_trades(tmp_path / 'missing.jsonl')
        assert trades == []


class TestSaveTrades:
    """Test save_trades round-trip."""

    def test_round_trip(self, tmp_path):
        f = tmp_path / 'out.jsonl'
        trades = [{'ticker': 'AAPL'}, {'ticker': 'MSFT'}]
        ctt.save_trades(trades, f)
        loaded = ctt.load_trades(f)
        assert len(loaded) == 2
        assert loaded[0]['ticker'] == 'AAPL'


class TestCreateBackup:
    """Test create_backup."""

    def test_creates_backup(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text('data')
        backup = ctt.create_backup(f)
        assert backup.exists()
        assert backup.read_text() == 'data'

    def test_missing_file_returns_path_anyway(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        backup = ctt.create_backup(f)
        assert not backup.exists()


class TestMain:
    """Test main() entry point."""

    def test_dry_run_no_changes(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text(json.dumps({'ticker': 'AAPL', 'entry_price': 150.0, 'shares': 100, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'}) + '\n')
        test_args = ['clean_test_trades.py', '--dry-run', '--file', str(f)]
        with patch.object(sys, 'argv', test_args):
            result = ctt.main()
        assert result == 0

    def test_auto_mode_cleans_file(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text(
            json.dumps({'ticker': 'AAPL', 'entry_price': 150.0, 'shares': 100, 'event': 'ENTRY', 'timestamp': '2026-04-01T10:00:00'}) + '\n' +
            json.dumps({'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50, 'event': 'ENTRY', 'timestamp': '2026-04-01T11:00:00'}) + '\n'
        )
        test_args = ['clean_test_trades.py', '--auto', '--file', str(f)]
        with patch.object(sys, 'argv', test_args):
            with patch('builtins.input', return_value='clean'):
                result = ctt.main()
        assert result == 0
        # Verify only production trade remains
        trades = ctt.load_trades(f)
        assert len(trades) == 1
        assert trades[0]['ticker'] == 'XOM'

    def test_no_test_entries_returns_zero(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text(json.dumps({'ticker': 'XOM', 'entry_price': 85.5, 'shares': 50, 'event': 'ENTRY', 'timestamp': '2026-04-01T11:00:00'}) + '\n')
        test_args = ['clean_test_trades.py', '--auto', '--file', str(f)]
        with patch.object(sys, 'argv', test_args):
            result = ctt.main()
        assert result == 0

    def test_empty_file_returns_one(self, tmp_path):
        f = tmp_path / 'trades.jsonl'
        f.write_text('')
        test_args = ['clean_test_trades.py', '--file', str(f)]
        with patch.object(sys, 'argv', test_args):
            result = ctt.main()
        assert result == 1
