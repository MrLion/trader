---
name: Target Price Logic Bug (range_20d) — RESOLVED
description: range_20d pivot target removed; ticker_analyzer now computes target from actual stop
type: project
---

When a technique's stop is rejected for being too loose, its target is still applied, producing wildly inflated price targets.

**Status:** Fixed 2026-04-30 in `traderlib/pivot_detection.py`.

**Root cause:** `detect_range_20d_pivot()` computed a 2R target from the full 20-day range (pivot_high − range_low), which was ~$195 on MU — 3.8× the actual trade risk. This target was passed via `PivotSignal.target_price` and took priority in `ticker_analyzer.py:373-375`.

**Fix:** Removed target computation from `detect_range_20d_pivot()`. The function no longer sets `target_price`, so `ticker_analyzer` falls through to the config-driven formula `current + (risk_per_share × min_r_multiple)`. VCP and pocket_pivot still supply their own targets since their stops are technique-specific and more likely to be accepted.

## Repro (before fix): MU at $510.64

| What | Stop | Risk/Share | 2R Target |
|:-----|:-----|:-----------|:----------|
| Technique (range_20d) | $340.20 | $195.30 | $926.10 ← was shown |
| Actual trade stop | $459.58 | $51.06 | $612.76 ← correct |

## After fix: MU at $509.59

Target: $611.51 = $509.59 + ($50.96 × 2.0) ✓
