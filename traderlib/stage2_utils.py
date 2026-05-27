#!/usr/bin/env python3
"""Shared Stage 2 criteria calculation utilities.

Canonical 10-point system based on Mark Minervini's trend template
plus short-term trend confirmation and 150-day MA:
1.  Price > 20 MA  (short-term trend)
2.  Price > 50 MA  (medium-term trend)
3.  Price > 100 MA (intermediate trend)
4.  Price > 150 MA (long intermediate trend)
5.  Price > 200 MA (long-term trend)
6.  MA Stacking: 50 > 100 > 200 (proper order)
7.  MA Stacking extended: 50 > 100 > 150 > 200
8.  200 MA rising for 20+ days (sustained uptrend)
9.  Price within 25% of 52-week high
10. Price >= 1.25x 52-week low (strong recovery)
"""

from typing import Optional

import pandas as pd


def calculate_stage2_score(hist: pd.DataFrame) -> int:
    """
    Calculate Stage 2 score using canonical 10-point system.

    Args:
        hist: DataFrame with price history containing 'Close', 'High', 'Low' columns
              Must have at least 200 days for full calculation

    Returns:
        int: Score from 0-10
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
    ma150 = hist['Close'].rolling(150).mean().iloc[-1] if len(hist) >= 150 else None
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

    # 4. Price > 150 MA
    if ma150 is not None and current > ma150:
        score += 1

    # 5. Price > 200 MA
    if current > ma200:
        score += 1

    # 6. MA stacking: 50 > 100 > 200 (20 MA excluded, too volatile)
    if ma50 > ma100 > ma200:
        score += 1

    # 7. Extended MA stacking: 50 > 100 > 150 > 200
    if ma150 is not None and ma50 > ma100 > ma150 > ma200:
        score += 1

    # 8. 200 MA rising for 20+ days (compare to value 20 days ago)
    if len(hist) >= 221:
        ma200_20days_ago = hist['Close'].rolling(200).mean().iloc[-21]
        if ma200 > ma200_20days_ago:
            score += 1
    else:
        # Fallback: just check if MA200 is rising vs 1 day ago
        ma200_1day_ago = hist['Close'].rolling(200).mean().iloc[-2]
        if ma200 > ma200_1day_ago:
            score += 1

    # 9. Price within 25% of 52-week high
    from_high = ((high_52w - current) / high_52w) * 100
    if from_high < 25:
        score += 1

    # 10. Price >= 1.25x 52-week low (strong recovery from lows)
    if current >= low_52w * 1.25:
        score += 1

    return score


def get_stage2_details(hist: pd.DataFrame) -> dict:
    """
    Get detailed breakdown of Stage 2 criteria for reporting.

    Includes all MAs: 10, 20, 50, 100, 150, 200. Score = sum of 10 boolean criteria.

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
    ma150 = hist['Close'].rolling(150).mean().iloc[-1] if len(hist) >= 150 else None
    ma200 = hist['Close'].rolling(200).mean().iloc[-1]

    from_high = ((high_52w - current) / high_52w) * 100

    criteria = {
        'price_above_20ma': current > ma20,
        'price_above_50ma': current > ma50,
        'price_above_100ma': current > ma100,
        'price_above_150ma': ma150 is not None and current > ma150,
        'price_above_200ma': current > ma200,
        'ma_stacking': ma50 > ma100 > ma200,
        'ma_stacking_extended': ma50 > ma100 > ma150 > ma200 if ma150 is not None else ma50 > ma100 > ma200,
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

    result = {
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

    if ma150 is not None:
        result['ma150'] = ma150

    return result


def is_stage2_compliant(score: int, min_score: int = 5) -> bool:
    """
    Check if a stock meets minimum Stage 2 compliance.

    Args:
        score: Stage 2 score (0-10)
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
    Calculate entry attractiveness score (0-100) using updated thresholds for 10-point system.

    Max breakdown: Stage2=25 + Risk=25 + Proximity=25 + Momentum=15 + RS=10 = 100.

    Args:
        stage2_score: Stage 2 score (0-10)
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

    # Stage 2 score component (25 pts max) — scaled for 10-point system
    if stage2_score >= 9:    # Excellent  (90%+)
        entry_score += 25
    elif stage2_score >= 8:  # Very good  (80%+)
        entry_score += 20
    elif stage2_score >= 7:  # Good       (70%+)
        entry_score += 15
    elif stage2_score >= 6:  # Fair       (60%+)
        entry_score += 10
    elif stage2_score >= 5:  # Weak       (50%+)
        entry_score += 5

    # Risk % component (25 pts max)
    if risk_pct < 10:
        entry_score += 25
    elif risk_pct < 15:
        entry_score += 15
    elif risk_pct < 20:
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


def get_convergence_grade(convergence_score: int) -> str:
    """
    Get convergence grade classification — separate from entry_score tiers.

    Convergence measures MA cluster quality (technical structure),
    while entry_score measures timing readiness.

    Args:
        convergence_score: MA convergence quality score (0-100)

    Returns:
        str: Grade classification (A/B/C)
    """
    if convergence_score >= 70:
        return "Grade A"  # Excellent MA support — tight cluster, great risk structure
    elif convergence_score >= 50:
        return "Grade B"  # Developing convergence — monitor for improvement
    else:
        return "Grade C"  # Weak/poor convergence — low priority


# ============ MA Convergence Scoring (Trend Screener) ============

def calculate_convergence_score(
    current_price: float,
    s2_details: dict,
    atr_stop: Optional[float] = None,
    cluster_spread_pct: float = 0.05,
    min_cluster_size: int = 2
) -> dict:
    """
    Calculate MA convergence quality score (0-100).

    Composite score based on:
    - Cluster Tightness (30%): How close MAs are to each other
    - Cluster Size (25%): Number of MAs in convergence cluster
    - Price Distance (15%): How close price is to cluster
    - Risk Improvement (30%): MA stop vs ATR stop risk reduction

    Args:
        current_price: Current stock price
        s2_details: Dictionary from get_stage2_details() with MA values
        atr_stop: Optional ATR-based stop for risk comparison
        cluster_spread_pct: Maximum spread for cluster (default 5%)
        min_cluster_size: Minimum MAs required (default 2)

    Returns:
        dict with score and component breakdown:
        {
            'score': int,  # 0-100 composite score
            'components': {
                'tightness': int,  # 0-30
                'cluster_size': int,  # 0-25
                'price_distance': int,  # 0-15
                'risk_improvement': int  # 0-30
            },
            'cluster_data': {
                'cluster_mas': list,  # MA names in cluster
                'cluster_size': int,
                'cluster_spread_pct': float,
                'lowest_ma': str
            },
            'ma_support_stop': float,  # Calculated stop price
            'atr_risk_pct': float,  # ATR stop risk %
            'ma_risk_pct': float  # MA stop risk %
        }
    """
    if not s2_details:
        return {
            'score': 0,
            'components': {'tightness': 0, 'cluster_size': 0, 'price_distance': 0, 'risk_improvement': 0},
            'cluster_data': {'cluster_mas': [], 'cluster_size': 0, 'cluster_spread_pct': 0, 'lowest_ma': None},
            'ma_support_stop': None,
            'atr_risk_pct': 0,
            'ma_risk_pct': 0
        }

    # Calculate MA support stop
    ma_result = calculate_ma_support_stop(
        current_price,
        s2_details,
        cluster_spread_pct=cluster_spread_pct,
        min_cluster_size=min_cluster_size
    )

    if ma_result is None:
        return {
            'score': 0,
            'components': {'tightness': 0, 'cluster_size': 0, 'price_distance': 0, 'risk_improvement': 0},
            'cluster_data': {'cluster_mas': [], 'cluster_size': 0, 'cluster_spread_pct': 0, 'lowest_ma': None},
            'ma_support_stop': None,
            'atr_risk_pct': 0,
            'ma_risk_pct': 0
        }

    cluster_mas = ma_result['cluster_mas']
    cluster_size = len(cluster_mas)
    spread_pct = ma_result['cluster_spread_pct']
    ma_stop = ma_result['ma_support_stop']

    # Component 1: Cluster Tightness (30%)
    # Score inversely proportional to spread, saturates at 4% spread (score=20)
    if spread_pct <= 4.0:
        tightness_score = 30
    elif spread_pct <= 5.0:
        tightness_score = int(30 * (5.0 - spread_pct) / 1.0)  # Linear drop from 4% to 5%
    else:
        tightness_score = 0

    # Component 2: Cluster Size (25%)
    # 2 MAs = 50%, 3 MAs = 75%, 4+ MAs = 100%
    cluster_size_score = min(25, cluster_size * 25 // 2)
    if cluster_size >= 4:
        cluster_size_score = 25

    # Component 3: Price Distance (15%)
    # Distance from current price to top of cluster
    top_cluster_ma = max([s2_details.get(ma, 0) for ma in cluster_mas])
    if top_cluster_ma > 0:
        distance_pct = (current_price - top_cluster_ma) / current_price * 100
        if distance_pct <= 3.0:
            distance_score = 15
        elif distance_pct <= 5.0:
            distance_score = 9  # 60% of max
        elif distance_pct <= 8.0:
            distance_score = 5  # 30% of max
        else:
            distance_score = 0
    else:
        distance_score = 0
        distance_pct = 100

    # Component 4: Risk Improvement (30%)
    # Compare MA stop risk % vs ATR stop risk %
    if atr_stop and atr_stop > 0:
        atr_risk_pct = (current_price - atr_stop) / current_price * 100
        ma_risk_pct = (current_price - ma_stop) / current_price * 100
        improvement = atr_risk_pct - ma_risk_pct

        # If MA stop is worse (larger risk), no improvement credit
        # Only count improvement if MA stop is actually tighter
        if improvement > 0 and atr_risk_pct > 0:
            improvement_pct = improvement / atr_risk_pct * 100
            # 30%+ improvement = full 30 points
            if improvement_pct >= 30:
                risk_score = 30
            else:
                risk_score = int(30 * improvement_pct / 30)
        else:
            # MA stop is worse - no credit, but don't penalize
            risk_score = 0
    else:
        atr_risk_pct = 0
        ma_risk_pct = (current_price - ma_stop) / current_price * 100
        risk_score = 15  # Neutral if no ATR comparison

    # Composite score
    composite_score = tightness_score + cluster_size_score + distance_score + risk_score

    return {
        'score': min(100, composite_score),
        'components': {
            'tightness': tightness_score,
            'cluster_size': cluster_size_score,
            'price_distance': distance_score,
            'risk_improvement': risk_score
        },
        'cluster_data': {
            'cluster_mas': cluster_mas,
            'cluster_size': cluster_size,
            'cluster_spread_pct': spread_pct,
            'lowest_ma': ma_result['lowest_ma']
        },
        'ma_support_stop': ma_stop,
        'atr_risk_pct': round(atr_risk_pct, 2) if atr_risk_pct > 0 else 0,
        'ma_risk_pct': round(ma_risk_pct, 2)
    }


# ============ Volume Analysis Utilities ============

def calculate_volume_metrics(hist: pd.DataFrame, lookback_days: int = 50) -> dict:
    """
    Calculate volume metrics for a stock.

    Args:
        hist: DataFrame with 'Volume' and 'Close' columns
        lookback_days: Days for average calculation (default 50)

    Returns:
        dict with volume metrics:
        {
            'current_volume': int,
            'avg_volume': float,
            'avg_dollar_volume': float,
            'volume_ratio': float,
            'volume_trend': str,  # 'increasing', 'decreasing', 'stable'
            'volume_percentile': int  # 0-100
        }
    """
    if len(hist) < lookback_days or 'Volume' not in hist.columns:
        return {
            'current_volume': 0,
            'avg_volume': 0,
            'avg_dollar_volume': 0,
            'volume_ratio': 0,
            'volume_trend': 'unknown',
            'volume_percentile': 0
        }

    current_volume = int(hist['Volume'].iloc[-1])
    avg_volume = hist['Volume'].tail(lookback_days).mean()

    # Dollar volume
    current_price = hist['Close'].iloc[-1]
    avg_dollar_volume = avg_volume * current_price

    # Volume ratio (current vs average)
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    # Volume trend (compare recent 10 days vs previous 10 days)
    if len(hist) >= lookback_days + 10:
        recent_avg = hist['Volume'].tail(10).mean()
        prev_avg = hist['Volume'].iloc[-20:-10].mean()
        if prev_avg > 0:
            if recent_avg > prev_avg * 1.2:
                volume_trend = 'increasing'
            elif recent_avg < prev_avg * 0.8:
                volume_trend = 'decreasing'
            else:
                volume_trend = 'stable'
        else:
            volume_trend = 'unknown'
    else:
        volume_trend = 'unknown'

    # Volume percentile (where current volume ranks vs lookback period)
    volumes = hist['Volume'].tail(lookback_days).values
    percentile = (volumes < current_volume).mean() * 100 if len(volumes) > 0 else 0

    return {
        'current_volume': current_volume,
        'avg_volume': round(avg_volume, 0),
        'avg_dollar_volume': round(avg_dollar_volume, 0),
        'volume_ratio': round(volume_ratio, 2),
        'volume_trend': volume_trend,
        'volume_percentile': int(percentile)
    }


def check_volume_dry_up(
    hist: pd.DataFrame,
    contraction_periods: list[tuple[int, int]],
    dry_up_threshold: float = 0.6
) -> dict:
    """
    Check if volume is drying up during contractions (VCP pattern).

    Args:
        hist: DataFrame with 'Volume' column
        contraction_periods: List of (start_idx, end_idx) tuples for contractions
        dry_up_threshold: Volume threshold as % of average (default 60%)

    Returns:
        dict with dry-up analysis:
        {
            'valid': bool,  # All contractions show dry-up
            'dry_up_pct': float,  # Average volume % of 50-day avg in final contraction
            'volume_declining': bool,  # Each contraction has lower volume
            'contraction_volumes': list  # Volume ratio for each contraction
        }
    """
    if len(hist) < 50 or 'Volume' not in hist.columns:
        return {
            'valid': False,
            'dry_up_pct': 0,
            'volume_declining': False,
            'contraction_volumes': []
        }

    avg_50d = hist['Volume'].tail(50).mean()
    if avg_50d == 0:
        return {
            'valid': False,
            'dry_up_pct': 0,
            'volume_declining': False,
            'contraction_volumes': []
        }

    contraction_volumes = []
    for start_idx, end_idx in contraction_periods:
        if end_idx > len(hist) or start_idx < 0:
            continue
        period_volume = hist['Volume'].iloc[start_idx:end_idx].mean()
        volume_ratio = period_volume / avg_50d
        contraction_volumes.append(volume_ratio)

    if not contraction_volumes:
        return {
            'valid': False,
            'dry_up_pct': 0,
            'volume_declining': False,
            'contraction_volumes': []
        }

    # Check if volume is declining across contractions
    volume_declining = all(
        contraction_volumes[i] > contraction_volumes[i+1]
        for i in range(len(contraction_volumes)-1)
    ) if len(contraction_volumes) >= 2 else True

    # Final contraction volume vs threshold
    final_volume_ratio = contraction_volumes[-1] if contraction_volumes else 1.0
    dry_up_pct = final_volume_ratio * 100
    valid = dry_up_pct <= dry_up_threshold * 100

    return {
        'valid': valid and volume_declining,
        'dry_up_pct': round(dry_up_pct, 1),
        'volume_declining': volume_declining,
        'contraction_volumes': [round(v, 2) for v in contraction_volumes]
    }
