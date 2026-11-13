# Code Review: PR #22 — "feat: enrich universes with sector data + shared SectorResolver"

**18 files (+792/-102) on branch `worktree-sector-enrichment` vs `main`**

---

### 1. Architecture Assessment

The design is sound. Three clear layers:

- **Source of truth**: `UniverseBuilder._fetch_sectors_from_fmp()` fetches sector for the full validated ticker list (~600) at universe-build time and persists it in a `Sector` column of the cached CSV (4h TTL). This means every scan that loads from cache gets sector data for free, no API calls.
- **Runtime resolver**: `SectorResolver` provides a 3-tier fallback (watchlist → universe → FMP) for any code that needs sector data outside the universe-build pipeline. In-memory cache prevents redundant lookups.
- **Consumers**: `TickerAnalyzer`, `PaperEngine`, `PaperPortfolio`, `TrendScreener`, `VCPBreakout`, `BacktestStrategy` — all use `SectorResolver` and get sector data without duplicating lookup logic.

The key benefit: sector data flows through the existing `TickerAnalysis.to_dict()['sector']` pipeline to CSV/HTML/JSON outputs with zero changes to the export code.

---

### 2. ThreadSafeRateLimiter — Correctness Review

**Location**: `traderlib/sector_resolver.py`

**Token bucket algorithm** is implemented correctly:
- Tokens refill continuously based on elapsed time since last `acquire()`
- Capped at `max_per_minute` (no runaway accumulation)
- `time.sleep()` is called **outside** the lock (good practice)

**Issue 1 (Minor): Recursive `acquire()` after sleep**

```python
def acquire(self) -> None:
    with self.lock:
        # ... token check ...
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return
        sleep_time = (1.0 - self.tokens) * (60.0 / self.max_per_minute)

    time.sleep(sleep_time)
    self.acquire()  # <-- recursive call
```

Python allows re-entering a `threading.Lock()` from the same thread, so this doesn't deadlock. But it adds an unnecessary stack frame on every rate-limited call. A `while` loop would be cleaner:

```python
def acquire(self) -> None:
    while True:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.max_per_minute, self.tokens + elapsed * (self.max_per_minute / 60.0))
            self.last_update = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            sleep_time = (1.0 - self.tokens) * (60.0 / self.max_per_minute)
        time.sleep(sleep_time)
```

**Issue 2 (Minor, benign): Burst race on wake**

When multiple threads sleep and wake simultaneously, all re-enter the lock. The first thread drains the token; the rest find tokens refilled (because time passed) and proceed. Each may get slightly less than the intended 1/min rate, but because `self.last_update = now` is set every entry, the budget self-corrects. In practice at 300/min with max 10 workers, this window is negligible.

---

### 3. SectorResolver 3-Tier Fallback — Edge Case Analysis

**Tier 1: Watchlist CSV** — `_from_watchlist(ticker)`
- Caches DataFrame across calls, invalidates on mtime change
- Edge case: If watchlist has duplicate `Ticker` rows, `df[df["Ticker"] == ticker]` returns multiple rows and `.values[0]` takes the first. This matches existing behavior.

**Tier 2: Universe CSV** — `_from_universe(ticker, path)`
- Caches by path + mtime, re-reads on change
- Edge case: `_latest_universe_path()` without a profile filter returns the most recently modified universe CSV across **all** profiles. In `paper_engine_alpaca.py` and `paper_portfolio.py`, `resolve(ticker)` is called without a `universe_path`, so it picks the latest universe file regardless of profile. If `high_octane` was built after `large_cap`, the `large_cap` scan might get wrong sector data for tickers that belong to the wrong universe. **Low risk** in practice (sector data is not profile-specific), but the profile-agnostic fallback is semantically imprecise.

**Tier 3: FMP API** — `_from_fmp(ticker)`
- Returns `'Unknown'` for: `"—"`, `"ETF"`, `""` — normalized correctly
- Fails open: any exception → `'Unknown'` (logged at DEBUG level)
- No API key → returns `'Unknown'` without logging (check is fast-path)

---

### 4. FMP Duplication — Design Issue

`UniverseBuilder._fetch_sectors_from_fmp()` and `SectorResolver.prefetch_from_fmp()` are functionally identical: both create their own `ThreadSafeRateLimiter`, both use `ThreadPoolExecutor(max_workers=10)`, both hit FMP `/stable/profile`. This duplication means:

- **They don't share a rate-limit budget**. If both ran concurrently, each would allow 300 req/min, potentially exceeding the FMP plan limit. In practice they never overlap (universe build is a one-shot operation; sector lookups are on-demand), so this is safe but fragile.

**Recommendation**: Have `UniverseBuilder._fetch_sectors_from_fmp()` call `SectorResolver.prefetch_from_fmp()` instead of duplicating the logic. This eliminates the duplication and unifies the rate limit. Low priority but clean architectural debt.

---

### 5. Integration Point Review

**entry_signals.py** (+14/-0):
- `_resolve_universe_path(source)` duplicates the glob + mtime sort pattern from `SectorResolver._latest_universe_path()`. Two implementations of the same logic.
- `set_universe_path()` is called once before the scan loop — correct, avoids per-ticker CSV re-read.

**ticker_analyzer.py** (+33/-30):
- `getattr(self, '_universe_path', None)` on line ~209 is defensive but unnecessary — `_universe_path` is always initialized to `None` in `__init__`. Could be just `self._universe_path`.
- Pivot lookup is now cleanly separated from sector lookup. Good.

**paper_engine_alpaca.py** (+19/-20):
- `SectorResolver()` created without `watchlist_path` → uses default `data/watchlist.csv`. Correct.
- Watchlist `Stop_Level`/`Pivot_Price` lookup is preserved via `watchlist_df` — only the sector part was removed. Correct refactoring.

**paper_portfolio.py** (+5/-28):
- `watchlist_df` loading errors changed from `TradingExceptionHandler.log_exception(...)` to bare `except Exception: pass`. Acceptable since it's just a convenience fallback for stop-level data, but loses diagnostic visibility.
- `sector_resolver.resolve(ticker)` only called when `sector == 'Unknown'` — avoids unnecessary lookups.

**trend_screener.py** (+3/-0):
- Creates a fresh `SectorResolver()` per `TrendScreener.__init__`. No cache sharing with other components. This means repeated FMP API calls across scan cycles. Could benefit from a shared singleton or passing an existing instance.

**vcp_breakout.py** (+3/-3):
- `from traderlib.sector_resolver import SectorResolver` is inside `__init__()` rather than at module level. Works but unusual. Likely to avoid circular imports with the plugin system. If so, worth a comment.

**backtest/strategy.py** (+13/-2):
- Column normalization `[c.lower().replace(' ', '_') for c in df.columns]` fixes the PascalCase bug in watchlist CSV reads. Good defensive fix.
- `sector_dict` parameter provides explicit sector data. Used by backtest caller.

---

### 6. Test Coverage Analysis

| Area | Tests | Quality |
|------|-------|---------|
| `ThreadSafeRateLimiter` | 4 | Good — thread safety, gap enforcement, non-blocking first call |
| `SectorResolver` watchlist | 3 | Good — basic, unknown, missing column |
| `SectorResolver` universe | 3 | Good — basic, watchlist override, missing column |
| `SectorResolver` caching | 2 | OK — per-ticker cache, cross-call persistence |
| `SectorResolver` FMP fail-open | 2 | OK — no-key handling for single + batch |
| `PaperPortfolio` integration | 1 | Minimal |

**Missing test coverage**:
- `UniverseBuilder._fetch_sectors_from_fmp()` — 0 tests (hard to test without mock)
- `entry_signals._resolve_universe_path()` — 0 tests
- `ticker_analyzer._load_watchlist_pivot_and_sector()` sector path — 0 tests
- `backtest/strategy._get_sector()` with `sector_dict` — 0 tests
- `SectorResolver._latest_universe_path()` — 0 tests
- `SectorResolver.prefetch_from_fmp()` with actual API key mock — 0 tests

The existing test coverage for `SectorResolver` itself is solid. The integration points in consumers are thin.

**Test isolation**: All tests use `tmp_path` and don't touch filesystem defaults. Good.

**Thread safety test**: `test_thread_safety_under_contention` spawns 20 threads, each calling `acquire()`. A good stress test. The `test_enforces_gap_between_two_threads` manually drains the token bucket before testing — clever pattern to avoid long sleeps in tests.

---

### 7. Bug Findings

**None critical.** No logic errors, no data races, no memory leaks, no security issues.

**Minor findings** (none blocking):

1. **Recursive `acquire()`** — Works correctly but is inelegant. A `while` loop would be clearer.
2. **Duplicate universe path resolution logic** — `entry_signals._resolve_universe_path()` and `SectorResolver._latest_universe_path()` are independent implementations. Should converge on one.
3. **Duplicate FMP fetch logic** — `UniverseBuilder._fetch_sectors_from_fmp()` and `SectorResolver.prefetch_from_fmp()` share ~95% identical code, including the FMP normalization of `"—"`, `"ETF"`, `""`.
4. **Profile-agnostic universe fallback** — When `resolve()` falls back to `_latest_universe_path()` without a profile filter, it could pick a universe from the wrong profile. Low practical impact since sector data is profile-independent.
5. **`getattr(self, '_universe_path', None)`** — Unnecessary defensive pattern. `self._universe_path` is always initialized.

---

### 8. Summary

**Overall assessment**: The PR is production-ready. The architecture is clean — enrich at the source (universe build time) with a resolver for consumers. The 3-tier fallback handles all scenarios correctly. The in-memory cache avoids redundant I/O. FMP integration follows the same patterns as existing code. Test coverage for the core module is good; integration points are thinner but functional.

**Three non-blocking fixes worth doing**:
1. Replace recursive `acquire()` with a `while` loop
2. Have `UniverseBuilder._fetch_sectors_from_fmp()` delegate to `SectorResolver.prefetch_from_fmp()` to eliminate duplication
3. Drop `getattr(self, '_universe_path', None)` → `self._universe_path`
