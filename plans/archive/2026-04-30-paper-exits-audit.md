# paper_exits.py Audit — Math Flaws, Hardcoded Values, Logical Inconsistencies

**File:** `traderlib/paper_exits.py` (742 lines)
**Date:** 2026-04-30
**Verified:** 2026-04-30 — all claims confirmed, line numbers corrected
**Scope:** `ExitEngine` class — exit logic, position sizing, stop/target math
**Status:** ✅ ALL 10 ISSUES RESOLVED — shipped in v0.6.15.27 + v0.6.15.28

---

## Critical Logic Bugs

### 1. Trailing stop `elif` chain blocks lower-tier protection (HIGH) ✅ FIXED v0.6.15.27
**Lines:** `evaluate_exit` 267-283, `evaluate_exit_action` 421-437

At `+3R`, the code checks `if ema21 > current_stop`. If `False`, it drops through — never checking EMA10 or breakeven. A position at `+5R` could sit on its initial stop if EMA21 hasn't crossed above it, instead of being protected by breakeven at minimum.

```python
# Lines 267-283 (identical at 421-437):
if r_multiple >= ema21_r and ema21 is not None:
    if ema21 > current_stop:
        new_stop = ema21
elif r_multiple >= ema10_r and ema10 is not None:  # NEVER checked if r >= ema21_r
    ...
```

**Fix:** Flatten or nest so higher-R positions still get lower-tier protection when the higher EMA hasn't caught up.

---

### 2. Cache age uses `.seconds` instead of `.total_seconds()` (HIGH) ✅ FIXED v0.6.15.27
**Line:** `_get_cached_data` 127

```python
(now - self.cache_timestamp).seconds
```

Wraps at 86400. A cache older than 1 day appears fresh.

**Fix:** Use `.total_seconds()`.

---

### 3. `evaluate_exit` ignores trailing engine (HIGH) ✅ FIXED v0.6.15.27
**Line:** `evaluate_exit` 197 vs `evaluate_exit_action` 339

When `self.risk_config.profit_target.mode` is `trailing` or `hybrid`, `evaluate_exit_action` delegates to `TrailingExitEngine` at line 339, but `evaluate_exit` does not — it always uses the old elif-chain logic. Calling both on the same position yields different decisions.

**Fix:** Deprecate `evaluate_exit` and route all calls through `evaluate_exit_action`, or have `evaluate_exit` call `evaluate_exit_action` internally.

---

### 4. Profit target exit uses config `min_r`, not entry `min_r` (HIGH)
**Lines:** `evaluate_exit` 290, `evaluate_exit_action` 444

```python
min_r = self.risk_config.profit_target.min_r_multiple if self.risk_config else 2.0
if current_price >= target_price or r_multiple >= min_r:
```

Exit logic checks `self.risk_config.profit_target.min_r_multiple`. If entry used `3R` but config says `2R`, position exits at `2R` even though target was set at `3R`.

**Fix:** Check `r_multiple >= position.target_r_multiple` instead of config value, or compute target with the same min_r that will be checked on exit.

---

### 5. Fallback position sizing forces a trade (HIGH)
**Line:** `calculate_position_size` 702

```python
return max(shares, 10)
```

Main path (`calculate_position_size_with_constraints`) returns `0` when constraints reject. Fallback does `return max(shares, 10)` — if risk math says 0 or 3 shares, it still buys at least 10.

**Fix:** Return `0` in fallback when `shares < 10`, consistent with main path.

---

## Medium Issues

### 6. Global cache TTL is per-session, not per-ticker (MED)
**Line:** `_get_cached_data` 99, 143

`cache_timestamp` (line 99) is a single timestamp. Fetch TSLA at t=0, then AAPL at t=4min, then check AAPL at t=6min: cache not cleared because most recent fetch was only 2min ago, even though TSLA data is 6min old.

**Fix:** Use per-ticker timestamps: `self.price_cache[ticker]['timestamp'] = now`.

---

### 7. `get_position_summary` uses current stop for R-multiple (MED)
**Line:** `get_position_summary` 480

```python
initial_stop = position.stop_price  # CURRENT stop, possibly trailed
```

Meanwhile `evaluate_exit` (line 224) and `evaluate_exit_action` (line 382) use `getattr(position, 'initial_stop_price', None)`. For trailed positions, summary computes a different (lower) R-multiple.

**Fix:** Use `getattr(position, 'initial_stop_price', position.stop_price)` for consistency.

---

### 8. Position mutation in supposedly read-only method (MED)
**Line:** `evaluate_exit_action` 363-364

```python
if hasattr(position, 'record_scale_out') and result.trigger_r is not None:
    position.record_scale_out(result.trigger_r)
```

The trailing-engine path mutates the position. The old-logic path is documented as "no mutation — caller applies." The contract should be consistent.

**Fix:** Do not mutate position in exit evaluation. Return scale-out info and let caller apply.

---

## Low Issues

### 9. yfinance path stricter than injected data path (LOW)
**Line:** `_get_cached_data` 107-109

```python
if len(hist) < 50:
    return None
```

Requires 50 bars before storing data, but `_get_ema_values` with injected data only needs `ema_long_period` (default 21). Live data gets stricter validation than backtests.

**Fix:** Use `ema_long_period` instead of hardcoded `50`.

---

### 10. EMA column names hardcoded to `EMA10`/`EMA21` (LOW)
**Lines:** `_get_cached_data` 140-141, `_get_ema_values` 195

```python
hist['EMA10'] = hist['Close'].ewm(span=ema_short, adjust=False).mean()
hist['EMA21'] = hist['Close'].ewm(span=ema_long, adjust=False).mean()
# ...
return hist['EMA10'].iloc[-1], hist['EMA21'].iloc[-1]
```

Columns always named `EMA10`/`EMA21` even when config sets different periods. Functionally works but confusing and brittle.

**Fix:** Use `f"EMA{ema_short}"` and `f"EMA{ema_long}"` for column names.

---

## Hardcoded Values

| Location | Line | Value | Should Come From |
|---|---|---|---|
| `calculate_initial_stop` (recent low) | 299 | `tail(10)` | Configurable lookback window |
| `calculate_initial_stop` (stop bounds) | 626-629 | `0.97` / `0.85` | `risk_config.stop_loss.min/max_stop_distance_pct` |
| `calculate_position_size` fallback | 698 | `0.0075` | `risk_config.account.risk_per_trade_pct` |
| `calculate_position_size` fallback | 702 | `max(shares, 10)` | `0` (rejects tiny size, consistent with main path) |
| `evaluate_exit` / `evaluate_exit_action` | 290, 444 | `min_r = 2.0` default | Should match `position.target_price` entry-level min_r |
| `_get_cached_data` min bars | 107 | `50` days minimum | Should be `ema_long_period` |

---

## Summary Table

| Severity | Issue | Lines | Action |
|---|---|---|---|
| HIGH | elif chain blocks lower-tier trailing | 267-283, 421-437 | Flatten nested logic |
| HIGH | Cache age `.seconds` wraps at 86400 | 127 | Use `.total_seconds()` |
| HIGH | `evaluate_exit` ignores trailing engine | 197 vs 339 | Route through `evaluate_exit_action` |
| HIGH | Exit checks config min_r not entry min_r | 290, 444 | Store/verify entry-level min_r |
| HIGH | Fallback sizing forces a trade | 702 | Return 0 for rejected sizes |
| MED | Cache TTL is global not per-ticker | 99, 143 | Per-ticker timestamps |
| MED | `get_position_summary` R-multiple drift | 480 | Use `initial_stop_price` |
| MED | Position mutation in exit eval | 363-364 | Return info, don't mutate |
| LOW | yfinance path needs 50 bars | 107 | Use `ema_long_period` |
| LOW | Column names hardcoded | 140-141, 195 | Dynamic naming |

---

## Test Recommendation

- Add unit tests for the `elif` trailing chain: verify that at `+3R` with `ema21 < current_stop`, breakeven or EMA10 still gets applied.
- Test `calculate_position_size` with `risk_per_share > entry_price` (returns 0, not 10).
- Test cache after 24h+ interval to catch `.seconds` wrap.
- Verify `evaluate_exit` and `evaluate_exit_action` return identical results for the same position.
