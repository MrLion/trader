# Design Spec: Remove Convergence Scoring from Trend Screener

**Date:** 2026-05-31
**Author:** Claude (revised after architect review)
**Status:** Draft — pending user approval

---

## Problem Statement

The `trend_screener.py` convergence scoring system produces zero actionable Grade A results after scanning 1,328 stocks. The scoring formula (`calculate_convergence_score()` in `stage2_utils.py`) is mathematically incompatible with the screener's momentum filters:

1. `min_price_vs_10ma: 4` caps `distance_score` at 9/15 for every passing ticker
2. Strong Stage 2 uptrends (above 200MA) score 0 because the cluster spread exceeds 15%
3. Grade A threshold (≥70) is structurally unreachable in the high-octane profile

The result: 95 candidates out of 1,328, with 93 in Grade C (score <50), 2 in Grade B (score 50-70), and 0 in Grade A. The convergence score adds ~67 seconds of computation per scan with no filtering value.

## Decision

Remove convergence scoring and grade grouping from the trend screener. The screener will return to its core function: applying structural filters (price, volume, MA stack, RS, Stage 2) and ranking by setup readiness or Stage 2 score.

---

## Scope

### In Scope

| File | Action | Details |
|------|--------|---------|
| `scripts/trend_screener.py` | **Edit** | Remove convergence imports, calculation call, result fields, `rank_by='convergence'` path, grade display, and CLI args |
| `config/screener_config.yaml` | **Edit** | Remove `min_convergence_score` from both profiles |
| `config/strategies/example_trailing.yaml` | **Edit** | Remove `min_convergence_score` reference |
| `tests/test_trend_screener.py` | **Edit** | Rewrite convergence-dependent tests to assert `stage2_score` ranking |

### Out of Scope

| File | Action | Rationale |
|------|--------|-----------|
| `traderlib/stage2_utils.py` | **Keep** | `calculate_convergence_score()`, `get_convergence_grade()`, `calculate_ma_support_stop()` remain as library utilities |
| `tests/test_ma_convergence.py` | **Keep** | Unit tests for the underlying scoring functions are preserved |
| `entry_signals.py` | **Keep** | Still displays convergence data for single-ticker deep analysis |

---

## Dependency Audit

Before removing any field or CLI arg, verify no downstream consumer depends on it. Run these greps and confirm zero matches outside `trend_screener.py`:

```bash
# Fields being removed from result dict
grep -r "convergence_score\|cluster_spread_pct\|cluster_size\|ma_risk_pct\|atr_risk_pct\|risk_improvement_pct" scripts/ config/ tests/ --include="*.py" --include="*.yaml" | grep -v "trend_screener.py" | grep -v "stage2_utils.py" | grep -v "test_ma_convergence.py"

# CLI args being removed
grep -r "min-convergence-score\|cluster-spread-pct\|min-cluster-size\|hide-grade-c" scripts/ config/ tests/ --include="*.py" | grep -v "trend_screener.py"
```

**Known reference to check:** `config/strategies/example_trailing.yaml` contains `min_convergence_score: 50` — this is in scope for removal.

**Known safe function:** `calculate_convergence_score()` is called by `entry_signals.py` and tested by `test_ma_convergence.py`. These callers are outside the removal scope.

---

## New Behavior

### Output Format

**Before:**
```
Total: 95 | Grade A: 0 | Grade B: 2 | Grade C: 93
```

**After:**
```
  Profile: high-octane  |  Universe: 1,328 tickers  |  Ranked by: setup
────────────────────────────────────────────────────────────────────────────────────────
  Top candidates (sorted by entry readiness → proximity → stage2 score)

  Ticker    Price   Stage2   Prox%   Setup        Vol$    RS%
  ─────────────────────────────────────────────────────────────────
  KFY      $69.98      6     1.1%   trend       $45M    8.5
  RCI      $38.55      8     0.3%   trend       $32M    7.2
  ...

  Total: 95 candidates
```

Single table, no grade grouping. `--top` shows top N total (not per-grade).

### Filter Pipeline

1. Data sufficiency (≥200 bars)
2. Price floor
3. Price vs 10MA (optional momentum filter)
4. Stage 2 score (≥5)
5. MA stack short (10>21>50)
6. MA stack long (50>150>200) — optional
7. RS near 52-week high
8. Liquidity

No convergence gate. All passing candidates are returned ungraded.

### Result Fields

**Removed:**
- `convergence_score`
- `cluster_size`
- `cluster_spread_pct`
- `ma_risk_pct`
- `atr_risk_pct`
- `risk_improvement_pct`

**Kept:**
- `ticker`, `price`, `stage2_score`
- `setup_type` (renamed from `'convergence'` to `'trend'` when `entry_mode='any'`)
- `entry_ready`, `proximity_pct`
- `volume_ratio`, `avg_dollar_volume`
- `rs_from_high`
- `ma10`, `ma20`, `ma50`, `ma150`, `ma200`
- `sector`, `vcp_data`

### Ranking

**Default:** `setup`

**Sort key for `setup`:**
```python
sorted(results, key=lambda x: (
    not x['entry_ready'],      # Entry-ready first
    x['proximity_pct'],         # Closest to pivot first
    -x['stage2_score']         # Higher stage2 score first (tiebreaker)
))
```

**Sort key for `rs`:** (unchanged)
```python
sorted(results, key=lambda x: x['rs_from_high'])
```

---

## CLI Changes

### Removed Args

| Arg | Removal Reason |
|-----|---------------|
| `--min-convergence-score` | No convergence gate exists |
| `--cluster-spread-pct` | No convergence calculation |
| `--min-cluster-size` | No convergence calculation |
| `--rank-by convergence` | Ranking choice removed |
| `--hide-grade-c` / `--no-hide-grade-c` | No grade groups exist |
| `--show-score-stats` | No convergence score distribution to show |

### Modified Args

| Arg | Before | After |
|-----|--------|-------|
| `--rank-by` | Choices: `convergence`, `setup`, `rs` | Choices: `setup`, `rs`. Default: `setup` |
| `--top` | Top N per grade (20 A, 20 B, 20 C) | Top N total |

### Kept Args

All trend filters, entry timing, VCP detection, export, and display args remain unchanged.

---

## Migration Notes

### Breaking Change: `--rank-by` Default

**Before:** `python3 trend_screener.py --profile large-cap` defaulted to `rank-by=convergence`.
**After:** Same command now defaults to `rank-by=setup`.

**Impact:** Cron jobs, scripts, and muscle memory that relied on convergence ranking will see different output order. The new order is arguably better (entry-ready stocks first), but it is different.

**Mitigation:** No deprecation period. The convergence ranking was non-functional (max score 64, no Grade A), so maintaining backward compatibility provides no value. The minor version bump (`0.6.19.1 → 0.6.20.0`) signals a breaking change.

### `setup_type` Label Change

When `entry_mode='any'` and no VCP/pivot is detected, `setup_type` was `'convergence'`. It is now `'trend'`.

**Impact:** CSV consumers parsing `setup_type` will see a new string. If any downstream tool branches on `setup_type == 'convergence'`, that branch will never fire.

**Mitigation:** Verify via dependency audit (see above) that no consumer branches on this value.

---

## Test Rewrite

### `tests/test_trend_screener.py`

**Remove:** `test_convergence_score_calculation` — tests `calculate_convergence_score()` directly. This belongs in `test_ma_convergence.py`, not the screener integration test.

**Remove:** `test_convergence_score_invalid_when_no_cluster` — same reasoning.

**Rewrite:** Any test that constructs mock results with `convergence_score` fields must replace that field with `stage2_score` and update the `rank_results()` assertion.

**Example rewrite pattern:**
```python
# Before
results = [
    {'ticker': 'A', 'convergence_score': 75, 'stage2_score': 7, 'entry_ready': True, ...},
    {'ticker': 'B', 'convergence_score': 60, 'stage2_score': 5, 'entry_ready': True, ...},
]
ranked = screener.rank_results(results, rank_by='convergence')
assert ranked[0]['ticker'] == 'A'

# After
results = [
    {'ticker': 'A', 'stage2_score': 7, 'entry_ready': True, 'proximity_pct': 1.0, ...},
    {'ticker': 'B', 'stage2_score': 5, 'entry_ready': True, 'proximity_pct': 2.0, ...},
]
ranked = screener.rank_results(results, rank_by='setup')
assert ranked[0]['ticker'] == 'A'  # higher stage2 score, lower proximity
```

**Add:** `test_rank_by_setup_sorts_entry_ready_first` — prove the new default ranking works.

---

## Risks and Mitigations

| Risk | Verification | Mitigation |
|------|-------------|------------|
| Downstream consumer depends on removed CSV column | Dependency audit grep | Fix consumer before merge; add column back temporarily if needed |
| `backtest.py --watchlist` fails on missing `convergence_score` | Read `backtest.py` watchlist loading code | If `usecols` is used, add a default value or remove the column requirement |
| User scripts pass `--rank-by convergence` | N/A (argparse will reject) | Clear error message: "convergence ranking removed; use setup or rs" |
| `calculate_ma_support_stop()` orphaned | Check if any non-screener code calls it | If unused outside tests, consider deprecating in a separate PR |
| Premarket report references convergence | Read `premarket_report.py` convergence refs | Remove or replace refs in same session |

---

## Success Criteria

- [ ] Dependency audit grep returns zero unexpected matches
- [ ] `python3 scripts/trend_screener.py --profile high-octane` runs without convergence-related output
- [ ] Output shows a single ranked table, no Grade A/B/C grouping
- [ ] `--rank-by convergence` is rejected by argparse with a clear error
- [ ] `--rank-by setup` sorts entry-ready stocks first, then by proximity, then by stage2 score
- [ ] `setup_type` is `'trend'` (not `'convergence'`) when `entry_mode='any'` and no VCP/pivot found
- [ ] Tests pass (`tests/test_trend_screener.py` with rewritten ranking tests)
- [ ] `calculate_convergence_score()` in `stage2_utils.py` is untouched
- [ ] `entry_signals.py` still displays convergence data for single-ticker analysis
- [ ] `backtest.py` and `paper_engine_alpaca.py` do not crash on screener CSV output

---

## Notes

- This is a **removal** spec. The implementation is primarily deletion.
- Version bump should be **patch** (`0.6.19.1 → 0.6.19.2`) — removing a non-functional feature is a fix, not a new feature. Note: this is technically a breaking change for `--rank-by` default and CSV output.
- The convergence scoring function in `stage2_utils.py` is intentionally preserved — it may be useful for dashboard visualization or future single-ticker tools.
- `calculate_ma_support_stop()` stops being called by the screener but remains in `stage2_utils.py`. If no other production code calls it, consider deprecating it in a follow-up cleanup PR.
