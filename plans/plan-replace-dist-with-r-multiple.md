# Plan: Replace DIST with R-Multiple Column

**Date:** 2026-05-10
**Files:** `traderlib/dashboard.py`, `scripts/paper_engine_alpaca.py`

## Problem

The DIST column displays `(current - stop) / risk_per_share * 100` — a percentage that's unintuitive, explodes at breakeven, and doesn't map to any familiar trading concept. R-Multiple is already calculated internally for row coloring but isn't shown to the trader.

## Changes

### 1. `traderlib/dashboard.py` — Replace DIST column with R-Multiple

- Rename column header `"DIST"` → `"R"` (line 255)
- Remove `dist_pct`, `dist_style`, `dist_icon` logic (lines 281-293, ~12 lines)
- Display `r_mult` formatted as `+1.6R` with color coding matching existing row thresholds:
  - bold red (<0R)
  - yellow (0 to <1R)
  - green (1R to <2R)
  - bold green (≥2R)

### 2. `scripts/paper_engine_alpaca.py` — Add `initial_stop_price` to post-market state

- In `_load_post_market_state()`, add `'initial_stop_price': pos.get('initial_stop_price', 0)` to the `positions_data` dict (around line 1614)
- Without this, post-market dashboard cannot compute R-Multiple (falls back to current stop, zero-division at breakeven)

## What doesn't change

- `r_mult` already calculated at line 279 — no formula change needed
- Row color already uses `r_mult` (lines 296-303) — no change needed
- `risk_per_share` already uses `initial_stop_price` (line 277) — no change needed
- All other columns (TICKER, ENTRY, CURRENT, STOP, TYPE, UNREAL) stay
