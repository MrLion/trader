"""VCP (Volatility Contraction Pattern) detection utilities.

Implements swing high/low detection and VCP pattern validation
based on Minervini/O'Neil methodology.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

import pandas as pd
import numpy as np


@dataclass
class SwingPoint:
    """A swing high or low point."""
    type: str  # 'high' or 'low'
    price: float
    date: pd.Timestamp
    idx: int  # Index in original dataframe


@dataclass
class Contraction:
    """A single contraction within a VCP pattern."""
    start_idx: int
    end_idx: int
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    high: float
    low: float
    depth_pct: float  # (high - low) / high * 100
    volume_avg: float
    volume_ratio: float  # vs 50-day average


@dataclass
class VCPPattern:
    """Complete VCP pattern detection result."""
    valid: bool
    contractions: List[Contraction] = field(default_factory=list)
    pivot_high: float = 0.0
    pivot_date: Optional[pd.Timestamp] = None
    stop_low: float = 0.0
    stop_date: Optional[pd.Timestamp] = None
    total_depth: float = 0.0  # From first high to last low
    progression_valid: bool = False  # Each contraction < 70% of prior
    volume_declining: bool = False
    error_message: str = ""


def detect_swing_points(
    hist: pd.DataFrame,
    reversal_threshold: float = 0.05,
    min_bars: int = 5
) -> List[SwingPoint]:
    """
    Detect swing highs and lows using price reversal threshold.

    Algorithm:
    1. Track local maxima/minima in rolling windows
    2. Confirm swing when price reverses > threshold from extreme
    3. Require minimum bars between swings to avoid noise

    Args:
        hist: DataFrame with 'High', 'Low', 'Close' columns
        reversal_threshold: Minimum % reversal to confirm swing (default 5%)
        min_bars: Minimum bars between swing points (default 5)

    Returns:
        List of SwingPoint objects alternating high/low
    """
    if len(hist) < min_bars * 3:
        return []

    highs = hist['High'].values
    lows = hist['Low'].values
    closes = hist['Close'].values
    dates = hist.index

    swings = []
    last_swing_idx = -min_bars
    last_swing_type = None
    last_extreme_price = 0.0

    i = min_bars
    while i < len(hist) - min_bars:
        # Look for local extreme in window
        window_start = max(0, i - min_bars)
        window_end = min(len(hist), i + min_bars + 1)

        local_high_idx = window_start + np.argmax(highs[window_start:window_end])
        local_low_idx = window_start + np.argmin(lows[window_start:window_end])

        # Check for swing high
        if local_high_idx == i and (last_swing_type != 'high' or i - last_swing_idx >= min_bars):
            if last_swing_type == 'low':
                # Confirm prior low with reversal
                reversal_pct = (highs[i] - last_extreme_price) / abs(last_extreme_price)
                if reversal_pct >= reversal_threshold:
                    swings.append(SwingPoint(
                        type='high',
                        price=float(highs[i]),
                        date=dates[i],
                        idx=i
                    ))
                    last_swing_idx = i
                    last_swing_type = 'high'
                    last_extreme_price = highs[i]
            else:
                # First swing or after gap
                swings.append(SwingPoint(
                    type='high',
                    price=float(highs[i]),
                    date=dates[i],
                    idx=i
                ))
                last_swing_idx = i
                last_swing_type = 'high'
                last_extreme_price = highs[i]

        # Check for swing low
        elif local_low_idx == i and (last_swing_type != 'low' or i - last_swing_idx >= min_bars):
            if last_swing_type == 'high':
                # Confirm prior high with reversal
                reversal_pct = (last_extreme_price - lows[i]) / last_extreme_price
                if reversal_pct >= reversal_threshold:
                    swings.append(SwingPoint(
                        type='low',
                        price=float(lows[i]),
                        date=dates[i],
                        idx=i
                    ))
                    last_swing_idx = i
                    last_swing_type = 'low'
                    last_extreme_price = lows[i]
            else:
                swings.append(SwingPoint(
                    type='low',
                    price=float(lows[i]),
                    date=dates[i],
                    idx=i
                ))
                last_swing_idx = i
                last_swing_type = 'low'
                last_extreme_price = lows[i]

        i += 1

    return swings


def measure_contraction(
    hist: pd.DataFrame,
    swing_high: SwingPoint,
    swing_low: SwingPoint,
    avg_volume_50d: float
) -> Contraction:
    """Measure a single contraction between swing points."""
    slice_hist = hist.iloc[swing_high.idx:swing_low.idx+1]

    volume_avg = slice_hist['Volume'].mean() if 'Volume' in slice_hist.columns else 0
    volume_ratio = volume_avg / avg_volume_50d if avg_volume_50d > 0 else 1.0

    high = swing_high.price
    low = swing_low.price
    depth_pct = ((high - low) / high) * 100 if high > 0 else 0

    return Contraction(
        start_idx=swing_high.idx,
        end_idx=swing_low.idx,
        start_date=swing_high.date,
        end_date=swing_low.date,
        high=high,
        low=low,
        depth_pct=depth_pct,
        volume_avg=volume_avg,
        volume_ratio=volume_ratio
    )


def validate_vcp_progression(
    contractions: List[Contraction],
    max_size_ratio: float = 0.70,
    min_size_ratio: float = 0.50
) -> Tuple[bool, str]:
    """
    Validate VCP contraction progression.

    Each contraction should be 50-70% of the prior contraction.
    A 25% → 15% → 8% sequence is valid (60%, 53%).
    A 25% → 20% → 15% sequence is NOT valid (80%, 75% - too wide).

    Args:
        contractions: List of contractions in order
        max_size_ratio: Maximum allowed % of previous (default 70%)
        min_size_ratio: Minimum allowed % of previous (default 50%)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(contractions) < 2:
        return False, "Need at least 2 contractions"

    for i in range(1, len(contractions)):
        current_depth = contractions[i].depth_pct
        prior_depth = contractions[i-1].depth_pct

        if prior_depth <= 0:
            return False, f"Invalid prior depth at contraction {i}"

        size_ratio = current_depth / prior_depth

        if size_ratio > max_size_ratio:
            return False, (
                f"Contraction {i+1} ({current_depth:.1f}%) is {size_ratio:.0%} of "
                f"contraction {i} ({prior_depth:.1f}%) - exceeds {max_size_ratio:.0%} limit"
            )

        if size_ratio < min_size_ratio:
            # Not invalid, just note it's tighter than typical
            pass

    return True, ""


def detect_vcp_pattern(
    hist: pd.DataFrame,
    min_contractions: int = 2,
    max_contractions: int = 5,
    reversal_threshold: float = 0.05,
    max_total_depth: float = 35.0,
    min_final_contraction_depth: float = 3.0,
    max_final_contraction_depth: float = 10.0,
    require_volume_dry_up: bool = True,
    volume_dry_up_threshold: float = 0.60
) -> VCPPattern:
    """
    Detect VCP pattern with progressively tighter contractions.

    Args:
        hist: DataFrame with OHLCV data
        min_contractions: Minimum contractions required (default 2)
        max_contractions: Maximum contractions to consider (default 5)
        reversal_threshold: % reversal to confirm swing (default 5%)
        max_total_depth: Max % from first high to last low (default 35%)
        min_final_contraction_depth: Min % for final contraction (default 3%)
        max_final_contraction_depth: Max % for final contraction (default 10%)
        require_volume_dry_up: Check volume declining (default True)
        volume_dry_up_threshold: Final volume % of 50-day avg (default 60%)

    Returns:
        VCPPattern with validation results
    """
    if len(hist) < 50:
        return VCPPattern(valid=False, error_message="Insufficient data (<50 bars)")

    # Calculate 50-day average volume
    avg_volume_50d = hist['Volume'].tail(50).mean() if 'Volume' in hist.columns else 0

    # Detect swing points
    swings = detect_swing_points(hist, reversal_threshold=reversal_threshold)

    if len(swings) < min_contractions * 2:
        return VCPPattern(
            valid=False,
            error_message=f"Found {len(swings)} swing points, need {min_contractions * 2}"
        )

    # Build contractions from swing pairs (high-low sequences)
    contractions = []
    last_high = None

    for swing in swings:
        if swing.type == 'high':
            last_high = swing
        elif swing.type == 'low' and last_high is not None:
            # Only add if this low is after the high
            if swing.idx > last_high.idx:
                contraction = measure_contraction(hist, last_high, swing, avg_volume_50d)
                contractions.append(contraction)
                last_high = None  # Reset to find next high

    if len(contractions) < min_contractions:
        return VCPPattern(
            valid=False,
            error_message=f"Found {len(contractions)} contractions, need {min_contractions}"
        )

    # Limit to max_contractions (most recent)
    contractions = contractions[-max_contractions:]

    # Validate progression (each contraction 50-70% of prior)
    progression_valid, error_msg = validate_vcp_progression(contractions)
    if not progression_valid:
        return VCPPattern(valid=False, error_message=error_msg)

    # Check final contraction depth
    final_contraction = contractions[-1]
    if not (min_final_contraction_depth <= final_contraction.depth_pct <= max_final_contraction_depth):
        return VCPPattern(
            valid=False,
            error_message=(
                f"Final contraction depth {final_contraction.depth_pct:.1f}% "
                f"outside range [{min_final_contraction_depth}, {max_final_contraction_depth}]"
            )
        )

    # Check total depth
    total_depth = ((contractions[0].high - contractions[-1].low) / contractions[0].high) * 100
    if total_depth > max_total_depth:
        return VCPPattern(
            valid=False,
            error_message=f"Total depth {total_depth:.1f}% exceeds max {max_total_depth}%"
        )

    # Check volume dry-up
    volume_declining = True
    if require_volume_dry_up:
        # Each contraction should have lower volume
        for i in range(1, len(contractions)):
            if contractions[i].volume_ratio >= contractions[i-1].volume_ratio * 1.1:  # Allow 10% tolerance
                volume_declining = False
                break

        # Final contraction should be below threshold
        if final_contraction.volume_ratio > volume_dry_up_threshold:
            volume_declining = False

    # Pivot is high of final (tightest) contraction
    pivot_high = final_contraction.high
    pivot_date = final_contraction.start_date

    # Stop is low of final contraction
    stop_low = final_contraction.low
    stop_date = final_contraction.end_date

    return VCPPattern(
        valid=True,
        contractions=contractions,
        pivot_high=pivot_high,
        pivot_date=pivot_date,
        stop_low=stop_low,
        stop_date=stop_date,
        total_depth=total_depth,
        progression_valid=True,
        volume_declining=volume_declining
    )


def format_vcp_summary(pattern: VCPPattern) -> Dict:
    """Format VCP pattern for display/export."""
    if not pattern.valid:
        return {
            'valid': False,
            'error': pattern.error_message
        }

    summary = {
        'valid': True,
        'num_contractions': len(pattern.contractions),
        'pivot_high': round(pattern.pivot_high, 2),
        'stop_low': round(pattern.stop_low, 2),
        'risk_pct': round(((pattern.pivot_high - pattern.stop_low) / pattern.pivot_high) * 100, 2),
        'total_depth_pct': round(pattern.total_depth, 2),
        'volume_declining': pattern.volume_declining,
        'contractions': []
    }

    for i, c in enumerate(pattern.contractions, 1):
        summary['contractions'].append({
            'number': i,
            'depth_pct': round(c.depth_pct, 2),
            'high': round(c.high, 2),
            'low': round(c.low, 2),
            'volume_ratio': round(c.volume_ratio, 2),
            'start_date': c.start_date.strftime('%Y-%m-%d') if hasattr(c.start_date, 'strftime') else str(c.start_date),
            'end_date': c.end_date.strftime('%Y-%m-%d') if hasattr(c.end_date, 'strftime') else str(c.end_date)
        })

    return summary
