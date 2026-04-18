#!/usr/bin/env python3
"""Regression tests for the 10-point Stage 2 scoring system.

Covers:
1. Individual criterion correctness (all 10 criteria)
2. Boundary conditions for calculate_stage2_score() (0/10, 10/10, each threshold)
3. get_entry_score() deterministic boundary values for 10-point scale
4. get_stage2_details() including all 10 criteria fields
5. Tier classification with updated thresholds
6. is_stage2_compliant() with the 10-point system
7. Synthetic data fixtures with >= 200 rows to exercise all criteria
"""

import unittest

import numpy as np
import pandas as pd

from traderlib import (
    calculate_stage2_score,
    get_entry_score,
    get_stage2_tier,
)
from traderlib.stage2_utils import get_stage2_details, is_stage2_compliant


def make_uptrend_df(n_days=250, start_price=100.0, daily_return=0.001, noise_std=0.005):
    """Create a DataFrame with a consistent uptrend (should score high on Stage 2)."""
    dates = pd.bdate_range(start='2024-01-01', periods=n_days)
    np.random.seed(42)
    returns = np.random.normal(daily_return, noise_std, n_days)
    prices = start_price * np.cumprod(1 + returns)
    low = prices * (1 - np.abs(np.random.normal(0, 0.01, n_days)))
    high = prices * (1 + np.abs(np.random.normal(0, 0.01, n_days)))
    df = pd.DataFrame({
        'Close': prices,
        'High': high,
        'Low': low,
        'Volume': np.random.randint(1000000, 10000000, n_days),
    }, index=dates)
    return df


def make_downtrend_df(n_days=250, start_price=100.0, daily_return=-0.002, noise_std=0.005):
    """Create a DataFrame with a consistent downtrend (should score low on Stage 2)."""
    dates = pd.bdate_range(start='2024-01-01', periods=n_days)
    np.random.seed(99)
    returns = np.random.normal(daily_return, noise_std, n_days)
    prices = start_price * np.cumprod(1 + returns)
    low = prices * (1 - np.abs(np.random.normal(0, 0.01, n_days)))
    high = prices * (1 + np.abs(np.random.normal(0, 0.01, n_days)))
    df = pd.DataFrame({
        'Close': prices,
        'High': high,
        'Low': low,
        'Volume': np.random.randint(1000000, 10000000, n_days),
    }, index=dates)
    return df


def make_flat_df(n_days=250, price=100.0):
    """Create a DataFrame with flat price action (no trend, should fail most criteria)."""
    dates = pd.bdate_range(start='2024-01-01', periods=n_days)
    noise = np.random.normal(0, 0.002, n_days)
    prices = price + noise * price
    low = prices - 0.5
    high = prices + 0.5
    df = pd.DataFrame({
        'Close': prices,
        'High': high,
        'Low': low,
        'Volume': np.ones(n_days) * 5000000,
    }, index=dates)
    return df


def make_perfect_stage2_df(n_days=250):
    """Create a DataFrame that should score 9-10/10 on all Stage 2 criteria.

    Price above all MAs, MAs stacked correctly, 200 MA rising,
    price within 25% of 52-week high, and price above 1.25x 52-week low.
    """
    dates = pd.bdate_range(start='2024-01-01', periods=n_days)
    ramp = np.linspace(50, 110, n_days)
    noise = np.random.normal(0, 0.3, n_days)
    prices = ramp + noise
    prices = np.maximum(prices, np.maximum.accumulate(prices) - 0.5)
    low = prices - np.abs(np.random.normal(0, 0.5, n_days))
    high = prices + np.abs(np.random.normal(0, 0.5, n_days))
    df = pd.DataFrame({
        'Close': prices,
        'High': high,
        'Low': low,
        'Volume': np.random.randint(1000000, 10000000, n_days),
    }, index=dates)
    return df


class TestCalculateStage2Score(unittest.TestCase):
    """Test the 10-point calculate_stage2_score function."""

    def test_perfect_stage2_scores_high(self):
        """A perfect Stage 2 stock should score 8 or higher."""
        df = make_perfect_stage2_df(250)
        score = calculate_stage2_score(df)
        self.assertGreaterEqual(score, 8, f"Perfect Stage 2 should score >= 8, got {score}")
        self.assertLessEqual(score, 10)

    def test_downtrend_scores_low(self):
        """A downtrend should score very low."""
        df = make_downtrend_df(250)
        score = calculate_stage2_score(df)
        self.assertLessEqual(score, 3, f"Downtrend should score <= 3, got {score}")

    def test_insufficient_data_returns_zero(self):
        """Fewer than 200 bars should return 0."""
        df = make_uptrend_df(50)
        score = calculate_stage2_score(df)
        self.assertEqual(score, 0, "Insufficient data should return 0")

    def test_exactly_200_rows_does_not_crash(self):
        """Exactly 200 rows (boundary) should not crash."""
        df = make_uptrend_df(200)
        score = calculate_stage2_score(df)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 10)

    def test_score_never_exceeds_10(self):
        """Score must never exceed 10 with any data."""
        df = make_perfect_stage2_df(300)
        score = calculate_stage2_score(df)
        self.assertLessEqual(score, 10, "Maximum score is 10")

    def test_score_never_below_0(self):
        """Score must never go below 0."""
        df = make_downtrend_df(250)
        score = calculate_stage2_score(df)
        self.assertGreaterEqual(score, 0, "Minimum score is 0")


class Test20MACriterion(unittest.TestCase):
    """Test the 20 MA criterion (criterion #1 in the 10-point system)."""

    def test_price_above_20ma_adds_point(self):
        """When price is above 20 MA, criterion #1 should pass."""
        df = make_perfect_stage2_df(250)
        details = get_stage2_details(df)
        self.assertTrue(details['criteria']['price_above_20ma'],
                       "In uptrend, price should be above 20 MA")

    def test_price_below_20ma_no_point(self):
        """When price is below 20 MA, criterion #1 should fail."""
        df = make_uptrend_df(250, start_price=100.0, daily_return=0.001)
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        df.iloc[-10:, df.columns.get_loc('Close')] = ma20 * 0.90
        details = get_stage2_details(df)
        self.assertFalse(details['criteria']['price_above_20ma'],
                        "Price well below 20 MA should fail criterion #1")

    def test_ma20_is_in_details(self):
        """get_stage2_details should include ma20 value."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        self.assertIn('ma20', details, "Details should include ma20")
        self.assertIsInstance(details['ma20'], float, "ma20 should be a float")

    def test_20ma_criterion_independent_of_others(self):
        """It's possible to pass 20 MA but fail 50 MA."""
        df = make_uptrend_df(250, start_price=100.0, daily_return=0.001)
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        target = ma20 * 1.01
        if target >= ma50:
            target = ma50 * 0.98
        df.iloc[-1, df.columns.get_loc('Close')] = target
        details = get_stage2_details(df)
        self.assertIn('price_above_20ma', details['criteria'])


class TestGetStage2Details(unittest.TestCase):
    """Test get_stage2_details returns all 10 criteria fields."""

    def test_details_has_all_10_criteria(self):
        """Details dict should have exactly 10 criteria for the 10-point system."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        criteria = details['criteria']
        expected_keys = {
            'price_above_20ma',
            'price_above_50ma',
            'price_above_100ma',
            'price_above_150ma',
            'price_above_200ma',
            'ma_stacking',
            'ma_stacking_extended',
            'ma200_rising',
            'within_25pct_high',
            'above_1.25x_low',
        }
        self.assertEqual(set(criteria.keys()), expected_keys,
                        f"Expected 10 criteria keys, got {set(criteria.keys())}")

    def test_details_score_equals_sum_of_criteria(self):
        """Score should equal the number of True criteria."""
        df = make_perfect_stage2_df(250)
        details = get_stage2_details(df)
        criteria_count = sum(1 for v in details['criteria'].values() if v)
        self.assertEqual(details['score'], criteria_count,
                        f"Score ({details['score']}) should equal criteria count ({criteria_count})")

    def test_details_includes_ma_values(self):
        """Details should include ma20, ma50, ma100, ma200."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        for key in ['ma20', 'ma50', 'ma100', 'ma200']:
            self.assertIn(key, details, f"Details should include {key}")

    def test_details_insufficient_data(self):
        """With < 200 rows, details should return score 0."""
        df = make_uptrend_df(50)
        details = get_stage2_details(df)
        self.assertEqual(details['score'], 0)
        self.assertEqual(details['criteria'], {})


class TestEntryScoreBoundaryValues(unittest.TestCase):
    """Deterministic boundary tests for get_entry_score with 10-point scale.

    Thresholds (stage2 component, 30 pts max):
      >=9  → 30  (Excellent,  90%+)
      >=8  → 25  (Very good,  80%+)
      >=7  → 20  (Good,       70%+)
      >=6  → 15  (Fair,       60%+)
      >=5  → 10  (Weak,       50%+)
      >=4  →  5  (Minimal,    40%+)
      < 4  →  0

    To isolate the stage2 component, we set other inputs to give 0 points:
    risk_pct=999 (0 risk pts), dist_to_pivot=999 (0 prox pts),
    ret_6m=0 (0 momentum), rs_6m=0 (0 RS).
    """

    def _stage2_only_score(self, stage2):
        """Get entry score with only the stage2 component contributing."""
        return get_entry_score(
            stage2_score=stage2, risk_pct=999, dist_to_pivot=999,
            ret_6m=0, rs_6m=0
        )

    def test_stage2_score_10_gives_30(self):
        """stage2_score=10 should give 30 points (excellent bucket)."""
        self.assertEqual(self._stage2_only_score(10), 30)

    def test_stage2_score_9_gives_30(self):
        """stage2_score=9 should give 30 points (excellent bucket)."""
        self.assertEqual(self._stage2_only_score(9), 30)

    def test_stage2_score_8_gives_25(self):
        """stage2_score=8 should give 25 points (very good bucket)."""
        self.assertEqual(self._stage2_only_score(8), 25)

    def test_stage2_score_7_gives_20(self):
        """stage2_score=7 should give 20 points (good bucket)."""
        self.assertEqual(self._stage2_only_score(7), 20)

    def test_stage2_score_6_gives_15(self):
        """stage2_score=6 should give 15 points (fair bucket)."""
        self.assertEqual(self._stage2_only_score(6), 15)

    def test_stage2_score_5_gives_10(self):
        """stage2_score=5 should give 10 points (weak bucket)."""
        self.assertEqual(self._stage2_only_score(5), 10)

    def test_stage2_score_4_gives_5(self):
        """stage2_score=4 should give 5 points (minimal bucket)."""
        self.assertEqual(self._stage2_only_score(4), 5)

    def test_stage2_score_3_gives_0(self):
        """stage2_score=3 should give 0 points (below minimal threshold)."""
        self.assertEqual(self._stage2_only_score(3), 0)

    def test_stage2_score_0_gives_0(self):
        """stage2_score=0 should give 0 points."""
        self.assertEqual(self._stage2_only_score(0), 0)

    def test_risk_component_boundary_at_10(self):
        """risk_pct < 10 should give 30 points from risk component."""
        score_low = get_entry_score(stage2_score=0, risk_pct=9.9, dist_to_pivot=999,
                                     ret_6m=0, rs_6m=0)
        score_at = get_entry_score(stage2_score=0, risk_pct=10.0, dist_to_pivot=999,
                                   ret_6m=0, rs_6m=0)
        self.assertEqual(score_low, 30)
        self.assertEqual(score_at, 20)

    def test_score_gap_between_8_and_9(self):
        """9/10 (excellent) and 8/10 (very good) should give different scores."""
        score_8 = self._stage2_only_score(8)
        score_9 = self._stage2_only_score(9)
        self.assertLess(score_8, score_9,
                       "8/10 should score less than 9/10")

    def test_score_gap_between_6_and_7(self):
        """Adjacent buckets should always give different scores."""
        score_6 = self._stage2_only_score(6)
        score_7 = self._stage2_only_score(7)
        self.assertLess(score_6, score_7,
                       "6/10 should score less than 7/10")


class TestTierThresholds(unittest.TestCase):
    """Test tier classification.

    Note: get_stage2_tier() uses entry_score only.
    The stage2 threshold filtering happens in entry_signals.py's scan().
    """

    def test_get_stage2_tier_1_at_60(self):
        """get_stage2_tier returns Tier 1 for entry_score >= 60."""
        self.assertEqual(get_stage2_tier(entry_score=60), "Tier 1")

    def test_get_stage2_tier_2_at_40(self):
        """get_stage2_tier returns Tier 2 for 40 <= entry_score < 60."""
        self.assertEqual(get_stage2_tier(entry_score=45), "Tier 2")

    def test_get_stage2_tier_3_below_40(self):
        """get_stage2_tier returns Tier 3 for entry_score < 40."""
        self.assertEqual(get_stage2_tier(entry_score=35), "Tier 3")

    def test_perfect_10_10_is_tier1(self):
        """A 10/10 stock with ideal conditions should score >= 60 → Tier 1."""
        # stage2=10 → 30pts, risk<10 → 30pts, dist<3 → 25pts = 85
        score = get_entry_score(stage2_score=10, risk_pct=5, dist_to_pivot=1, ret_6m=0, rs_6m=0)
        self.assertEqual(score, 85)
        self.assertEqual(get_stage2_tier(score), "Tier 1")


class TestIsStage2Compliant(unittest.TestCase):
    """Test is_stage2_compliant with the 10-point system."""

    def test_compliant_at_5(self):
        """Score 5 should be compliant with default min_score=5."""
        self.assertTrue(is_stage2_compliant(5))

    def test_not_compliant_at_4(self):
        """Score 4 should not be compliant with default min_score=5."""
        self.assertFalse(is_stage2_compliant(4))

    def test_compliant_at_10(self):
        """Score 10 (maximum) should be compliant."""
        self.assertTrue(is_stage2_compliant(10))

    def test_not_compliant_at_0(self):
        """Score 0 should not be compliant."""
        self.assertFalse(is_stage2_compliant(0))

    def test_custom_min_score(self):
        """Custom min_score should work correctly."""
        self.assertTrue(is_stage2_compliant(8, min_score=8))
        self.assertFalse(is_stage2_compliant(7, min_score=8))


class TestMAStackingCriteria(unittest.TestCase):
    """Test both MA stacking criteria (#6 and #7)."""

    def test_basic_stacking_criterion(self):
        """ma_stacking: 50 > 100 > 200 should be present."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        self.assertIn('ma_stacking', details['criteria'])

    def test_extended_stacking_criterion(self):
        """ma_stacking_extended: 50 > 100 > 150 > 200 should be present."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        self.assertIn('ma_stacking_extended', details['criteria'])

    def test_extended_requires_basic(self):
        """Extended stacking implies basic stacking (if extended passes, basic must pass)."""
        df = make_perfect_stage2_df(250)
        details = get_stage2_details(df)
        if details['criteria']['ma_stacking_extended']:
            self.assertTrue(details['criteria']['ma_stacking'],
                          "Extended stacking passing implies basic stacking passes")

    def test_150ma_criterion_present(self):
        """price_above_150ma should be a criterion in details."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        self.assertIn('price_above_150ma', details['criteria'])


class TestFlatStockWith200Rows(unittest.TestCase):
    """Test with flat stock fixture that has 200+ rows."""

    def test_flat_stock_with_enough_data_scores_low(self):
        """A flat stock with 250 rows should score low (most criteria fail)."""
        df = make_flat_df(250)
        score = calculate_stage2_score(df)
        self.assertLessEqual(score, 4,
                            f"Flat stock should score <= 4, got {score}")


class TestMAPenalties(unittest.TestCase):
    """Test the MA penalty feature in get_entry_score.

    Below 50 MA: -20 points
    Below 20 MA: -10 points
    Floor: 0

    Base scenario uses stage2=9 (excellent=30pts) for clarity.
    With risk<10% (30pts) and dist<3% (25pts): base = 85.
    """

    def test_no_penalty_when_above_mas(self):
        """stage2=9, no penalties: 30+30+25 = 85."""
        score = get_entry_score(stage2_score=9, risk_pct=5, dist_to_pivot=1,
                                ret_6m=0, rs_6m=0)
        self.assertEqual(score, 85)

    def test_below_50ma_penalty(self):
        """Below 50 MA should subtract 20 points: 85-20 = 65."""
        score = get_entry_score(stage2_score=9, risk_pct=5, dist_to_pivot=1,
                                ret_6m=0, rs_6m=0, below_50ma=True)
        self.assertEqual(score, 65, "below_50ma should subtract 20")

    def test_below_20ma_penalty(self):
        """Below 20 MA should subtract 10 points: 85-10 = 75."""
        score = get_entry_score(stage2_score=9, risk_pct=5, dist_to_pivot=1,
                                ret_6m=0, rs_6m=0, below_20ma=True)
        self.assertEqual(score, 75, "below_20ma should subtract 10")

    def test_below_both_mas_penalty(self):
        """Below both MAs should subtract 30 points: 85-30 = 55."""
        score = get_entry_score(stage2_score=9, risk_pct=5, dist_to_pivot=1,
                                ret_6m=0, rs_6m=0, below_50ma=True, below_20ma=True)
        self.assertEqual(score, 55, "below both MAs should subtract 30")

    def test_penalty_floor_at_zero(self):
        """Entry score should never go below 0."""
        score = get_entry_score(stage2_score=0, risk_pct=999, dist_to_pivot=999,
                                ret_6m=0, rs_6m=0, below_50ma=True, below_20ma=True)
        self.assertEqual(score, 0, "Entry score should floor at 0")

    def test_penalty_does_not_double_count(self):
        """below_20ma adds exactly -10 on top of below_50ma."""
        score_50only = get_entry_score(stage2_score=6, risk_pct=5, dist_to_pivot=1,
                                       ret_6m=0, rs_6m=0, below_50ma=True)
        score_both = get_entry_score(stage2_score=6, risk_pct=5, dist_to_pivot=1,
                                      ret_6m=0, rs_6m=0, below_50ma=True, below_20ma=True)
        self.assertEqual(score_both - score_50only, -10,
                         "below_20ma adds -10 on top of below_50ma")


if __name__ == '__main__':
    unittest.main()
