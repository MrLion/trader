# Plan: Add `--entry-mode pocket` to Trend Screener

## Context

The trend screener's `--entry-mode pivot` checks if a stock is within 5% of its 20-day high — it's a simple range filter, not actual pivot detection. Meanwhile `entry_signals.py` uses pocket pivot detection (volume-confirmed institutional buying) from the shared `traderlib/pivot_detection.py` library. This creates confusion: the same term "pivot" means different things in different tools, and stocks with valid pocket pivots get marked "No Setup" by the trend screener.

VCP has been retired from the project, so this plan also removes VCP-specific handling from the trend screener.

## What's changing

Add `--entry-mode pocket` as a new option that uses the shared pocket pivot detection library. The existing modes (`any`, `pivot`, `volume`) stay unchanged.

## Files to modify

**`scripts/trend_screener.py`** — 4 changes:

1. **Import** — add `from traderlib.pivot_detection import detect_pivot`.

2. **Entry timing** — detect pocket pivot as a signal overlay for every ticker:
   - Call `detect_pivot(ticker, hist, technique='pocket_pivot')`
   - If it returns a `PivotSignal`, always set `has_pocket_pivot = True` and `pocket_pivot_price` on the result dict
   - When `--entry-mode pocket` is selected, also use the signal as the primary setup: if proximity <= 5%, set `entry_ready = True`, `setup_type = 'pocket'`

3. **`--entry-mode any` redesign** — instead of only trying the 20-day pivot, `any` now tries all primary setups in priority order, while pocket pivot is detected separately as a signal badge:
   1. 20-day range pivot
   2. Volume-confirmed pivot
   3. If none match, fall back to `setup_type='trend'`
   4. Pocket pivot is always detected and displayed as a `pocket $price` signal badge

4. **Argument** — add `'pocket'` to the `--entry-mode` choices and update help text.

5. **HTML export** — restore the rich interactive HTML template with filter buttons, summary cards, grouped sections (Ready Now / Near Pivot / Extended / No Setup), and detail rows with the MA stack.

## Behavior

| Flag | What it checks |
|------|----------------|
| `--entry-mode pocket` | Volume-confirmed pocket pivot within 5% of current price |
| `--entry-mode pivot` | Within 5% of 20-day high (unchanged) |
| `--entry-mode any` | Try 20-day pivot → volume spike, then fall back to trend. Pocket pivot is always detected and shown as a signal badge. |

## Verification

1. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode pocket --export csv`
2. Check the CSV output for `has_pocket_pivot` and `pocket_pivot_price` columns
3. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode pocket`
4. Confirm VSH and TGT show up as candidates (they have pocket pivots but were previously "No Setup")
5. Run: `python3 scripts/trend_screener.py --tickers AAPL --entry-mode pocket`
6. Confirm AAPL may or may not have a pocket pivot (real data)
7. Run: `python3 scripts/trend_screener.py --tickers VSH TGT --entry-mode any --rank-by setup`
8. Confirm VSH and TGT are still candidates and show `has_pocket_pivot=True` in any mode
9. Run: `python3 scripts/trend_screener.py --profile large-cap --export html` and verify the rich interactive HTML is generated with grouped sections
10. Run full test suite: `python3 -m pytest tests/ -q --no-header --ignore=tests/test_mcstock_historical_scraper.py --ignore=tests/test_backtest_cli.py`
11. Run unit tests: `python3 -m pytest tests/test_trend_screener.py -v`
