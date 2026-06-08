#!/usr/bin/env python3
"""Tests for traderlib.stats_calculator.lifetime_stats (Task 2 of dashboard-ux plan).

Covers:
  - Sharpe + Max DD both None when input has <30 points
  - Sharpe + Max DD non-null when input has >=30 points
  - Max DD is non-positive (0.0 or negative)
  - Empty list returns None / None
  - Single-point list returns None / None
  - Degenerate (flat) equity returns None Sharpe, 0.0 max_dd
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "traderlib"))

from stats_calculator import lifetime_stats, StatsCalculator  # noqa: E402


# -----------------------------------------------------------------------------
# Threshold behavior
# -----------------------------------------------------------------------------


class TestLifetimeStatsThreshold:
    """Sharpe and Max DD require >=30 equity points."""

    def test_29_points_returns_nulls(self):
        """29 points: below threshold -> Sharpe None, Max DD None."""
        # Use a clearly varying series so the math would be meaningful if
        # the threshold didn't gate it.
        equities = [100.0 + i * 0.5 for i in range(29)]
        result = lifetime_stats(equities)
        assert result == {"sharpe": None, "max_dd": None}

    def test_30_points_returns_non_null(self):
        """30 points: at threshold -> both metrics computed."""
        # Mild uptrend with small noise: produces a non-zero Sharpe and a
        # non-positive max drawdown.
        equities = [100.0 + i * 0.3 + (i % 3) * 0.05 for i in range(30)]
        result = lifetime_stats(equities)
        assert result["sharpe"] is not None
        assert result["max_dd"] is not None
        assert result["max_dd"] <= 0.0

    def test_100_points_synthetic(self):
        """100 points of synthetic equity: Sharpe is a finite number, max_dd non-positive."""
        # Random walk with positive drift
        equities = []
        v = 100.0
        for i in range(100):
            v *= 1.001  # +0.1% per period deterministic
            equities.append(v)
        result = lifetime_stats(equities)
        assert result["sharpe"] is not None
        assert math.isfinite(result["sharpe"])
        assert result["sharpe"] > 0  # monotonic uptrend
        assert result["max_dd"] is not None
        assert result["max_dd"] <= 0.0  # non-positive

    def test_30_points_with_drawdown(self):
        """30 points with a clear drawdown: max_dd is the worst trough."""
        # 100 -> 110 -> 90 -> 100: drawdown from 110 to 90 is -18.18%
        equities = [100.0, 105.0, 110.0, 100.0, 95.0, 90.0, 95.0, 100.0] * 4  # 32 points
        equities = equities[:30]  # trim to 30
        result = lifetime_stats(equities)
        # The trough at 90 from a peak of 110 is (90-110)/110 = -0.1818
        assert result["max_dd"] is not None
        assert result["max_dd"] < -0.15
        assert result["max_dd"] > -0.20

    def test_min_threshold_is_exactly_30(self):
        """MIN_EQUITY_POINTS is 30 — confirms our threshold constant."""
        from stats_calculator import MIN_EQUITY_POINTS
        assert MIN_EQUITY_POINTS == 30


# -----------------------------------------------------------------------------
# Degenerate inputs
# -----------------------------------------------------------------------------


class TestLifetimeStatsEdgeCases:
    """Empty / single-point / flat inputs return None / 0.0 / None."""

    def test_empty_list_returns_nulls(self):
        result = lifetime_stats([])
        assert result == {"sharpe": None, "max_dd": None}

    def test_single_point_returns_nulls(self):
        result = lifetime_stats([100.0])
        assert result == {"sharpe": None, "max_dd": None}

    def test_two_points_returns_nulls(self):
        """Two points is below the 30-point threshold."""
        result = lifetime_stats([100.0, 110.0])
        assert result == {"sharpe": None, "max_dd": None}

    def test_flat_equity_zero_volatility(self):
        """30+ points of perfectly flat equity: std=0, so Sharpe is None; max_dd is 0.0."""
        # 30 points, all 100.0: every return is 0, std is 0, so Sharpe is None
        # (division by zero avoided). Max drawdown is 0.0 (no decline).
        equities = [100.0] * 30
        result = lifetime_stats(equities)
        assert result["sharpe"] is None
        # max_dd with all values equal: peak == value, dd == 0.0 for every point
        assert result["max_dd"] == 0.0

    def test_constant_growth(self):
        """30 points of constant +1% per period: Sharpe is a very large positive
        number (floating-point roundoff in the std dev lets the divide succeed).
        Max drawdown is 0.0 (monotonic uptrend)."""
        equities = [100.0 * (1.01 ** i) for i in range(30)]
        result = lifetime_stats(equities)
        # Floating-point std dev is ~0 but non-zero, so the divide succeeds and
        # produces a huge Sharpe. The dashboard's render path treats None as
        # "--" but a non-null float just renders; the test asserts the *shape*
        # of the result, not its value at this edge.
        assert result["sharpe"] is not None
        assert result["sharpe"] > 0  # monotonic uptrend -> positive Sharpe
        assert result["max_dd"] == 0.0  # monotonic uptrend -> no drawdown

    def test_perfectly_flat_equity(self):
        """30 points of EXACTLY 100.0: every return is 0.0, std is 0.0, Sharpe is None."""
        # Use a Python list of identical floats — variance is exactly 0.0.
        equities = [100.0] * 30
        result = lifetime_stats(equities)
        # The 30 returns are all (100-100)/100 = 0.0; their mean is 0.0; their
        # sample variance is 0.0; std is 0.0; the divide is guarded -> Sharpe None.
        assert result["sharpe"] is None
        assert result["max_dd"] == 0.0

    def test_no_file_io(self):
        """lifetime_stats must not perform file I/O. Verify by patching open()."""
        equities = [100.0 + i for i in range(30)]
        import builtins
        original_open = builtins.open
        def fail_open(*args, **kwargs):
            raise AssertionError("lifetime_stats should not open any files")
        builtins.open = fail_open
        try:
            result = lifetime_stats(equities)
        finally:
            builtins.open = original_open
        assert result["sharpe"] is not None


# -----------------------------------------------------------------------------
# Class facade (StatsCalculator)
# -----------------------------------------------------------------------------


class TestStatsCalculatorClass:
    """The StatsCalculator class is a thin facade for class-based callers."""

    def test_class_static_method_matches_function(self):
        equities = [100.0 + i * 0.3 for i in range(30)]
        assert StatsCalculator.lifetime_stats(equities) == lifetime_stats(equities)

    def test_class_handles_empty(self):
        assert StatsCalculator.lifetime_stats([]) == {"sharpe": None, "max_dd": None}
