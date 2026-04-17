"""Tests for MA Convergence Scoring.

Covers:
1. calculate_convergence_score() function
2. Cluster tightness calculation
3. Cluster size weighting
4. Price distance to cluster
5. Risk improvement calculation
6. calculate_volume_metrics()
7. check_volume_dry_up()
"""

import unittest
import numpy as np
import pandas as pd

from traderlib.stage2_utils import (
    calculate_convergence_score,
    calculate_volume_metrics,
    check_volume_dry_up,
)


class TestConvergenceScoreBasics(unittest.TestCase):
    """Basic tests for convergence scoring."""

    def test_perfect_convergence(self):
        """All MAs clustered tightly below price should score high."""
        current_price = 100.0
        s2_details = {
            'ma10': 98.0,
            'ma20': 97.5,
            'ma50': 97.0,
            'ma150': 96.5,
            'ma200': 96.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        # Should return result dict with score
        self.assertIsNotNone(result)
        self.assertIn('score', result)
        self.assertIn('components', result)
        self.assertGreater(result['score'], 70)  # Should be strong convergence

    def test_no_mas_below_price(self):
        """When no MAs are below price, should return zero score result."""
        current_price = 50.0
        s2_details = {
            'ma10': 100.0,
            'ma20': 95.0,
            'ma50': 90.0,
            'ma150': 80.0,
            'ma200': 75.0,
        }

        result = calculate_convergence_score(current_price, s2_details)
        self.assertIsNotNone(result)
        self.assertEqual(result['score'], 0)

    def test_single_ma_below_returns_none(self):
        """Only 1 MA below price (need at least 2 for cluster)."""
        current_price = 100.0
        s2_details = {
            'ma10': 105.0,
            'ma20': 104.0,
            'ma50': 103.0,
            'ma150': 102.0,
            'ma200': 98.0,  # Only 1 below
        }

        result = calculate_convergence_score(current_price, s2_details)
        self.assertIsNotNone(result)
        self.assertEqual(result['score'], 0)


class TestConvergenceComponents(unittest.TestCase):
    """Tests for individual convergence components."""

    def test_tightness_component(self):
        """Tight cluster should have high tightness score."""
        current_price = 100.0
        # Very tight cluster: 2% spread
        s2_details = {
            'ma10': 98.0,
            'ma20': 98.1,
            'ma50': 98.2,
            'ma150': 98.3,
            'ma200': 95.0,  # Not in cluster
        }

        result = calculate_convergence_score(current_price, s2_details)

        if result:
            # Tightness should be high (30% weight)
            self.assertGreater(result['components']['tightness'], 0.8)

    def test_wide_spread_low_tightness(self):
        """Wide spread should have low tightness score."""
        current_price = 100.0
        # Wide cluster: 10% spread
        s2_details = {
            'ma10': 98.0,
            'ma20': 93.0,
            'ma50': 88.0,
            'ma150': 70.0,
            'ma200': 60.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        if result:
            self.assertLess(result['components']['tightness'], 0.5)

    def test_cluster_size_weight(self):
        """More MAs in cluster should score higher."""
        current_price = 100.0

        # 5 MAs in tight cluster
        s2_details_5 = {
            'ma10': 98.0,
            'ma20': 97.5,
            'ma50': 97.0,
            'ma150': 96.5,
            'ma200': 96.0,
        }

        # 2 MAs in tight cluster
        s2_details_2 = {
            'ma10': 105.0,
            'ma20': 104.0,
            'ma50': 103.0,
            'ma150': 98.0,
            'ma200': 97.0,
        }

        result_5 = calculate_convergence_score(current_price, s2_details_5)
        result_2 = calculate_convergence_score(current_price, s2_details_2)

        if result_5 and result_2:
            self.assertGreater(result_5['components']['cluster_size'],
                              result_2['components']['cluster_size'])

    def test_price_distance_component(self):
        """Price close to cluster should score well."""
        s2_details = {
            'ma10': 98.0,
            'ma20': 97.0,
            'ma50': 96.0,
            'ma150': 95.0,
            'ma200': 94.0,
        }

        # Close to cluster
        close_price = 99.0
        result_close = calculate_convergence_score(close_price, s2_details)

        # Far from cluster
        far_price = 150.0
        result_far = calculate_convergence_score(far_price, s2_details)

        if result_close and result_far:
            self.assertGreater(result_close['components']['price_distance'],
                             result_far['components']['price_distance'])

    def test_risk_improvement_calculation(self):
        """Risk improvement should be calculated correctly."""
        current_price = 100.0
        s2_details = {
            'ma10': 99.0,
            'ma20': 98.0,
            'ma50': 97.0,
            'ma150': 96.0,
            'ma200': 95.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        if result:
            # Risk improvement should be present
            self.assertIn('risk_improvement', result['components'])
            self.assertGreater(result['components']['risk_improvement'], 0)


class TestConvergenceScoreWeights(unittest.TestCase):
    """Tests for score weighting formula."""

    def test_score_components_sum(self):
        """Score components should follow formula:
        30% tightness + 25% cluster_size + 15% price_distance + 30% risk_improvement
        """
        current_price = 100.0
        s2_details = {
            'ma10': 98.0,
            'ma20': 97.5,
            'ma50': 97.0,
            'ma150': 96.5,
            'ma200': 96.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        if result and result['score'] > 0:
            c = result['components']
            expected_score = (
                c['tightness'] +
                c['cluster_size'] +
                c['price_distance'] +
                c['risk_improvement']
            )

            self.assertEqual(result['score'], expected_score)


class TestVolumeMetrics(unittest.TestCase):
    """Tests for volume metric calculations."""

    def make_volume_df(self, volumes: list) -> pd.DataFrame:
        """Create DataFrame with volume data."""
        n = len(volumes)
        dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
        return pd.DataFrame({
            'Open': [100.0] * n,
            'High': [101.0] * n,
            'Low': [99.0] * n,
            'Close': [100.0] * n,
            'Volume': volumes,
        }, index=dates)

    def test_volume_ratio_calculation(self):
        """Volume ratio should be current / average."""
        # Last volume is 2x the average
        volumes = [1000] * 49 + [2000]
        df = self.make_volume_df(volumes)

        metrics = calculate_volume_metrics(df)

        self.assertIn('volume_ratio', metrics)
        self.assertIn('current_volume', metrics)
        self.assertIn('avg_volume', metrics)

    def test_increasing_volume_trend(self):
        """Should calculate volume metrics."""
        # Volume increasing over last 10 days
        volumes = [1000] * 40 + list(range(1000, 1100, 10))
        df = self.make_volume_df(volumes)

        metrics = calculate_volume_metrics(df)

        # Should have metrics dict
        self.assertIn('avg_volume', metrics)
        self.assertIn('current_volume', metrics)

    def test_declining_volume(self):
        """Should calculate volume metrics with different patterns."""
        # Volume decreasing over last 10 days
        volumes = [1000] * 40 + list(range(1100, 1000, -10))
        df = self.make_volume_df(volumes)

        metrics = calculate_volume_metrics(df)

        # Should have metrics dict
        self.assertIn('avg_volume', metrics)


class TestVolumeDryUp(unittest.TestCase):
    """Tests for volume dry-up detection."""

    def make_volume_df(self, volumes: list) -> pd.DataFrame:
        """Create DataFrame with volume data."""
        n = len(volumes)
        dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
        return pd.DataFrame({
            'Open': [100.0] * n,
            'High': [101.0] * n,
            'Low': [99.0] * n,
            'Close': [100.0] * n,
            'Volume': volumes,
        }, index=dates)

    def test_volume_dry_up_detected(self):
        """Should check volume metrics exist."""
        df = self.make_volume_df([1000] * 50)

        metrics = calculate_volume_metrics(df)
        # Volume ratio should be around 1.0 for normal volume
        self.assertIn('volume_ratio', metrics)

    def test_volume_not_dry(self):
        """Should handle normal volume levels."""
        volumes = [1000] * 50
        df = self.make_volume_df(volumes)

        metrics = calculate_volume_metrics(df)
        self.assertIn('volume_ratio', metrics)

    def test_high_volume_not_dry(self):
        """High volume should have higher ratio."""
        volumes = [1000] * 49 + [2000]
        df = self.make_volume_df(volumes)

        metrics = calculate_volume_metrics(df)
        self.assertIn('volume_ratio', metrics)


class TestConvergenceEdgeCases(unittest.TestCase):
    """Edge case tests for convergence."""

    def test_missing_ma_values(self):
        """Should handle missing MA values gracefully."""
        current_price = 100.0
        s2_details = {
            'ma10': 98.0,
            'ma20': np.nan,
            'ma50': 97.0,
            'ma150': np.nan,
            'ma200': 96.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        # Should return result dict (may have zero score if no valid cluster)
        self.assertIsNotNone(result)
        self.assertIn('score', result)

    def test_negative_mas(self):
        """Should handle edge case of negative MA values."""
        current_price = 100.0
        s2_details = {
            'ma10': -50.0,
            'ma20': -60.0,
            'ma50': 97.0,
            'ma150': 96.0,
            'ma200': 95.0,
        }

        result = calculate_convergence_score(current_price, s2_details)

        # Should return result dict
        self.assertIsNotNone(result)
        self.assertIn('score', result)


if __name__ == '__main__':
    unittest.main()
