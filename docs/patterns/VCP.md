# VCP Pattern Detection

**Module:** `traderlib/vcp_utils.py`

Volatility Contraction Pattern (VCP) detection based on Minervini/O'Neil methodology. Identifies stocks with proper contraction progression and volume drying up.

---

## Overview

VCP is a technical pattern where price volatility contracts progressively through multiple swings, indicating supply is being absorbed. The pattern signals a potential breakout is near.

**Key Characteristics:**
- Multiple price contractions (swings)
- Each contraction shallower than the prior (progression)
- Volume dries up during contractions
- Price consolidates near recent high (pivot)

---

## Core Data Structures

### SwingPoint

```python
@dataclass
class SwingPoint:
    """A swing high or low point."""
    type: str       # 'high' or 'low'
    price: float    # Price at swing point
    date: pd.Timestamp
    idx: int        # Index in dataframe
```

### Contraction

```python
@dataclass
class Contraction:
    """A single contraction within a VCP pattern."""
    start_idx: int
    end_idx: int
    high: float     # Swing high starting contraction
    low: float      # Swing low ending contraction
    depth_pct: float  # (high - low) / high * 100
    volume_avg: float
    volume_ratio: float  # vs 50-day average
```

### VCPPattern

```python
@dataclass
class VCPPattern:
    """Complete VCP pattern detection result."""
    valid: bool
    contractions: List[Contraction]
    pivot_high: float   # Entry trigger price
    stop_low: float     # Failure point
    total_depth: float  # Total contraction from first high to final low
    progression_valid: bool  # Each contraction < 70% of prior
    volume_declining: bool
```

---

## Detection Algorithm

### Step 1: Swing Detection

Find local highs and lows using a 5% reversal threshold:

```python
def detect_swing_points(df: pd.DataFrame, reversal_pct: float = 0.05) -> List[SwingPoint]:
    """
    Identify swing highs and lows.
    
    Swing High: Price higher than N bars before and after
    Swing Low: Price lower than N bars before and after
    """
    swing_points = []
    
    # Look for local highs
    for i in range(window, len(df) - window):
        if df['High'].iloc[i] == max(df['High'].iloc[i-window:i+window+1]):
            swing_points.append(SwingPoint(type='high', ...))
    
    # Look for local lows
    for i in range(window, len(df) - window):
        if df['Low'].iloc[i] == min(df['Low'].iloc[i-window:i+window+1]):
            swing_points.append(SwingPoint(type='low', ...))
    
    return swing_points
```

### Step 2: Contraction Identification

Measure depth from each swing high to subsequent swing low:

```python
def identify_contractions(swing_points: List[SwingPoint], df: pd.DataFrame) -> List[Contraction]:
    """
    Pair swing highs with subsequent lows to measure contractions.
    """
    contractions = []
    
    for i in range(0, len(swing_points) - 1, 2):
        if swing_points[i].type == 'high' and swing_points[i+1].type == 'low':
            high = swing_points[i].price
            low = swing_points[i+1].price
            depth_pct = (high - low) / high * 100
            
            # Calculate volume metrics
            contraction_bars = df.iloc[swing_points[i].idx:swing_points[i+1].idx]
            volume_avg = contraction_bars['Volume'].mean()
            volume_50d_avg = df['Volume'].iloc[:swing_points[i].idx].rolling(50).mean().iloc[-1]
            volume_ratio = volume_avg / volume_50d_avg if volume_50d_avg else 1.0
            
            contractions.append(Contraction(
                start_idx=swing_points[i].idx,
                end_idx=swing_points[i+1].idx,
                high=high,
                low=low,
                depth_pct=depth_pct,
                volume_avg=volume_avg,
                volume_ratio=volume_ratio
            ))
    
    return contractions
```

### Step 3: Progression Validation

Each contraction must be < 70% depth of prior:

```python
def validate_progression(contractions: List[Contraction]) -> bool:
    """
    Check that each contraction is shallower than the prior.
    
    Valid: 25% → 12% → 5% (each < 70% of prior)
    Invalid: 25% → 20% → 15% (not contracting properly)
    """
    if len(contractions) < 2:
        return False
    
    for i in range(1, len(contractions)):
        prior_depth = contractions[i-1].depth_pct
        current_depth = contractions[i].depth_pct
        
        # Current must be < 70% of prior
        if current_depth >= 0.70 * prior_depth:
            return False
    
    return True
```

### Step 4: Volume Analysis

Check for declining volume through contractions:

```python
def check_volume_decline(contractions: List[Contraction]) -> bool:
    """
    Volume should dry up through the pattern.
    
    Later contractions should have lower volume ratios than earlier ones.
    """
    if len(contractions) < 2:
        return False
    
    # Compare first half vs second half volume
    first_half_avg = sum(c.volume_ratio for c in contractions[:len(contractions)//2]) / (len(contractions)//2)
    second_half_avg = sum(c.volume_ratio for c in contractions[len(contractions)//2:]) / (len(contractions) - len(contractions)//2)
    
    return second_half_avg < first_half_avg * 0.80  # 20% decline
```

### Step 5: Pivot/Stop Definition

Identify pivot high (entry trigger) and stop low (failure point):

```python
def define_pivot_and_stop(contractions: List[Contraction], current_price: float) -> Tuple[float, float]:
    """
    Pivot: Highest point of first contraction (breakout trigger)
    Stop: Lowest point of final contraction (pattern failure)
    """
    pivot_high = contractions[0].high * 1.01  # 1% above for trigger
    stop_low = contractions[-1].low * 0.97    # 3% below for failure
    
    return pivot_high, stop_low
```

---

## Valid Pattern Criteria

| Criterion | Requirement | Rationale |
|-----------|-------------|-----------|
| **Minimum Contractions** | 2+ | Single swing is not a pattern |
| **Progression** | Each < 70% of prior | Proper volatility contraction |
| **Volume Decline** | Second half < 80% of first | Supply drying up |
| **Price Near Pivot** | Within 1-5% | Ready to breakout |

---

## Usage

### Basic Usage

```python
from traderlib.vcp_utils import detect_vcp_pattern, format_vcp_summary

# Detect VCP pattern
pattern = detect_vcp_pattern(df, min_contractions=2)

if pattern.valid:
    print(format_vcp_summary(pattern))
    print(f"Pivot: ${pattern.pivot_high:.2f}")
    print(f"Stop: ${pattern.stop_low:.2f}")
    print(f"Total contraction: {pattern.total_depth:.1f}%")
```

### With Trend Screener

```bash
# Detect VCP on specific tickers
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp

# Show VCP in output
python3 scripts/trend_screener.py --profile large-cap --detect-vcp --top 30
```

### VCP Output Format

```
NVDA: VCP Detected — VALID
  Contractions: 3
  Depths: 22% → 11% → 5% (progression valid ✓)
  Volume: Drying up ✓
  Pivot: $126.50
  Stop: $118.20
  Total contraction: 28%
```

---

## VCP Strategy Integration

The VCP pattern detection is used by `VCPBreakoutStrategy`:

```python
from traderlib.strategies.vcp_breakout import VCPBreakoutBase

class VCPBreakoutLargeCap(VCPBreakoutBase):
    """VCP breakout strategy for large-cap stocks."""
    
    def evaluate_entries(self, context):
        # Detect VCP pattern
        pattern = detect_vcp_pattern(hist, min_contractions=2)
        
        if not pattern.valid:
            return None
        
        # Check proximity to pivot
        distance_pct = abs(current_price - pattern.pivot_high) / pattern.pivot_high * 100
        if distance_pct > self.params['max_pivot_proximity_pct']:
            return None
        
        # Check volume on breakout day
        if volume_ratio < self.params['breakout_volume_min']:
            return None
        
        # Generate entry signal
        return EntrySignal(
            ticker=ticker,
            entry_price=pattern.pivot_high,
            stop_price=pattern.stop_low,
            metadata={'vcp_pattern': pattern, ...}
        )
```

---

## Configuration

VCP parameters in `config/risk_config.yaml`:

```yaml
vcp:
  large_cap:
    min_dollar_volume: 80000000    # $80M+ daily
    min_share_volume: 1000000      # 1M+ shares
    contraction_ranges:            # Typical contraction depths
      - [15, 25]                   # First: 15-25%
      - [8, 12]                    # Second: 8-12%
      - [3, 8]                     # Third: 3-8%
    volume_dry_up_threshold: 0.60  # Volume < 60% of average
    breakout_volume_min: 1.4       # 1.4x average on breakout
    max_pivot_proximity_pct: 5.0   # Within 5% of pivot
    
  high_octane:
    min_dollar_volume: 20000000    # $20M+ daily
    min_share_volume: 400000       # 400K+ shares
    contraction_ranges:
      - [30, 35]                   # Deeper first contraction
      - [15, 15]
      - [3, 6]
    volume_dry_up_threshold: 0.50
    breakout_volume_min: 2.0       # Higher volume requirement
    max_pivot_proximity_pct: 5.0
```

---

## Phase Progression

VCP patterns progress through phases:

| Phase | Description | Action |
|-------|-------------|--------|
| **Phase 1** | Initial contraction (largest) | Watch |
| **Phase 2** | Second contraction (< 70% of first) | Prepare |
| **Phase 3** | Third contraction (< 70% of second) | Ready |
| **Breakout** | Price above pivot on volume | Enter |
| **Follow-through** | Continued upside momentum | Hold/Trail |

---

## Edge Cases

### Not Enough History

```python
if len(df) < 200:
    return VCPPattern(
        valid=False,
        contractions=[],
        pivot_high=0,
        stop_low=0,
        total_depth=0,
        progression_valid=False,
        volume_declining=False
    )
```

### Only One Contraction

```python
if len(contractions) < 2:
    # Not a valid VCP - need at least 2 contractions
    return VCPPattern(valid=False, ...)
```

### Progression Fails

```python
# Example: 25% → 22% → 18% (not contracting properly)
# Each contraction should be < 70% of prior
# 22/25 = 88% (fails), 18/22 = 82% (fails)
progression_valid = False
```

---

## Examples

### Valid VCP

```
AAPL: VCP Detected — VALID
  Contractions: 3
  Depths: 24% → 10% → 4%
  Progression: 10/24=42% ✓, 4/10=40% ✓
  Volume: 1.2x → 0.8x → 0.5x (drying up ✓)
  Pivot: $185.50
  Stop: $175.20
```

### Invalid VCP (Poor Progression)

```
TSLA: VCP Detected — INVALID
  Contractions: 3
  Depths: 20% → 18% → 15%
  Progression: 18/20=90% ✗ (should be < 70%)
  Reason: Contractions not tightening properly
```

### Invalid VCP (Volume Not Declining)

```
NVDA: VCP Detected — INVALID
  Contractions: 2
  Depths: 18% → 8%
  Progression: 8/18=44% ✓
  Volume: 0.9x → 1.1x ✗ (increasing, not drying up)
  Reason: Volume not confirming pattern
```

---

## Related Documentation

- [../trend_screener/USER_GUIDE.md](../trend_screener/USER_GUIDE.md) — Trend Screener with VCP detection
- [../strategies/VCP_BREAKOUT.md](../strategies/VCP_BREAKOUT.md) — VCP breakout strategy
- [traderlib/vcp_utils.py](../../traderlib/vcp_utils.py) — Source code
- [../METHODOLOGY.md](../METHODOLOGY.md) — Stage 2 methodology
