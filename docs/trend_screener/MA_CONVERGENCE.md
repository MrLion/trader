# MA Convergence Scoring System

**Module:** `traderlib/stage2_utils.py`

MA convergence scoring quantifies the quality of moving average clustering below price. Used by Trend Screener to identify stocks with optimal support zones.

---

## Overview

When multiple moving averages converge (cluster tightly) below price, it creates a strong support zone. Stocks with tight MA clusters tend to:
- Have clearer risk definitions (tighter stops)
- Offer better reward/risk ratios
- Show more predictable support bounces

The convergence score (0-100) provides a single number to rank this quality.

---

## Scoring Components (100 points total)

| Component | Max Points | Description |
|-----------|------------|-------------|
| **Tightness** | 30 | Inverse of cluster spread — tighter cluster = more points |
| **Cluster Size** | 25 | Number of MAs in cluster — more MAs = more points |
| **Price Distance** | 15 | How close price is to cluster — closer = more points |
| **Risk Improvement** | 30 | Stop improvement vs ATR-only stop — bigger improvement = more points |

---

## Cluster Detection Algorithm

### Step 1: Collect MAs Below Price

```python
mas_below = []
for ma_name in ['ma10', 'ma20', 'ma50', 'ma100', 'ma200']:
    if ma_values[ma_name] < current_price:
        mas_below.append((ma_name, ma_values[ma_name]))
```

**Requirement:** Minimum 2 MAs to form a valid cluster.

### Step 2: Check Cluster Spread

```python
highest_ma = max(ma_values for _, ma_values in mas_below)
lowest_ma = min(ma_values for _, ma_values in mas_below)
cluster_spread_pct = (highest_ma - lowest_ma) / highest_ma * 100

# Valid cluster: spread ≤ 5%
is_valid_cluster = cluster_spread_pct <= 5.0
```

### Step 3: Calculate MA Support Stop

```python
# Stop placed below lowest MA in cluster
buffer_pct = 0.01  # 1% buffer
ma_support_stop = lowest_ma * (1 - buffer_pct)
```

---

## Component Calculations

### 1. Tightness Score (0-30 points)

```python
# Tighter cluster = higher score
# Spread of 0% = 30 pts, Spread of 5% = 0 pts
tightness_score = 30 * (1 - (cluster_spread_pct / 5.0))
tightness_score = max(0, min(30, tightness_score))  # Clamp to 0-30
```

**Examples:**
| Cluster Spread | Score |
|----------------|-------|
| 0.5% | 27 pts |
| 1.0% | 24 pts |
| 2.0% | 18 pts |
| 3.0% | 12 pts |
| 5.0%+ | 0 pts |

### 2. Cluster Size Score (0-25 points)

```python
# More MAs in cluster = higher score
# 5 MAs = 25 pts, 2 MAs = 10 pts
cluster_size = len(mas_below)
size_score = min(25, cluster_size * 5)  # 5 pts per MA, max 25
```

**Examples:**
| MAs in Cluster | Score |
|----------------|-------|
| 5 (all) | 25 pts |
| 4 | 20 pts |
| 3 | 15 pts |
| 2 | 10 pts |

### 3. Price Distance Score (0-15 points)

```python
# Closer price to cluster = higher score
# Price at cluster = 15 pts, Price 10% above = 0 pts
distance_pct = (current_price - highest_ma) / highest_ma * 100
distance_score = 15 * (1 - (distance_pct / 10.0))
distance_score = max(0, min(15, distance_score))  # Clamp to 0-15
```

**Examples:**
| Price Distance | Score |
|----------------|-------|
| At cluster (0%) | 15 pts |
| +2% above | 12 pts |
| +5% above | 7 pts |
| +10% above | 0 pts |

### 4. Risk Improvement Score (0-30 points)

```python
# Compare MA support stop vs ATR stop
# MA stop tighter (higher) = improvement

atr_risk_pct = (entry_price - atr_stop) / entry_price * 100
ma_risk_pct = (entry_price - ma_support_stop) / entry_price * 100

# Improvement: MA stop provides tighter risk
if ma_risk_pct < atr_risk_pct:
    improvement = (atr_risk_pct - ma_risk_pct) / atr_risk_pct
    risk_score = 30 * min(1.0, improvement)
else:
    risk_score = 0  # MA stop is wider, no improvement
```

**Examples:**
| ATR Stop | MA Stop | Improvement | Score |
|----------|---------|-------------|-------|
| -8% | -5% | 37.5% | 11 pts |
| -10% | -4% | 60% | 18 pts |
| -12% | -3% | 75% | 22 pts |
| -10% | -10% | 0% | 0 pts |

---

## Final Score & Grade

```python
total_score = tightness_score + size_score + distance_score + risk_score
# total_score ranges from 0 to 100
```

### Grade Thresholds

| Grade | Score Range | Meaning |
|-------|-------------|---------|
| **A** | 70-100 | Optimal convergence — prime candidate |
| **B** | 50-69 | Good convergence — watch list |
| **C** | 30-49 | Weak convergence — monitor |
| **D** | < 30 | No meaningful convergence |

---

## Return Structure

The `calculate_convergence_score()` function returns:

```python
{
    'score': 85,  # 0-100
    'grade': 'A',  # A/B/C/D
    'components': {
        'tightness': 27,      # 0-30
        'cluster_size': 20,   # 0-25
        'price_distance': 13, # 0-15
        'risk_improvement': 25 # 0-30
    },
    'cluster_data': {
        'cluster_mas': ['ma20', 'ma50', 'ma100'],
        'cluster_size': 3,
        'cluster_spread_pct': 2.1,
        'lowest_ma': 'ma100',
        'highest_ma': 'ma20'
    },
    'ma_support_stop': 118.50,  # Alternative stop based on MA cluster
    'atr_risk_pct': 8.5,        # Risk % using ATR stop
    'ma_risk_pct': 5.2          # Risk % using MA support stop
}
```

---

## Integration with MA Support Stop

The MA support stop feature uses convergence detection to provide an alternative stop calculation:

```python
# Dual risk parameter: use tighter of ATR or MA support stop
final_stop = max(atr_stop, ma_support_stop)
final_risk_pct = min(atr_risk_pct, ma_risk_pct)
```

**Benefits:**
- Tighter stops = better R-multiples on winners
- Objective support level (not arbitrary)
- Works best when convergence score is high (50+)

See [../METHODOLOGY.md](../METHODOLOGY.md#ma-support-stop) for stop methodology.

---

## Edge Cases

### No MAs Below Price
```python
if len(mas_below) < 2:
    return {
        'score': 0,
        'grade': 'D',
        'components': {...},
        'cluster_data': None,
        'ma_support_stop': None,
        ...
    }
```

### Cluster Spread Too Wide
```python
if cluster_spread_pct > 5.0:
    # Not a valid cluster - return low score
    return {'score': tightness_score * 0.5, ...}  # Penalty
```

### Insufficient History
```python
if len(hist) < 200:
    # Can't calculate ma200 - use available MAs
    # Score capped at 80 (max cluster size = 4)
```

---

## Usage Examples

### Basic Usage

```python
from traderlib.stage2_utils import calculate_convergence_score

# Get Stage 2 details (includes MA values)
s2_details = get_stage2_details(df)

# Calculate convergence score
convergence = calculate_convergence_score(
    current_price=df['Close'].iloc[-1],
    s2_details=s2_details
)

print(f"Convergence: {convergence['score']} ({convergence['grade']})")
print(f"MA Support Stop: ${convergence['ma_support_stop']:.2f}")
```

### With Trend Screener

```bash
# Automatically calculates convergence for all candidates
python3 scripts/trend_screener.py --profile large-cap --rank-by convergence

# Filter by minimum score
python3 scripts/trend_screener.py --profile large-cap --min-convergence-score 60

# Show detailed MA data
python3 scripts/trend_screener.py --tickers AAPL --show-ma-data
```

---

## Configuration

Convergence parameters in `config/risk_config.yaml`:

```yaml
ma_convergence:
  min_cluster_mas: 2           # Minimum MAs for valid cluster
  max_cluster_spread_pct: 5.0  # Maximum spread for valid cluster
  ma_buffer_pct: 1.0           # Buffer below lowest MA for stop
  
ma_support:
  enabled: true                # Enable MA support stop feature
  default_buffer_pct: 1.0      # Default buffer
  profile_overrides:
    conservative: 1.5          # Wider buffer
    aggressive: 0.5            # Tighter buffer
    tight_stops: 0.75          # Tight buffer, requires 3+ MAs
```

---

## Related Documentation

- [USER_GUIDE.md](USER_GUIDE.md) — Trend Screener usage
- [../METHODOLOGY.md](../METHODOLOGY.md) — Stage 2 methodology, MA support stop
- [../patterns/VCP.md](../patterns/VCP.md) — VCP pattern detection
- [traderlib/stage2_utils.py](../../traderlib/stage2_utils.py) — Source code
