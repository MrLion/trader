# Prevent Repeat Losing Trades — Same-Level Re-Entry Rejection

**Status:** Draft — for review  
**Date:** 2026-06-20  
**Scope:** `scripts/paper_engine_alpaca.py`, `traderlib/risk_config.py`, `config/paper/risk_config.yaml`

---

## Problem

MXL entered 3 times in 4 days at nearly identical prices ($91.91, $92.94, $92.70), all stopped out. Total losses: $1,154. The engine has no mechanism to recognize that a stock keeps failing at the same level — it re-enters the same setup at the same price and gets the same result.

---

## Design

### Same-level re-entry rejection

If a new entry price is within X% of a previous stopped-out entry, reject the trade. The setup hasn't changed, so the result won't either. This directly prevents the MXL pattern — three entries within $1 of each other.

Key behaviors:
- **Loss stores the entry price** — when a trade is stopped out, the entry price is remembered for that ticker
- **Profit clears the memory** — a realized win means the level works now, so the block is lifted. Mirrors the existing `consecutive_losses` profit-reset pattern
- **Memory has a time window** — stopped entries expire after N days so a stock isn't permanently blocked from a level
- **Independent of cooldown system** — uses its own state, not shared with `consecutive_losses` or `last_exit_time`. No coupling, no lifecycle conflicts

---

## Changes

### A. Configuration (`traderlib/risk_config.py` + `config/paper/risk_config.yaml`)

Add two new settings to `CooldownConfig`:

```python
# Reject re-entry if new entry price is within this % of a previous stopped-out entry
# 0.0 = disabled
same_level_rejection_pct: float = 2.0  # within 2% of previous stopped entry

# How long to remember stopped-out entry prices for same-level check (in minutes)
stopped_entry_memory_minutes: int = 4320  # 3 trading days
```

Add corresponding YAML to `config/paper/risk_config.yaml` under `cooldown:`

### B. Engine — same-level rejection (`scripts/paper_engine_alpaca.py`)

#### B1. Track stopped-out entry prices

Add `self.stopped_entries: Dict[str, List[Tuple[datetime, float]]]` — maps ticker to list of (exit_time, entry_price) for stopped-out trades.

#### B2. Check same-level on entry

In `_execute_entry()`, after the cooldown check (line 1129), add:

```python
# Check same-level rejection
same_level_pct = self.risk_config.cooldown.same_level_rejection_pct
if same_level_pct > 0:
    memory_cutoff = datetime.now() - timedelta(
        minutes=self.risk_config.cooldown.stopped_entry_memory_minutes)
    for exit_time, prev_entry_price in self.stopped_entries.get(ticker, []):
        if exit_time < memory_cutoff:
            continue  # Too old, skip
        price_diff_pct = abs(entry_price - prev_entry_price) / prev_entry_price * 100
        if price_diff_pct <= same_level_pct:
            print(f"   ⛔ {ticker}: Rejected — entry ${entry_price:.2f} within {same_level_pct:.1f}% of previous stopped entry ${prev_entry_price:.2f}")
            return
```

#### B3. Record stopped-out entries

Extract a `_prune_stopped_entries(ticker)` helper to avoid repeating the memory-window cutoff in multiple places:

```python
def _prune_stopped_entries(self, ticker: str):
    """Remove stopped entries older than the memory window."""
    memory_cutoff = datetime.now() - timedelta(
        minutes=self.risk_config.cooldown.stopped_entry_memory_minutes)
    self.stopped_entries[ticker] = [
        (t, p) for t, p in self.stopped_entries.get(ticker, [])
        if t >= memory_cutoff
    ]
```

In `_record_position_exit()`, add `entry_price` as an optional kwarg (`entry_price=0.0`) so existing 2-arg callers (including 5 test calls) keep working unchanged. When `entry_price == 0.0` and `same_level_rejection_pct > 0`, log a warning so a forgotten caller is visible:

```python
# In _record_position_exit:
if is_loss:
    if entry_price > 0.0:
        self.stopped_entries.setdefault(ticker, []).append((datetime.now(), entry_price))
        self._prune_stopped_entries(ticker)
    elif self.risk_config.cooldown.same_level_rejection_pct > 0:
        print(f"   ⚠️  {ticker}: entry_price not passed to _record_position_exit, same-level rejection may not work")
else:
    # Profit clears stopped entries — a realized win means the level works now
    if ticker in self.stopped_entries:
        del self.stopped_entries[ticker]
        print(f"   ⏱️  {ticker}: Stopped-entry memory cleared (profit), same-level rejection reset")
```

The caller at line 1347 has access to `position.entry_price` — pass it through.

#### B4. Persist across restarts

In `_rebuild_cooldown_state()`, widen the cutoff window to cover the stopped-entry memory duration. Currently the cutoff is `max_cooldown_minutes` (360 = 6h). The stopped-entry memory lasts `stopped_entry_memory_minutes` (4320 = 72h). The rebuild must read back far enough to reconstruct this.

Change the cutoff in `_rebuild_cooldown_state()` to:

```python
rebuild_window = max(
    self.risk_config.cooldown.max_cooldown_minutes,
    self.risk_config.cooldown.stopped_entry_memory_minutes,
)
cutoff = datetime.now() - timedelta(minutes=rebuild_window)
```

Then rebuild `stopped_entries` from trade log EXIT events that were losses. Each EXIT record has `entry_price` and `timestamp`. Uses the same widened cutoff — no additional change needed since the rebuild loop already reads back 72h.

This is a one-line cutoff change that reuses the existing rebuild loop. The trade log is tiny so reading more lines on restart is negligible cost.

#### B5. Daily reset preserves stopped entries

In `_reset_daily_signals()`, call `_prune_stopped_entries(ticker)` for each ticker with stopped entries. Do NOT clear the entire list — only remove entries older than the memory window. The helper ensures the window definition stays in one place.

### C. Dashboard display

Add a `stopped_entries` summary to the dashboard footer showing tickers blocked by same-level rejection. Keep separate from cooldowns — different concept, different unit:

```
COOLDOWNS: VRT(201m) | BLOCKED: MXL(2 levels)
```

Engine: add `_get_active_blocks() -> Dict[str, int]` returning count of active stopped entries per ticker. Dashboard: add a render block for the `blocked_tickers` key.

### D. Tests

- Test same-level rejection: entry within 2% of stopped entry → rejected
- Test same-level expiry: entry after memory window → allowed
- Test profit clears stopped entries
- Test stopped entries survive daily reset
- Test rebuild from trade log preserves stopped entries
- Test entry_price=0.0 default doesn't break existing callers
- Test warning logged when entry_price not passed and same-level enabled
- Test disabled config: same_level_rejection_pct=0.0 → no block (off-switch for production rollback)
- Test multiple stopped entries for one ticker: list appends and prunes correctly
- Test dashboard BLOCKED render smoke: `blocked_tickers` state key renders the segment
- Test naive-vs-aware datetime: rebuild timestamps vs in-memory `datetime.now()` comparison does not raise (defensive — guard against tz-aware trade-log timestamps)

---

## Out of scope — backtest parity TODO

The same-level rejection rule is implemented only in `scripts/paper_engine_alpaca.py`. The backtest engine (`traderlib/backtest/`) does not use cooldown/consecutive_losses at all — zero references. This means:

- Historical backtests won't simulate this risk rule
- You can't backtest to tune `same_level_rejection_pct`
- Backtested strategy performance won't reflect the live engine's actual re-entry behavior — a live-vs-backtest divergence

This is captured here so a future PR can port the rule to the backtest engine with full context. The urgent fix (stop the MXL bleeding) ships paper-only first. Until the port lands, backtests overstate re-entry opportunity for repeat-failure tickers.

---

## Files affected

| File | Changes |
|---|---|
| `traderlib/risk_config.py` | Add `same_level_rejection_pct`, `stopped_entry_memory_minutes` to `CooldownConfig` |
| `config/paper/risk_config.yaml` | Add new settings under `cooldown:` |
| `scripts/paper_engine_alpaca.py` | Track stopped entries, check same-level on entry, record on loss, clear on profit, `_prune_stopped_entries` helper, persist across restarts, preserve across daily reset, dashboard display |
| `tests/test_paper_state_*.py` | Same-level rejection tests |
| `traderlib/dashboard.py` | BLOCKED render segment + `blocked_tickers` state key (do not fold into cooldowns) |

---

## What already exists (reuse, not rebuild)

- `consecutive_losses`, `last_exit_time`, and exponential-backoff cooldown (`_check_cooldown`, engine:650) already exist. This plan does NOT touch them — same-level rejection uses its own `stopped_entries` state, deliberately independent to avoid lifecycle coupling (the daily-reset wipe of `consecutive_losses` every 6h is exactly what would have broken a ban).
- Trade log EXIT records already carry `entry_price` (paper_state.py:670, engine:726), so rebuild-from-log needs no schema change.
- `_rebuild_cooldown_state` (engine:845) and `_reset_daily_signals` (engine:1349) already exist; this plan extends them with a widened cutoff and a prune call respectively.
- `timedelta` already imported (engine:10).
- Dashboard cooldown render pattern (dashboard.py:693) is the model for the new BLOCKED segment.

## NOT in scope

- **Backtest parity** — porting same-level rejection to `traderlib/backtest/` (zero cooldown refs today). Captured as TODO above; ships in a follow-up PR. Live-vs-backtest divergence accepted until then.
- **Consecutive-loss ban (Option 3)** — dropped per the eng review. The daily reset wipes `consecutive_losses` every 6h, so a multi-day ban can never fire for the MXL pattern it was justified by. Same-level rejection alone prevents MXL. Revisit only if evidence of an intraday 3-different-price-loss cycle appears, and then fix the daily-reset expiry first.
- **Tuning `same_level_rejection_pct` / `stopped_entry_memory_minutes`** — defaults (2.0%, 72h) are starting points; tuning needs the backtest port (out of scope) to validate against history.

## Failure modes

| Codepath | Realistic failure | Test? | Error handling? | User sees |
|---|---|---|---|---|
| B2 same-level check | `entry_price` undefined if placed before engine:1139 | Covered (placement spec: after 1139) | N/A | Correct block |
| B3 record | `entry_price=0.0` sentinel — caller forgot to pass it | Covered (warning test) | Warning log | Warning, not silent |
| B4 rebuild | trade log malformed EXIT line | Covered (existing skip) | try/except per line | Graceful skip |
| B4 rebuild | naive vs tz-aware datetime comparison | Defensive test added | None today | Potential crash — defensive test guards |
| B5 daily reset | prune window drift across call sites | Covered (helper extraction) | N/A | Correct |
| Dashboard | BLOCKED segment empty when no blocks | Smoke test | Empty-string branch | Clean footer |

**Critical gaps:** 0 silent unhandled failures. The naive-vs-aware datetime mismatch is the one residual risk (medium confidence) — the defensive test covers it.

## Worktree parallelization strategy

| Step | Modules touched | Depends on |
|---|---|---|
| Config (A) | traderlib/risk_config.py, config/paper/risk_config.yaml | — |
| Engine state + entry/exit (B1-B3) | scripts/paper_engine_alpaca.py | Config |
| Rebuild + daily reset (B4-B5) | scripts/paper_engine_alpaca.py | Engine state |
| Dashboard (C) | scripts/paper_engine_alpaca.py, traderlib/dashboard.py | Engine state |
| Tests (D) | tests/ | Engine + Dashboard |

All steps touch `scripts/paper_engine_alpaca.py` except Config and the dashboard render block. **Sequential implementation, no parallelization opportunity** — the engine is the shared module across 3 of 5 steps; worktrees would merge-conflict on the same file. One workstream.

## Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific finding above.

- [ ] **T1 (P1, human ~15min / CC ~5min)** — config — Add `same_level_rejection_pct`, `stopped_entry_memory_minutes` to `CooldownConfig` + yaml
  - Surfaced by: Section A
  - Files: `traderlib/risk_config.py`, `config/paper/risk_config.yaml`
  - Verify: config loads; fix the stale `max_cooldown_minutes` "4 hours" comment while here (360 min is 6h)
- [ ] **T2 (P1, human ~30min / CC ~10min)** — engine state + entry/exit — init `stopped_entries`, same-level check in `_execute_entry` (after line 1139 so `entry_price` is defined), record on loss + clear on profit in `_record_position_exit` with `entry_price=0.0` kwarg + warning, `_prune_stopped_entries` helper
  - Surfaced by: Sections B1-B3, D2 (kwarg), D5 (profit clear), D6 (NameError class), D7 (helper)
  - Files: `scripts/paper_engine_alpaca.py`
  - Verify: same-level rejection + profit-clear unit tests pass
- [ ] **T3 (P1, human ~20min / CC ~10min)** — persistence — widen `_rebuild_cooldown_state` cutoff to `max(max_cooldown_minutes, stopped_entry_memory_minutes)`; rebuild `stopped_entries` from EXIT loss records (extend the tuple to capture `entry_price`); daily reset calls `_prune_stopped_entries`
  - Surfaced by: Sections B4-B5, D1 (rebuild window), outside voice (rebuild must capture entry_price, not just ts/pnl)
  - Files: `scripts/paper_engine_alpaca.py`
  - Verify: restart >6h but <72h rebuilds stopped entries
- [ ] **T4 (P2, human ~20min / CC ~10min)** — dashboard — `_get_active_blocks()`, `blocked_tickers` state key, BLOCKED render segment in dashboard.py
  - Surfaced by: Section C, D3 (separate key, not folded into cooldowns)
  - Files: `scripts/paper_engine_alpaca.py`, `traderlib/dashboard.py`
  - Verify: dashboard smoke test
- [ ] **T5 (P1, human ~40min / CC ~15min)** — tests — full suite per section D including disabled-config, multiple stopped entries, dashboard smoke, naive-vs-aware datetime defensive
  - Surfaced by: Section D, D8 (boil the lake)
  - Files: `tests/test_cooldown_rebuild.py`, `tests/test_paper_engine_fills.py`
  - Verify: `pytest tests/test_cooldown_rebuild.py tests/test_paper_engine_fills.py`

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | /plan-ceo-review | Scope & strategy | 0 | — | not run |
| Codex Review | /codex review | Independent 2nd opinion | 0 | — | codex auth failed (401); Claude subagent used instead |
| Eng Review | /plan-eng-review | Architecture & tests (required) | 1 | CLEAR | 10 issues resolved, scope reduced (Option 3 dropped), 0 critical gaps |
| Design Review | /plan-design-review | UI/UX gaps | 0 | — | not run (BLOCKED dashboard segment is minor) |
| DX Review | /plan-devex-review | Developer experience gaps | 0 | — | not run |

- **CROSS-MODEL:** Claude subagent (outside voice) caught a structural bug the in-review missed — the Option 3 ban could not fire for the multi-day MXL case because `_reset_daily_signals` (engine:1363-1365) wipes `consecutive_losses` every 6h. User resolved by dropping Option 3; Option 4 (same-level rejection) alone prevents MXL. Both reviewers now agree the simpler design is correct.
- **UNRESOLVED:** 0 — all 10 decisions (D1-D10) resolved.
- **VERDICT:** ENG CLEARED — ready to implement. Ship Option 4 (same-level rejection) only per D10. Backtest parity deferred as TODO.