# Design Spec: Progress Indicators for Discovery Pipeline

**Date:** 2026-05-31
**Author:** Claude
**Status:** Draft — pending user approval

---

## Problem Statement

The trend screener discovery mode (`--profile`) produces 4+ minutes of dead silence during external API calls. Three slow steps in `traderlib/universe_builder.py` and `traderlib/sector_resolver.py` have no feedback:

1. **`_get_current_prices()`** — Alpaca API, batches of 100 tickers. With ~7,000 tickers after filtering, that's ~70 API calls. Currently: one print at start, one at end.
2. **`_compute_dollar_volumes()`** — Alpaca bars API, chunks of 500 tickers × 60-day lookback. Heavy requests. Currently: one print at start, one at end.
3. **`SectorResolver.prefetch_from_fmp()`** — FMP `/stable/profile` endpoint, one request per ticker. ThreadPool with 2 workers + 300 req/min rate limiter. Currently: zero progress output.

The scan loop in `scripts/trend_screener.py` already has a Rich progress bar. The discovery pipeline needs equivalent visibility.

## Decision

Add an optional `progress_callback` parameter to `UniverseBuilder` and `SectorResolver` slow methods. The callback reports `(step, current, total, message)`. Callers (like `trend_screener.py`) pass a callback that prints progress. Other callers (tests, paper engine) can omit it for backward compatibility.

## Scope

### In Scope

| File | Action | Details |
|------|--------|---------|
| `traderlib/universe_builder.py` | **Edit** | Add `progress_callback` param to `_get_current_prices()`, `_compute_dollar_volumes()`, and `_fetch_sectors_from_fmp()`. Emit progress on each batch/chunk. |
| `traderlib/sector_resolver.py` | **Edit** | Add `progress_callback` param to `prefetch_from_fmp()`. Emit progress as futures complete (time-throttled). |
| `scripts/trend_screener.py` | **Edit** | Pass a print-based progress callback to `UniverseBuilder.load_universe()`. |

### Out of Scope

- The scan loop progress bar in `trend_screener.py` — already exists, not changing
- Any changes to AlpacaClient or FMP rate limiting — callbacks don't change I/O behavior
- Non-discovery paths (cached universe hit returns immediately, no callback needed)

### Entry Point Audit

Before implementing, verify all public entry points that trigger slow I/O:

```bash
grep -r "build_universe\|load_universe" scripts/ tests/ traderlib/ --include="*.py"
```

Propagate `progress_callback` through every public entry point (`load_universe()`, `build_universe()`, etc.) so no caller is accidentally left without progress visibility.

### Gap Resolutions (from outside review)

**Gap 1: `prefetch_from_fmp` uses `for future in futures`, NOT `as_completed`**

The spec originally showed `as_completed`; actual code iterates in submission order. **Resolution:** Keep the existing `for future in futures:` loop. The callback emission inside the loop is safe because `future.result()` blocks until that specific future completes. No behavior change. The time-based throttle still works.

**Gap 2: Fallback paths in `_get_current_prices` and `_compute_dollar_volumes` emit zero progress**

If a batch/chunk fails and falls back to individual API calls, the user sees silence. **Resolution:** Emit one fallback notice when a batch fails:

```python
except Exception:
    if progress_callback:
        progress_callback({
            "step": PROGRESS_STEP_PRICES,
            "current": batch_start + len(batch),
            "total": total,
            "message": f"Batch failed — falling back to {len(batch)} individual fetches"
        })
    # ... fallback loop ...
```

This is acceptable because fallback is rare (Alpaca paid tier is reliable). No per-ticker progress inside fallback — just one notice.

**Gap 3: `_fetch_sectors_from_fmp` wrapper blocks callback propagation**

`build_universe()` calls `_fetch_sectors_from_fmp()` which instantiates `SectorResolver` internally. The callback must propagate through this wrapper. **Resolution:** Add `progress_callback` parameter to `_fetch_sectors_from_fmp()` and forward it to `resolver.prefetch_from_fmp()`.

```python
def _fetch_sectors_from_fmp(self, tickers, progress_callback=None):
    from traderlib.sector_resolver import SectorResolver
    resolver = SectorResolver()
    return resolver.prefetch_from_fmp(tickers, progress_callback=progress_callback)
```

**Gap 4: `build_universe` already prints stage headers**

Existing prints like `"Fetching current prices for 7305 tickers..."` must remain. The callback adds detail *between* headers, it does not replace them. **Resolution:** Do not remove existing print statements in `build_universe()`. The callback is additive only.

## Design

### Callback Interface

Use a `TypedDict` so the callback is self-documenting, extensible, and avoids brittle positional arguments:

```python
from typing import TypedDict, Optional, Callable

class ProgressUpdate(TypedDict):
    step: str          # 'prices' | 'liquidity' | 'sectors'
    current: int
    total: int
    message: str

ProgressCallback = Callable[[ProgressUpdate], None]
# step: short slug identifying the pipeline stage
# current: completed items
# total: total items
# message: human-readable description for display
```

**Library responsibility:** emit raw updates only. Never prefix messages with whitespace, arrows, or formatting — that belongs to the caller.

**Caller responsibility:** decide how to render (Rich bar, `print()`, log line, or silent).

### `UniverseBuilder` Changes

Add module-level step constants so callers can match on them reliably:

```python
# traderlib/universe_builder.py
PROGRESS_STEP_PRICES = "prices"
PROGRESS_STEP_LIQUIDITY = "liquidity"
```

```python
# In build_universe(), pass callback through to slow methods

def build_universe(self, ..., progress_callback: Optional[ProgressCallback] = None):
    ...
    current_prices = self._get_current_prices(tickers_to_check, progress_callback)
    ...
    dvol_result = self._compute_dollar_volumes(
        tickers_for_dvol, lookback_days, progress_callback
    )
```

**`_get_current_prices()` progress:**
```python
for i, batch_start in enumerate(range(0, len(tickers), batch_size)):
    batch = tickers[batch_start:batch_start + batch_size]
    # ... API call ...
    if progress_callback:
        progress_callback({
            "step": PROGRESS_STEP_PRICES,
            "current": min(batch_start + batch_size, total),
            "total": total,
            "message": f"Fetching prices {min(batch_start + batch_size, total)}/{total}"
        })
```

**`_compute_dollar_volumes()` progress:**
```python
for chunk_start in range(0, len(tickers), chunk_size):
    chunk = tickers[chunk_start:chunk_start + chunk_size]
    # ... fetch bars, compute metrics ...
    if progress_callback:
        progress_callback({
            "step": PROGRESS_STEP_LIQUIDITY,
            "current": min(chunk_start + chunk_size, total),
            "total": total,
            "message": f"Computing liquidity {min(chunk_start + chunk_size, total)}/{total}"
        })
```

### `SectorResolver` Changes

Add module-level step constant:

```python
# traderlib/sector_resolver.py
PROGRESS_STEP_SECTORS = "sectors"
```

```python
# In prefetch_from_fmp(), emit progress as futures complete
import time

def prefetch_from_fmp(self, tickers, progress_callback: Optional[ProgressCallback] = None):
    ...
    completed = 0
    total = len(tickers)
    last_emit = time.time()
    for future in futures:
        t, s = future.result()
        completed += 1
        if progress_callback and (time.time() - last_emit > 2.0):
            progress_callback({
                "step": PROGRESS_STEP_SECTORS,
                "current": completed,
                "total": total,
                "message": f"Fetching sectors {completed}/{total}"
            })
            last_emit = time.time()
    # Final emit
    if progress_callback:
        progress_callback({
            "step": PROGRESS_STEP_SECTORS,
            "current": total,
            "total": total,
            "message": f"Resolved sectors for {total} tickers"
        })
```

**Why time-based?** Count-based throttling (every 10th) hides tail latency. If the last 9 stragglers hang on 429 retry, the counter appears stuck. Time-based emission guarantees the user sees movement at least every 2 seconds.

**Thread safety:** The loop above is safe because `future.result()` blocks on the main thread. The cleanup pass (`unknowns` loop) also runs serially in the main thread — no concurrent callback invocation.

### `TrendScreener` Integration

In `trend_screener.py`, the caller decides how to render. Example with simple print:

```python
# In main(), before calling builder.load_universe():

def make_progress(update: ProgressUpdate):
    # Caller owns formatting — library provides raw message only
    print(f"  {update['message']}")

# Pass to load_universe
result = builder.load_universe(
    profile=...,
    force_refresh=args.refresh,
    progress_callback=make_progress
)
```

**Alternative with Rich:** If Rich is installed, use a proper progress bar. But a simple print callback is sufficient and doesn't require Rich in the library code.

## Output Example

```
🔍 Discovery mode: building universe from Alpaca...
   Profile: high-octane
   Force refresh: bypassing cache
  Fetching assets from Alpaca...
  Fetched 13,753 assets
  Filtered to 7,305 (tradable, exclude OTC, AMEX, 4,999 ETFs, marginable only)
  Fetching current prices for 7305 tickers...
    Fetching prices 100/7305
    Fetching prices 200/7305
    ...
    Fetching prices 7300/7305
  Received prices for 7303 tickers
  Filtered to 5,509 (price >= $5)
  Computing liquidity metrics for 5,509 stocks (60-day lookback)...
    Computing liquidity 500/5509
    Computing liquidity 1000/5509
    ...
    Computing liquidity 5509/5509
  Filtered to 1,328 (dollar vol $20M-$150M)
  Fetching sectors for 1328 tickers from FMP...
    Fetching sectors 10/1328
    Fetching sectors 20/1328
    ...
    Fetching sectors 1328/1328
  Resolved sectors for 1318/1328 tickers
  Saved to ...
```

## Backward Compatibility

- All `progress_callback` parameters are `Optional` with default `None`
- Existing callers (tests, paper engine, backtest) pass no callback → zero behavior change
- No new dependencies required (standard library only)
- The callback is injected by the caller, not hardcoded in the library

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Callback firing too fast creates log spam | Time-based throttle (≥2s between emits) for FMP; batch-level emits for Alpaca |
| ThreadPoolExecutor futures block the callback loop | Emit after `future.result()` returns on main thread (no `as_completed` — keeps existing iteration order) |
| Existing tests break from new parameter | Default `None`, no required positional params added |
| Rich import fails in headless environments | Simple print callback as default; Rich is caller-side optional |

## Success Criteria

- [ ] `trend_screener.py --profile high-octane --refresh` shows progress for prices, liquidity, and sectors
- [ ] No new dependencies added to library code
- [ ] Existing tests pass without modification
- [ ] Backward compatible: `UniverseBuilder.load_universe()` without callback works unchanged
- [ ] Progress callback fires at reasonable intervals (not every single item)
- [ ] Unit test mocks callback and asserts it receives expected `ProgressUpdate` values during `_get_current_prices()` and `_compute_dollar_volumes()`

---

## Notes

- The scan loop already has a Rich progress bar. This spec only covers the discovery pipeline.
- The cleanup pass in `prefetch_from_fmp()` (stragglers after 429s) runs serially in the main thread and does not need its own callback.
- This is an additive change. No existing code paths are removed.
- **Alpaca API limits:** The historical bars endpoint limits requests to ~200 symbols. The current `chunk_size=500` in `_compute_dollar_volumes()` may trigger frequent fallback to individual fetches. Fallback progress notices (Gap 2) are particularly valuable here because they provide visibility during these slower individual calls.
- **FMP rate limit:** Confirmed on Starter tier (300 req/min). The `ThreadSafeRateLimiter(300)` and 2-worker ThreadPool configuration matches this limit exactly.
