# Configurable Trailing Exit Strategies

## Implementation Status

**Status:** ✅ **IMPLEMENTED**  
**Date:** 2026-04-25  
**All Tasks Complete:** 17/17  

### Summary
**Core Implementation (Tasks 1-7):**
- ✅ Task 1: Extended Risk Config with trailing modes
- ✅ Task 2: Created Trailing Exit Engine (all 3 modes)
- ✅ Task 3: Added scale-out state persistence
- ✅ Task 4: Integrated into ExitEngine
- ✅ Task 5: Created example configuration
- ✅ Task 6: Backtest integration verified
- ✅ Task 7: Documentation complete

**Post-Review Fixes (Tasks 8-13):**
- ✅ Task 8: Fixed scale-out with 0 shares (CRITICAL)
- ✅ Task 9: Invalid YAML config now fails loudly (CRITICAL)
- ✅ Task 10: Removed dead `executed` fields from config
- ✅ Task 11: Added validation for non-empty stages/bands
- ✅ Task 12: Documented `breakeven_at_r` mode-specific behavior
- ✅ Task 13: Added float precision safety for scale-out deduplication

### Test Results
- 9 tests in `test_risk_config.py` (trailing config) ✅
- 23 tests in `test_trailing_exits.py` (engine) ✅
- 3 tests in `test_trailing_integration.py` (ExitEngine) ✅
- 2 tests in `test_backtest_trailing.py` (backtest) ✅

**Total: 37 tests passing**

---

## Overview
Design a YAML-configurable exit system that lets winning trades run with dynamically adjusting trailing stops, replacing the current fixed 2R profit target system.

---

## Motivation

The current system takes profit at fixed 2R minimum targets (e.g., AMD Apr 20 trade exited at 2.8R for +$1,114, but could have captured more with a trailing approach). This design enables backtesting of various trailing stop strategies to optimize for extended trends.

---

## Goals

1. **Let winners run** — No fixed profit targets; exit on trailing stop breach
2. **Protect capital** — Move to breakeven at +2R
3. **Progressive tightening** — Trail with tighter MAs early, wider MAs later
4. **Configurable via YAML** — Backtest different strategies without code changes
5. **Compatible with scale-out** — Option to sell partial positions at R-levels

---

## Proposed Approaches

### Approach A: Stage-Based Trailing (Recommended)

Explicit stages trigger stop adjustments at R-multiple thresholds.

```yaml
profit_target:
  mode: "trailing"
  trailing_mode: "stage_based"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21
```

**Pros:** Clear, explicit, easy to backtest permutations  
**Cons:** Discrete steps vs smooth transitions

**Validation:** Requires at least one stage; stages must have increasing `trigger_r` values.

### Approach B: Continuous Trailing

Smooth band transitions with configurable width.

```yaml
profit_target:
  mode: "trailing"
  trailing_mode: "continuous"
  breakeven_at_r: 2.0  # Note: only applies in continuous mode
  continuous_bands:
    - from_r: 2.5
      to_r: 4.0
      method: "ema10"
    - from_r: 4.0
      method: "ema21"  # No to_r = unlimited
```

**Pros:** Handles gradual transitions  
**Cons:** More complex configuration

**Validation:** Requires at least one band; bands must not overlap.

### Approach C: Hybrid Scale-Out + Trail

Combines partial profit-taking with trailing remaining position.

```yaml
profit_target:
  mode: "hybrid"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
  scale_out_steps:
    - trigger_r: 3.0
      fraction: 0.33  # Sell 1/3
    - trigger_r: 4.0
      fraction: 0.50  # Sell 1/2 of remaining
```

**Pros:** Most flexible  
**Cons:** More code paths

**Validation:** Scale-out fractions must sum to ≤ 1.0; position tracks executed scale-outs via `scale_out_history` to prevent duplicate triggers.

---

## Design Decisions

### 1. R-Multiple as Trigger

All triggers based on R-multiple (current gain / initial risk) — universal across different priced stocks.

### 2. Stop Never Moves Lower

Trailing stops only ratchet up, never down. Protects against volatility giving back gains.

### 3. Method Options

| Method | Description | Best For | Status |
|--------|-------------|----------|--------|
| `breakeven` | Move stop to entry price | Protecting capital | ✅ Implemented |
| `trail_ema` | Trail below N-period EMA (10 or 21) | Trend following | ✅ Implemented |
| `swing_low` | Trail below recent swing low | Volatile stocks | ❌ Not implemented |
| `atr_multiple` | Trail at Nx ATR below price | Custom width | ❌ Not implemented |
| `fixed_pct` | Trail at fixed % below price | Simple rules | ❌ Not implemented |

**Note:** EMA periods are limited to 10 and 21. Other periods will raise `ValueError`.

### 4. Configuration Location

- Per-strategy: `config/strategies/<strategy>.yaml`
- Global default: `config/risk_config.yaml` (for strategies without explicit exit config)

---

## Example: AMD Apr 9 Trade

With user-preferred strategy:

| Stage | Trigger | Action | Stop Location |
|-------|---------|--------|---------------|
| Entry | — | Initial stop | $217.81 (ATR-based) |
| Breakeven | 2.0R ($252.48) | Move stop | $229.33 (entry) |
| Early trail | 3.0R ($263.89) | Trail 10 EMA | ~$255 (dynamic) |
| Late trail | 5.0R ($286.93) | Trail 20 EMA | ~$275 (dynamic) |
| Exit | When price hits trailing stop | — | Final price |

**Result:** Position runs until momentum exhausts, not fixed target.

---

## Post-Review Fixes

The following fixes were applied after initial code review:

### Critical Fixes

| Task | Issue | Fix |
|------|-------|-----|
| 8 | Scale-out with 0 shares blocks future triggers | Added minimum-shares guard; skip if `shares_to_sell <= 0` or `>= position.shares` |
| 9 | Invalid YAML config silently falls back to defaults | `ValueError` from validation now raises `SystemExit`; only YAML/I/O errors fall back |

### Important Fixes

| Task | Issue | Fix |
|------|-------|-----|
| 10 | Dead `executed` fields on config dataclasses | Removed; runtime uses `position.scale_out_history` instead |
| 11 | Empty stages/bands cause hold-forever | Added validation requiring at least one stage/band |
| 12 | `breakeven_at_r` behavior undocumented | Added docstrings explaining continuous-mode only |
| 13 | Float equality for scale-out deduplication | Round R-levels to 6 decimal places for safe comparison |

## Implementation Notes

1. **Backward compatibility:** Existing `target` mode remains default
2. **Validation:** YAML validates at load time (stage R-values must increase, bands must not overlap)
3. **Error handling:** Invalid config raises `SystemExit` to prevent silent reversion to defaults
4. **Performance:** Cache EMA calculations per ticker
5. **Logging:** Record each stop adjustment in trade log
6. **Scale-out safety:** Positions too small for fraction result in skipped scale-out, not recorded execution

---

## Resolved Questions

1. ✅ **Scale-out fractions:** Based on current position (not original)
2. ✅ **Gap-down handling:** Hard stop check happens first; gap below stop exits immediately
3. ⚠️ **Trailing stop pause:** Not implemented (could be future enhancement for earnings)
4. ✅ **Visualization:** Stop adjustments logged in trade log; can be tracked per position

---

## Related Files

| File | Status | Description |
|------|--------|-------------|
| `traderlib/risk_config.py` | ✅ Extended | Added `ProfitTargetConfig` with trailing modes |
| `traderlib/trailing_exits.py` | ✅ Created | Core trailing engine with all 3 modes |
| `traderlib/paper_state.py` | ✅ Modified | Added `scale_out_history` to Position |
| `traderlib/paper_exits.py` | ✅ Modified | Integrated trailing into ExitEngine |
| `config/strategies/example_trailing.yaml` | ✅ Created | Example configuration |
| `tests/test_trailing_exits.py` | ✅ Created | Engine tests (23 tests) |
| `tests/test_trailing_integration.py` | ✅ Created | Integration tests (3 tests) |
| `tests/test_backtest_trailing.py` | ✅ Created | Backtest tests (2 tests) |
| `tests/test_risk_config.py` | ✅ Extended | Config tests (9 trailing tests) |

---

*Design approved for implementation planning.*
