# Discovery Progress Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional progress callback to `UniverseBuilder` and `SectorResolver` slow methods so `trend_screener.py --profile` shows live feedback during the 4+ minute discovery pipeline.

**Architecture:** Use a `ProgressUpdate` TypedDict with `step`, `current`, `total`, `message` fields. Library code emits raw updates; callers decide how to render. All callback params are optional (`None` default) for backward compatibility. No new dependencies.

**Tech Stack:** Python 3.11+, standard library (`typing`, `time`). Existing imports: `alpaca-py`, `pandas`, `requests`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `traderlib/universe_builder.py` | **Edit** | Add `ProgressUpdate` TypedDict, step constants, callback params to slow methods and public entry points |
| `traderlib/sector_resolver.py` | **Edit** | Add `PROGRESS_STEP_SECTORS`, time-throttled callback in `prefetch_from_fmp()` |
| `scripts/trend_screener.py` | **Edit** | Add `make_progress` print callback, pass to `builder.load_universe()` |
| `tests/test_universe_builder.py` | **Edit** | Add tests mocking callback and asserting `ProgressUpdate` values |

---

### Task 1: Define `ProgressUpdate` TypedDict and step constants in `UniverseBuilder`

**Files:**
- Modify: `traderlib/universe_builder.py` (top of file, after imports)

- [ ] **Step 1: Add TypedDict and constants**

Add after the existing imports (before the `UniverseResult` dataclass):

```python
from typing import TypedDict, Callable


class ProgressUpdate(TypedDict):
    """Raw progress update emitted by library code. Callers decide how to render."""
    step: str          # 'prices' | 'liquidity' | 'sectors'
    current: int
    total: int
    message: str


ProgressCallback = Callable[[ProgressUpdate], None]

PROGRESS_STEP_PRICES = "prices"
PROGRESS_STEP_LIQUIDITY = "liquidity"
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python3 -m py_compile traderlib/universe_builder.py`
Expected: PASS (no output)

- [ ] **Step 3: Commit**

```bash
git add traderlib/universe_builder.py
git commit -m "feat: add ProgressUpdate TypedDict and step constants for discovery pipeline"
```

---

### Task 2: Add callback param to `_get_current_prices()` with batch-level progress

**Files:**
- Modify: `traderlib/universe_builder.py:204-231`

- [ ] **Step 1: Modify method signature and add progress emission**

Replace the existing `_get_current_prices` method with:

```python
    def _get_current_prices(self, tickers: List[str],
                            progress_callback: Optional[ProgressCallback] = None) -> Dict[str, float]:
        """Get current prices for a list of tickers with batching and rate limiting."""
        prices = {}
        batch_size = 100  # Safe batch size to avoid 414 errors
        total = len(tickers)

        # Process in batches
        for batch_start in range(0, len(tickers), batch_size):
            batch = tickers[batch_start:batch_start + batch_size]
            try:
                batch_prices = self.alpaca.get_latest_prices_batch(batch)
                for k, v in batch_prices.items():
                    if v is not None:
                        prices[k] = v
            except Exception:
                # Fallback for this batch: fetch individually
                if progress_callback:
                    progress_callback({
                        "step": PROGRESS_STEP_PRICES,
                        "current": batch_start + len(batch),
                        "total": total,
                        "message": f"Batch failed — falling back to {len(batch)} individual fetches"
                    })
                for ticker in batch:
                    try:
                        price = self.alpaca.get_latest_price(ticker)
                        if price:
                            prices[ticker] = price
                    except Exception:
                        pass

            if progress_callback:
                progress_callback({
                    "step": PROGRESS_STEP_PRICES,
                    "current": min(batch_start + batch_size, total),
                    "total": total,
                    "message": f"Fetching prices {min(batch_start + batch_size, total)}/{total}"
                })

        return prices
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python3 -m py_compile traderlib/universe_builder.py`
Expected: PASS (no output)

- [ ] **Step 3: Commit**

```bash
git add traderlib/universe_builder.py
git commit -m "feat: add progress callback to _get_current_prices"
```

---

### Task 3: Add callback param to `_compute_dollar_volumes()` with chunk-level progress

**Files:**
- Modify: `traderlib/universe_builder.py:233-299`

- [ ] **Step 1: Modify method signature and add progress emission**

Replace the existing `_compute_dollar_volumes` method with:

```python
    def _compute_dollar_volumes(self, tickers: List[str], lookback_days: int,
                                progress_callback: Optional[ProgressCallback] = None) -> Dict[str, float]:
        """Compute average daily dollar volume for multiple tickers.

        Processes in chunks of 500 to avoid URL-length limits on large universes.
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from datetime import datetime, timedelta

        results = {}
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        chunk_size = 500
        total = len(tickers)

        for chunk_start in range(0, len(tickers), chunk_size):
            chunk = tickers[chunk_start:chunk_start + chunk_size]
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=chunk,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=end,
                    adjustment=Adjustment.ALL
                )

                bars_response = self.alpaca.data_client.get_stock_bars(request)
                bars_dict = bars_response.data if hasattr(bars_response, 'data') else bars_response

                for ticker in chunk:
                    if ticker not in bars_dict:
                        continue
                    bars = bars_dict[ticker]
                    if len(bars) < 10:
                        continue
                    dollar_vols = [b.close * b.volume for b in bars]
                    results[ticker] = sum(dollar_vols) / len(dollar_vols)

            except Exception:
                # Fallback: compute individually for failed chunk
                if progress_callback:
                    progress_callback({
                        "step": PROGRESS_STEP_LIQUIDITY,
                        "current": chunk_start + len(chunk),
                        "total": total,
                        "message": f"Chunk failed — falling back to {len(chunk)} individual fetches"
                    })
                for ticker in chunk:
                    if ticker not in results:
                        dvol = self._compute_dollar_volume_single(ticker, lookback_days)
                        if dvol:
                            results[ticker] = dvol

            if progress_callback:
                progress_callback({
                    "step": PROGRESS_STEP_LIQUIDITY,
                    "current": min(chunk_start + chunk_size, total),
                    "total": total,
                    "message": f"Computing liquidity {min(chunk_start + chunk_size, total)}/{total}"
                })

        return results
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python3 -m py_compile traderlib/universe_builder.py`
Expected: PASS (no output)

- [ ] **Step 3: Commit**

```bash
git add traderlib/universe_builder.py
git commit -m "feat: add progress callback to _compute_dollar_volumes"
```

---

### Task 4: Add callback param to `_fetch_sectors_from_fmp()` and propagate through `build_universe()`/`load_universe()`

**Files:**
- Modify: `traderlib/universe_builder.py:300-309` (`_fetch_sectors_from_fmp`)
- Modify: `traderlib/universe_builder.py:311-451` (`build_universe`)
- Modify: `traderlib/universe_builder.py:453-472` (`load_universe`)

- [ ] **Step 1: Modify `_fetch_sectors_from_fmp`**

Replace:
```python
    def _fetch_sectors_from_fmp(self, tickers: List[str]) -> Dict[str, str]:
        """Fetch sector data from FMP for a list of tickers.

        Delegates to SectorResolver.prefetch_from_fmp to avoid
        duplicating rate-limiting and fetch logic.
        """
        from traderlib.sector_resolver import SectorResolver

        resolver = SectorResolver()
        return resolver.prefetch_from_fmp(tickers)
```

With:
```python
    def _fetch_sectors_from_fmp(self, tickers: List[str],
                                  progress_callback: Optional[ProgressCallback] = None) -> Dict[str, str]:
        """Fetch sector data from FMP for a list of tickers.

        Delegates to SectorResolver.prefetch_from_fmp to avoid
        duplicating rate-limiting and fetch logic.
        """
        from traderlib.sector_resolver import SectorResolver

        resolver = SectorResolver()
        return resolver.prefetch_from_fmp(tickers, progress_callback=progress_callback)
```

- [ ] **Step 2: Modify `build_universe` signature and propagate callback**

Change:
```python
    def build_universe(self, profile: str, force_refresh: bool = False) -> UniverseResult:
```

To:
```python
    def build_universe(self, profile: str, force_refresh: bool = False,
                       progress_callback: Optional[ProgressCallback] = None) -> UniverseResult:
```

Then update the three internal calls:

1. `_get_current_prices` call (around line 387):
```python
        current_prices = self._get_current_prices(tickers_to_check, progress_callback)
```

2. `_compute_dollar_volumes` call (around line 406):
```python
        dollar_volumes = self._compute_dollar_volumes(tickers_for_dvol, lookback_days, progress_callback)
```

3. `_fetch_sectors_from_fmp` call (around line 424):
```python
        sectors = self._fetch_sectors_from_fmp(validated, progress_callback)
```

- [ ] **Step 3: Modify `load_universe` signature and propagate callback**

Change:
```python
    def load_universe(self, profile: str = None, force_refresh: bool = False) -> UniverseResult:
```

To:
```python
    def load_universe(self, profile: str = None, force_refresh: bool = False,
                       progress_callback: Optional[ProgressCallback] = None) -> UniverseResult:
```

Then change:
```python
        return self.build_universe(profile, force_refresh)
```

To:
```python
        return self.build_universe(profile, force_refresh, progress_callback)
```

- [ ] **Step 4: Verify no syntax errors**

Run: `python3 -m py_compile traderlib/universe_builder.py`
Expected: PASS (no output)

- [ ] **Step 5: Run existing tests**

Run: `python3 -m pytest tests/test_universe_builder.py -v`
Expected: All tests pass (no regressions from new optional param)

- [ ] **Step 6: Commit**

```bash
git add traderlib/universe_builder.py
git commit -m "feat: propagate progress_callback through build_universe and load_universe"
```

---

### Task 5: Add callback to `SectorResolver.prefetch_from_fmp()` with time-throttled emission

**Files:**
- Modify: `traderlib/sector_resolver.py:105-172`

- [ ] **Step 1: Add step constant**

After the `_FMP_BASE` constant at line 17, add:

```python
PROGRESS_STEP_SECTORS = "sectors"
```

- [ ] **Step 2: Modify `prefetch_from_fmp` signature and add progress emission**

Replace the method with:

```python
    def prefetch_from_fmp(self, tickers: List[str],
                          progress_callback: Optional[Callable[[Dict[str, any]], None]] = None) -> Dict[str, str]:
        """Batch-fetch sectors from FMP and populate cache.

        Retries up to 3 times on HTTP 429 (rate limit) with exponential backoff.
        Non-429 errors are treated as permanent and return Unknown immediately.
        """
        if not self._fmp_api_key:
            logger.warning("FMP_API_KEY not set; skipping sector prefetch")
            return {t: "Unknown" for t in tickers}

        from concurrent.futures import ThreadPoolExecutor
        import time as _time

        def fetch_one(ticker: str) -> tuple[str, str]:
            self._limiter.acquire()
            import requests as req

            url = f"{_FMP_BASE}/profile"
            params = {"symbol": ticker, "apikey": self._fmp_api_key}
            for attempt in range(5):
                try:
                    resp = req.get(url, params=params, timeout=_REQUEST_TIMEOUT)
                    if resp.status_code == 429:
                        if attempt < 4:
                            _time.sleep(1.0 + attempt * 1.5 + (hash(ticker) % 10) * 0.1)
                            continue
                        logger.debug("FMP 429 rate limited for %s after 5 attempts", ticker)
                        return ticker, "Unknown"
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        sector = data[0].get("sector", "Unknown")
                        if sector in ("—", "ETF", ""):
                            sector = "Unknown"
                        return ticker, sector
                except req.HTTPError as exc:
                    if attempt < 4:
                        _time.sleep(1.0 + attempt * 1.5 + (hash(ticker) % 10) * 0.1)
                        continue
                    logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
                    return ticker, "Unknown"
                except Exception as exc:
                    logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
                    return ticker, "Unknown"
                _time.sleep(0.5)
            return ticker, "Unknown"

        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fetch_one, t) for t in tickers]
            completed = 0
            total = len(tickers)
            last_emit = _time.time()
            for future in futures:
                t, s = future.result()
                completed += 1
                results[t] = s
                if s != "Unknown":
                    self._cache[t] = s
                if progress_callback and (_time.time() - last_emit > 2.0):
                    progress_callback({
                        "step": PROGRESS_STEP_SECTORS,
                        "current": completed,
                        "total": total,
                        "message": f"Fetching sectors {completed}/{total}"
                    })
                    last_emit = _time.time()

        # Final emit
        if progress_callback:
            progress_callback({
                "step": PROGRESS_STEP_SECTORS,
                "current": total,
                "total": total,
                "message": f"Resolved sectors for {total} tickers"
            })

        # Sequential cleanup pass — stragglers that 429'd despite retries
        unknowns = [t for t, s in results.items() if s == "Unknown"]
        if unknowns:
            logger.info("Cleanup pass for %s stragglers...", len(unknowns))
            _time.sleep(5.0)
            for t in unknowns:
                sector = fetch_one(t)[1]
                if sector != "Unknown":
                    results[t] = sector
                    self._cache[t] = sector

        return results
```

**Note:** The callback type annotation uses `Dict[str, any]` instead of `ProgressUpdate` because `sector_resolver.py` doesn't import from `universe_builder.py` (to avoid circular dependency risk). The caller passes the same dict shape regardless.

- [ ] **Step 3: Verify no syntax errors**

Run: `python3 -m py_compile traderlib/sector_resolver.py`
Expected: PASS (no output)

- [ ] **Step 4: Commit**

```bash
git add traderlib/sector_resolver.py
git commit -m "feat: add time-throttled progress callback to prefetch_from_fmp"
```

---

### Task 6: Add `make_progress` callback in `trend_screener.py`

**Files:**
- Modify: `scripts/trend_screener.py:679-714` (discovery mode block)

- [ ] **Step 1: Define callback before discovery call**

In the discovery mode block (around line 688), before `builder.load_universe()`, add:

```python
        def make_progress(update):
            # Caller owns formatting — library provides raw message only
            print(f"    {update['message']}")
```

- [ ] **Step 2: Pass callback to `load_universe()`**

Change:
```python
            result = builder.load_universe(profile=args.profile.replace('-', '_'), force_refresh=args.refresh)
```

To:
```python
            result = builder.load_universe(
                profile=args.profile.replace('-', '_'),
                force_refresh=args.refresh,
                progress_callback=make_progress
            )
```

- [ ] **Step 3: Verify no syntax errors**

Run: `python3 -m py_compile scripts/trend_screener.py`
Expected: PASS (no output)

- [ ] **Step 4: Commit**

```bash
git add scripts/trend_screener.py
git commit -m "feat: print progress during trend screener discovery mode"
```

---

### Task 7: Add unit tests for callback invocation

**Files:**
- Modify: `tests/test_universe_builder.py`

- [ ] **Step 1: Add mock callback test for `_get_current_prices`**

Add this test class after `TestFetchAssets`:

```python
class TestProgressCallback:
    """Test progress callback invocation in slow methods."""

    def test_get_current_prices_emits_progress(self, builder, mock_alpaca):
        mock_alpaca.get_latest_prices_batch.return_value = {"AAPL": 150.0}
        updates = []

        def callback(update):
            updates.append(update)

        builder._get_current_prices(["AAPL"], progress_callback=callback)
        assert len(updates) == 1
        assert updates[0]["step"] == "prices"
        assert updates[0]["current"] == 1
        assert updates[0]["total"] == 1
        assert "Fetching prices" in updates[0]["message"]

    def test_compute_dollar_volumes_emits_progress(self, builder, mock_alpaca):
        """Test that _compute_dollar_volumes emits progress updates."""
        import pandas as pd

        # Create mock bars that AlpacaClient would return
        mock_bar = Mock()
        mock_bar.close = 100.0
        mock_bar.volume = 1_000_000
        mock_bars = [mock_bar] * 20  # 20 bars

        # Mock the data_client.get_stock_bars response
        mock_response = Mock()
        mock_response.data = {"AAPL": mock_bars}
        mock_alpaca.data_client.get_stock_bars.return_value = mock_response

        updates = []

        def callback(update):
            updates.append(update)

        result = builder._compute_dollar_volumes(["AAPL"], 60, progress_callback=callback)
        assert len(updates) == 1
        assert updates[0]["step"] == "liquidity"
        assert updates[0]["current"] == 1
        assert updates[0]["total"] == 1
        assert "Computing liquidity" in updates[0]["message"]
        assert "AAPL" in result

    def test_build_universe_propagates_callback(self, builder, mock_alpaca):
        """Test that build_universe forwards callback to slow methods."""
        assets = [
            _make_asset("AAPL", name="Apple Inc", marginable=True),
        ]
        updates = []

        def callback(update):
            updates.append(update)

        with patch.object(builder, "_fetch_assets", return_value=assets):
            with patch.object(builder, "_get_current_prices", return_value={"AAPL": 150.0}):
                with patch.object(builder, "_compute_dollar_volumes", return_value={"AAPL": 100_000_000}):
                    with patch.object(builder, "_fetch_sectors_from_fmp", return_value={"AAPL": "Technology"}):
                        result = builder.build_universe("large_cap", progress_callback=callback)

        # Should receive at least prices and liquidity updates
        steps = [u["step"] for u in updates]
        assert "prices" in steps
        assert "liquidity" in steps
        assert "sectors" in steps
```

- [ ] **Step 2: Run new tests**

Run: `python3 -m pytest tests/test_universe_builder.py::TestProgressCallback -v`
Expected: All 3 tests pass

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest tests/test_universe_builder.py -v`
Expected: All tests pass (no regressions)

- [ ] **Step 4: Commit**

```bash
git add tests/test_universe_builder.py
git commit -m "test: add progress callback invocation tests"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run all existing tests**

```bash
python3 -m pytest tests/test_universe_builder.py tests/test_trend_screener.py -v
```
Expected: All tests pass

- [ ] **Step 2: Dry-run trend screener discovery**

Since live discovery requires Alpaca/FMP API keys and takes 4+ minutes, verify the import path:

```bash
python3 -c "from traderlib.universe_builder import UniverseBuilder, ProgressUpdate, PROGRESS_STEP_PRICES, PROGRESS_STEP_LIQUIDITY; from traderlib.sector_resolver import SectorResolver, PROGRESS_STEP_SECTORS; print('Imports OK')"
```
Expected: `Imports OK`

- [ ] **Step 3: Check backward compatibility**

```bash
python3 -c "from traderlib.universe_builder import UniverseBuilder; b = UniverseBuilder(); print('No callback required:', 'OK')"
```
Expected: `No callback required: OK` (no TypeError from missing positional args)

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "feat: discovery progress indicators complete"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] TypedDict callback interface — Task 1
- [x] Step constants (`PROGRESS_STEP_PRICES`, `PROGRESS_STEP_LIQUIDITY`, `PROGRESS_STEP_SECTORS`) — Task 1, 5
- [x] Batch-level progress in `_get_current_prices()` — Task 2
- [x] Chunk-level progress in `_compute_dollar_volumes()` — Task 3
- [x] Fallback progress notices — Tasks 2, 3
- [x] Time-throttled FMP progress (2s) — Task 5
- [x] Final emit on completion — Task 5
- [x] Propagation through `build_universe()`/`load_universe()` — Task 4
- [x] Propagation through `_fetch_sectors_from_fmp()` — Task 4
- [x] Trend screener integration (print callback) — Task 6
- [x] Backward compatibility (optional params) — all tasks
- [x] Test coverage (mock callback assertions) — Task 7

**2. Placeholder scan:**
- [x] No "TBD", "TODO", or "implement later"
- [x] No vague "add error handling" without specifics
- [x] No "similar to Task N" — each task is self-contained
- [x] Complete code blocks in every step

**3. Type consistency:**
- [x] `ProgressCallback` used everywhere (or compatible `Dict[str, any]` in sector_resolver to avoid circular imports)
- [x] `Optional[ProgressCallback]` with default `None` everywhere
- [x] Method signatures in tests match actual signatures

---

## Rollback

If issues arise, individual commits can be reverted:
- `git revert HEAD` (trend screener callback)
- `git revert HEAD~1` (sector resolver callback)
- `git revert HEAD~2` (build_universe propagation)
- `git revert HEAD~3` (_compute_dollar_volumes callback)
- `git revert HEAD~4` (_get_current_prices callback)
- `git revert HEAD~5` (TypedDict + constants)

All changes are additive and isolated per file.
