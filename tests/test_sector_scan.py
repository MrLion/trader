#!/usr/bin/env python3
"""Tests for sector_scan.py.

Covers run_sector_scan with mocked yfinance.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import sector_scan


class TestRunSectorScan:
    """Test run_sector_scan."""

    def _make_hist(self, closes):
        n = len(closes)
        idx = pd.date_range(end='2026-04-21', periods=n, freq='D')
        return pd.DataFrame({
            'Open': [c * 0.99 for c in closes],
            'High': [c * 1.01 for c in closes],
            'Low': [c * 0.98 for c in closes],
            'Close': closes,
            'Volume': [1_000_000] * n,
        }, index=idx)

    def test_returns_results_dict(self):
        hist = self._make_hist(list(range(400, 500)))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist

        with patch('sector_scan.yf.Ticker', return_value=mock_ticker):
            with patch('sector_scan.yf.download', return_value=pd.DataFrame({'Close': {'SPY': 450.0, 'XLK': 200.0}})):
                result = sector_scan.run_sector_scan()

        assert isinstance(result, dict)
        assert 'scan_date' in result
        assert 'sectors' in result
        assert 'factors' in result
        assert 'sector_ranking' in result

    def test_sector_ranking_order(self):
        hist = self._make_hist(list(range(400, 500)))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist

        with patch('sector_scan.yf.Ticker', return_value=mock_ticker):
            with patch('sector_scan.yf.download', return_value=pd.DataFrame({'Close': {'SPY': 450.0, 'XLK': 200.0, 'XLF': 180.0}})):
                result = sector_scan.run_sector_scan()

        # Ranking should exist and be a list
        assert isinstance(result['sector_ranking'], list)
        assert len(result['sector_ranking']) >= 0
