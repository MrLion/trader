#!/usr/bin/env python3
"""Tests for entry_signals module."""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from entry_signals import EntrySignalScanner
from traderlib.risk_config import RiskConfigManager


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
        assert scanner.spy_cache == {'date': None, 'return_6m': 0.0, 'price': None}


class TestGetSPYReturn:
    """Test _get_spy_return_6m method."""

    def test_spy_cache_hit(self, scanner):
        """Test that cached value is returned on same day."""
        today = datetime.now().strftime('%Y-%m-%d')
        scanner.spy_cache = {'date': today, 'return_6m': 15.5, 'price': 450.0}

        result = scanner._get_spy_return_6m()

        assert result == 15.5

    def test_spy_cache_miss_fetches_data(self, scanner, mock_alpaca):
        """Test that data is fetched when cache is empty."""
        # Create mock historical data
        hist_data = pd.DataFrame({
            'Close': [400.0] * 130 + [450.0]  # 130 days ago + current
        })
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = scanner._get_spy_return_6m()

        expected_return = ((450.0 / 400.0) - 1) * 100
        assert abs(result - expected_return) < 0.01
        mock_alpaca.get_historical_bars.assert_called_once_with('SPY')
        assert scanner.spy_cache['return_6m'] == result

    def test_spy_insufficient_data_returns_zero(self, scanner, mock_alpaca):
        """Test that zero is returned when insufficient data."""
        hist_data = pd.DataFrame({'Close': [450.0] * 50})  # Only 50 bars
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = scanner._get_spy_return_6m()

        assert result == 0.0

    def test_spy_exception_returns_zero(self, scanner, mock_alpaca):
        """Test that zero is returned on exception."""
        mock_alpaca.get_historical_bars.side_effect = Exception('API error')

        result = scanner._get_spy_return_6m()

        assert result == 0.0


class TestGetCurrentPrice:
    """Test _get_current_price method."""

    def test_get_price_from_quote(self, scanner, mock_alpaca):
        """Test price fetched from get_latest_price."""
        mock_alpaca.get_latest_price.return_value = 150.0

        result = scanner._get_current_price('AAPL')

        assert result == 150.0

    def test_get_price_from_close(self, scanner, mock_alpaca):
        """Test fallback to historical bars when get_latest_price returns None."""
        mock_alpaca.get_latest_price.return_value = None
        hist_data = pd.DataFrame({'Close': [145.0, 146.0, 149.5]})
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = scanner._get_current_price('AAPL')

        assert result == 149.5

    def test_get_price_fallback_to_historical(self, scanner, mock_alpaca):
        """Test fallback to historical bars when get_latest_price returns None."""
        mock_alpaca.get_latest_price.return_value = None
        hist_data = pd.DataFrame({'Close': [145.0, 146.0, 147.0]})
        mock_alpaca.get_historical_bars.return_value = hist_data

        result = scanner._get_current_price('AAPL')

        assert result == 147.0

    def test_get_price_returns_none_when_all_fail(self, scanner, mock_alpaca):
        """Test None returned when all price sources fail."""
        mock_alpaca.get_latest_price.return_value = None
        mock_alpaca.get_historical_bars.return_value = None

        result = scanner._get_current_price('AAPL')

        assert result is None


class TestCheckMarketConditions:
    """Test _check_market_conditions method."""

    @patch('yfinance.Ticker')
    def test_market_ok_when_spy_flat(self, mock_ticker_class, scanner):
        """Test market OK when SPY is flat."""
        scanner._get_current_price = Mock(return_value=450.0)

        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame({'Close': [450.0, 450.0]})
        mock_ticker_class.return_value = mock_ticker

        result, msg = scanner._check_market_conditions()

        assert result is True
        assert '0.00%' in msg

    @patch('yfinance.Ticker')
    def test_market_blocked_when_spy_declines(self, mock_ticker_class, scanner):
        """Test market blocked when SPY declines below threshold."""
        scanner._get_current_price = Mock(return_value=440.0)

        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame({'Close': [450.0, 440.0]})
        mock_ticker_class.return_value = mock_ticker

        result, msg = scanner._check_market_conditions()

        assert result is False
        assert '-2.22%' in msg

    def test_market_ok_when_no_spy_price(self, scanner):
        """Test market OK when SPY price unavailable."""
        scanner._get_current_price = Mock(return_value=None)

        result, msg = scanner._check_market_conditions()

        assert result is True
        assert 'unavailable' in msg


class TestAnalyzeTicker:
    """Test _analyze_ticker method."""

    def test_analyze_insufficient_data_returns_none(self, scanner, mock_alpaca):
        """Test None returned when insufficient historical data."""
        mock_alpaca.get_historical_bars.return_value = pd.DataFrame({'Close': [100.0] * 10})

        result = scanner._analyze_ticker('AAPL')

        assert result is None

    def test_analyze_no_price_returns_none(self, scanner):
        """Test None returned when price unavailable."""
        scanner._get_current_price = Mock(return_value=None)

        result = scanner._analyze_ticker('AAPL')

        assert result is None

    @patch('entry_signals.calculate_stage2_score')
    @patch('entry_signals.get_entry_score')
    @patch('entry_signals.pd.read_csv')
    def test_analyze_valid_ticker(self, mock_read_csv, mock_get_entry_score, mock_stage2, scanner, mock_alpaca):
        """Test analysis of valid ticker."""
        # Mock historical data
        hist_data = pd.DataFrame({
            'Close': [100.0 + i * 0.5 for i in range(130)] + [150.0],
            'High': [101.0 + i * 0.5 for i in range(130)] + [151.0],
            'Low': [99.0 + i * 0.5 for i in range(130)] + [149.0],
            'Volume': [1000000] * 131
        })
        mock_alpaca.get_historical_bars.return_value = hist_data

        # Mock stage2 score
        mock_stage2.return_value = 7

        # Mock entry score
        mock_get_entry_score.return_value = 85

        # Mock watchlist
        mock_watchlist = pd.DataFrame({
            'Ticker': ['AAPL'],
            'Pivot_Price': [150.0],
            'Sector': ['Technology']
        })
        mock_read_csv.return_value = mock_watchlist

        # Mock price and SPY return
        scanner._get_current_price = Mock(return_value=150.0)
        scanner._get_spy_return_6m = Mock(return_value=15.0)

        result = scanner._analyze_ticker('AAPL')

        assert result is not None
        assert result['ticker'] == 'AAPL'
        assert result['current'] == 150.0
        assert result['sector'] == 'Technology'


class TestLoadWatchlist:
    """Test _load_watchlist method."""

    @patch('entry_signals.pd.read_csv')
    def test_load_watchlist_success(self, mock_read_csv, scanner):
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
        scanner._check_market_conditions = Mock(return_value=(True, "SPY OK"))

        # Mock ticker analysis
        scanner._analyze_ticker = Mock(return_value={
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'entry_score': 85,
            'tier': 'Tier 1',
            'dist_to_pivot': 0.0,
            'stage2': 7,
            'sector': 'Tech',
            'risk_pct': 5.0
        })

        result = scanner.scan(tickers=['AAPL'], min_tier=1)

        assert len(result) == 1
        assert result[0]['ticker'] == 'AAPL'

    def test_scan_returns_only_tier1_signals(self, scanner):
        """Test scan only returns Tier 1 ready signals."""
        scanner._check_market_conditions = Mock(return_value=(True, "SPY OK"))

        # Return Tier 1 signal (score >= 60, within ±1%)
        scanner._analyze_ticker = Mock(return_value={
            'ticker': 'AAPL',
            'current': 150.0,
            'pivot': 150.0,
            'entry_score': 85,  # Tier 1 score
            'tier': 'Tier 1',
            'dist_to_pivot': 0.0,  # Within ±1%
            'stage2': 7,
            'sector': 'Tech',
            'risk_pct': 5.0
        })

        # Should return Tier 1 signals
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
            assert scanner.risk_config.entry.max_dist_to_pivot_pct == 2.0

    def test_scanner_default_max_spy_decline(self):
        """Test default max_spy_decline_pct from risk config."""
        with patch('entry_signals.AlpacaClient'):
            scanner = EntrySignalScanner(mode='paper')
            assert scanner.risk_config.market.max_spy_decline_pct == -0.5

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
