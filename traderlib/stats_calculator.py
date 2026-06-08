"""Pure equity-derived statistics for the dashboard lifetime panel.

The lifetime panel in the dashboard shows Sharpe, Max Drawdown, and Total
Trades. Total Trades comes from the engine's pre-fetched state dict. Sharpe
and Max DD are pure functions of an equity array and live here so the math
is testable in isolation, with no Alpaca, trade log, or file I/O.

Sharpe: annualizes per-period returns with sqrt(252) under the assumption
that the input is a daily equity series (1D timeframe). Max drawdown is
the worst peak-to-trough percentage decline, always non-positive.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

# Threshold for meaningful statistics. Below this point, the dashboard
# surfaces "--" for both metrics to avoid spurious precision on tiny samples.
MIN_EQUITY_POINTS: int = 30


def lifetime_stats(equities: List[float]) -> Dict[str, Optional[float]]:
    """Compute Sharpe ratio and maximum drawdown from an equity series.

    Args:
        equities: Time-ordered equity values. Assumed daily resolution
            (one point per trading day). All values must be positive.

    Returns:
        Dict with:
          - sharpe: Annualized Sharpe ratio (None if <30 points or std=0)
          - max_dd: Max drawdown as a non-positive fraction (None if <2 points)

        The output is always a dict with both keys present; values may be None
        when the input is too small or degenerate.
    """
    sharpe: Optional[float] = None
    max_dd: Optional[float] = None

    if not equities or len(equities) < MIN_EQUITY_POINTS:
        return {"sharpe": sharpe, "max_dd": max_dd}

    # --- Sharpe: per-period returns, annualized with sqrt(252) ---
    returns: List[float] = []
    for prev, curr in zip(equities, equities[1:]):
        if prev > 0:
            returns.append((curr - prev) / prev)

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        # Sample standard deviation (n-1)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance)
        if std_r > 0:
            sharpe = (mean_r / std_r) * math.sqrt(252)

    # --- Max drawdown: worst peak-to-trough decline, always non-positive ---
    if len(equities) >= 2:
        peak = equities[0]
        worst_dd = 0.0
        for value in equities:
            if value > peak:
                peak = value
            if peak > 0:
                dd = (value - peak) / peak  # 0.0 or negative
                if dd < worst_dd:
                    worst_dd = dd
        max_dd = worst_dd  # Non-positive (0.0 or negative)

    return {"sharpe": sharpe, "max_dd": max_dd}


# Backwards-compatible class wrapper: a few callers/tests in this codebase
# expect a StatsCalculator class. The class is a thin facade around the
# module-level function above.
class StatsCalculator:
    """Facade over `lifetime_stats` for class-based callers."""

    @staticmethod
    def lifetime_stats(equities: List[float]) -> Dict[str, Optional[float]]:
        return lifetime_stats(equities)
