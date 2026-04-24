"""Unified pivot detection module.

Detects breakout pivots via multiple techniques:
- range_20d: highest high of last 20 bars
- vcp: volatility contraction pattern pivot high
- pocket_pivot: up-day with volume spike above prior down-days
- manual: user-specified pivot from watchlist

Returns standardized PivotSignal dataclass for all techniques.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from traderlib.vcp_utils import detect_vcp_pattern, VCPPattern


@dataclass
class PivotSignal:
    """Standardized pivot detection result."""
    ticker: str
    pivot_price: float
    pivot_type: str
    confidence: float = 0.0
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    entry_mode: str = 'breakout'
    context: Dict = field(default_factory=dict)


def detect_range_20d_pivot(hist: pd.DataFrame, ticker: str = '') -> Optional[PivotSignal]:
    """Detect 20-day range high pivot.

    Pivot = highest high of last 20 bars.
    Stop = lowest low of the 20-bar range.
    Confidence based on position within the range (0.0-1.0).
    """
    if len(hist) < 20:
        return None

    recent = hist.tail(20)
    pivot_high = float(recent['High'].max())
    range_low = float(recent['Low'].min())
    current = float(hist['Close'].iloc[-1])

    # Guard against NaN data
    if pd.isna(pivot_high) or pd.isna(range_low) or pd.isna(current):
        return None

    # Confidence: how close to the pivot is current price?
    # 0.0 = at range low, 1.0 = at or above pivot
    if range_low >= pivot_high:
        # Degenerate range (zero width or inverted) — unusable signal
        return None
    confidence = max(0.0, min(1.0, (current - range_low) / (pivot_high - range_low)))

    # Risk-based target: 2R from pivot
    risk = pivot_high - range_low
    target = pivot_high + (2 * risk) if risk > 0 else pivot_high * 1.05

    return PivotSignal(
        ticker=ticker,
        pivot_price=round(pivot_high, 2),
        pivot_type='range_20d',
        confidence=round(confidence, 2),
        stop_price=round(range_low, 2),
        target_price=round(target, 2),
        entry_mode='immediate',
        context={
            'range_low': round(range_low, 2),
            'range_high': round(pivot_high, 2),
            'days': 20,
        }
    )


def detect_vcp_pivot(hist: pd.DataFrame, ticker: str = '') -> Optional[PivotSignal]:
    """Detect VCP pivot via existing detect_vcp_pattern().

    Requires valid VCP pattern with declining volume.
    """
    pattern = detect_vcp_pattern(hist)
    if not pattern.valid:
        return None
    if not pattern.volume_declining:
        return None

    # Validate pattern values to prevent catastrophic stops
    if not (pattern.stop_low > 0 and pattern.pivot_high > pattern.stop_low):
        return None

    # Confidence based on contraction quality
    # More contractions + tighter final contraction = higher confidence
    num_contractions = len(pattern.contractions)
    if num_contractions >= 3:
        base_confidence = 0.85
    elif num_contractions == 2:
        base_confidence = 0.70
    else:
        base_confidence = 0.55

    # Boost confidence if total depth is reasonable (15-30% ideal)
    if 15 <= pattern.total_depth <= 30:
        base_confidence += 0.10

    confidence = min(1.0, base_confidence)

    # Target based on risk from pivot to stop
    risk = pattern.pivot_high - pattern.stop_low
    target = pattern.pivot_high + (2 * risk) if risk > 0 else pattern.pivot_high * 1.05

    return PivotSignal(
        ticker=ticker,
        pivot_price=round(pattern.pivot_high, 2),
        pivot_type='vcp',
        confidence=round(confidence, 2),
        stop_price=round(pattern.stop_low, 2),
        target_price=round(target, 2),
        entry_mode='breakout',
        context={
            'num_contractions': num_contractions,
            'total_depth_pct': round(pattern.total_depth, 2),
            'volume_declining': pattern.volume_declining,
            'pivot_date': str(pattern.pivot_date) if pattern.pivot_date else None,
            'stop_date': str(pattern.stop_date) if pattern.stop_date else None,
        }
    )


def detect_pocket_pivot(hist: pd.DataFrame, ticker: str = '') -> Optional[PivotSignal]:
    """Detect pocket pivot: up-day with volume > max down-volume in prior 10 days.

    Pocket pivot is an intraday signal. For EOD scans, we look for the most
    recent day that qualifies and use that day's close as the pivot reference.
    """
    if len(hist) < 15 or 'Volume' not in hist.columns:
        return None

    # Need at least 10 prior days to compare volume
    closes = hist['Close'].values
    volumes = hist['Volume'].values
    highs = hist['High'].values
    lows = hist['Low'].values

    # Scan backwards from the most recent day
    for i in range(len(hist) - 1, 10, -1):
        # Must be an up-day (close > prior close)
        if closes[i] <= closes[i - 1]:
            continue

        # Look back 10 days for max down-day volume
        max_down_volume = 0.0
        for j in range(max(1, i - 10), i):
            if closes[j] < closes[j - 1]:  # down-day
                max_down_volume = max(max_down_volume, float(volumes[j]))

        if max_down_volume == 0:
            continue

        # Today's volume must exceed max down-volume
        if float(volumes[i]) > max_down_volume:
            # This is a pocket pivot day
            pivot_price = float(closes[i])

            # Stop: lowest low of the 10 days prior to the pocket pivot
            prior_lows = lows[i - 10:i]
            if np.isnan(prior_lows).any():
                continue
            stop_price = float(np.min(prior_lows))

            # Confidence: stronger volume = higher confidence
            volume_ratio = float(volumes[i]) / max_down_volume if max_down_volume > 0 else 1.0
            confidence = min(1.0, 0.60 + (volume_ratio - 1.0) * 0.20)

            # Target: 2R from pivot
            risk = pivot_price - stop_price
            target = pivot_price + (2 * risk) if risk > 0 else pivot_price * 1.05

            return PivotSignal(
                ticker=ticker,
                pivot_price=round(pivot_price, 2),
                pivot_type='pocket_pivot',
                confidence=round(confidence, 2),
                stop_price=round(stop_price, 2),
                target_price=round(target, 2),
                entry_mode='immediate',
                context={
                    'pocket_pivot_date': str(hist.index[i]),
                    'volume_ratio': round(volume_ratio, 2),
                    'prior_days': 10,
                }
            )

    return None


def detect_pivot(
    ticker: str,
    hist: pd.DataFrame,
    technique: str = 'auto',
) -> Optional[PivotSignal]:
    """Detect pivot for a given technique.

    Args:
        ticker: Stock symbol (populated into result)
        hist: DataFrame with OHLCV data
        technique: 'auto', 'range_20d', 'vcp', 'pocket_pivot'

    Returns:
        PivotSignal or None if no valid pivot found.
    """
    detectors = {
        'vcp': detect_vcp_pivot,
        'pocket_pivot': detect_pocket_pivot,
        'range_20d': detect_range_20d_pivot,
    }

    if technique == 'auto':
        # Try techniques in order of preference:
        # 1. VCP (highest quality setup)
        # 2. Pocket pivot (momentum confirmation)
        # 3. Range 20d (fallback)
        order = ['vcp', 'pocket_pivot', 'range_20d']
        signals = []
        for name in order:
            signal = detectors[name](hist, ticker=ticker)
            if signal is not None:
                signals.append(signal)

        if not signals:
            return None

        # Return highest confidence signal
        return max(signals, key=lambda s: s.confidence)

    if technique in detectors:
        return detectors[technique](hist, ticker=ticker)

    return None
