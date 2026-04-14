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


def get_entry_score(stage2_score: int, risk_pct: float, dist_to_pivot: float,
                    ret_6m: float, rs_6m: float) -> int:
    """
    Calculate entry attractiveness score (0-100) using updated thresholds for 8-point system.

    Args:
        stage2_score: Stage 2 score (0-8)
        risk_pct: Risk percentage
        dist_to_pivot: Distance to pivot point (positive = below pivot)
        ret_6m: 6-month return percentage
        rs_6m: Relative strength vs SPY (6-month)

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

    return entry_score


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