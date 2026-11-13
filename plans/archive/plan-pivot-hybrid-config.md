# Plan: Pivots, Hybrid Workflow, and Config Architecture

**Date:** 2026-04-19  
**Status:** PENDING — approved direction, not yet started

---

## Background

Three issues identified through a PM interview:

1. **Pivot opacity** — the dashboard shows a pivot distance but never says where the number came from (manual, VCP contraction, 20-day range). User relies on manual `Pivot_Price` because algorithmic pivots are untrustworthy / opaque.
2. **Hybrid VCP→Stage 2 workflow** — user enters via VCP (tight base pivot), then switches to Stage 2 momentum exit (trail 20/50 MA instead of hard stop). Currently modeled as two separate strategy classes with no transition mechanism.
3. **Config asymmetry** — `risk_config.yaml` mixes account-level risk with strategy params; `Stage2MomentumStrategy` has no config file at all (hardcoded thresholds).

---

## Key Decisions

### Hybrid workflow → no strategy switching needed
The VCP→Stage 2 lifecycle is a single position with two exit phases:
- **Phase 1 (VCP discipline):** Hard stop / ratchet below base. Pivot = VCP `pivot_high`.
- **Phase 2 (Stage 2 momentum discipline):** At 2R or MA confirmation, trail 20/50 MA instead of hard stop.

This maps directly onto the existing two-phase exit in `VCPLargeCapStrategy`. No mid-trade strategy switching required. Phase 2 just needs to be made explicit and configurable.

Same conclusion for backtest — no multi-strategy switching needed. A single `VCPLargeCapStrategy` (with explicit Phase 2) backtests the full lifecycle correctly.

### Config split
- `config/risk_config.yaml` → account-level risk only
- `config/strategies/vcp_large_cap.yaml` → VCP large cap strategy params
- `config/strategies/vcp_high_octane.yaml` → VCP high octane strategy params  
- `config/strategies/stage2_momentum.yaml` → Stage 2 params (currently all hardcoded)

---

## Implementation Phases

### Phase 1 — Pivot visibility (do first, highest leverage)
- Add `pivot_source` field to analysis dict in `entry_signals.py`
  - Values: `manual`, `vcp_contraction`, `range_20d`, `none`
- Show source badge next to pivot distance in dashboard
- Fix silent `current` fallback: if no pivot, show `—`, exclude from pivot-distance ranking, do not score as 0%
- Same fix in `paper_engine_alpaca.py`

### Phase 2 — Strategy config files
- Create `config/strategies/` directory
- Extract VCP parameters from `risk_config.yaml` → `vcp_large_cap.yaml` and `vcp_high_octane.yaml`
- Create `stage2_momentum.yaml` with all currently hardcoded thresholds
- Update strategy classes to load from their respective files

### Phase 3 — Hybrid exit formalization
- Annotate Phase 2 exit in `VCPLargeCapStrategy` as "Stage 2 momentum mode"
- Make trail MA periods configurable from `vcp_large_cap.yaml`
- Add `exit_phase` to position state so dashboard can show Phase 1 vs Phase 2 for live positions

### Phase 4 — Backtest pivot fix (lowest urgency)
- Wire VCP `pivot_high` computed during entry evaluation into backtest state
- R-multiples calculated from actual pivot, not `current`
- Ensures backtested results are comparable to live

### Supporting module — `traderlib/pivot_calculator.py`
- Returns `PivotResult(price, source, method)`
- Three strategy-specific methods loading params from strategy YAML files
- Used by `entry_signals.py`, `paper_engine_alpaca.py`, and backtest strategy classes for consistent attribution

---

## Files Affected

| File | Change |
|---|---|
| `scripts/entry_signals.py` | Add `pivot_source` to dict + badge in dashboard |
| `scripts/paper_engine_alpaca.py` | Fix `current` fallback, add `pivot_source` |
| `traderlib/pivot_calculator.py` | New module — `PivotResult`, strategy-specific methods |
| `config/risk_config.yaml` | Strip strategy params, keep account risk only |
| `config/strategies/vcp_large_cap.yaml` | New — VCP large cap params |
| `config/strategies/vcp_high_octane.yaml` | New — VCP high octane params |
| `config/strategies/stage2_momentum.yaml` | New — Stage 2 params |
| `traderlib/backtest/strategy.py` | Phase 4 — use real pivot in R-multiple calc |
