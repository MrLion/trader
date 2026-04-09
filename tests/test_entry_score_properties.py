#!/usr/bin/env python3
"""Phase 2: Property-Based Testing for Entry Scoring.
Use Hypothesis to prove invariants about the entry score logic.
"""

import unittest
from hypothesis import given, strategies as st
from pathlib import Path
import sys

from scripts.lib.stage2_utils import get_entry_score

class TestEntryScoreProperties(unittest.TestCase):
    """Prove properties of the entry score using Hypothesis."""

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000)
    )
    def test_score_bounds(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: Entry score must always be between 0 and 110."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 110)

    @given(
        stage2=st.floats(min_value=8, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=2),
        dist_to_pivot=st.floats(min_value=-0.5, max_value=0.5),
        ret_6m=st.floats(min_value=30, max_value=100),
        rs_6m=st.floats(min_value=10, max_value=50)
    )
    def test_tier1_implies_high_score(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: Ideal conditions must result in a Tier 1 score (>= 60)."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)
        self.assertGreaterEqual(score, 60)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=0, max_value=100),
        dist_to_pivot=st.floats(min_value=-1, max_value=1),
        ret_6m=st.floats(min_value=-100, max_value=100),
        rs_6m=st.floats(min_value=-100, max_value=100)
    )
    def test_symmetric_proximity(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: Symmetric distance from pivot should yield the same score."""
        score_pos = get_entry_score(stage2, risk_pct, abs(dist_to_pivot), ret_6m, rs_6m)
        score_neg = get_entry_score(stage2, risk_pct, -abs(dist_to_pivot), ret_6m, rs_6m)
        self.assertEqual(score_pos, score_neg)

    @given(
        stage2=st.floats(min_value=0, max_value=10),
        risk_pct=st.floats(min_value=26, max_value=100),
        dist_to_pivot=st.floats(min_value=-10, max_value=10),
        ret_6m=st.floats(min_value=-100, max_value=1000),
        rs_6m=st.floats(min_value=-100, max_value=1000)
    )
    def test_extreme_risk_penalty(self, stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m):
        """Property: Risk > 25% should severely penalize the score."""
        score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)
        # Given the logic, risk > 25% should’ve knocked out most of the points
        self.assertLess(score, 80)

if __name__ == '__main__':
    unittest.main()
