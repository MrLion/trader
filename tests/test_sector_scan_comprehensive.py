#!/usr/bin/env python3
"""Tests for sector_scan_comprehensive.py.

Covers calculate_stage2_score_from_hist and run_comprehensive_scan with mocked yfinance.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import sector_scan_comprehensive as ssc


class TestCalculateStage2ScoreFromHist:
    """Test calculate_stage2_score_from_hist wrapper."""

    def test_returns_score(self):
        n = 200
        idx = pd.date_range(end='2026-04-21', periods=n, freq='D')
        hist = pd.DataFrame({
            'Open': [100] * n,
            'High': [102] * n,
            'Low': [98] * n,
            'Close': list(range(100, 300)),
            'Volume': [1_000_000] * n,
        }, index=idx)
        score = ssc.calculate_stage2_score_from_hist(hist)
        assert isinstance(score, (int, float))


class TestRunComprehensiveScan:
    """Test run_comprehensive_scan."""

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

    def test_runs_without_error(self):
        hist = self._make_hist(list(range(100, 300)))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist

        with patch('sector_scan_comprehensive.yf.Ticker', return_value=mock_ticker):
            # Does not raise
            ssc.run_comprehensive_scan()
