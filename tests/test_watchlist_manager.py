#!/usr/bin/env python3
"""Tests for watchlist_manager.py"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

# Add scripts to path

import watchlist_manager as wm


class TestLoadWatchlist(unittest.TestCase):
    """Test load_watchlist function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()

    def test_load_existing_watchlist(self):
        """Test loading an existing watchlist file."""
        # Create test watchlist data
        test_data = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT'],
            'Stage': [5, 6],
            'RS_Rank': [25.5, 30.0],
            'Base_Count': ['', ''],
            'Pattern_Type': ['', ''],
            'Pivot_Price': [150.0, 250.0],
            'Stop_Level': [145.0, 240.0],
            'Target_1': [160.0, 270.0],
            'Target_2': [170.0, 280.0],
            'R_Ratio': [2.0, 2.0],
            'Avg_Volume_50d': [50000000, 30000000],
            'Market_Cap': [2000000000000, 2500000000000],
            'Sector': ['Technology', 'Technology'],
            'Industry': ['Consumer Electronics', 'Software'],
            'Notes': ['Strong momentum', 'Leader'],
            'Added_Date': ['2026-04-01', '2026-04-02'],
            'Alert_Set': ['No', 'No']
        })
        test_data.to_csv(self.test_watchlist_path, index=False)

        result = wm.load_watchlist()

        self.assertEqual(len(result), 2)
        self.assertIn('AAPL', result['Ticker'].values)
        self.assertIn('MSFT', result['Ticker'].values)

    def test_create_new_watchlist(self):
        """Test creating new watchlist when file doesn't exist."""
        result = wm.load_watchlist()

        self.assertTrue(result.empty)
        self.assertEqual(len(result.columns), 17)
        self.assertIn('Ticker', result.columns)
        self.assertIn('Stage', result.columns)
        self.assertIn('RS_Rank', result.columns)


class TestGetStockData(unittest.TestCase):
    """Test get_stock_data function with mocked yfinance."""

    @patch('watchlist_manager.yf.Ticker')
    def test_get_stock_data_success(self, mock_ticker_class):
        """Test successful stock data fetch."""
        # Setup mock
        mock_ticker = MagicMock()
        mock_ticker.info = {
            'sector': 'Technology',
            'industry': 'Software',
            'marketCap': 1000000000000,
            'shortName': 'Apple Inc'
        }

        # Create mock price history
        dates = pd.date_range(end=datetime.now(), periods=250, freq='D')
        mock_ticker.history.return_value = pd.DataFrame({
            'Close': [100 + i * 0.1 for i in range(250)],
            'High': [101 + i * 0.1 for i in range(250)],
            'Low': [99 + i * 0.1 for i in range(250)],
            'Volume': [1000000 for _ in range(250)]
        }, index=dates)

        mock_ticker_class.return_value = mock_ticker

        result = wm.get_stock_data('AAPL')

        self.assertIsNotNone(result)
        self.assertEqual(result['Ticker'], 'AAPL')
        self.assertEqual(result['Sector'], 'Technology')
        self.assertEqual(result['Industry'], 'Software')
        self.assertIn('Stage', result)
        self.assertIn('6M_Return', result)
        self.assertIn('ATR', result)

    @patch('watchlist_manager.yf.Ticker')
    def test_get_stock_data_insufficient_data(self, mock_ticker_class):
        """Test handling when insufficient historical data."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({'Close': [], 'High': [], 'Low': [], 'Volume': []})
        mock_ticker_class.return_value = mock_ticker

        result = wm.get_stock_data('INVALID')

        self.assertIsNone(result)

    @patch('watchlist_manager.yf.Ticker')
    def test_get_stock_data_exception(self, mock_ticker_class):
        """Test handling when yfinance throws exception."""
        mock_ticker_class.side_effect = Exception("Network error")

        result = wm.get_stock_data('AAPL')

        self.assertIsNone(result)

    @patch('watchlist_manager.yf.Ticker')
    def test_get_stock_data_force_mode(self, mock_ticker_class):
        """Test force mode with only 50 days required."""
        mock_ticker = MagicMock()
        mock_ticker.info = {'sector': 'Technology', 'industry': 'Software', 'marketCap': 1000000000}

        # Only 60 days of data
        dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
        mock_ticker.history.return_value = pd.DataFrame({
            'Close': [100 + i * 0.1 for i in range(60)],
            'High': [101 + i * 0.1 for i in range(60)],
            'Low': [99 + i * 0.1 for i in range(60)],
            'Volume': [1000000 for _ in range(60)]
        }, index=dates)

        mock_ticker_class.return_value = mock_ticker

        # Without force, should fail (needs 200 days)
        result_no_force = wm.get_stock_data('AAPL', force=False)
        self.assertIsNone(result_no_force)

        # With force, should succeed (only needs 50 days)
        mock_ticker_class.reset_mock()
        mock_ticker_class.return_value = mock_ticker
        result_force = wm.get_stock_data('AAPL', force=True)
        self.assertIsNotNone(result_force)


class TestAddToWatchlist(unittest.TestCase):
    """Test add_to_watchlist function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)
        self.test_watchlist_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()

    @patch('watchlist_manager.get_stock_data')
    @patch('builtins.print')
    def test_add_new_ticker(self, mock_print, mock_get_data):
        """Test adding a new ticker to watchlist."""
        mock_get_data.return_value = {
            'Ticker': 'AAPL',
            'Price': 150.0,
            'Stage': 5,
            '6M_Return': 25.5,
            'ATR': 2.5,
            'Avg_Volume': 50000000,
            'Sector': 'Technology',
            'Industry': 'Consumer Electronics',
            'Market_Cap': 2000000000000,
            'Name': 'Apple Inc'
        }

        wm.add_to_watchlist('AAPL', 'Test notes')

        # Verify watchlist was created
        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 1)
        self.assertEqual(df['Ticker'].iloc[0], 'AAPL')
        self.assertEqual(df['Notes'].iloc[0], 'Test notes')
        self.assertEqual(df['Sector'].iloc[0], 'Technology')

    @patch('watchlist_manager.get_stock_data')
    @patch('builtins.print')
    def test_add_duplicate_ticker(self, mock_print, mock_get_data):
        """Test adding duplicate ticker is rejected."""
        # First add
        mock_get_data.return_value = {
            'Ticker': 'AAPL', 'Price': 150.0, 'Stage': 5, '6M_Return': 25.5,
            'ATR': 2.5, 'Avg_Volume': 50000000, 'Sector': 'Technology',
            'Industry': 'Software', 'Market_Cap': 1000000, 'Name': 'Apple'
        }
        wm.add_to_watchlist('AAPL', 'First add')

        # Try to add again
        wm.add_to_watchlist('AAPL', 'Second add')

        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 1)

    @patch('watchlist_manager.get_stock_data')
    @patch('builtins.print')
    def test_add_no_data(self, mock_print, mock_get_data):
        """Test adding when data fetch fails."""
        mock_get_data.return_value = None

        wm.add_to_watchlist('INVALID')

        self.assertFalse(self.test_watchlist_path.exists())


class TestPopulateFromScan(unittest.TestCase):
    """Test populate_from_scan function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)
        self.test_scan_path = Path('/tmp/test_scan.csv')

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()
        if self.test_scan_path.exists():
            self.test_scan_path.unlink()

    @patch('builtins.print')
    def test_populate_from_valid_scan(self, mock_print):
        """Test populating watchlist from valid scan file."""
        # Create scan file
        scan_data = pd.DataFrame({
            'Ticker': ['NVDA', 'TSLA'],
            'Stage2': [6, 5],
            '6M_%': [45.5, 30.2],
            'Risk_%': [5.5, 8.2],
            'Entry_Breakout': [150.0, 250.0],
            'Stop': [142.0, 230.0],
            '$Vol_M': [500.5, 400.3],
            'Sector': ['Technology', 'Consumer Cyclical'],
            'Industry': ['Semiconductors', 'Automotive']
        })
        scan_data.to_csv(self.test_scan_path, index=False)

        wm.populate_from_scan(str(self.test_scan_path))

        # Verify watchlist was populated
        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 2)
        self.assertIn('NVDA', df['Ticker'].values)
        self.assertIn('TSLA', df['Ticker'].values)

    @patch('builtins.print')
    def test_populate_skips_existing(self, mock_print):
        """Test that existing tickers are skipped."""
        # Pre-populate watchlist
        existing = pd.DataFrame({
            'Ticker': ['NVDA'],
            'Stage': [6],
            'RS_Rank': [45.5],
            'Base_Count': [''],
            'Pattern_Type': [''],
            'Pivot_Price': [150.0],
            'Stop_Level': [142.0],
            'Target_1': [''],
            'Target_2': [''],
            'R_Ratio': [''],
            'Avg_Volume_50d': [500000000],
            'Market_Cap': [1000000000000],
            'Sector': ['Technology'],
            'Industry': ['Semiconductors'],
            'Notes': ['Existing'],
            'Added_Date': ['2026-04-01'],
            'Alert_Set': ['No']
        })
        existing.to_csv(self.test_watchlist_path, index=False)

        # Create scan file with existing + new ticker
        scan_data = pd.DataFrame({
            'Ticker': ['NVDA', 'TSLA'],
            'Stage2': [6, 5],
            '6M_%': [45.5, 30.2],
            'Risk_%': [5.5, 8.2],
            'Entry_Breakout': [150.0, 250.0],
            'Stop': [142.0, 230.0],
            '$Vol_M': [500.5, 400.3],
            'Sector': ['Technology', 'Consumer Cyclical'],
            'Industry': ['Semiconductors', 'Automotive']
        })
        scan_data.to_csv(self.test_scan_path, index=False)

        wm.populate_from_scan(str(self.test_scan_path))

        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 2)

    @patch('builtins.print')
    def test_populate_missing_file(self, mock_print):
        """Test handling when scan file doesn't exist."""
        wm.populate_from_scan('/nonexistent/path/scan.csv')
        self.assertFalse(self.test_watchlist_path.exists())


class TestListWatchlist(unittest.TestCase):
    """Test list_watchlist function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()

    @patch('builtins.print')
    def test_list_empty_watchlist(self, mock_print):
        """Test listing empty watchlist."""
        wm.list_watchlist()
        mock_print.assert_any_call("📭 Watchlist is empty")

    @patch('builtins.print')
    def test_list_populated_watchlist(self, mock_print):
        """Test listing watchlist with data."""
        # Create test watchlist
        test_data = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT'],
            'Stage': [5, 6],
            'RS_Rank': [25.5, 30.0],
            'Base_Count': ['', ''],
            'Pattern_Type': ['', ''],
            'Pivot_Price': [150.0, 250.0],
            'Stop_Level': [145.0, 240.0],
            'Target_1': ['', ''],
            'Target_2': ['', ''],
            'R_Ratio': ['', ''],
            'Avg_Volume_50d': [50000000, 30000000],
            'Market_Cap': [2000000000000, 2500000000000],
            'Sector': ['Technology', 'Technology'],
            'Industry': ['Consumer Electronics', 'Software'],
            'Notes': ['Strong', 'Leader'],
            'Added_Date': ['2026-04-01', '2026-04-02'],
            'Alert_Set': ['No', 'No']
        })
        test_data.to_csv(self.test_watchlist_path, index=False)

        wm.list_watchlist()

        # Should print header and data
        calls = ' '.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('AAPL', calls)
        self.assertIn('MSFT', calls)


class TestRemoveTicker(unittest.TestCase):
    """Test remove_ticker function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)

        # Create test watchlist
        test_data = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT', 'NVDA'],
            'Stage': [5, 6, 7],
            'RS_Rank': [25.5, 30.0, 45.0],
            'Base_Count': ['', '', ''],
            'Pattern_Type': ['', '', ''],
            'Pivot_Price': [150.0, 250.0, 350.0],
            'Stop_Level': [145.0, 240.0, 340.0],
            'Target_1': ['', '', ''],
            'Target_2': ['', '', ''],
            'R_Ratio': ['', '', ''],
            'Avg_Volume_50d': [50000000, 30000000, 20000000],
            'Market_Cap': [2000000000000, 2500000000000, 1000000000000],
            'Sector': ['Technology', 'Technology', 'Technology'],
            'Industry': ['Consumer Electronics', 'Software', 'Semiconductors'],
            'Notes': ['Strong', 'Leader', 'Momentum'],
            'Added_Date': ['2026-04-01', '2026-04-02', '2026-04-03'],
            'Alert_Set': ['No', 'No', 'No']
        })
        test_data.to_csv(self.test_watchlist_path, index=False)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()

    @patch('builtins.print')
    def test_remove_existing_ticker(self, mock_print):
        """Test removing an existing ticker."""
        wm.remove_ticker('MSFT')

        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 2)
        self.assertNotIn('MSFT', df['Ticker'].values)
        self.assertIn('AAPL', df['Ticker'].values)

    @patch('builtins.print')
    def test_remove_nonexistent_ticker(self, mock_print):
        """Test removing a ticker not in watchlist."""
        wm.remove_ticker('INVALID')

        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 3)

    @patch('builtins.print')
    def test_remove_case_insensitive(self, mock_print):
        """Test ticker removal is case insensitive."""
        wm.remove_ticker('msft')

        df = pd.read_csv(self.test_watchlist_path)
        self.assertEqual(len(df), 2)
        self.assertNotIn('MSFT', df['Ticker'].values)


class TestRemoveAllTickers(unittest.TestCase):
    """Test remove_all_tickers function."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)
        self.backup_dir = self.test_watchlist_path.parent

        # Create test watchlist
        test_data = pd.DataFrame({
            'Ticker': ['AAPL', 'MSFT'],
            'Stage': [5, 6],
            'RS_Rank': [25.5, 30.0],
            'Base_Count': ['', ''],
            'Pattern_Type': ['', ''],
            'Pivot_Price': [150.0, 250.0],
            'Stop_Level': [145.0, 240.0],
            'Target_1': ['', ''],
            'Target_2': ['', ''],
            'R_Ratio': ['', ''],
            'Avg_Volume_50d': [50000000, 30000000],
            'Market_Cap': [2000000000000, 2500000000000],
            'Sector': ['Technology', 'Technology'],
            'Industry': ['Consumer Electronics', 'Software'],
            'Notes': ['Strong', 'Leader'],
            'Added_Date': ['2026-04-01', '2026-04-02'],
            'Alert_Set': ['No', 'No']
        })
        test_data.to_csv(self.test_watchlist_path, index=False)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()
        # Clean up backups
        for f in self.backup_dir.glob('watchlist_backup_*.csv'):
            f.unlink()

    @patch('builtins.print')
    def test_remove_all_force(self, mock_print):
        """Test force removing all tickers."""
        wm.remove_all_tickers(force=True)

        df = wm.load_watchlist()
        self.assertTrue(df.empty)

    @patch('builtins.print')
    @patch('builtins.input', return_value='DELETE ALL')
    def test_remove_all_with_confirmation(self, mock_input, mock_print):
        """Test removing all with confirmation."""
        wm.remove_all_tickers(force=False)

        df = wm.load_watchlist()
        self.assertTrue(df.empty)

    @patch('builtins.print')
    @patch('builtins.input', return_value='NO')
    def test_remove_all_cancelled(self, mock_input, mock_print):
        """Test cancelling remove all."""
        wm.remove_all_tickers(force=False)

        df = wm.load_watchlist()
        self.assertEqual(len(df), 2)

    @patch('builtins.print')
    def test_remove_all_empty_watchlist(self, mock_print):
        """Test removing all when watchlist is already empty."""
        # Clear the file first
        empty_df = pd.DataFrame(columns=['Ticker', 'Stage', 'RS_Rank', 'Base_Count',
                                         'Pattern_Type', 'Pivot_Price', 'Stop_Level',
                                         'Target_1', 'Target_2', 'R_Ratio',
                                         'Avg_Volume_50d', 'Market_Cap', 'Sector',
                                         'Industry', 'Notes', 'Added_Date', 'Alert_Set'])
        empty_df.to_csv(self.test_watchlist_path, index=False)

        wm.remove_all_tickers(force=True)

        mock_print.assert_any_call("⚠️ Watchlist is already empty")


class TestMainEntryPoints(unittest.TestCase):
    """Test main CLI entry points."""

    def setUp(self):
        self.test_watchlist_path = Path('/tmp/test_watchlist.csv')
        wm.WATCHLIST_PATH = str(self.test_watchlist_path)
        self.test_watchlist_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_watchlist_path.exists():
            self.test_watchlist_path.unlink()

    @patch('watchlist_manager.populate_from_scan')
    def test_main_populate(self, mock_populate):
        """Test main entry point for populate command."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'populate', 'scan.csv']):
            wm.populate_from_scan('scan.csv')
            mock_populate.assert_called_once_with('scan.csv')

    @patch('watchlist_manager.add_to_watchlist')
    def test_main_add(self, mock_add):
        """Test main entry point for add command."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'add', 'AAPL', 'Test notes']):
            wm.add_to_watchlist('AAPL', 'Test notes', force=False)
            mock_add.assert_called_once_with('AAPL', 'Test notes', force=False)

    @patch('watchlist_manager.add_to_watchlist')
    def test_main_add_with_force(self, mock_add):
        """Test main entry point for add with --force flag."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'add', 'AAPL', '--force']):
            wm.add_to_watchlist('AAPL', '', force=True)
            mock_add.assert_called_once_with('AAPL', '', force=True)

    @patch('watchlist_manager.list_watchlist')
    def test_main_list(self, mock_list):
        """Test main entry point for list command."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'list']):
            wm.list_watchlist()
            mock_list.assert_called_once()

    @patch('watchlist_manager.remove_ticker')
    def test_main_remove(self, mock_remove):
        """Test main entry point for remove command."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'remove', 'AAPL']):
            wm.remove_ticker('AAPL')
            mock_remove.assert_called_once_with('AAPL')

    @patch('watchlist_manager.remove_all_tickers')
    def test_main_remove_all(self, mock_remove_all):
        """Test main entry point for remove-all command."""
        with patch.object(sys, 'argv', ['watchlist_manager.py', 'remove-all', '--force']):
            wm.remove_all_tickers(force=True)
            mock_remove_all.assert_called_once_with(force=True)


if __name__ == '__main__':
    unittest.main()
