#!/usr/bin/env python3
"""Shared Stage 2 criteria calculation utilities.

Canonical 8-point system based on Mark Minervini's trend template
plus short-term trend confirmation:
1. Price > 20 MA (short-term trend)
2. Price > 50 MA (medium-term trend)
3. Price > 100 MA (intermediate trend)
4. Price > 200 MA (long-term trend)
5. MA Stacking: 50 > 100 > 200 (proper order, 20 MA excluded as too volatile)
6. 200 MA rising for 20+ days (sustained uptrend)
7. Price within 25% of 52-week high
8. Price >= 1.25x 52-week low (strong recovery)
"""

from typing import Optional

import pandas as pd


def calculate_stage2_score(hist: pd.DataFrame) -> int:
    """
    Calculate Stage 2 score using canonical 8-point system.

    Args:
        hist: DataFrame with price history containing 'Close', 'High', 'Low' columns
              Must have at least 200 days for full calculation

    Returns:
        int: Score from 0-8
    """
    if len(hist) < 200:
        return 0

    current = hist['Close'].iloc[-1]
    high_52w = hist['Close'].max()
    low_52w = hist['Close'].min()

    # Calculate moving averages
    ma20 = hist['Close'].rolling(20).mean().iloc[-1]
    ma50 = hist['Close'].rolling(50).mean().iloc[-1]
    ma100 = hist['Close'].rolling(100).mean().iloc[-1]
    ma200 = hist['Close'].rolling(200).mean().iloc[-1]

    score = 0

    # 1. Price > 20 MA
    if current > ma20:
        score += 1

    # 2. Price > 50 MA
    if current > ma50:
        score += 1

    # 3. Price > 100 MA
    if current > ma100:
        score += 1

    # 4. Price > 200 MA
    if current > ma200:
        score += 1

    # 5. Proper MA stacking: 50 > 100 > 200 (20 MA excluded, too volatile)
    if ma50 > ma100 > ma200:
        score += 1

    # 6. 200 MA rising for 20+ days (compare to value 20 days ago)
    if len(hist) >= 221:
        ma200_20days_ago = hist['Close'].rolling(200).mean().iloc[-21]
        if ma200 > ma200_20days_ago:
            score += 1
    else:
        # Fallback: just check if MA200 is rising vs 1 day ago
        ma200_1day_ago = hist['Close'].rolling(200).mean().iloc[-2]
        if ma200 > ma200_1day_ago:
            score += 1

    # 7. Price within 25% of 52-week high
    from_high = ((high_52w - current) / high_52w) * 100
    if from_high < 25:
        score += 1

    # 8. Price >= 1.25x 52-week low (strong recovery from lows)
    if current >= low_52w * 1.25:
        score += 1

    return score


def get_stage2_details(hist: pd.DataFrame) -> dict:
    """
    Get detailed breakdown of Stage 2 criteria for reporting.

    Args:
        hist: DataFrame with price history

    Returns:
        dict with score and individual criterion status
    """
    if len(hist) < 200:
        return {'score': 0, 'criteria': {}}

    current = hist['Close'].iloc[-1]
    high_52w = hist['Close'].max()
    low_52w = hist['Close'].min()

    ma10 = hist['Close'].rolling(10).mean().iloc[-1]
    ma20 = hist['Close'].rolling(20).mean().iloc[-1]
    ma50 = hist['Close'].rolling(50).mean().iloc[-1]
    ma100 = hist['Close'].rolling(100).mean().iloc[-1]
    ma200 = hist['Close'].rolling(200).mean().iloc[-1]

    from_high = ((high_52w - current) / high_52w) * 100

    criteria = {
        'price_above_20ma': current > ma20,
        'price_above_50ma': current > ma50,
        'price_above_100ma': current > ma100,
        'price_above_200ma': current > ma200,
        'ma_stacking': ma50 > ma100 > ma200,
        'ma200_rising': False,
        'within_25pct_high': from_high < 25,
        'above_1.25x_low': current >= low_52w * 1.25
    }

    # 200 MA rising check
    if len(hist) >= 221:
        ma200_20days_ago = hist['Close'].rolling(200).mean().iloc[-21]
        criteria['ma200_rising'] = ma200 > ma200_20days_ago
    else:
        ma200_1day_ago = hist['Close'].rolling(200).mean().iloc[-2]
        criteria['ma200_rising'] = ma200 > ma200_1day_ago

    score = sum(criteria.values())

    return {
        'score': score,
        'criteria': criteria,
        'current': current,
        'ma10': ma10,
        'ma20': ma20,
        'ma50': ma50,
        'ma100': ma100,
        'ma200': ma200,
        'high_52w': high_52w,
        'low_52w': low_52w,
        'from_high_pct': from_high
    }


def is_stage2_compliant(score: int, min_score: int = 5) -> bool:
    """
    Check if a stock meets minimum Stage 2 compliance.

    Args:
        score: Stage 2 score (0-8)
        min_score: Minimum score to be considered compliant (default 5)

    Returns:
        bool: True if compliant
    """
    return score >= min_score


def calculate_ma_support_stop(
    current_price: float,
    s2_details: dict,
    buffer_pct: float = 0.01,
    cluster_spread_pct: float = 0.05,
    min_cluster_size: int = 2
) -> Optional[dict]:
    """
    Calculate MA support stop based on clustered moving averages below price.

    When moving averages converge below the price, they form a natural support zone.
    A stop based on that zone is structurally more logical and often tighter than ATR.

    Algorithm:
    1. Collect all MAs from s2_details that are below current_price
    2. If fewer than min_cluster_size MAs below price -> return None
    3. Check cluster spread: (highest_ma - lowest_ma) / highest_ma
       If > cluster_spread_pct -> return None (not converged)
    4. Stop = lowest_ma * (1 - buffer_pct) — pure percentage buffer, NO ATR

    Args:
        current_price: Current stock price
        s2_details: Dictionary from get_stage2_details() containing MA values
        buffer_pct: Buffer percentage below lowest MA (default 1%)
        cluster_spread_pct: Maximum spread for MA cluster (default 5%)
        min_cluster_size: Minimum number of MAs required in cluster (default 2)

    Returns:
        Dictionary with MA support stop details, or None if no valid cluster
        {
            'ma_support_stop': float,
            'lowest_ma': str,
            'cluster_mas': list,
            'cluster_spread_pct': float
        }
    """
    if not s2_details or 'ma10' not in s2_details:
        return None

    # Collect all MAs that are below current price
    ma_values = {
        'ma10': s2_details.get('ma10'),
        'ma20': s2_details.get('ma20'),
        'ma50': s2_details.get('ma50'),
        'ma100': s2_details.get('ma100'),
        'ma200': s2_details.get('ma200'),
    }

    mas_below_price = []
    for ma_name, ma_val in ma_values.items():
        if ma_val is not None and pd.notna(ma_val) and ma_val < current_price:
            mas_below_price.append((ma_name, float(ma_val)))

    # Need at least min_cluster_size MAs below price
    if len(mas_below_price) < min_cluster_size:
        return None

    # Sort by value (lowest first)
    mas_below_price.sort(key=lambda x: x[1])

    lowest_ma_name, lowest_ma_val = mas_below_price[0]
    highest_ma_name, highest_ma_val = mas_below_price[-1]

    # Check cluster spread
    spread_pct = (highest_ma_val - lowest_ma_val) / highest_ma_val
    if spread_pct > cluster_spread_pct:
        return None

    # Calculate stop: lowest MA minus buffer
    stop = lowest_ma_val * (1 - buffer_pct)

    return {
        'ma_support_stop': round(stop, 2),
        'lowest_ma': lowest_ma_name,
        'cluster_mas': [name for name, _ in mas_below_price],
        'cluster_spread_pct': round(spread_pct * 100, 2)
    }


def get_entry_score(stage2_score: int, risk_pct: float, dist_to_pivot: float,
                    ret_6m: float, rs_6m: float,
                    below_50ma: bool = False,
                    below_20ma: bool = False) -> int:
    """
    Calculate entry attractiveness score (0-100) using updated thresholds for 8-point system.

    Args:
        stage2_score: Stage 2 score (0-8)
        risk_pct: Risk percentage
        dist_to_pivot: Distance to pivot point (positive = below pivot)
        ret_6m: 6-month return percentage
        rs_6m: Relative strength vs SPY (6-month)
        below_50ma: True if price is below 50 MA (applies -20 penalty)
        below_20ma: True if price is below 20 MA (applies -10 penalty)

    Returns:
        int: Entry score (0-100)
    """
    entry_score = 0

    # Stage 2 score component (30 pts max) - updated for 8-point system
    if stage2_score >= 7:   # Excellent
        entry_score += 30
    elif stage2_score >= 6:  # Very good
        entry_score += 25
    elif stage2_score >= 5:  # Good
        entry_score += 20
    elif stage2_score >= 4:  # Fair
        entry_score += 15
    elif stage2_score >= 3:  # Weak
        entry_score += 10
    elif stage2_score >= 2:  # Minimal
        entry_score += 5

    # Risk % component (30 pts max)
    if risk_pct < 10:
        entry_score += 30
    elif risk_pct < 15:
        entry_score += 20
    elif risk_pct < 20:
        entry_score += 10
    elif risk_pct < 25:
        entry_score += 5

    # Proximity to pivot component (25 pts max) - symmetric (within ±10%)
    dist_abs = abs(dist_to_pivot)
    if dist_abs < 3:
        entry_score += 25
    elif dist_abs < 5:
        entry_score += 15
    elif dist_abs < 10:
        entry_score += 5

    # Momentum component (15 pts max)
    if ret_6m > 50:
        entry_score += 15
    elif ret_6m > 25:
        entry_score += 10

    # RS bonus (10 pts max)
    if rs_6m > 20:
        entry_score += 10
    elif rs_6m > 10:
        entry_score += 5

    # MA penalties — below key MAs indicates trend weakness
    if below_50ma:
        entry_score -= 20
    if below_20ma:
        entry_score -= 10

    return max(entry_score, 0)


def get_stage2_tier(entry_score: int) -> str:
    """
    Get tier classification based on entry score.

    Args:
        entry_score: Entry attractiveness score (0-100)

    Returns:
        str: Tier classification
    """
    if entry_score >= 60:
        return "Tier 1"
    elif entry_score >= 40:
        return "Tier 2"
    else:
        return "Tier 3"
