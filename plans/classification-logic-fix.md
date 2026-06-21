# Classification Logic Fix — Proximity-Based Section Assignment

**Status:** Draft — for review  
**Date:** 2026-06-20  
**Scope:** `scripts/trend_screener.py`, `AGENTS.md`, `scans/mockup-improved.html`

---

## Problem

The current section classification uses `entry_ready + setup_type` as a proxy for proximity. This worked accidentally in the original code because 20d range high was always above current price, so the setup detectors naturally produced the right split. Making pocket pivot the default priority broke this proxy — all 87 stocks became `pp` with `entry_ready=True`, dumping everything into Ready Now.

The section labels (Ready Now, Near Pivot, Extended, No Setup) imply proximity-based tiers, but the logic never actually checked proximity for section assignment.

Two additional problems:
- Pocket pivot detector fires for all 87 stocks. In `any` mode with pocket-first priority, the 20d and trend paths are never reached — every stock becomes `pp` regardless of which entry is actually better.
- The `any` mode should select the better entry between pocket pivot and 20d range high, not blindly pick whichever fires first.

---

## Design

### `any` mode entry selection — lower risk wins

In `any` mode, both pocket pivot and 20d range high are evaluated. Each has a stop price:

- **Pocket pivot:** `pocket_signal.stop_price` (from PivotSignal)
- **20d range high:** `pivot_data_20d['stop_low']` (20-day low)

Risk is calculated for each:

```
risk_pp  = pocket_signal.pivot_price - pocket_signal.stop_price
risk_20d = pivot_data_20d['pivot_high'] - pivot_data_20d['stop_low']
```

The entry with lower risk wins. This sets `setup_type`, `pivot_price`, and `stop_price` in the result dict. A stock could have a pocket pivot signal but still get `20d` if the 20d range high has less risk.

If only one detector fires (e.g., no pocket pivot signal), that one is used. If neither fires within proximity, trend fallback assigns the 20d range high as buy point. If no buy point at all → No Setup.

### Section classification by proximity to buy point

Five sections, ordered by trader priority:

| Section | Condition | Meaning | Color |
|---|---|---|---|
| Ready Now | Within ±2% of buy point | Act now | Green |
| Near Pivot | 2% to 5% below buy point | Set alerts | Yellow |
| Extended | More than 2% above buy point | Skip — missed it, wait for pullback | Orange |
| Developing | More than 5% below buy point | Watch list — still forming, buy point visible | Blue |
| No Setup | No buy point detected (`pivot_price` is None) | No entry signal | Gray |

Classification is purely proximity-based. No dependency on `entry_ready` or `setup_type`. Works regardless of which setup detector fired or which entry was selected.

Developing stocks must show a buy point in the table — otherwise the section is indistinguishable from No Setup. The difference: Developing has a buy point to watch, No Setup doesn't.

### Proximity formula

```
proximity = ((current - buy_point) / buy_point) * 100
```

- Positive = stock is above buy point (past it)
- Negative = stock is below buy point (hasn't reached it)
- ±2% means -2% to +2%

This reads naturally — same convention as price changes. Positive means above, negative means below.

Classification uses the stored `proximity_pct` from the result dict, not a recomputed value, to avoid rounding mismatches between displayed proximity and section assignment.

### Threshold changes

- `--pivot-proximity` default: 5% → 3% (how close to buy point for detector to fire)
- Entry protocol (AGENTS.md): ">3% past = PASS" → ">2% past = PASS"

### Relationship between detector threshold and section classification

The `--pivot-proximity` threshold (3%) determines whether a setup detector fires. The section classification then sorts stocks by actual proximity to the chosen buy point:

- Detector fires (within 3%): stock gets a buy point → classified by proximity into Ready or Near
- Detector doesn't fire (>3% below): stock has no buy point from that detector. In `any` mode, trend fallback may assign a buy point (20d range high). If no buy point at all → No Setup.
- Stock is above buy point by more than 2% → Extended (missed the entry)
- Stock is 3-5% below buy point → Near (detector fired, buy point assigned, not close enough for Ready)
- Stock is >5% below buy point → Developing (trend fallback assigned buy point, far from it)

Note: in `pp` or `20d` mode (no trend fallback), stocks outside the 3% detector threshold get no buy point → No Setup. In `any` mode, trend fallback assigns the 20d range high as buy point for stocks that pass discovery filters but don't trigger a primary detector, so they land in Developing or Near depending on proximity.

### Ranking

`rank_results` currently sorts by `entry_ready` first, then `proximity_pct`. With proximity-based classification, ranking should sort by `proximity_pct` (closest to buy point first). This aligns the display order with the section logic.

---

## Changes

### A. AGENTS.md

Update entry protocol:
- "Within 1-2% of buy point. >3% past = PASS" → "Within ±2% of buy point. >2% past = PASS"

### B. `scripts/trend_screener.py`

#### B1. Default proximity threshold
- Change `--pivot-proximity` default from 5 to 3

#### B2. Fix proximity check in all three setup detectors
- `_try_pocket_pivot_setup()`: add lower bound (`-2.0 <= proximity <= max_proximity`)
- `_try_range_pivot()`: add lower bound (`-2.0 <= proximity <= max_proximity`)
- `_try_volume_pivot()`: add lower bound (`-2.0 <= proximity <= max_proximity`)

Note: proximity is now `((current - buy_point) / buy_point) * 100`. The lower bound (-2.0) means "no more than 2% above buy point." The upper bound (max_proximity, default 3) means "no more than 3% below buy point."

#### B3. `any` mode — lower risk entry selection
Replace the current priority chain (`_try_pocket_pivot_setup() or _try_range_pivot() or _try_volume_pivot()`) with a comparison:

- Evaluate both pocket pivot and 20d range high
- Compute risk for each: `buy_point - stop_price`
- Select the entry with lower risk
- Set `setup_type` (`pp` or `20d`), `pivot_price`, and `stop_price` accordingly
- If only one fires, use that one
- If neither fires within proximity, trend fallback assigns 20d range high as buy point

#### B4. Section classification — rewrite to be proximity-based
Replace the current `entry_ready + setup_type` logic with proximity-based logic:

```python
def classify_section(r):
    bp = r.get('pivot_price')
    if bp is None or bp == 0:
        return 'nosetup'
    prox = r.get('proximity_pct', ((r['price'] - bp) / bp) * 100)
    if -2.0 <= prox <= 2.0:
        return 'ready'
    elif prox > 2.0:
        return 'extended'       # more than 2% above buy point
    elif prox >= -5.0:
        return 'near'           # 2% to 5% below buy point
    else:
        return 'developing'     # more than 5% below buy point
```

Uses stored `proximity_pct` to avoid rounding mismatches. Proximity sign: positive = above buy point, negative = below.

#### B5. Proximity display
- The "To Buy Point" column should show proximity to the buy point, not to the 10-day MA
- Currently trend fallback sets `proximity_pct = abs(price_vs_10ma)` — this should be proximity to buy point instead
- Column label: "To Pivot" → "To Buy Point"
- Proximity formula: `((current - buy_point) / buy_point) * 100` (positive = above, negative = below)

#### B6. Ranking alignment
- Update `rank_results` to sort by `proximity_pct` ascending (closest to buy point first), not by `entry_ready`

#### B7. Section ordering
Sections ordered by trader priority:
1. Ready Now (green)
2. Near Pivot (yellow)
3. Extended (orange)
4. Developing (blue)
5. No Setup (gray)

Developing is at the bottom before No Setup — these are long-term watch list stocks, not immediately actionable.

#### B8. HTML template changes
- Add `.row-developing` CSS class with blue background (`#0a1a2e`)
- Add `.summary-developing .num` CSS class with blue color (`#60a5fa`)
- Filter tabs: `All | Ready Now | Near Pivot | Extended | Developing | No Setup`
- Summary cards: `Ready Now | Near Pivot | Extended | Developing | No Setup`
- Update section rendering to produce 5 sections in priority order
- Always render all 5 sections (even when empty) with empty state messages
- Update "To Pivot" column header to "To Buy Point"
- Fix double `<tr>` bug in thead (pre-existing from previous implementation)
- Update JavaScript: add `developing` to section lists (`sc` object, live-count loop, hash validation, filter labels)

### C. Mockup
- Mockup at `scans/mockup-improved.html` has been updated with:
  - 5 sections in trader-priority order: Ready Now → Near Pivot → Extended → Developing → No Setup
  - Blue color for Developing section and summary card
  - "To Buy Point" column label
  - Proximity displayed as `((current - buy_point) / buy_point) * 100` (positive = above, negative = below)
  - All 5 sections always rendered with empty states
  - Real production data from 06/20 scan, reclassified using new proximity-based logic
  - Filter tabs and summary cards ordered to match section order
- Implementation must reproduce the mockup exactly

### D. Tests

- Update tests that assert section classification based on old `entry_ready + setup_type` logic
- Add tests for proximity-based classification:
  - Stock at +1% (above buy point) → Ready
  - Stock at -1% (below buy point) → Ready
  - Stock at -3% (below buy point) → Near
  - Stock at -6% (below buy point) → Developing
  - Stock at +3% (above buy point) → Extended
  - Stock with no buy point → No Setup
- Add test for `any` mode lower-risk selection:
  - Stock where pocket pivot risk < 20d risk → `setup_type='pp'`
  - Stock where 20d risk < pocket pivot risk → `setup_type='20d'`
  - Stock where only one detector fires → uses that one

---

## Files affected

| File | Changes |
|---|---|
| `AGENTS.md` | Entry protocol threshold 3% → 2% |
| `scripts/trend_screener.py` | Default proximity, proximity sign flip, proximity check fix, any-mode risk selection, section classification rewrite, Developing section, ranking alignment, HTML template, column label, double `<tr>` fix, JS for 5 sections |
| `scans/mockup-improved.html` | Updated — 5 sections, new ordering, blue for Developing, column label, flipped proximity sign |
| `tests/test_trend_screener.py` | Classification tests, any-mode risk selection tests |