# Plan: Add `--entry-mode pocket` to Trend Screener

## Context

The trend screener's `--entry-mode pivot` checks if a stock is within 5% of its 20-day high — it's a simple range filter, not actual pivot detection. Meanwhile `entry_signals.py` uses pocket pivot detection (volume-confirmed institutional buying) from the shared `traderlib/pivot_detection.py` library. This creates confusion: the same term "pivot" means different things in different tools, and stocks with valid pocket pivots get marked "No Setup" by the trend screener.

## What's changing

Add `--entry-mode pocket` as a new option that uses the shared pocket pivot detection library. The existing modes (`any`, `pivot`, `vcp`, `volume`) stay unchanged.

## Files to modify

**`scripts/trend_screener.py`** — 4 changes:

1. **Import** — add `from traderlib.pivot_detection import detect_pivot` after existing VCP import.

2. **Entry timing** — add a new `_try_pocket_pivot()` helper:
   - Call `detect_pivot(ticker, hist, technique='pocket_pivot')`
   - If it returns a `PivotSignal`, use `signal.pivot_price` as the pivot
   - Calculate proximity: `((pivot_price - current) / pivot_price) * 100`
   - If proximity <= max_proximity (5%), set `entry_ready = True`, `setup_type = 'pocket'`
   - Always set `has_pocket_pivot` and `pocket_pivot_price` on the result dict when a signal exists

3. **`--entry-mode any` redesign** — instead of only trying the 20-day pivot, `any` now tries all actionable setups in priority order:
   1. VCP
   2. Pocket pivot
   3. 20-day range pivot
   4. Volume-confirmed pivot
   5. If none match, fall back to `setup_type = 'trend'`

4. **Argument** — add `'pocket'` to the `--entry-mode` choices and update help text.

**No changes to the HTML export** — the existing `df.to_html()` output will include the new fields automatically. The interactive HTML redesign is a separate concern.

## Behavior

| Flag | What it checks |
|------|----------------|
| `--entry-mode pocket` | Volume-confirmed pocket pivot within 5% of current price |
| `--entry-mode pivot` | Within 5% of 20-day high (unchanged) |
| `--entry-mode any` | Try VCP → pocket pivot → 20-day pivot → volume spike, then fall back to trend |

## Verification

1. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode pocket --export csv`
2. Check the CSV output for `has_pocket_pivot` and `pocket_pivot_price` columns
3. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode pocket`
4. Confirm VSH and TGT show up as candidates (they have pocket pivots but were previously "No Setup")
5. Run: `python3 scripts/trend_screener.py --tickers AAPL --entry-mode pocket`
6. Confirm AAPL may or may not have a pocket pivot (real data)
7. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode any --rank-by setup`
8. Confirm VSH and TGT are still candidates (any mode now includes pocket pivot)
9. Run full test suite: `python3 -m pytest tests/ -q --no-header --ignore=tests/test_mcstock_historical_scraper.py --ignore=tests/test_backtest_cli.py`
10. Run unit tests: `python3 -m pytest tests/test_trend_screener.py -v`
