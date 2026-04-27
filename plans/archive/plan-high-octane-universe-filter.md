---
name: High-Octane Universe Filter Fix
description: Fix high-octane universe pollution by adding max_dollar_volume filter to exclude large-cap stocks like DIS, AMD, NVDA
type: project
---

# Fix Plan: High-Octane Universe Pollution

## Problem Summary

High-octane universe includes large-cap stocks (DIS, AMD, NVDA, etc.) because it only filters by `min_dollar_volume: 20000000` without an upper bound. The universe is effectively "$20M+" instead of "$20M-$150M" (true mid-cap gap).

**Evidence:**
- `data/universes/high_octane_2026-04-18.csv` contains DIS (~$700M daily volume) and AMD (~$5B daily volume)
- Both should be in large-cap only

## Solution

Add `max_dollar_volume: 150000000` to create a true mid-cap gap universe ($20M-$150M daily dollar volume).

## Implementation Steps

### Step 1: Update config/screener_config.yaml

Add `max_dollar_volume` to high_octane profile:

```yaml
high_octane:
  min_price: 5
  min_dollar_volume: 20000000    # $20M
  max_dollar_volume: 150000000   # $150M ← NEW
  lookback_days: 60
  exclude_exchanges: ["OTC", "AMEX"]
  stack_short: true
  stack_long: false
  rs_near_high_pct: 12
  min_price_vs_10ma: 4
  min_share_volume: 400000
  min_stage2_score: 5
  min_convergence_score: null
```

### Step 2: Update traderlib/universe_builder.py

Modify the dollar volume filter (around line 383) to support max:

```python
# Current (line 383):
validated = [t for t, dvol in dollar_volumes.items() if dvol and dvol >= min_dvol]

# New:
max_dvol = profile_config.get('max_dollar_volume')
validated = [
    t for t, dvol in dollar_volumes.items()
    if dvol and dvol >= min_dvol and (max_dvol is None or dvol <= max_dvol)
]
```

### Step 3: Clear Existing Caches

Delete stale high-octane cache files to force rebuild with new filter:

```bash
rm data/universes/high_octane_*.csv
```

### Step 4: Test the Fix

Run trend screener to verify DIS/AMD excluded:

```bash
python3 scripts/trend_screener.py --profile high-octane --force-refresh
# Check output — should NOT see AMD, DIS, NVDA, etc.
```

## Expected Results

| Stock | Dollar Volume | Market Cap | Before Fix | After Fix |
|-------|--------------|------------|------------|-----------|
| AMD | ~$5B/day | ~$150B | ✗ Included | ✓ Excluded |
| DIS | ~$700M/day | ~$170B | ✗ Included | ✓ Excluded |
| NVDA | ~$20B/day | ~$2.5T | ✗ Included | ✓ Excluded |
| MSFT | ~$3B/day | ~$3T | ✗ Included | ✓ Excluded |
| HOOD | ~$80M/day | ~$20B | ✓ Included | ✓ Included |
| W (Wayfair) | ~$40M/day | ~$3B | ✓ Included | ✓ Included |
| CVNA | ~$200M/day | ~$15B | ✓ Included | ✗ Excluded (borderline) |

High-octane universe should shrink from ~2,100 tickers to ~800-1,200 tickers.

## Files to Modify

1. `config/screener_config.yaml` — add `max_dollar_volume: 150000000`
2. `traderlib/universe_builder.py` — enforce max filter in dollar volume validation
3. `docs/universe/DYNAMIC_FILTERING.md` — document new parameter

## Design Rationale

- **Why dollar volume instead of market cap?** Alpaca Asset API doesn't expose market cap. FMP has it but 300 req/min rate limit makes 2,000 ticker lookups take ~7 minutes.
- **Why $150M?** This is the threshold where large-cap universe begins (configured at $150M). Creates clean separation between profiles.
- **Backward compatible?** Yes — large_cap profile doesn't use max_dollar_volume, so behavior unchanged.

## Verification Checklist

- [ ] Config updated with max_dollar_volume
- [ ] Universe builder updated to enforce max bound
- [ ] Old cache files deleted
- [ ] Trend screener rebuilds with ~50% fewer tickers
- [ ] DIS, AMD, NVDA not in high-octane output
- [ ] HOOD, W still in high-octane output
- [ ] Documentation updated
