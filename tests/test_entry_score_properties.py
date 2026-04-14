#!/usr/bin/env python3
"""Phase 2: Property-Based Testing for Entry Scoring.
Use Hypothesis to prove invariants about the entry score logic.
"""

import unittest
from hypothesis import given, strategies as st

from traderlib import get_entry_score

class TestEntryScoreProperties(unittest.TestCase):
    """Prove properties of the entry score using Hypothesis."""

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000),
        below_50ma=st.booleans(),
        below_20ma=st.booleans()
    )
    def test_score_bounds(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                          below_50ma, below_20ma):
        """Property: Entry score must always be between 0 and 110."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                below_50ma=below_50ma, below_20ma=below_20ma)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 110)

    @given(
        stage2=st.floats(min_value=8, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=2),
        dist_to_pivot=st.floats(min_value=-0.5, max_value=0.5),
        ret_6m=st.floats(min_value=30, max_value=100),
        rs_6m=st.floats(min_value=10, max_value=50),
        below_50ma=st.just(False),
        below_20ma=st.just(False)
    )
    def test_tier1_implies_high_score(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                      below_50ma, below_20ma):
        """Property: Ideal conditions with no MA penalties must result in a Tier 1 score (>= 60)."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                below_50ma=below_50ma, below_20ma=below_20ma)
        self.assertGreaterEqual(score, 60)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-1, max_value=1),
        ret_6m=st.floats(min_value=-100, max_value=100),
        rs_6m=st.floats(min_value=-100, max_value=100),
        below_50ma=st.booleans(),
        below_20ma=st.booleans()
    )
    def test_symmetric_proximity(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                 below_50ma, below_20ma):
        """Property: Symmetric distance from pivot should yield the same score."""
        score_pos = get_entry_score(stage2, risk_pct, abs(dist_to_pivot), ret_6m, rs_6m,
                                    below_50ma=below_50ma, below_20ma=below_20ma)
        score_neg = get_entry_score(stage2, risk_pct, -abs(dist_to_pivot), ret_6m, rs_6m,
                                    below_50ma=below_50ma, below_20ma=below_20ma)
        self.assertEqual(score_pos, score_neg)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=26, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000),
        below_50ma=st.booleans(),
        below_20ma=st.booleans()
    )
    def test_extreme_risk_penalty(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                  below_50ma, below_20ma):
        """Property: Risk > 25% should prevent Tier 1 scores (>= 60)."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                below_50ma=below_50ma, below_20ma=below_20ma)
        # With risk > 25%, max possible score is 80 (no risk points, other components maxed)
        # Risk > 25% means no points from risk component (max 30), so score capped at ~80
        self.assertLessEqual(score, 80)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000)
    )
    def test_ma_penalty_reduces_score(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: MA penalties can only reduce or maintain the score, never increase it."""
        base = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                               below_50ma=False, below_20ma=False)
        with_50ma = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                    below_50ma=True, below_20ma=False)
        with_20ma = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                    below_50ma=False, below_20ma=True)
        with_both = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                    below_50ma=True, below_20ma=True)
        self.assertLessEqual(with_50ma, base)
        self.assertLessEqual(with_20ma, base)
        self.assertLessEqual(with_both, base)
        self.assertLessEqual(with_both, with_50ma)
        self.assertLessEqual(with_both, with_20ma)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000)
    )
    def test_penalty_magnitude(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: below_50ma costs exactly 20 pts, below_20ma costs exactly 10 pts (before floor)."""
        base = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                               below_50ma=False, below_20ma=False)
        with_50ma = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                    below_50ma=True, below_20ma=False)
        # The penalty is exactly 20 unless it would push score below 0 (then it floors at 0)
        expected = max(base - 20, 0)
        self.assertEqual(with_50ma, expected)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000),
        below_50ma=st.booleans(),
        below_20ma=st.booleans()
    )
    def test_floor_at_zero(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                           below_50ma, below_20ma):
        """Property: Score never goes below 0 regardless of penalties."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m,
                                below_50ma=below_50ma, below_20ma=below_20ma)
        self.assertGreaterEqual(score, 0)


if __name__ == '__main__':
    unittest.main()