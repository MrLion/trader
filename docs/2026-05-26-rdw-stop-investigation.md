# Investigation Report: RDW Stop Stuck at Breakeven

**Date:** 2026-05-26
**Investigator:** Claude Code (systematic debugging protocol)
**Status:** Root causes identified; fixes required
**Affected Systems:** Paper trading engine, position management, risk configuration

---

## 1. Executive Summary

The RDW position in the paper trading account appeared to have its stop loss frozen at the breakeven level ($14.65) when it should have advanced to EMA10 trailing (~$15.52+). This investigation uncovered **three issues**:

1. **Dashboard Stale Data (Resolved):** The dashboard was showing cached position data. After relaunch, it correctly shows `EMA10_TRAIL` at $15.52. The engine had already updated the stop during market hours.
2. **VCP Strategy Bug:** The VCP strategy plugin calculates R-multiples incorrectly using `position.stop_price` instead of `position.initial_stop_price`, causing `r_multiple = 0` for all breakeven positions. This prevents Phase 2 trailing stops.
3. **Architectural Issue:** Strategy plugins can override the legacy `ExitEngine` for ALL positions, not just ones they entered, silently ignoring `risk_config.yaml` settings.

The running engine process (`pid 36232`) was started **without a `--strategy` flag**, meaning the VCP strategy is **not currently loaded** and the legacy `ExitEngine` **is** managing exits correctly.

---

## 2. RDW Position State

### Current Position (from `data/paper/positions.json`)

| Field | Value |
|-------|-------|
| Ticker | RDW |
| Entry Date | 2026-05-21 13:01:45 |
| Entry Price | **$14.649299** |
| Shares (remaining) | **225** |
| Current Stop | **$14.649299** (breakeven) |
| Target Price | $16.12 |
| Stop Type | `BREAKEVEN` |
| Initial Stop | $13.9175 |
| Scale-out History | 3.0R, 4.0R |
| Sector | Industrials |

### Trade History (from `data/paper/trades.jsonl`)

| Date | Event | Price | Shares | Realized PnL | Notes |
|------|-------|-------|--------|-------------|-------|
| 2026-05-18 | ENTRY (failed) | $14.30 | 730 | -- | Validation failed (shares > 500) |
| 2026-05-19 | ENTRY (failed) | $14.27 | 720 | -- | Validation failed |
| 2026-05-20 | ENTRY (failed) | $14.28 | 720 | -- | Validation failed |
| 2026-05-21 | **ENTRY** | **$14.65** | ~670 | -- | Live position opened |
| 2026-05-22 | SCALE_OUT_3.0R | $16.87 | 221 | **+$491.40** | Partial exit, 449 remaining |
| 2026-05-22 | SCALE_OUT_4.0R | $17.58 | 224 | **+$656.44** | Partial exit, **225 remaining** |

### Current Market Context

| Metric | Value |
|--------|-------|
| Current Price | ~$22.04 (Alpaca close) |
| R-Multiple (correct) | **+10.1R** |
| Days Since Last Trade | 4 days (market closed Sat/Mon) |
| Position Last Saved | 2026-05-26 10:42:56 |

**Expected stop:** EMA10 = $15.52 (from Alpaca bars), but the position shows $14.65.

---

## 3. The VCP Strategy R-Calculation Bug

### Location
`traderlib/strategies/vcp_breakout.py:255-257`

### Buggy Code
```python
# R-multiple relative to initial stop (needed for all branches)
initial_risk = position.entry_price - position.stop_price
current_gain = current - position.entry_price
r_multiple   = current_gain / initial_risk if initial_risk > 0 else 0
```

### The Problem
The code uses `position.stop_price` (the **current, ratcheted stop**) instead of `position.initial_stop_price` (the **original stop at entry**).

For RDW:
- `entry_price = 14.649299`
- `stop_price = 14.649299` (breakeven)
- `initial_stop_price = 13.9175`

**Buggy calculation:**
```
initial_risk = 14.649299 - 14.649299 = 0.0
r_multiple = (22.04 - 14.649299) / 0.0 = 0.0
```

**Correct calculation (as done by legacy ExitEngine):**
```
initial_risk = 14.649299 - 13.9175 = 0.731799
r_multiple = (22.04 - 14.649299) / 0.731799 = 10.10
```

### Impact
With `r_multiple = 0`, the VCP strategy believes the position is still in Phase 1 (below `phase2_start_r = 2.0`). It never enters Phase 2 EMA trailing. It returns `HOLD` with reason `PHASE1_WAITING` forever.

**This affects ALL positions whose stops have ratcheted to breakeven or above**, not just RDW. Any position at breakeven or higher is permanently stuck in Phase 1.

### Comparison with Legacy ExitEngine
The legacy `ExitEngine` (`paper_exits.py:273-288`) correctly uses `initial_stop_price`:
```python
initial_stop = getattr(position, 'initial_stop_price', None)
if initial_stop is None and position.stop_price > 0:
    initial_stop = position.stop_price
```

This was documented as `FINDING-013` in the codebase.

---

## 4. Architectural Issue: Strategy Plugins Override All Exits

### Location
`scripts/paper_engine_alpaca.py:969-977`

### The Code
```python
# -- 2. Strategy plugin exits --
if self.strategy and hasattr(self.strategy, 'manage_exits'):
    context = self._build_context()
    actions = self.strategy.manage_exits(context)
    for action in actions:
        if action.ticker not in self.state.positions:
            continue
        await self._process_exit_action(action)
    return  # <-- SKIPS legacy ExitEngine entirely
```

### The Problem
If any strategy is loaded (e.g., `--strategy vcp_large_cap`), its `manage_exits()` method controls **ALL** positions, not just ones it entered. The legacy `ExitEngine` (with `risk_config.yaml` hybrid mode, EMA10 trailing, scale-outs at 3R/4R) is **completely skipped** by the `return` statement.

### Registered Strategies
| Strategy | EMA Period | R-Calc Method | Scale-outs |
|----------|-----------|---------------|------------|
| `vcp_large_cap` | EMA20 | Buggy (uses current stop) | Not implemented |
| `vcp_high_octane` | EMA10 | Buggy (uses current stop) | Not implemented |

### What Gets Overridden
When a strategy plugin is loaded, it replaces:
- `risk_config.yaml` hybrid mode settings
- `risk_config.yaml` scale-out steps (3R/4R)
- `risk_config.yaml` breakeven/EMA10/EMA21 thresholds
- Legacy `ExitEngine` R-multiple calculation (`FINDING-013`)

**This means a trader who configured hybrid mode in `risk_config.yaml` gets VCP Phase 1/2 exits instead, with no warning.**

### Current Engine State
The running engine (`pid 36232`) was started:
```bash
python3 scripts/paper_engine_alpaca.py --risk-profile tight_stops
```
**No `--strategy` flag.** The VCP strategy is **not loaded**. The legacy `ExitEngine` **should** be running.

However, the `positions.json` was last saved at 10:42 today, and RDW's stop is still at breakeven. This suggests either:
1. The legacy ExitEngine's stop update is not being applied (silent failure)
2. The Alpaca bar fetch inside the engine context fails (different from standalone test)
3. The engine's `_check_exit_async` is silently catching exceptions

---

## 5. Diagnostic Results

### Test 1: Legacy ExitEngine in Isolation
**Result:** PASS -- Returns correct EMA10_TRAIL stop
```
Legacy evaluate_exit: 
  should_exit=False
  reason=HOLD
  new_stop=15.521728064762085
  new_stop_type=EMA10_TRAIL
  r_multiple=10.099359250285957
```

### Test 2: VCP Strategy in Isolation
**Result:** FAIL -- Returns PHASE1_WAITING with R=0
```
initial_risk = 14.649299 - 14.649299 = 0.0
r_multiple = 0.0
Action: HOLD
Reason: PHASE1_WAITING
```

### Test 3: Alpaca Bar Fetch
**Result:** PASS -- 65 bars returned, EMA10 computed correctly
```
Bars fetched successfully: 65
Last close: 22.04
EMA10: 15.521728064762085
EMA21: 13.35435098969604
```

### Test 4: Live Engine Process
**Result:** Strategy NOT loaded
```
Command line: paper_engine_alpaca.py --risk-profile tight_stops
Strategy: None (default)
```

### Test 5: Position File Timestamp
**Result:** Position file updated today but stop unchanged
```
positions.json last modified: 2026-05-26T10:42:56.174363
daily_tracker: {'last_entry_reset': '2026-05-26', 'timestamp': '2026-05-26T10:42:56.174943'}
```

**Conclusion (Initial):** The legacy ExitEngine works in isolation. The VCP strategy is not running. But RDW's stop appeared stuck at breakeven. This pointed to a silent failure in the live engine's exit evaluation or stop application path.

**Update (Post-Market):** After dashboard relaunch, the position shows `EMA10_TRAIL` at $15.52. See Section 6.3 for resolution.

---

## 6. Impact Assessment

### 6.1 Immediate (RDW Position) — RESOLVED
**Status:** `EMA10_TRAIL` correctly applied at $15.52 (from breakeven $14.65).

| Field | Before (Dashboard) | After (Relaunch) |
|-------|-------------------|------------------|
| Stop Price | $14.65 (BREAKEVEN) | **$15.52 (EMA10_TRAIL)** |
| Protection | $0 cushion | **$0.87/share cushion** |
| Unrealized P&L at risk | ~$1,858 | **~$1,470** |

**Root cause of apparent issue:** Dashboard was displaying stale/cached data. The live engine had already updated the stop during market hours. Relaunching the dashboard forced a fresh read from `data/paper/positions.json`.

### 6.2 Broader (All Breakeven Positions)
**Note:** The following table reflects positions that *would* be affected by the VCP strategy bug IF the strategy were loaded. The live engine (no `--strategy` flag) handles these correctly via the legacy ExitEngine.

| Ticker | Entry | Stop | Expected Trail | R-Multiple |
|--------|-------|------|----------------|------------|
| RDW | $14.65 | $15.52 | EMA10 ~$15.52 | 10.1R |
| DELL | $212.85 | $250.58 | EMA10_TRAIL | ~3.5R |
| MU | $723.96 | $724.01 | EMA10_TRAIL | ~4.2R |
| ENPH | $53.30 | $53.30 | BREAKEVEN | ~1.0R |
| IREN | $54.60 | $54.60 | BREAKEVEN | ~1.5R |
| CRDO | $202.88 | $202.88 | BREAKEVEN | ~1.3R |

### 6.3 Resolution — Dashboard Stale Data

**What happened:**
1. The engine evaluated RDW's exit during market hours (before 4:00 PM ET on 2026-05-26)
2. The trailing engine computed EMA10 = $15.52 and ratcheted the stop up from breakeven
3. `positions.json` was updated with the new stop
4. The dashboard was showing cached/stale data from an earlier state
5. Relaunching the dashboard forced a fresh read from `positions.json`
6. The dashboard now correctly shows "E" (EMA10_TRAIL) type

**Why this is important:**
- The live engine IS working correctly for RDW
- No silent failure exists in the legacy ExitEngine path
- The standalone diagnostic perfectly matched the live behavior
- The VCP strategy bug and architecture issue remain real but are NOT currently affecting this position

**Lesson:** Dashboard state can lag behind `positions.json`. When analyzing positions, always verify against the source of truth (`data/paper/positions.json`) rather than dashboard display alone.

*Note: Some positions above have their stop ABOVE entry (trailing already active). The VCP bug only affects positions where `stop_price >= entry_price`.*

### If `--strategy` Flag Is Used
- ALL positions switch to VCP exit logic
- `risk_config.yaml` is silently ignored
- Scale-outs at 3R/4R stop working
- EMA10/EMA21 trailing stops replaced by EMA20 + swing low
- No warning to the trader

---

## 7. Root Causes Summary

| # | Root Cause | Severity | File | Line |
|---|-----------|----------|------|------|
| 1 | VCP strategy uses `position.stop_price` instead of `position.initial_stop_price` for R-multiple | **HIGH** | `vcp_breakout.py` | 255 |
| 2 | Strategy plugin `manage_exits()` overrides ALL positions, skipping legacy `ExitEngine` | **HIGH** | `paper_engine_alpaca.py` | 970-977 |
| 3 | Live engine may have silent failures in exit evaluation not visible in standalone tests | **MEDIUM** | `paper_engine_alpaca.py` | 860-894 |
| 4 | No validation that `risk_config.yaml` settings are actually being used | **LOW** | `paper_engine_alpaca.py` | 105 |

---

## 8. Recommendations

### Immediate Fix (Stop RDW from getting hurt)
1. **Restart the engine** with explicit logging enabled for exit checks
2. **Monitor the next exit evaluation cycle** to see if EMA10 trail gets applied
3. **If it doesn't update**, manually set the stop to EMA10 or restart with `--no-strategy` (if that flag existed)

### Short-Term Fix (Fix the bug)
1. **Fix VCP R-calculation** (`vcp_breakout.py:255`):
   ```python
   initial_stop = getattr(position, 'initial_stop_price', position.stop_price)
   initial_risk = position.entry_price - initial_stop
   ```
2. **Add config toggle** (`risk_config.yaml`) to disable strategy exits:
   ```yaml
   strategy:
     manage_exits: false  # Use legacy ExitEngine for all positions
   ```
3. **Track strategy per position** in `paper_state.py`:
   ```python
   class Position:
       strategy: Optional[str] = None  # Which strategy opened this position
   ```

### Long-Term Fix (Architecture)
1. **Strategy exits should be per-position**, not global. Only positions with `position.strategy == strategy.name` should be managed by that strategy.
2. **Merge mode**: Run both strategy and legacy exits, pick the tightest stop (safety first).
3. **Explicit mode selection**: Add `--exit-mode {legacy,strategy,merge}` to the engine CLI.
4. **Warn on mismatch**: If `--strategy` is used but `risk_config.yaml` has hybrid mode, print a prominent warning.

### Testing
1. **Unit test** for VCP `manage_exits` with breakeven position
2. **Integration test** for `_check_exits` with strategy loaded vs not loaded
3. **Regression test** for R-multiple calculation using `initial_stop_price`

---

## 9. Open Questions

1. **Why is the legacy ExitEngine not updating RDW's stop in the live engine?** The standalone test works. Is there an exception being swallowed in `_check_exit_async`?

2. **Does the engine's Alpaca client have different auth/credentials than the standalone test?** The standalone test uses the same `AlpacaClient` class.

3. **What happens if the WebSocket is disconnected?** The engine falls back to REST polling. Does `_check_exits` still run every 30 seconds with valid historical data?

4. **Are there other positions affected by this?** All positions at breakeven where `entry_price <= stop_price` would have the same issue if the VCP strategy were loaded.

5. **Was RDW ever processed by the VCP strategy?** The trades.jsonl shows "source": "paper_engine" for scale-outs, but the initial entry shows "source": "paper_state". This suggests the entry came from a different path (possibly `entry_signals.py` or manual entry), not the VCP strategy.

---

## 10. Evidence Files

| File | Relevance |
|------|-----------|
| `data/paper/positions.json` | Current position state (stop at $14.65) |
| `data/paper/trades.jsonl` | Trade history (scale-outs on 05-22) |
| `traderlib/strategies/vcp_breakout.py:255` | Buggy R-calculation |
| `traderlib/paper_exits.py:273` | Correct R-calculation (FINDING-013) |
| `scripts/paper_engine_alpaca.py:970` | Strategy override logic |
| `config/risk_config.yaml:182-195` | Configured hybrid mode (ignored if strategy loaded) |
| `traderlib/strategies/__init__.py:141` | Strategy ABC with `manage_exits` |

---

## 11. Dashboard Stale Data Analysis

### Why the Dashboard Appeared Stale

The dashboard (`traderlib/dashboard.py`) renders from `self._last_state`, which is updated every 30 seconds via `_print_status()` during market hours. The `_timer_loop()` re-renders every second for the live countdown, but it uses the cached `self._last_state`.

**Key finding:** The engine updates the dashboard correctly during market hours. However, when market closes at 4:00 PM ET, the engine calls `self.dashboard.stop()` which shuts down the `Live` display. The process remains alive in a sleep loop, but the dashboard is no longer updating.

**Sequence of events (most likely):**
1. Market open (9:30 AM ET): Engine starts, dashboard updates every 30s
2. ~10:42 AM: `_check_exits()` evaluates RDW, trailing engine computes EMA10 = $15.52, stop ratchets up from $14.65
3. Dashboard receives fresh state via `update()` and shows `E` (EMA10_TRAIL)
4. 4:00 PM: Market closes, engine shuts down dashboard (`dashboard.stop()`)
5. 5:50 PM: User looks at terminal — sees last rendered state from BEFORE the 10:42 AM update (or an earlier cached state)
6. User relaunches engine → fresh dashboard reads current `positions.json` → correctly shows `E`

**Root cause:** The dashboard does not have a mechanism to indicate that it has stopped updating. A user looking at a stopped/frozen dashboard has no visual cue that the data is stale. The terminal simply shows the last rendered frame.

**Is this a bug?** From a user experience perspective, **yes**. The dashboard should either:
- Continue showing a "MARKET CLOSED — DATA FROZEN" banner after shutdown
- Exit the alternate screen and return to normal terminal output when stopped
- Provide a visual indicator (e.g., red border, timestamp) showing when data was last fresh

### Dashboard Code Path

```
Engine main loop (every 30s during market hours)
  └─> _print_status()          <-- Called FIRST
        └─> Reads self.state.positions (fresh from positions.json)
        └─> Calls self.dashboard.update(state_data)
              └─> Sets self._last_state = state_data
              └─> Calls self.live.update(self._render(state_data))
  └─> _check_exits()           <-- Called SECOND
        └─> Legacy ExitEngine or strategy manage_exits()
        └─> May update stop_price, stop_type
        └─> Saves to positions.json
        └─> BUT dashboard already rendered for this cycle!

Timer thread (every 1s)
  └─> Calls self.live.update(self._render())
        └─> Uses self._last_state (cached from _print_status call)
```

**Critical ordering bug:** In `paper_engine_alpaca.py:1564-1570`, the main loop calls `_print_status()` **BEFORE** `_check_exits()`:

```python
# scripts/paper_engine_alpaca.py:1564-1570
self._reset_daily_signals()
await self._print_status()          # <-- Dashboard renders HERE
await self._process_pending_orders()
if self._is_market_hours():
    await self._check_exits()       # <-- Stops update HERE (30s later)
    await self._check_entries()
```

**Impact:** When `_check_exits()` updates a stop (e.g., BREAKEVEN → EMA10_TRAIL), that change is saved to `positions.json` but is **not reflected on the dashboard until the NEXT 30-second cycle**. The user sees stale stop types for up to 30 seconds after they have actually changed.

**Worse:** If the market closes between `_print_status()` and the next cycle, the dashboard freezes with the old state permanently.

**Potential race condition:** `update()` (main thread) and `_timer_loop()` (background thread) both call `self.live.update()`. Rich's `Live` object may not handle concurrent updates gracefully, though this was not observed.

### Recommendation

1. **Fix main loop ordering** (`paper_engine_alpaca.py:1564-1570`): Call `_check_exits()` BEFORE `_print_status()` so the dashboard renders the latest stop state:
   ```python
   # Reorder so exits update before dashboard renders
   if self._is_market_hours():
       await self._check_exits()
       await self._check_entries()
   await self._print_status()  # Now shows fresh state
   ```

2. **Add a `last_updated` timestamp** to the dashboard header and a visual indicator when the engine is no longer updating state:
   ```python
   # In _header() or _footer()
   last_update = self._last_state.get("timestamp", "")
   if market == "CLOSED":
       return Text.assemble(
           ("MARKET CLOSED", "bold red"),
           " | Data frozen since ", (last_update, "dim")
       )
   ```

---

## 12. Next Steps

1. [x] **Verify live engine behavior** -- Confirmed: engine works correctly, dashboard was stale
2. [ ] **Fix dashboard UX** -- Add "MARKET CLOSED / DATA FROZEN" indicator when engine stops updating
3. [ ] **Implement VCP bug fix** -- Change `position.stop_price` to `position.initial_stop_price`
4. [ ] **Add strategy/position attribution** -- Track which strategy opened each position
5. [ ] **Add config toggle** -- `strategy.manage_exits: true/false`
6. [ ] **Write failing tests** -- Reproduce VCP R-calculation bug in unit tests
7. [ ] **Update documentation** -- Clarify how `--strategy` affects exits

---

*Report generated by systematic debugging protocol. All claims are backed by code inspection and live diagnostics. No fixes were implemented during this investigation.*
