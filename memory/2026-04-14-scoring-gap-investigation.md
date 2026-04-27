# Scoring Gap Investigation: NEE/NFG High Scores Despite Below Key MAs

**Date:** 2026-04-14
**Status:** Investigation complete, pending implementation decision

## Problem

NEE and NFG score 85 (Tier 1, 6/7 Stage2) in the entry signal scanner despite being below their 50 MA and 20 MA. The scanner places them in "READY NOW" alongside stocks with proper trend alignment.

## Root Cause

1. **No 20 MA check.** The 7-point system (`traderlib/stage2_utils.py`) only checks 50/100/200 MAs. Being below 20 MA has zero scoring impact.

2. **6/7 and 7/7 map to the same 30 points.** `get_entry_score()` lumps both scores into one bucket at `stage2_utils.py:169`. A stock failing "Price > 50 MA" gets the same Stage 2 contribution as a perfect 7/7.

3. **Easy to score 85 with no momentum.** Stage2=6 (30pts) + Risk<10% (30pts) + Distance<3% (25pts) = 85. Zero momentum or RS needed.

## NEE Specific Analysis

NEE below 50 MA but above 100/200 MA:
- Fails criterion 1 (Price > 50 MA) only
- Passes criteria 2-7
- Gets 6/7, which earns 30 points (same as 7/7)

## Recommendations

### Option A: Split Scoring + 20 MA Penalty (Pragmatic)

- Split 6/7 to 25pts (was 30), 7/7 stays 30
- Add -10 penalty for price below 20 MA
- Files: 3 (stage2_utils.py, entry_signals.py, tests)
- NEE: 70 (was 85)
- Low regression risk

### Option B: Expand to 8-Point System (Clean)

- Add "Price > 20 MA" as criterion 1
- Keep MA stacking at 50>100>200 (20 MA too noisy for stacking)
- Recalibrate get_entry_score buckets for 0-8 range
- NEE: 75, Tier 2 (was Tier 1)
- Files: 15+ (stage2_utils.py, backtest/strategy.py, paper_engine, reports, tests, docs)
- Higher regression risk, but self-consistent long-term

### Recommended Path

Option A for immediate fix. Can evolve to Option B in v0.5.0 if needed.

If choosing Option B, do in two phases:
1. Phase 1: Add 20 MA criterion + recalibrate scoring
2. Phase 2: Update tier thresholds + displays + docs after verifying backtest results

## Key Files

- `traderlib/stage2_utils.py` - scoring logic (calculate_stage2_score, get_entry_score)
- `scripts/entry_signals.py` - scanner that produced the output
- `traderlib/backtest/strategy.py` - backtesting uses same functions
- `scripts/paper_engine_alpaca.py` - paper engine uses same functions

## Verification

1. `python3 scripts/entry_signals.py --ticker NEE` (before/after score comparison)
2. `pytest tests/test_stage2_with_fixtures.py tests/test_entry_score_properties.py`
3. `python3 scripts/backtest.py` (compare results before/after for Option B)