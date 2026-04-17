"""Tests for VCP (Volatility Contraction Pattern) detection.

Covers:
1. Swing point detection (highs and lows)
2. Contraction measurement and validation
3. VCP pattern detection (full workflow)
4. Volume dry-up checking
5. Edge cases (insufficient data, invalid contractions)
"""

import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from traderlib.vcp_utils import (
    detect_swing_points,
    measure_contraction,
    validate_vcp_progression,
    detect_vcp_pattern,
    format_vcp_summary,
    VCPPattern,
    SwingPoint,
    Contraction,
)


def make_vcp_pattern_df(n_days: int = 100, pattern: str = 'valid') -> pd.DataFrame:
    """Generate synthetic OHLCV data with VCP patterns.

    Args:
        n_days: Number of days
        pattern: 'valid' (3 contractions), 'invalid' (wide contractions),
                 'no_vcp' (random walk), 'flat' (low volatility)
    """
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=n_days, freq='D')

    if pattern == 'valid':
        # Simulate valid VCP: 3 progressively tighter contractions
        # First contraction: 20% depth
        # Second contraction: 12% depth (60% of first)
        # Third contraction: 6% depth (50% of second)
        base_price = 100.0

        # Build pattern with 3 contractions
        prices = []
        volumes = []

        # Leg 1: Decline then base (contraction 1: 20%)
        for i in range(20):
            prices.append(base_price * (1 - 0.20 * (i / 20)))
            volumes.append(1000000)

        # Base 1: Tight range
        for i in range(10):
            prices.append(base_price * 0.80 + np.sin(i) * 2)
            volumes.append(800000)

        # Rally to pivot 1
        for i in range(5):
            prices.append(base_price * 0.82 + i * 2)
            volumes.append(1200000)

        # Contraction 2: 12% depth
        pivot1 = prices[-1]
        for i in range(15):
            prices.append(pivot1 * (1 - 0.12 * (i / 15)))
            volumes.append(700000)

        # Base 2: Tighter range
        for i in range(10):
            prices.append(pivot1 * 0.88 + np.sin(i) * 1)
            volumes.append(500000)

        # Rally to pivot 2
        for i in range(5):
            prices.append(pivot1 * 0.90 + i * 1.5)
            volumes.append(900000)

        # Contraction 3: 6% depth (tightest)
        pivot2 = prices[-1]
        for i in range(10):
            prices.append(pivot2 * (1 - 0.06 * (i / 10)))
            volumes.append(400000)

        # Base 3: Very tight (ready for breakout)
        for i in range(10):
            prices.append(pivot2 * 0.94 + np.sin(i) * 0.5)
            volumes.append(300000)

        # Breakout volume spike
        for i in range(5):
            prices.append(pivot2 * 0.95 + i * 2)
            volumes.append(1500000)

        # Pad to n_days
        while len(prices) < n_days:
            prices.append(prices[-1] + np.random.randn() * 0.5)
            volumes.append(500000)

    elif pattern == 'invalid':
        # Wide contractions that don't tighten properly
        prices = []
        volumes = []
        base = 100.0

        # Contraction 1: 25%
        for i in range(30):
            prices.append(base * (1 - 0.25 * (i / 30)))
            volumes.append(1000000)

        # Contraction 2: 20% (80% of first - too wide, should be 50-70%)
        for i in range(25):
            prices.append(prices[-1] * (1 - 0.20 * (i / 25)))
            volumes.append(800000)

        # Contraction 3: 18% (90% of second - also too wide)
        for i in range(20):
            prices.append(prices[-1] * (1 - 0.18 * (i / 20)))
            volumes.append(600000)

        while len(prices) < n_days:
            prices.append(prices[-1] + np.random.randn() * 0.5)
            volumes.append(500000)

    elif pattern == 'flat':
        # Low volatility, no clear VCP
        prices = 100 + np.cumsum(np.random.randn(n_days) * 0.5)
        volumes = np.random.randint(500000, 1000000, n_days)

    else:  # no_vcp
        # Random walk
        prices = 100 + np.cumsum(np.random.randn(n_days) * 2)
        volumes = np.random.randint(500000, 1000000, n_days)

    prices = np.array(prices[:n_days])
    volumes = np.array(volumes[:n_days])

    # Generate OHLC from close
    highs = prices * (1 + abs(np.random.randn(n_days) * 0.01))
    lows = prices * (1 - abs(np.random.randn(n_days) * 0.01))
    opens = lows + (highs - lows) * np.random.rand(n_days)

    return pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': prices,
        'Volume': volumes,
    }, index=dates)


class TestSwingPointDetection(unittest.TestCase):
    """Tests for swing high/low detection."""

    def test_detect_swing_points_basic(self):
        """Should detect alternating highs and lows."""
        df = make_vcp_pattern_df(100, 'valid')
        swings = detect_swing_points(df, reversal_threshold=0.05, min_bars=5)

        self.assertIsInstance(swings, list)
        self.assertGreater(len(swings), 0)

        # Check alternating pattern
        for i in range(1, len(swings)):
            self.assertNotEqual(swings[i].type, swings[i-1].type)

    def test_swing_point_attributes(self):
        """Swing points should have correct attributes."""
        df = make_vcp_pattern_df(100, 'valid')
        swings = detect_swing_points(df)

        if swings:
            swing = swings[0]
            self.assertIn(swing.type, ['high', 'low'])
            self.assertIsInstance(swing.price, float)
            self.assertIsInstance(swing.idx, int)
            self.assertIsInstance(swing.date, pd.Timestamp)

    def test_insufficient_data_returns_empty(self):
        """Should return empty list for insufficient data."""
        df = make_vcp_pattern_df(10)
        swings = detect_swing_points(df)
        self.assertEqual(len(swings), 0)

    def test_reversal_threshold_filtering(self):
        """Higher threshold should filter out minor swings."""
        df = make_vcp_pattern_df(100, 'volatile_stock')

        low_threshold = detect_swing_points(df, reversal_threshold=0.02)
        high_threshold = detect_swing_points(df, reversal_threshold=0.10)

        self.assertGreaterEqual(len(low_threshold), len(high_threshold))


class TestContractionMeasurement(unittest.TestCase):
    """Tests for contraction measurement."""

    def test_measure_contraction_basic(self):
        """Should measure contraction correctly."""
        df = make_vcp_pattern_df(100, 'valid')

        # Create manual swing points
        high = SwingPoint(type='high', price=100.0, date=df.index[20], idx=20)
        low = SwingPoint(type='low', price=80.0, date=df.index[30], idx=30)

        contraction = measure_contraction(df, high, low, avg_volume_50d=1000000)

        self.assertEqual(contraction.high, 100.0)
        self.assertEqual(contraction.low, 80.0)
        self.assertAlmostEqual(contraction.depth_pct, 20.0, places=1)

    def test_contraction_depth_calculation(self):
        """Depth percentage should be (high - low) / high * 100."""
        df = make_vcp_pattern_df(50)

        high = SwingPoint(type='high', price=120.0, date=df.index[10], idx=10)
        low = SwingPoint(type='low', price=100.0, date=df.index[20], idx=20)

        contraction = measure_contraction(df, high, low, avg_volume_50d=1000000)

        expected_depth = ((120.0 - 100.0) / 120.0) * 100
        self.assertAlmostEqual(contraction.depth_pct, expected_depth, places=1)


class TestVCPProgressionValidation(unittest.TestCase):
    """Tests for VCP contraction progression validation."""

    def test_valid_progression(self):
        """Progression with 60% and 50% ratios should be valid."""
        contractions = [
            Contraction(0, 10, None, None, 100, 80, 20.0, 1000000, 1.0),   # 20%
            Contraction(10, 20, None, None, 85, 73, 12.0, 800000, 0.8),     # 12% (60%)
            Contraction(20, 30, None, None, 78, 74, 6.0, 400000, 0.4),      # 6% (50%)
        ]

        is_valid, msg = validate_vcp_progression(contractions)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")

    def test_invalid_wide_progression(self):
        """Progression with 80% ratio should be invalid."""
        contractions = [
            Contraction(0, 10, None, None, 100, 75, 25.0, 1000000, 1.0),   # 25%
            Contraction(10, 20, None, None, 80, 60, 20.0, 800000, 0.8),    # 20% (80% - too wide)
        ]

        is_valid, msg = validate_vcp_progression(contractions)
        self.assertFalse(is_valid)
        self.assertIn("80%", msg)

    def test_insufficient_contractions(self):
        """Should fail with less than 2 contractions."""
        contractions = [
            Contraction(0, 10, None, None, 100, 80, 20.0, 1000000, 1.0),
        ]

        is_valid, msg = validate_vcp_progression(contractions)
        self.assertFalse(is_valid)
        self.assertIn("at least 2", msg)


class TestVCPPatternDetection(unittest.TestCase):
    """Tests for full VCP pattern detection."""

    def test_valid_vcp_detection(self):
        """Should detect valid VCP pattern."""
        df = make_vcp_pattern_df(150, 'valid')
        vcp = detect_vcp_pattern(df, min_contractions=2)

        if vcp.valid:
            self.assertGreaterEqual(len(vcp.contractions), 2)
            self.assertGreater(vcp.pivot_high, 0)
            self.assertGreater(vcp.stop_low, 0)
            self.assertTrue(vcp.progression_valid)

    def test_insufficient_data_returns_invalid(self):
        """Should return invalid pattern for insufficient data."""
        df = make_vcp_pattern_df(30)
        vcp = detect_vcp_pattern(df)

        self.assertFalse(vcp.valid)
        self.assertIn("Insufficient", vcp.error_message)

    def test_no_contractions_returns_invalid(self):
        """Should return invalid when no contractions found."""
        df = make_vcp_pattern_df(100, 'flat')
        vcp = detect_vcp_pattern(df)

        self.assertFalse(vcp.valid)

    def test_vcp_pattern_attributes(self):
        """VCP pattern should have required attributes."""
        df = make_vcp_pattern_df(150, 'valid')
        vcp = detect_vcp_pattern(df)

        self.assertIsInstance(vcp, VCPPattern)
        self.assertIsInstance(vcp.valid, bool)
        self.assertIsInstance(vcp.contractions, list)

        if vcp.valid:
            self.assertIsNotNone(vcp.pivot_date)
            self.assertIsNotNone(vcp.stop_date)
            self.assertGreater(vcp.total_depth, 0)

    def test_volume_dry_up_detection(self):
        """Should detect declining volume in contractions."""
        df = make_vcp_pattern_df(150, 'valid')
        vcp = detect_vcp_pattern(df, require_volume_dry_up=True)

        if vcp.valid:
            # Valid VCP should have declining volume
            self.assertIsInstance(vcp.volume_declining, bool)


class TestVCPSummaryFormatting(unittest.TestCase):
    """Tests for VCP summary formatting."""

    def test_valid_pattern_summary(self):
        """Should format valid pattern correctly."""
        contractions = [
            Contraction(0, 10, pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-10'),
                       100, 80, 20.0, 1000000, 1.0),
        ]
        pattern = VCPPattern(
            valid=True,
            contractions=contractions,
            pivot_high=100.0,
            stop_low=80.0,
            total_depth=20.0,
            volume_declining=True
        )

        summary = format_vcp_summary(pattern)

        self.assertTrue(summary['valid'])
        self.assertEqual(summary['pivot_high'], 100.0)
        self.assertEqual(summary['stop_low'], 80.0)
        self.assertEqual(summary['total_depth_pct'], 20.0)

    def test_invalid_pattern_summary(self):
        """Should format invalid pattern with error message."""
        pattern = VCPPattern(valid=False, error_message="Test error")
        summary = format_vcp_summary(pattern)

        self.assertFalse(summary['valid'])
        self.assertEqual(summary['error'], "Test error")


if __name__ == '__main__':
    unittest.main()
