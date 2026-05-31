# Design Spec: Sync Merge Fix + Minimal State Audit Logging

**Date:** 2026-05-30
**Author:** Claude (revised after independent architect review)
**Status:** Implemented — 2026-05-30

---

## Background

The NXT position corruption (May 15–29, 2026) happened because `_sync_with_alpaca()` replaced an existing position with a brand new object, destroying `initial_stop_price`, `entry_date`, and `scale_out_history`. The reconstruction used watchlist data — a living technical level — for immutable entry facts.

An independent architect review concluded: logging the destruction is theater, not engineering. The correct fix is to **merge** instead of **replace**.

---

## Goal

1. **Fix the sync loop** so it updates mutable fields (shares, current stop) while preserving immutable entry facts.
2. **Add minimal audit logging** so the next time state diverges from the broker, there is a forensic record — not 800 lines/day of noise.

---

## Design: Part 1 — Sync Merge Fix

### Current Behavior (Bug)

In `scripts/paper_engine_alpaca.py`, when `sync_result['added']` contains a ticker, the sync loop creates a **brand new `Position` object** and assigns it:

```python
self.state.positions[ticker] = position   # DESTROYS existing object and all its fields
```

This overwrites:
- `initial_stop_price` → watchlist stop (wrong)
- `entry_date` → `datetime.now()` (wrong)
- `scale_out_history` → `[]` (wrong)
- `entry_price` → Alpaca `avg_entry_price` (correct, but unnecessary overwrite)
- `shares` → Alpaca `qty` (correct)

### New Behavior

The sync loop checks `self.state.positions` **before** deciding whether to create or update:

```
if ticker in self.state.positions:
    # MERGE: update only mutable fields
    existing = self.state.positions[ticker]
    existing.shares = pos['qty']
    existing.stop_price = stop_price          # Current watchlist stop
    existing.target_price = target_price       # May have updated
    existing.current_stop_type = new_stop_type
    self.state.save_state()
    log: [INFO] SYNC_MERGE: ticker={T}, shares={N}, stop={P} (immutable fields preserved)
else:
    # CREATE: truly new position, no local history
    position = Position(...)
    self.state.positions[ticker] = position
    log: [WARNING] SYNC_NEW: ticker={T}, data_source={watchlist|unsynced}, initial_stop={P}
```

### What This Prevents

| Field | Before (Replace) | After (Merge) |
|-------|------------------|---------------|
| `initial_stop_price` | Overwritten with watchlist stop | **Preserved** |
| `entry_date` | Overwritten with today | **Preserved** |
| `scale_out_history` | Wiped to `[]` | **Preserved** |
| `entry_price` | Overwritten with Alpaca avg | **Preserved** (or updated if avg changed) |
| `shares` | Updated from Alpaca | Updated from Alpaca |
| `stop_price` | Updated from watchlist | Updated from watchlist |

### Edge Case: What if `positions.json` failed to load and local state is truly empty?

If `_load_state()` silently swallowed an error and started with an empty `positions` dict, `existing` will be `None`. The sync loop falls through to `CREATE`. The position is rebuilt with best-available data. This is the current behavior — the only difference is that it is now **logged** as a new reconstruction, not silently masked.

The merge fix does not solve the root cause of file load failures. It solves the symptom: the sync loop making a bad situation worse by destroying what little state remained.

---

## Design: Part 2 — Minimal State Audit Logging

### Philosophy

Log only anomalies and state transitions. Do not log every 30-second sync heartbeat. A product manager should be able to read the log in under 30 seconds and know if something is wrong.

### Log Types

#### 1. `STATE_LOAD` (once per engine startup)

```
[INFO] STATE_LOAD: positions={N}, tickers=[...], file_size={bytes}
[WARNING] STATE_LOAD_EMPTY: file_exists={bool}, file_size={bytes}, starting_fresh={bool}
[ERROR] STATE_LOAD_FAIL: error={type}, file={path}
```

**Purpose:** Detect if the engine started with missing or empty state. This is the chokepoint where positions disappear.

#### 2. `STATE_SAVE_VERIFY` (once per save, lightweight)

```
[INFO] STATE_SAVE_VERIFY: positions={N}, file_size={bytes}, ok={bool}
[WARNING] STATE_SAVE_VERIFY_FAIL: memory_positions={N}, file_positions={M}, diff={list}
```

**Purpose:** Detect if `save_state()` wrote fewer positions than it had in memory. Not a full field-by-field comparison — just counts. Fast: re-reads a file that is already in disk cache.

#### 3. `SYNC_MERGE` / `SYNC_NEW` (only when sync finds a position)

```
[INFO] SYNC_MERGE: ticker={T}, shares={N}, stop={P} (immutable fields preserved)
[WARNING] SYNC_NEW: ticker={T}, data_source={watchlist|unsynced|trade_log}, initial_stop={P}
```

**Purpose:** Distinguish between "Alpaca has a position we already track" (merge) and "Alpaca has a position we've never seen" (new). The `SYNC_NEW` line is the red flag — it means local state was lost or the position was opened externally.

#### 4. `INTEGRITY_TRADE_LOG` (once per startup, after load)

```
[WARNING] INTEGRITY_TRADE_LOG: ticker={T}, last_entry={date}, missing_from_state={bool}
```

**Purpose:** Cross-reference the trade log with loaded positions. If the trade log has an `ENTRY` for NXT on May 14 but `positions.json` has no NXT, flag it.

### Log Volume Estimate

| Event | Frequency | Lines |
|-------|-----------|-------|
| `STATE_LOAD` | 1/day | 1 |
| `STATE_SAVE_VERIFY` | ~15–30/day | 15–30 |
| `SYNC_MERGE` | Rare (only when Alpaca has more than local) | 0–2 |
| `SYNC_NEW` | Rare (new external positions) | 0–1 |
| `INTEGRITY_TRADE_LOG` | 1/day | 0–1 per missing ticker |
| **Total** | | **~20–35 lines/day** |

This is a **25× reduction** from the previous spec's 800+ lines/day.

---

## Design: Part 3 — Alerting Integration

The `TradingExceptionHandler` already exists. We extend it with a new severity concept: `OPERATIONAL_ANOMALY`. This is not an exception — it is a state divergence that requires human attention.

When any of the following fire, a notification hook (optional) can send a message:

- `STATE_LOAD_EMPTY` — engine started with no positions
- `STATE_SAVE_VERIFY_FAIL` — save wrote fewer positions than memory had
- `SYNC_NEW` on a ticker that has a trade log entry — local state was lost
- `INTEGRITY_TRADE_LOG` — trade log has an entry but state file does not

**Default behavior:** Log to file and console. No external notifications unless the user configures them.

---

## Implementation Plan (High-Level)

1. **Modify `_sync_with_alpaca()` in `paper_engine_alpaca.py`**
   - Check `if ticker in self.state.positions` before deciding merge vs create.
   - Merge path: update `shares`, `stop_price`, `target_price`, `current_stop_type`.
   - Create path: unchanged logic, but add `SYNC_NEW` log line.
   - Add `SYNC_MERGE` log line on merge.

2. **Add `STATE_LOAD` and `STATE_LOAD_EMPTY` to `_load_state()` in `paper_state.py`**
   - Log file size, existence, and parsed position count.
   - Log empty-start conditions.
   - Wrap load error in `STATE_LOAD_FAIL`.

3. **Add `STATE_SAVE_VERIFY` to `save_state()` in `paper_state.py`**
   - After `_atomic_write_json`, re-read the file.
   - Compare `len(json.load(f))` to `len(self.positions)`.
   - Log `ok` or `diff`.

4. **Add `INTEGRITY_TRADE_LOG` to `_load_state()` in `paper_state.py`**
   - After loading positions, scan `trades.jsonl` for `ENTRY` events.
   - Build set of tickers with entries but no loaded position.
   - Log each missing ticker.

5. **Extend `TradingExceptionHandler`** (optional, if needed)
   - Add `log_operational()` method for non-exception events.
   - Or use the existing logger directly with a new `trading.ops` channel.

6. **Test**
   - Unit test: simulate sync with existing position, verify `initial_stop_price` survives.
   - Unit test: simulate sync with missing position, verify `SYNC_NEW` fires.
   - Unit test: simulate save with 2 positions, corrupt file to 1, verify `STATE_SAVE_VERIFY_FAIL` fires.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Merge path introduces a bug in the sync loop | The merge path only touches 4 mutable fields. It does not touch `initial_stop_price`, `entry_date`, `scale_out_history`, or `entry_price`. A unit test proves immutability is preserved. |
| Post-save verification reads a file that may be locked | Use a non-blocking read. If the file is locked, skip verification and log `STATE_SAVE_VERIFY_SKIP`. |
| Trade log scan on startup is slow | Only scan for tickers with `ENTRY` events. On a 6-month log (~10K lines), this is sub-millisecond in Python. |
| `SYNC_NEW` floods logs if Alpaca has many external positions | Rate-limit: if more than 3 `SYNC_NEW` events fire in a single sync cycle, switch to a single summary line: `SYNC_NEW_MULTIPLE: count={N}, tickers=[...]`. |

---

## Success Criteria

- [x] `_sync_with_alpaca()` merges instead of replaces existing positions.
- [x] After a merge, `initial_stop_price`, `entry_date`, and `scale_out_history` are unchanged.
- [x] `SYNC_NEW` fires when a position is truly new (no local record).
- [x] `STATE_LOAD_EMPTY` fires when the engine starts with no positions.
- [x] `STATE_SAVE_VERIFY_FAIL` fires when a save writes fewer positions than memory had.
- [x] `INTEGRITY_TRADE_LOG` fires when a trade log entry exists but no loaded position.
- [x] Log volume stays under ~50 lines/day during normal operation.
- [x] All log emissions are wrapped in `try/except` so a logging failure never crashes the engine.

---

## Notes

- This spec replaces the previous `2026-05-30-operational-state-logging-design.md`.
- The merge fix is the primary deliverable. Logging is secondary and minimal.
- The user is a product manager. All log messages are human-readable without code knowledge.
- No new files or CLI commands. All changes are within existing modules.
