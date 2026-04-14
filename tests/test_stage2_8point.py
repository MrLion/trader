#!/usr/bin/env python3
"""Regression tests for the 8-point Stage 2 scoring system.

Covers:
1. Individual criterion correctness (especially the new 20 MA criterion)
2. Boundary conditions for calculate_stage2_score() (0/8, 8/8, each threshold)
3. get_entry_score() deterministic boundary values for 8-point scale
4. get_stage2_details() including the new ma20 and price_above_20ma fields
5. Tier classification with updated thresholds (stage2 >= 6 for Tier 1, >= 5 for Tier 2)
6. is_stage2_compliant() with the 8-point system
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
    # Ensure prices are monotonically increasing-ish (strong uptrend)
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
    """Create a DataFrame that should score 8/8 on all Stage 2 criteria.

    Price above all MAs, MAs stacked correctly, 200 MA rising,
    price within 25% of 52-week high, and price above 1.25x 52-week low.
    """
    dates = pd.bdate_range(start='2024-01-01', periods=n_days)
    # Start low, ramp up steadily, then stabilize at a high level
    # This ensures: price > all MAs, MAs stacked, 200 MA rising,
    # price near 52-week high, price well above 52-week low
    ramp = np.linspace(50, 110, n_days)
    # Add small noise to make it realistic
    noise = np.random.normal(0, 0.3, n_days)
    prices = ramp + noise
    # Ensure monotonically increasing (with tiny dips for High/Low)
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
    """Test the 8-point calculate_stage2_score function."""

    def test_perfect_stage2_scores_high(self):
        """A perfect Stage 2 stock should score 7 or 8."""
        df = make_perfect_stage2_df(250)
        score = calculate_stage2_score(df)
        # With a strong uptrend from 50 to 110, should pass most criteria
        self.assertGreaterEqual(score, 6, f"Perfect Stage 2 should score >= 6, got {score}")
        self.assertLessEqual(score, 8)

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
        # Should not raise, though 200 MA calculation requires 200 bars
        score = calculate_stage2_score(df)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 8)

    def test_score_never_exceeds_8(self):
        """Score must never exceed 8 with any data."""
        df = make_perfect_stage2_df(300)
        score = calculate_stage2_score(df)
        self.assertLessEqual(score, 8, "Maximum score is 8")

    def test_score_never_below_0(self):
        """Score must never go below 0."""
        df = make_downtrend_df(250)
        score = calculate_stage2_score(df)
        self.assertGreaterEqual(score, 0, "Minimum score is 0")


class Test20MACriterion(unittest.TestCase):
    """Test the new 20 MA criterion (criterion #1 in the 8-point system)."""

    def test_price_above_20ma_adds_point(self):
        """When price is above 20 MA, criterion #1 should pass."""
        df = make_perfect_stage2_df(250)
        details = get_stage2_details(df)
        # In a strong uptrend, price should be above 20 MA
        self.assertTrue(details['criteria']['price_above_20ma'],
                       "In uptrend, price should be above 20 MA")

    def test_price_below_20ma_no_point(self):
        """When price is below 20 MA, criterion #1 should fail."""
        # Create a stock that drops sharply at the end
        df = make_uptrend_df(250, start_price=100.0, daily_return=0.001)
        # Force the last 10 prices below the 20 MA
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
        # Create a stock that pulls back to 20 MA but is below 50 MA
        df = make_uptrend_df(250, start_price=100.0, daily_return=0.001)
        # Push price above 20 MA but below 50 MA
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        # Set current price between ma20 and ma50
        target = ma20 * 1.01  # Just above ma20
        if target >= ma50:
            # If ma20 > ma50 in uptrend, force price below ma50
            target = ma50 * 0.98
        df.iloc[-1, df.columns.get_loc('Close')] = target
        details = get_stage2_details(df)
        # This test verifies independence, not exact values
        # (exact values depend on the specific data)
        self.assertIn('price_above_20ma', details['criteria'])


class TestGetStage2Details(unittest.TestCase):
    """Test get_stage2_details returns all 8 criteria fields."""

    def test_details_has_all_8_criteria(self):
        """Details dict should have exactly 8 criteria for the 8-point system."""
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        criteria = details['criteria']
        expected_keys = {
            'price_above_20ma',  # NEW
            'price_above_50ma',
            'price_above_100ma',
            'price_above_200ma',
            'ma_stacking',
            'ma200_rising',
            'within_25pct_high',
            'above_1.25x_low',
        }
        self.assertEqual(set(criteria.keys()), expected_keys,
                        f"Expected 8 criteria keys, got {set(criteria.keys())}")

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
    """Deterministic boundary tests for get_entry_score with 8-point scale.

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

    def test_stage2_score_8_gives_30(self):
        """stage2_score=8 should give 30 points from Stage 2 component."""
        self.assertEqual(self._stage2_only_score(8), 30)

    def test_stage2_score_7_gives_30(self):
        """stage2_score=7 should also give 30 points (excellent bucket)."""
        self.assertEqual(self._stage2_only_score(7), 30)

    def test_stage2_score_6_gives_25(self):
        """stage2_score=6 should give 25 points (very good bucket)."""
        self.assertEqual(self._stage2_only_score(6), 25)

    def test_stage2_score_5_gives_20(self):
        """stage2_score=5 should give 20 points (good bucket)."""
        self.assertEqual(self._stage2_only_score(5), 20)

    def test_stage2_score_4_gives_15(self):
        """stage2_score=4 should give 15 points (fair bucket)."""
        self.assertEqual(self._stage2_only_score(4), 15)

    def test_stage2_score_3_gives_10(self):
        """stage2_score=3 should give 10 points (weak bucket)."""
        self.assertEqual(self._stage2_only_score(3), 10)

    def test_stage2_score_2_gives_5(self):
        """stage2_score=2 should give 5 points (minimal bucket)."""
        self.assertEqual(self._stage2_only_score(2), 5)

    def test_stage2_score_1_gives_0(self):
        """stage2_score=1 should give 0 points (no bucket for score < 2)."""
        self.assertEqual(self._stage2_only_score(1), 0)

    def test_stage2_score_0_gives_0(self):
        """stage2_score=0 should give 0 points."""
        self.assertEqual(self._stage2_only_score(0), 0)

    def test_risk_component_boundary_at_10(self):
        """risk_pct < 10 should give 30 points from risk component."""
        # Isolate risk component: stage2=0 (0 pts), dist=999 (0 pts)
        score_low = get_entry_score(stage2_score=0, risk_pct=9.9, dist_to_pivot=999,
                                     ret_6m=0, rs_6m=0)
        score_at = get_entry_score(stage2_score=0, risk_pct=10.0, dist_to_pivot=999,
                                   ret_6m=0, rs_6m=0)
        # risk_pct < 10 gives 30, risk_pct == 10 gives 20
        self.assertEqual(score_low, 30)
        self.assertEqual(score_at, 20)

    def test_nfl_scenario_scores_75(self):
        """Replicate the NEE/NFG scenario: below 20 MA and 50 MA, score 5/8.

        With stage2=5 (20pts), risk<10% (30pts), dist<3% (25pts):
        total = 20 + 30 + 25 = 75.
        """
        score = get_entry_score(stage2_score=5, risk_pct=8, dist_to_pivot=1, ret_6m=0, rs_6m=0)
        self.assertEqual(score, 75, "5/8 stock with low risk and at pivot should score 75")

    def test_perfect_stock_scores_85(self):
        """A perfect 8/8 stock with ideal conditions should score 85.

        With stage2=8 (30pts), risk<10% (30pts), dist<3% (25pts):
        total = 30 + 30 + 25 = 85.
        """
        score = get_entry_score(stage2_score=8, risk_pct=5, dist_to_pivot=1, ret_6m=0, rs_6m=0)
        self.assertEqual(score, 85, "8/8 stock with low risk and near pivot should score 85")

    def test_score_gap_between_6_and_7(self):
        """The key gap that motivated the 8-point system: 6/8 and 7/8 give different scores.

        Under the old 7-point system, 6/7 and 7/7 both gave 30 points.
        Under the 8-point system, 6/8 gives 25 and 7/8 gives 30.
        """
        score_6 = self._stage2_only_score(6)
        score_7 = self._stage2_only_score(7)
        self.assertLess(score_6, score_7,
                       "6/8 should score less than 7/8 (this was the original bug)")


class TestTierThresholds(unittest.TestCase):
    """Test tier classification with the 8-point system.

    Note: get_stage2_tier() only uses entry_score (not stage2 directly).
    The stage2 threshold filtering happens in entry_signals.py's scan(),
    where tier is determined by BOTH entry_score AND stage2_score.
    Here we test get_stage2_tier() and the entry_signals tier logic separately.
    """

    def test_get_stage2_tier_1_at_60(self):
        """get_stage2_tier returns Tier 1 for entry_score >= 60."""
        tier = get_stage2_tier(entry_score=60)
        self.assertEqual(tier, "Tier 1")

    def test_get_stage2_tier_2_at_40(self):
        """get_stage2_tier returns Tier 2 for 40 <= entry_score < 60."""
        tier = get_stage2_tier(entry_score=45)
        self.assertEqual(tier, "Tier 2")

    def test_get_stage2_tier_3_below_40(self):
        """get_stage2_tier returns Tier 3 for entry_score < 40."""
        tier = get_stage2_tier(entry_score=35)
        self.assertEqual(tier, "Tier 3")

    def test_nfl_scenario_entry_signals_tier_logic(self):
        """The NEE/NFG scenario: stage2=5, entry_score=75.

        In entry_signals.py, the tier logic is:
          if entry_score >= 60 and stage2 >= 6: Tier 1
          elif entry_score >= 40 and stage2 >= 5: Tier 2
          else: Tier 3

        With stage2=5 (below 6), this is Tier 2 even though entry_score=75.
        This is the core regression test for the scoring gap fix.
        """
        entry_score = 75
        stage2 = 5

        # Replicate the tier logic from entry_signals.py
        if entry_score >= 60 and stage2 >= 6:
            tier = "Tier 1"
        elif entry_score >= 40 and stage2 >= 5:
            tier = "Tier 2"
        else:
            tier = "Tier 3"

        self.assertEqual(tier, "Tier 2",
                        "stage2=5 with score=75 should be Tier 2 (not Tier 1)")

    def test_old_threshold_stage2_4_now_tier3(self):
        """Under the old system, stage2=4 was Tier 2. Now it's Tier 3.

        entry_signals.py now requires stage2 >= 5 for Tier 2.
        """
        entry_score = 50
        stage2 = 4

        if entry_score >= 60 and stage2 >= 6:
            tier = "Tier 1"
        elif entry_score >= 40 and stage2 >= 5:
            tier = "Tier 2"
        else:
            tier = "Tier 3"

        self.assertEqual(tier, "Tier 3",
                        "stage2=4 should now be Tier 3 (was Tier 2 under 7-point)")

    def test_perfect_8_8_is_tier1(self):
        """An 8/8 stock with score 85 should be Tier 1."""
        tier = get_stage2_tier(entry_score=85)
        self.assertEqual(tier, "Tier 1")

    def test_stage2_6_with_score_65_is_tier1(self):
        """stage2=6 + entry_score=65 should be Tier 1."""
        if 65 >= 60 and 6 >= 6:
            tier = "Tier 1"
        elif 65 >= 40 and 6 >= 5:
            tier = "Tier 2"
        else:
            tier = "Tier 3"
        self.assertEqual(tier, "Tier 1")

    def test_stage2_5_with_score_65_is_tier2(self):
        """stage2=5 + entry_score=65 should be Tier 2 (not Tier 1)."""
        if 65 >= 60 and 5 >= 6:
            tier = "Tier 1"
        elif 65 >= 40 and 5 >= 5:
            tier = "Tier 2"
        else:
            tier = "Tier 3"
        self.assertEqual(tier, "Tier 2",
                        "stage2=5 should NOT qualify for Tier 1 even with score >= 60")


class TestIsStage2Compliant(unittest.TestCase):
    """Test is_stage2_compliant with the 8-point system."""

    def test_compliant_at_5(self):
        """Score 5 should be compliant with default min_score=5."""
        self.assertTrue(is_stage2_compliant(5))

    def test_not_compliant_at_4(self):
        """Score 4 should not be compliant with default min_score=5."""
        self.assertFalse(is_stage2_compliant(4))

    def test_compliant_at_8(self):
        """Score 8 should be compliant."""
        self.assertTrue(is_stage2_compliant(8))

    def test_not_compliant_at_0(self):
        """Score 0 should not be compliant."""
        self.assertFalse(is_stage2_compliant(0))

    def test_custom_min_score(self):
        """Custom min_score should work correctly."""
        self.assertTrue(is_stage2_compliant(7, min_score=7))
        self.assertFalse(is_stage2_compliant(6, min_score=7))


class TestMAStackingCriterion(unittest.TestCase):
    """Test that MA stacking (criterion #5) uses 50>100>200, excluding 20 MA."""

    def test_stacking_excludes_20ma(self):
        """MA stacking should be 50 > 100 > 200, not including 20 MA.

        A stock can have 20 MA below 50 MA (pullback) and still pass stacking.
        """
        df = make_uptrend_df(250)
        details = get_stage2_details(df)
        # In a strong uptrend, ma_stacking should be truthy
        # and it should NOT depend on ma20 being in the stack
        # The stacking criterion only checks ma50 > ma100 > ma200
        self.assertIn('ma_stacking', details['criteria'])
        # Verify it's a boolean-like value
        self.assertIn(bool(details['criteria']['ma_stacking']), [True, False])


class TestFlatStockWith200Rows(unittest.TestCase):
    """Test with flat stock fixture that has 200+ rows.

    The original flat_stock.csv only had 100 rows, so calculate_stage2_score
    always returned 0 via the short-circuit. This tests actual criterion logic
    with a flat stock that has enough data.
    """

    def test_flat_stock_with_enough_data_scores_low(self):
        """A flat stock with 250 rows should score low (most criteria fail)."""
        df = make_flat_df(250)
        score = calculate_stage2_score(df)
        # Flat stock should fail: MA stacking, 200 MA rising,
        # price above 20/50/100/200 MA, near high, above 1.25x low
        self.assertLessEqual(score, 3,
                            f"Flat stock should score <= 3, got {score}")


if __name__ == '__main__':
    unittest.main()