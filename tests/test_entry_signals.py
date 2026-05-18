#!/usr/bin/env python3
"""Tests for entry_signals module."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest


from entry_signals import EntrySignalScanner
from traderlib.risk_config import RiskConfigManager
from traderlib.ticker_analyzer import TickerAnalysis


@pytest.fixture
def mock_alpaca():
    """Fixture for mocked Alpaca client."""
    with patch('entry_signals.AlpacaClient') as mock_class:
        mock_instance = Mock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def scanner(mock_alpaca):
    """Fixture for EntrySignalScanner with mocked dependencies."""
    return EntrySignalScanner(mode='paper')


class TestEntrySignalScanner:
    """Test EntrySignalScanner initialization."""

    def test_initialization(self, scanner):
        """Test scanner initializes correctly."""
        assert hasattr(scanner, 'analyzer')
        assert scanner.analyzer is not None


class TestLoadWatchlist:
    """Test _load_watchlist method."""

    @patch('entry_signals.Path.exists', return_value=True)
    @patch('entry_signals.pd.read_csv')
    def test_load_watchlist_success(self, mock_read_csv, mock_exists, scanner):
        """Test successful watchlist loading."""
        mock_watchlist = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT', 'GOOGL'],
            'Sector': ['Tech', 'Tech', 'Tech']
        })
        mock_read_csv.return_value = mock_watchlist

        result = scanner._load_watchlist()

        assert result == ['AAPL', 'MSFT', 'GOOGL']

    @patch('entry_signals.pd.read_csv')
    def test_load_watchlist_missing_ticker_column(self, mock_read_csv, scanner):
        """Test empty list when Ticker column missing."""
        mock_watchlist = pd.DataFrame({
            'Symbol': ['AAPL', 'MSFT']  # Wrong column name
        })
        mock_read_csv.return_value = mock_watchlist

        result = scanner._load_watchlist()

        assert result == []

    def test_load_watchlist_file_not_found(self, scanner):
        """Test empty list when file not found."""
        with patch('entry_signals.pd.read_csv', side_effect=FileNotFoundError()):
            result = scanner._load_watchlist()

        assert result == []


class TestScan:
    """Test scan method."""

    def test_scan_with_ready_signals(self, scanner):
        """Test scan returns ready signals."""
        # Mock market conditions
        scanner.analyzer.check_market_conditions = Mock(return_value=(True, "SPY OK", None))

        # Mock ticker analysis
        mock_analysis = TickerAnalysis(
            ticker='AAPL',
            current=150.0,
            stage2=8,
            entry_score=85,
            tier='Tier 1',
            pivot=150.0,
            pivot_type='manual',
            dist_to_pivot=0.0,
            stop=142.5,
            target=165.0,
            sector='Tech',
            risk_pct=5.0,
        )
        scanner.analyzer.analyze = Mock(return_value=mock_analysis)
        scanner.earnings_calendar.get_next_earnings = Mock(return_value=None)

        result = scanner.scan(tickers=['AAPL'], min_tier=1)

        assert len(result) == 1
        assert result[0]['ticker'] == 'AAPL'

    def test_scan_returns_only_tier1_signals(self, scanner):
        """Test scan only returns Tier 1 ready signals."""
        scanner.analyzer.check_market_conditions = Mock(return_value=(True, "SPY OK", None))

        mock_analysis = TickerAnalysis(
            ticker='AAPL',
            current=150.0,
            stage2=8,
            entry_score=85,
            tier='Tier 1',
            pivot=150.0,
            pivot_type='manual',
            dist_to_pivot=0.0,
            stop=142.5,
            target=165.0,
            sector='Tech',
            risk_pct=5.0,
        )
        scanner.analyzer.analyze = Mock(return_value=mock_analysis)
        scanner.earnings_calendar.get_next_earnings = Mock(return_value=None)

        result = scanner.scan(tickers=['AAPL'])
        assert len(result) == 1
        assert result[0]['ticker'] == 'AAPL'
        assert result[0]['tier'] == 'Tier 1'

    def test_scan_empty_tickers(self, scanner):
        """Test scan returns empty list when no tickers."""
        scanner._load_watchlist = Mock(return_value=[])

        result = scanner.scan()

        assert result == []


class TestExportSignals:
    """Test export_signals method."""

    def test_export_empty_signals(self, scanner):
        """Test export with empty signals does nothing."""
        # Should not raise
        scanner.export_signals([])

    @patch('entry_signals.pd.DataFrame')
    @patch('entry_signals.SCANS_DIR')
    def test_export_csv_format(self, mock_scans_dir, mock_df_class, scanner):
        """Test export to CSV format."""
        signals = [{'ticker': 'AAPL', 'score': 85}]
        mock_df = Mock()
        mock_df_class.return_value = mock_df

        scanner.export_signals(signals, format='csv')

        mock_df.to_csv.assert_called_once()


class TestRiskConfigIntegration:
    """Test RiskConfigManager integration with scanner."""

    def test_scanner_uses_risk_config_manager(self):
        """Test scanner initializes with RiskConfigManager."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper')
            assert hasattr(scanner, 'risk_manager')
            assert isinstance(scanner.risk_manager, RiskConfigManager)
            assert hasattr(scanner, 'risk_config')

    def test_scanner_default_entry_threshold(self):
        """Test default min_entry_score from risk config."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper')
            assert scanner.risk_config.entry.min_entry_score == 60

    def test_scanner_default_max_dist_to_pivot(self):
        """Test default max_dist_to_pivot_pct from risk config."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper')
            assert scanner.risk_config.entry.max_dist_to_pivot_pct == 3.0

    def test_scanner_default_max_spy_decline(self):
        """Test default max_spy_decline_pct from risk config."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper')
            assert scanner.risk_config.market.max_spy_decline_pct == -1.0

    def test_scanner_uses_custom_risk_profile(self):
        """Test scanner loads custom risk profile."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper', risk_profile='conservative')
            # Conservative profile has 0.005 risk per trade
            assert scanner.risk_config.account.risk_per_trade_pct == 0.005

    def test_scanner_invalid_profile_uses_default(self):
        """Test scanner falls back to default on invalid profile."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper', risk_profile='nonexistent')
            # Should still have valid config with defaults
            assert scanner.risk_config.entry.min_entry_score == 60


class TestEntrySignalsSector:
    """Test universe path wiring for sector resolution."""

    def test_scan_sets_universe_path_for_universe_source(self, scanner, tmp_path):
        """Test that scanning from a universe profile sets the analyzer's universe path."""
        scanner.analyzer.check_market_conditions = Mock(return_value=(True, "SPY OK", None))
        scanner.analyzer.analyze = Mock(return_value=None)
        scanner.earnings_calendar.get_next_earnings = Mock(return_value=None)

        # Create a fake universe CSV
        universe_dir = tmp_path / "universes"
        universe_dir.mkdir()
        universe_csv = universe_dir / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(universe_csv, index=False)

        # Point scanner's DATA_DIR to tmp_path
        with patch("entry_signals.DATA_DIR", tmp_path):
            scanner.scan(tickers=["AAPL"], source="large_cap")

        assert scanner.analyzer._universe_path == universe_csv
