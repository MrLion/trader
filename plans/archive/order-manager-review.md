---
name: Order Manager Code Review — Hardcoded Values & Logical Issues
description: Audit of traderlib/order_manager.py for hardcoded math, magic numbers, and logical inconsistencies
type: project
---

## Hardcoded Values

### 1. Absolute path with username — line 144 ✅ FIXED 2026-04-30
```python
# Before:
default_data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
# After:
default_data_dir = Path(__file__).resolve().parent.parent / 'data'
```
Now derived from project root instead of hardcoded username path.

### 2. Default `max_tps: float = 2.0` — line 126
Reasonable default; only configurable at construction time.

### 3. Queue polling interval `timeout=0.5` — line 174
Polls queue twice per second even when idle. Event-driven or longer timeout would reduce CPU waste.

## Logical Inconsistencies

### 1. TPS rate limiting bypassed for direct submissions — BUG (lines 251-255, 319-322)

`_can_submit_directly()` checks `last_submit_time` inside the lock, but direct submissions never update `last_submit_time` — only `_process_queue` does (line 185). After a direct submission, the next caller also passes the check and submits directly, completely bypassing the rate limit.

Additionally, the check and submission happen outside a shared critical section — two callers can both pass `_can_submit_directly()` then submit back-to-back.

### 2. `submit_entry` missing telemetry params — lines 297-302 ✅ FIXED 2026-04-30

Added `pivot_type` and `entry_mode` optional params to `submit_entry()`, `_submit_entry_to_alpaca()`, and the queued-order path. Market entries now track technique/entry-mode the same as stop entries.

### 3. `close_position` ignores `shares` — line 570 ✅ FIXED 2026-04-30

Replaced `self.alpaca.close_position(ticker)` with `self.alpaca.submit_market_order(ticker, shares, 'sell')` so partial exits (e.g., hybrid mode scaling out at 3R) work correctly instead of liquidating the entire position.

### 4. No positive `shares` validation — lines 297, 384, 523 ✅ FIXED 2026-04-30

Added `if shares <= 0: raise ValueError(...)` guards to `submit_entry()`, `submit_stop_entry()`, and `submit_exit()`.

## Summary

| Severity | Issue | Status |
|:---------|:------|:-------|
| Critical | `close_position` ignores partial exit intent | ✅ Fixed |
| Medium | Hardcoded user path | ✅ Fixed |
| Medium | No qty > 0 validation | ✅ Fixed |
| Medium | `submit_entry` missing telemetry params | ✅ Fixed |
| Low | TPS bypassed for direct submissions | Open |
