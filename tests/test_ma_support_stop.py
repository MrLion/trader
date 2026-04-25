#!/usr/bin/env python3
"""Tests for MA Support Stop — Dual Risk Parameter.

Covers:
1. calculate_ma_support_stop() function behavior
2. Cluster detection (min_cluster_size, cluster_spread_pct)
3. Buffer calculation
4. Integration with RiskConfig
5. Edge cases (no MAs below price, wide spread, etc.)
6. Integration in stop calculation (paper_exits, backtest strategy)
"""

import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import sys
from pathlib import Path

# Add project root to path

from traderlib.stage2_utils import (
    calculate_ma_support_stop,
    get_stage2_details,
)
from traderlib.risk_config import RiskConfig, MASupportConfig


class TestMASupportStop(unittest.TestCase):
    """Test calculate_ma_support_stop function."""

    def test_no_mas_below_price_returns_none(self):
        """When no MAs are below price, should return None."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 95.0,
            'ma50': 90.0,
            'ma100': 85.0,
            'ma200': 80.0,
        }
        current_price = 50.0  # Below all MAs

        result = calculate_ma_support_stop(current_price, s2_details)

        self.assertIsNone(result)

    def test_one_ma_below_returns_none(self):
        """When only 1 MA is below price, should return None (min_cluster_size=2)."""
        s2_details = {
            'ma10': 100.0,  # Above price
            'ma20': 100.0,  # Above price
            'ma50': 100.0,  # Above price
            'ma100': 100.0,  # Above price
            'ma200': 80.0,   # Below price
        }
        current_price = 90.0

        result = calculate_ma_support_stop(current_price, s2_details, min_cluster_size=2)

        self.assertIsNone(result)

    def test_two_mas_below_returns_stop(self):
        """When 2 MAs are below price in tight cluster, should return valid stop."""
        # Spread = (88-86)/88 = 2.3% < 5%
        s2_details = {
            'ma10': 100.0,  # Above price
            'ma20': 100.0,  # Above price
            'ma50': 88.0,   # Below price
            'ma100': 86.0,  # Below price, close to ma50 for tight cluster
            'ma200': 100.0,  # Above price, not in cluster
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, min_cluster_size=2, cluster_spread_pct=0.05)

        self.assertIsNotNone(result)
        self.assertIn('ma_support_stop', result)
        self.assertIn('lowest_ma', result)
        self.assertIn('cluster_mas', result)

    def test_wide_spread_returns_none(self):
        """When cluster spread is too wide, should return None."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,   # Below price
            'ma100': 60.0,  # Below price but far away
            'ma200': 50.0,
        }
        current_price = 95.0

        # Spread = (90 - 60) / 90 = 33%, which is > 5% default
        result = calculate_ma_support_stop(current_price, s2_details, cluster_spread_pct=0.05)

        self.assertIsNone(result)

    def test_tight_spread_returns_stop(self):
        """When cluster spread is within threshold, should return stop."""
        # Spread = (88 - 85) / 88 = 3.4%, which is < 5% default
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 88.0,   # Below price
            'ma100': 85.0,  # Below price, close to ma50
            'ma200': 100.0,  # Above price, not in cluster
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, cluster_spread_pct=0.05)

        self.assertIsNotNone(result)

    def test_buffer_calculation(self):
        """Stop should be lowest MA * (1 - buffer_pct)."""
        # Use tight cluster: spread = (90-87)/90 = 3.3% < 5%
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 87.0,  # Close to ma50 for tight cluster
            'ma200': 100.0,  # Above price, not in cluster
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, buffer_pct=0.01)

        # Lowest MA in cluster is ma100 = 87
        # Stop = 87 * (1 - 0.01) = 86.13
        expected_stop = 87.0 * 0.99
        self.assertAlmostEqual(result['ma_support_stop'], expected_stop, places=2)

    def test_custom_buffer(self):
        """Custom buffer percentage should affect stop calculation."""
        # Use tight cluster: spread = (90-87)/90 = 3.3% < 5%
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 87.0,
            'ma200': 100.0,  # Above price
        }
        current_price = 95.0

        result_1pct = calculate_ma_support_stop(current_price, s2_details, buffer_pct=0.01)
        result_2pct = calculate_ma_support_stop(current_price, s2_details, buffer_pct=0.02)

        # 2% buffer should give lower stop than 1% buffer
        self.assertLess(result_2pct['ma_support_stop'], result_1pct['ma_support_stop'])

    def test_returns_lowest_ma_name(self):
        """Result should indicate which MA is the lowest in cluster."""
        # Use tight cluster: spread = (90-87)/90 = 3.3% < 5%
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 87.0,  # This is the lowest in cluster
            'ma200': 100.0,  # Above price, not in cluster
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details)

        self.assertEqual(result['lowest_ma'], 'ma100')

    def test_returns_cluster_mas_list(self):
        """Result should list all MAs in the cluster."""
        # Use tight cluster: spread = (90-87)/90 = 3.3% < 5%
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 87.0,
            'ma200': 100.0,  # Above price, not in cluster
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details)

        # MAs below price in tight cluster: ma50, ma100
        self.assertEqual(set(result['cluster_mas']), {'ma50', 'ma100'})

    def test_returns_cluster_spread(self):
        """Result should include cluster spread percentage."""
        # Use tight cluster
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 87.0,
            'ma200': 100.0,  # Above price
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details)

        # Spread = (90 - 87) / 90 = 3.33%
        expected_spread = (90.0 - 87.0) / 90.0 * 100
        self.assertAlmostEqual(result['cluster_spread_pct'], expected_spread, places=1)

    def test_invalid_s2_details_returns_none(self):
        """When s2_details is None or missing MA keys, should return None."""
        result = calculate_ma_support_stop(100.0, None)
        self.assertIsNone(result)

        result = calculate_ma_support_stop(100.0, {'score': 5})  # No MA keys
        self.assertIsNone(result)

    def test_rklb_scenario(self):
        """Test the RKLB example from the plan: MA support tighter than ATR.

        Example: ATR stop = $62.97 (14.4% risk), MA support stop = $66.83 (9.2% risk)
        This tests that MA support stop is calculated correctly.
        """
        # Simulate RKLB-like scenario with tight cluster
        current_price = 73.60
        s2_details = {
            'ma10': 70.0,
            'ma20': 68.0,
            'ma50': 67.50,
            'ma100': 67.0,  # Close to ma50 for tight cluster
            'ma200': 80.0,  # Above price, not in cluster
        }

        result = calculate_ma_support_stop(current_price, s2_details, buffer_pct=0.01)

        self.assertIsNotNone(result)
        # Verify the stop is reasonable (below price, above lowest MA * 0.99)
        lowest_ma = 67.0  # ma100
        expected_min = lowest_ma * 0.99
        self.assertAlmostEqual(result['ma_support_stop'], expected_min, places=2)

    def test_all_five_mas_below(self):
        """When all 5 MAs are below price and clustered, should work."""
        s2_details = {
            'ma10': 90.0,
            'ma20': 89.0,
            'ma50': 88.0,
            'ma100': 87.0,
            'ma200': 86.0,
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details)

        self.assertIsNotNone(result)
        self.assertEqual(len(result['cluster_mas']), 5)
        self.assertEqual(result['lowest_ma'], 'ma200')


class TestMASupportConfig(unittest.TestCase):
    """Test MASupportConfig dataclass."""

    def test_default_values(self):
        """Default config should have sensible values."""
        config = MASupportConfig()

        self.assertTrue(config.enabled)
        self.assertEqual(config.buffer_pct, 0.01)
        self.assertEqual(config.cluster_spread_pct, 0.05)
        self.assertEqual(config.min_cluster_size, 2)

    def test_conservative_profile(self):
        """Conservative profile should have wider buffer."""
        config = MASupportConfig()
        config.buffer_pct = 0.015  # 1.5%
        config.cluster_spread_pct = 0.05
        config.min_cluster_size = 2

        self.assertEqual(config.buffer_pct, 0.015)

    def test_aggressive_profile(self):
        """Aggressive profile should have tighter buffer."""
        config = MASupportConfig()
        config.buffer_pct = 0.005  # 0.5%
        config.cluster_spread_pct = 0.05
        config.min_cluster_size = 2

        self.assertEqual(config.buffer_pct, 0.005)

    def test_tight_stops_profile(self):
        """Tight stops profile should require more MAs and tighter spread."""
        config = MASupportConfig()
        config.buffer_pct = 0.01
        config.cluster_spread_pct = 0.03  # 3%
        config.min_cluster_size = 3  # Require 3 MAs

        self.assertEqual(config.cluster_spread_pct, 0.03)
        self.assertEqual(config.min_cluster_size, 3)


class TestMASupportIntegration(unittest.TestCase):
    """Test integration with other components."""

    def test_get_stage2_details_includes_ma10(self):
        """get_stage2_details should now include ma10."""
        dates = pd.bdate_range(start='2024-01-01', periods=250)
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.normal(0.001, 0.01, 250))
        df = pd.DataFrame({
            'Close': prices,
            'High': prices * 1.01,
            'Low': prices * 0.99,
            'Volume': np.random.randint(1000000, 10000000, 250),
        }, index=dates)

        details = get_stage2_details(df)

        self.assertIn('ma10', details)
        self.assertIsInstance(details['ma10'], float)

    def test_disabled_ma_support(self):
        """When ma_support is disabled in config, function should still work."""
        config = RiskConfig()
        config.ma_support.enabled = False

        # Function should still be callable
        s2_details = {
            'ma10': 100.0,
            'ma20': 95.0,
            'ma50': 90.0,
            'ma100': 85.0,
            'ma200': 80.0,
        }
        current_price = 95.0

        if config.ma_support.enabled:
            result = calculate_ma_support_stop(current_price, s2_details)
        else:
            result = None

        self.assertIsNone(result)


class TestMASupportEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_price_exactly_at_ma(self):
        """When price equals an MA, that MA should not be in cluster."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,  # Equal to price
            'ma100': 85.0,
            'ma200': 80.0,
        }
        current_price = 90.0

        result = calculate_ma_support_stop(current_price, s2_details)

        # ma50 is equal to price, not below, so should not be in cluster
        if result:
            self.assertNotIn('ma50', result['cluster_mas'])

    def test_very_tight_cluster(self):
        """MAs very close together should form valid cluster."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 89.5,  # Very close to ma50
            'ma200': 89.0,
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, cluster_spread_pct=0.05)

        self.assertIsNotNone(result)
        # Spread = (90 - 89) / 90 = 1.1%, well under 5%

    def test_exactly_at_spread_threshold(self):
        """When spread is exactly at threshold, should work."""
        # Spread = (90-85.5)/90 = 5%, which is NOT > 5%, so should be valid
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 85.5,  # Spread = (90-85.5)/90 = 5%
            'ma200': 100.0,  # Above price
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, cluster_spread_pct=0.05)

        # Spread is exactly 5%, which is NOT > 5%, so should be valid
        self.assertIsNotNone(result)

    def test_just_above_spread_threshold(self):
        """When spread is just above threshold, should return None."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': 85.49,  # Spread = (90-85.49)/90 = 5.01%
            'ma200': 80.0,
        }
        current_price = 95.0

        result = calculate_ma_support_stop(current_price, s2_details, cluster_spread_pct=0.05)

        # Spread is 5.01%, which is > 5%, so should be None
        self.assertIsNone(result)

    def test_missing_some_ma_values(self):
        """When some MA values are missing, should still work."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            # ma100 missing
            'ma200': 80.0,
        }
        current_price = 95.0

        # This should not raise an error
        try:
            result = calculate_ma_support_stop(current_price, s2_details)
            # Should work with available MAs
        except Exception as e:
            self.fail(f"Should not raise exception: {e}")

    def test_nan_values_handled(self):
        """When MA values are NaN, should handle gracefully."""
        s2_details = {
            'ma10': 100.0,
            'ma20': 100.0,
            'ma50': 90.0,
            'ma100': float('nan'),
            'ma200': 80.0,
        }
        current_price = 95.0

        # This should not raise an error
        try:
            result = calculate_ma_support_stop(current_price, s2_details)
        except Exception as e:
            self.fail(f"Should not raise exception with NaN: {e}")


if __name__ == '__main__':
    unittest.main()
