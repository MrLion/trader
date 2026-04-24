#!/usr/bin/env python3
"""Tests for pivot_detection module."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from traderlib.pivot_detection import (
    PivotSignal,
    detect_range_20d_pivot,
    detect_vcp_pivot,
    detect_pocket_pivot,
    detect_pivot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hist(days=60, trend='up', volume=True):
    """Create synthetic OHLCV data."""
    dates = pd.date_range(end='2024-04-08', periods=days, freq='D')
    base = 100.0
    data = []
    for i in range(days):
        if trend == 'up':
            close = base + i * 0.5 + (i % 5) * 0.2
        elif trend == 'flat':
            close = base + np.sin(i / 5) * 5
        else:
            close = base - i * 0.3
        high = close * 1.02
        low = close * 0.98
        open_p = close * 0.99
        vol = 1000000 + (i % 10) * 100000
        data.append({
            'Open': open_p,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': vol,
        })
    df = pd.DataFrame(data, index=dates)
    return df


def make_vcp_hist():
    """Create synthetic data with a valid VCP pattern.

    Uses realistic price action: uptrend, then base with progressively
    tighter contractions and declining volume.
    """
    np.random.seed(42)
    dates = pd.date_range(end='2024-04-08', periods=100, freq='D')
    data = []

    # Days 0-30: uptrend from 80 to 120
    for i in range(30):
        close = 80 + i * 1.5 + np.random.normal(0, 1)
        high = close + abs(np.random.normal(2, 0.5))
        low = close - abs(np.random.normal(1, 0.5))
        vol = 2000000 + np.random.normal(0, 200000)
        data.append({'Open': low, 'High': high, 'Low': low, 'Close': close, 'Volume': max(100000, vol)})

    # Days 30-50: first broad contraction (high ~120, low ~100)
    for i in range(20):
        base = 110
        swing = 10 * np.sin(i / 3) + np.random.normal(0, 1)
        close = base + swing
        high = close + 5 + abs(np.random.normal(1, 0.3))
        low = close - 5 - abs(np.random.normal(1, 0.3))
        vol = 1800000 - i * 15000 + np.random.normal(0, 100000)
        data.append({'Open': low, 'High': high, 'Low': low, 'Close': close, 'Volume': max(100000, vol)})

    # Days 50-70: second tighter contraction (high ~115, low ~105)
    for i in range(20):
        base = 110
        swing = 5 * np.sin(i / 3) + np.random.normal(0, 0.5)
        close = base + swing
        high = close + 3 + abs(np.random.normal(0.5, 0.2))
        low = close - 3 - abs(np.random.normal(0.5, 0.2))
        vol = 1200000 - i * 10000 + np.random.normal(0, 50000)
        data.append({'Open': low, 'High': high, 'Low': low, 'Close': close, 'Volume': max(100000, vol)})

    # Days 70-100: tightest contraction (high ~112, low ~108)
    for i in range(30):
        base = 110
        swing = 2 * np.sin(i / 3) + np.random.normal(0, 0.3)
        close = base + swing
        high = close + 1.5 + abs(np.random.normal(0.3, 0.1))
        low = close - 1.5 - abs(np.random.normal(0.3, 0.1))
        vol = 800000 - i * 5000 + np.random.normal(0, 30000)
        data.append({'Open': low, 'High': high, 'Low': low, 'Close': close, 'Volume': max(100000, vol)})

    df = pd.DataFrame(data, index=dates)
    return df


def make_pocket_pivot_hist():
    """Create data with a pocket pivot day.

    Pocket pivot: up-day where volume > max down-volume in prior 10 days.
    We need several down-days with moderate volume, then one up-day with
    volume exceeding all of them.
    """
    np.random.seed(43)
    dates = pd.date_range(end='2024-04-08', periods=30, freq='D')
    data = []
    base = 100.0

    for i in range(30):
        if i == 28:
            # Pocket pivot day: strong up-day with massive volume
            close = base + 5.0
            high = close + 1.0
            low = close - 0.5
            vol = 3000000  # way above prior down-day max (~1.5M)
        elif i == 27:
            # Down-day with moderate volume
            close = base + 2.0
            high = close + 0.5
            low = close - 1.5
            vol = 1500000
        elif i >= 20 and i % 3 == 0:
            # Scattered down-days with moderate volume
            close = base + i * 0.1 - 1.0
            high = close + 0.5
            low = close - 1.0
            vol = 1200000 + np.random.normal(0, 100000)
        else:
            # Up-days or flat with low volume
            close = base + i * 0.1
            high = close + 0.5
            low = close - 0.5
            vol = 800000 + np.random.normal(0, 50000)

        data.append({
            'Open': low,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': max(100000, vol),
        })
    df = pd.DataFrame(data, index=dates)
    return df


# ---------------------------------------------------------------------------
# detect_range_20d_pivot
# ---------------------------------------------------------------------------

class TestDetectRange20dPivot:

    def test_detects_pivot(self):
        hist = make_hist(days=60, trend='up')
        signal = detect_range_20d_pivot(hist)
        assert signal is not None
        assert signal.pivot_type == 'range_20d'
        assert signal.pivot_price > 0
        assert signal.stop_price is not None
        assert signal.target_price > signal.pivot_price
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.entry_mode == 'immediate'

    def test_insufficient_data(self):
        hist = make_hist(days=10)
        signal = detect_range_20d_pivot(hist)
        assert signal is None

    def test_context_fields(self):
        hist = make_hist(days=60)
        signal = detect_range_20d_pivot(hist)
        assert 'range_low' in signal.context
        assert 'range_high' in signal.context
        assert signal.context['days'] == 20


# ---------------------------------------------------------------------------
# detect_vcp_pivot
# ---------------------------------------------------------------------------

class TestDetectVCPPivot:

    @patch('traderlib.pivot_detection.detect_vcp_pattern')
    def test_valid_vcp(self, mock_detect):
        """Test wrapper with mocked valid VCP pattern."""
        from traderlib.vcp_utils import VCPPattern, Contraction
        mock_detect.return_value = VCPPattern(
            valid=True,
            contractions=[
                Contraction(start_idx=0, end_idx=5, start_date='2024-01-01',
                           end_date='2024-01-05', high=110, low=100,
                           depth_pct=9.1, volume_avg=1000, volume_ratio=1.0),
                Contraction(start_idx=6, end_idx=10, start_date='2024-01-06',
                           end_date='2024-01-10', high=108, low=103,
                           depth_pct=4.6, volume_avg=800, volume_ratio=0.8),
                Contraction(start_idx=11, end_idx=15, start_date='2024-01-11',
                           end_date='2024-01-15', high=106, low=104,
                           depth_pct=1.9, volume_avg=600, volume_ratio=0.6),
            ],
            pivot_high=106.0,
            pivot_date='2024-01-15',
            stop_low=104.0,
            stop_date='2024-01-15',
            total_depth=5.5,
            progression_valid=True,
            volume_declining=True,
        )
        hist = make_hist(days=60)
        signal = detect_vcp_pivot(hist)
        assert signal is not None
        assert signal.pivot_type == 'vcp'
        assert signal.pivot_price == 106.0
        assert signal.stop_price == 104.0
        assert signal.confidence >= 0.5
        assert signal.entry_mode == 'breakout'
        assert signal.context['num_contractions'] == 3

    @patch('traderlib.pivot_detection.detect_vcp_pattern')
    def test_invalid_without_volume_decline(self, mock_detect):
        """Test wrapper rejects VCP without volume decline."""
        from traderlib.vcp_utils import VCPPattern
        mock_detect.return_value = VCPPattern(
            valid=True,
            volume_declining=False,
        )
        hist = make_hist(days=60)
        signal = detect_vcp_pivot(hist)
        assert signal is None

    @patch('traderlib.pivot_detection.detect_vcp_pattern')
    def test_invalid_when_not_valid(self, mock_detect):
        """Test wrapper rejects VCP when pattern.valid is False."""
        from traderlib.vcp_utils import VCPPattern
        mock_detect.return_value = VCPPattern(
            valid=False,
            volume_declining=True,
        )
        hist = make_hist(days=60)
        signal = detect_vcp_pivot(hist)
        assert signal is None

    def test_insufficient_data(self):
        hist = make_hist(days=30)
        signal = detect_vcp_pivot(hist)
        assert signal is None


# ---------------------------------------------------------------------------
# detect_pocket_pivot
# ---------------------------------------------------------------------------

class TestDetectPocketPivot:

    def test_detects_pocket_pivot(self):
        hist = make_pocket_pivot_hist()
        signal = detect_pocket_pivot(hist)
        assert signal is not None
        assert signal.pivot_type == 'pocket_pivot'
        assert signal.pivot_price > 0
        assert signal.stop_price is not None
        assert signal.confidence >= 0.5
        assert signal.entry_mode == 'immediate'

    def test_insufficient_data(self):
        hist = make_hist(days=10)
        signal = detect_pocket_pivot(hist)
        assert signal is None

    def test_no_volume_column(self):
        hist = make_hist(days=30)
        hist = hist.drop(columns=['Volume'])
        signal = detect_pocket_pivot(hist)
        assert signal is None


# ---------------------------------------------------------------------------
# detect_pivot dispatcher
# ---------------------------------------------------------------------------

class TestDetectPivotDispatcher:

    @patch('traderlib.pivot_detection.detect_vcp_pattern')
    def test_auto_prefers_vcp(self, mock_detect):
        """Auto should prefer VCP when it has highest confidence."""
        from traderlib.vcp_utils import VCPPattern, Contraction
        # 3 contractions + ideal total_depth = 0.85 + 0.10 = 0.95 confidence
        mock_detect.return_value = VCPPattern(
            valid=True,
            contractions=[
                Contraction(start_idx=0, end_idx=5, start_date='2024-01-01',
                           end_date='2024-01-05', high=110, low=100,
                           depth_pct=9.1, volume_avg=1000, volume_ratio=1.0),
                Contraction(start_idx=6, end_idx=10, start_date='2024-01-06',
                           end_date='2024-01-10', high=108, low=103,
                           depth_pct=4.6, volume_avg=800, volume_ratio=0.8),
                Contraction(start_idx=11, end_idx=15, start_date='2024-01-11',
                           end_date='2024-01-15', high=106, low=104,
                           depth_pct=1.9, volume_avg=600, volume_ratio=0.6),
            ],
            pivot_high=106.0,
            stop_low=104.0,
            total_depth=20.0,  # ideal 15-30 range for confidence boost
            volume_declining=True,
        )
        hist = make_hist(days=60)
        signal = detect_pivot('AAPL', hist, technique='auto')
        assert signal is not None
        assert signal.ticker == 'AAPL'
        assert signal.pivot_type == 'vcp'

    def test_auto_fallback_to_range_20d(self):
        hist = make_hist(days=60)
        signal = detect_pivot('AAPL', hist, technique='auto')
        assert signal is not None
        assert signal.ticker == 'AAPL'
        # When no VCP or pocket pivot, falls back to range_20d
        assert signal.pivot_type == 'range_20d'

    def test_explicit_range_20d(self):
        hist = make_hist(days=60)
        signal = detect_pivot('AAPL', hist, technique='range_20d')
        assert signal is not None
        assert signal.pivot_type == 'range_20d'

    @patch('traderlib.pivot_detection.detect_vcp_pattern')
    def test_explicit_vcp(self, mock_detect):
        from traderlib.vcp_utils import VCPPattern, Contraction
        mock_detect.return_value = VCPPattern(
            valid=True,
            contractions=[
                Contraction(start_idx=0, end_idx=5, start_date='2024-01-01',
                           end_date='2024-01-05', high=110, low=100,
                           depth_pct=9.1, volume_avg=1000, volume_ratio=1.0),
            ],
            pivot_high=110.0,
            stop_low=100.0,
            total_depth=9.1,
            volume_declining=True,
        )
        hist = make_hist(days=60)
        signal = detect_pivot('AAPL', hist, technique='vcp')
        assert signal is not None
        assert signal.pivot_type == 'vcp'

    def test_explicit_pocket_pivot(self):
        hist = make_pocket_pivot_hist()
        signal = detect_pivot('AAPL', hist, technique='pocket_pivot')
        assert signal is not None
        assert signal.pivot_type == 'pocket_pivot'

    def test_invalid_technique(self):
        hist = make_hist(days=60)
        signal = detect_pivot('AAPL', hist, technique='invalid')
        assert signal is None

    def test_none_on_no_signal(self):
        hist = make_hist(days=10)  # too short for any detector
        signal = detect_pivot('AAPL', hist, technique='auto')
        assert signal is None
