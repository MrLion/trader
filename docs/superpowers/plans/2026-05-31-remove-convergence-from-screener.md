# Remove Convergence Scoring from Trend Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove convergence scoring, grade grouping, and related CLI args from `trend_screener.py`, making it a structural filter + setup readiness tool.

**Architecture:** Single-file change (`trend_screener.py`) plus config cleanup and test rewrite. The `calculate_convergence_score()` library function in `stage2_utils.py` is preserved for `entry_signals.py` and other tools. No new files created.

**Tech Stack:** Python 3.11, `argparse`, `rich` (for table output), `pandas` (for CSV export).

---

## File Structure

| File | Action | Responsibility |
|------|--------|--------------|
| `scripts/trend_screener.py` | **Edit** | Remove convergence imports, calculation, result fields, ranking, grade display, CLI args |
| `config/screener_config.yaml` | **Edit** | Remove `min_convergence_score` from both profiles |
| `config/strategies/example_trailing.yaml` | **Edit** | Remove `min_convergence_score` reference |
| `tests/test_trend_screener.py` | **Edit** | Remove/rewrite convergence-dependent tests |

---

## Pre-Implementation Verification

Run the dependency audit from the spec to confirm no unexpected consumers exist.

```bash
# Fields being removed from result dict
grep -r "convergence_score\|cluster_spread_pct\|cluster_size\|ma_risk_pct\|atr_risk_pct\|risk_improvement_pct" scripts/ config/ tests/ --include="*.py" --include="*.yaml" | grep -v "trend_screener.py" | grep -v "stage2_utils.py" | grep -v "test_ma_convergence.py" | grep -v "__pycache__"

# CLI args being removed
grep -r "min-convergence-score\|cluster-spread-pct\|min-cluster-size\|hide-grade-c" scripts/ config/ tests/ --include="*.py" | grep -v "trend_screener.py" | grep -v "__pycache__"

# Check for pandas usecols (explicit column dependencies)
grep -r "usecols" scripts/ config/ tests/ --include="*.py"
```

**Expected:** `example_trailing.yaml` and `screener_config.yaml` match (in scope). `premarket_report.py` and `postmarket_report.py` call `calculate_ma_support_stop()` directly with hardcoded params — not reading screener CSV. `entry_signals.py` reads `atr_risk_pct` from single-ticker analysis dict — not CSV. No `usecols` found.

**If unexpected matches appear:** Stop and assess before proceeding.

---

## Task 1: Remove Convergence Imports and Calculation from `trend_screener.py`

**Files:**
- Modify: `scripts/trend_screener.py`

- [ ] **Step 1: Remove convergence imports**

Remove these two imports from the top of `scripts/trend_screener.py`:

```python
# OLD (lines 38, 41)
from traderlib.stage2_utils import (
    calculate_stage2_score,
    get_stage2_details,
    calculate_convergence_score,
    calculate_volume_metrics,
    calculate_ma_support_stop,
    get_convergence_grade,
)
```

```python
# NEW
from traderlib.stage2_utils import (
    calculate_stage2_score,
    get_stage2_details,
    calculate_volume_metrics,
)
```

- [ ] **Step 2: Remove convergence calculation from `_analyze_ticker()`**

Delete lines 210-239 in `_analyze_ticker()`. The entire "CONVERGENCE SCORING" block becomes:

```python
        # === ENTRY TIMING ===
```

Also remove the `cluster_spread` and `min_cluster` variable declarations (lines 222-225).

- [ ] **Step 3: Remove convergence result fields from result dict**

Edit the result dict compilation (lines 295-317). Remove these keys:
- `'convergence_score': conv_score['score']`
- `'cluster_size': ma_cluster.get('cluster_size', 0)`
- `'cluster_spread_pct': ma_cluster.get('cluster_spread_pct', 0)`
- `'ma_risk_pct': conv_score.get('ma_risk_pct', 0)`
- `'atr_risk_pct': conv_score.get('atr_risk_pct', 0)`
- `'risk_improvement_pct': conv_score['components']['risk_improvement']`

Remove the `ma_cluster = conv_score.get('cluster_data', {})` line.

- [ ] **Step 4: Change `setup_type` from `'convergence'` to `'trend'`**

Edit line 288:

```python
# OLD
            setup_type = 'convergence'

# NEW
            setup_type = 'trend'
```

- [ ] **Step 5: Remove convergence filter from `_analyze_ticker()`**

The convergence score gate (lines 236-239) was already deleted in Step 2. Verify it's gone.

- [ ] **Step 6: Commit**

```bash
git add scripts/trend_screener.py
git commit -m "refactor: remove convergence scoring from trend screener core logic

Removes convergence imports, calculation block, result fields,
and renames setup_type 'convergence' → 'trend'.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Remove Grade Display and Convergence Ranking from `trend_screener.py`

**Files:**
- Modify: `scripts/trend_screener.py`

- [ ] **Step 1: Remove convergence ranking from `rank_results()`**

Edit `rank_results()` (lines 415-434). Remove the `rank_by == 'convergence'` branch:

```python
# OLD
        if rank_by == 'convergence':
            return sorted(results, key=lambda x: (x['convergence_score'], x['cluster_size']), reverse=True)

        elif rank_by == 'setup':
# NEW
        if rank_by == 'setup':
```

- [ ] **Step 2: Simplify `display_results()` to single table**

The `display_results()` method (lines 436-584) currently groups by Grade A/B/C. Rewrite it to show a single table.

Replace lines 484-486 (grade grouping):

```python
# REMOVE:
grade_a = [r for r in results if get_convergence_grade(r['convergence_score']) == "Grade A"]
grade_b = [r for r in results if get_convergence_grade(r['convergence_score']) == "Grade B"]
grade_c = [r for r in results if get_convergence_grade(r['convergence_score']) == "Grade C"]
```

Replace the `_print_group_rich` and `_print_group_plain` calls (lines 560-569) with a single call that prints all results:

```python
# OLD (grade-grouped print calls)
        if use_rich:
            _print_group_rich(grade_a, ...)
            _print_group_rich(grade_b, ...)
            if not hide_grade_c:
                _print_group_rich(grade_c, ...)

# NEW (single table)
        if use_rich:
            _print_group_rich(results, "Candidates", "📊", "white", "white")
        else:
            _print_group_plain(results, "Candidates", "📊")
```

Also update `_make_table` to remove the title argument (no longer per-grade):

```python
# In _make_table, change:
# OLD
            title=f"{icon} {grade_name}",
# NEW
            title=f"{icon} Top {top} {grade_name}",
```

Update the summary line (lines 577-578) to remove grade counts:

```python
# OLD
        summary = (f"\nTotal: {len(results)} | Grade A: {len(grade_a)} | "
                   f"Grade B: {len(grade_b)}{c_note}")

# NEW
        summary = f"\nTotal: {len(results)} candidates"
```

Remove `hide_grade_c` from the method signature and all references.

Remove `show_score_stats` from the method signature and all references (the score distribution print on lines 460-463).

- [ ] **Step 3: Update `_print_group_rich` to remove convergence columns**

The table currently shows: Ticker, Price, Stage2, Score, MAs, MA Stop%, To Pivot, Vol Ratio.

Remove the "Score" and "MAs" columns (convergence-specific). Keep: Ticker, Price, Stage2, To Pivot, Vol Ratio, and optionally Entry if `show_entry_col`.

Update `_make_table`:

```python
        table.add_column("Ticker", style=row_style, no_wrap=True)
        table.add_column("Price", justify="right")
        table.add_column("Stage2", justify="right")
        table.add_column("To Pivot", justify="right")
        table.add_column("Vol Ratio", justify="right")
        if show_entry_col:
            table.add_column("Entry", justify="center")
```

Update the row assembly in `_print_group_rich` and `_print_group_plain` to match.

- [ ] **Step 4: Commit**

```bash
git add scripts/trend_screener.py
git commit -m "refactor: replace grade-grouped output with single ranked table

Removes Grade A/B/C grouping, convergence score columns, and
score distribution display. Output is now a single candidate table.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Remove Convergence CLI Args from `trend_screener.py`

**Files:**
- Modify: `scripts/trend_screener.py`

- [ ] **Step 1: Remove argparse args**

Delete these argument definitions from `main()` (lines 700-705, 730-733):

```python
# REMOVE:
    parser.add_argument('--min-convergence-score', type=int, default=None,
                        help='Filter min convergence score (default: from profile config; null in config = disabled)')
    parser.add_argument('--cluster-spread-pct', type=float, default=None,
                        help='Max cluster spread %% (default=adaptive, e.g. 0.05 for tight 5%%)')
    parser.add_argument('--min-cluster-size', type=int, default=1,
                        help='Min MAs in cluster (default: 1)')
```

```python
# REMOVE:
    parser.add_argument('--hide-grade-c', action='store_true', default=False,
                        help='Hide Grade C results (default: shown; use --hide-grade-c to suppress)')
    parser.add_argument('--no-hide-grade-c', dest='hide_grade_c', action='store_false',
                        help='Show Grade C results (default)')
```

- [ ] **Step 2: Update `--rank-by` choices**

Change line 724:

```python
# OLD
    parser.add_argument('--rank-by', choices=['convergence', 'setup', 'rs'], default='convergence',
                        help='Sort criteria (default: convergence)')

# NEW
    parser.add_argument('--rank-by', choices=['setup', 'rs'], default='setup',
                        help='Sort criteria (default: setup)')
```

- [ ] **Step 3: Remove convergence from `epilog` examples**

Edit lines 651-665 in the argparse epilog:

```python
# OLD
  # Discovery mode
  python3 %(prog)s --profile large-cap --rank-by convergence --top 20

  # Quality-tiered discovery (only Grade A+)
  python3 %(prog)s --profile large-cap --min-convergence-score 60

# NEW
  # Discovery mode
  python3 %(prog)s --profile large-cap --top 20
```

- [ ] **Step 4: Remove convergence from effective filter computation**

Delete line 764:

```python
# REMOVE:
    effective_min_conv = args.min_convergence_score if '--min-convergence-score' in _explicit else profile_cfg.get('min_convergence_score')
```

- [ ] **Step 5: Remove convergence from filters dict**

Delete these entries from the `filters` dict (lines 845-847):

```python
# REMOVE:
        'min_convergence_score': effective_min_conv,
        'cluster_spread_pct': args.cluster_spread_pct,
        'min_cluster_size': args.min_cluster_size,
```

- [ ] **Step 6: Remove convergence from context header**

Delete lines 867-868:

```python
# REMOVE:
    if effective_min_conv is not None:
        active_filters.append(f"conv≥{effective_min_conv}")
```

- [ ] **Step 7: Remove convergence from `scan()` filter breakdown**

Delete the convergence entry from `_filter_label()` (lines 395-397):

```python
# REMOVE:
            elif key == 'convergence':
                val = filters.get('min_convergence_score')
                return f'conv score (≥{val})' if val is not None else 'conv score'
```

And from `breakdown_order` (line 404):

```python
# OLD
        breakdown_order = ['data', 'price', 'price_vs_10ma', 'stage2',
                           'ma_stack_short', 'ma_stack_long', 'rs_near_high',
                           'liquidity', 'convergence', 'passed']

# NEW
        breakdown_order = ['data', 'price', 'price_vs_10ma', 'stage2',
                           'ma_stack_short', 'ma_stack_long', 'rs_near_high',
                           'liquidity', 'passed']
```

- [ ] **Step 8: Remove convergence from scan print**

Delete line 341:

```python
# REMOVE:
        print(f"  Filters: min_price={price_label}, min_conv_score={conv_label}")
```

And delete the `conv_label` variable (lines 335-336).

Also update line 880:

```python
# OLD
    print(f"\n📈 Scanning for MA convergence setups...")

# NEW
    print(f"\n📈 Scanning for trending setups...")
```

- [ ] **Step 9: Remove convergence from `display_results()` call**

Update the call at lines 890-898:

```python
# OLD
    screener.display_results(
        ranked,
        show_ma_data=args.show_ma_data,
        top=args.top,
        show_score_stats=show_score_stats,
        context=context,
        hide_grade_c=args.hide_grade_c,
        entry_mode=entry_mode,
    )

# NEW
    screener.display_results(
        ranked,
        show_ma_data=args.show_ma_data,
        top=args.top,
        context=context,
        entry_mode=entry_mode,
    )
```

- [ ] **Step 10: Commit**

```bash
git add scripts/trend_screener.py
git commit -m "refactor: remove convergence CLI args from trend screener

Removes --min-convergence-score, --cluster-spread-pct, --min-cluster-size,
--hide-grade-c, --rank-by convergence. Default rank changes to 'setup'.
Updates help text and scan header.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Update Config Files

**Files:**
- Modify: `config/screener_config.yaml`
- Modify: `config/strategies/example_trailing.yaml`

- [ ] **Step 1: Remove `min_convergence_score` from screener config**

Delete these lines from both profiles in `config/screener_config.yaml`:

```yaml
# REMOVE from large_cap:
    min_convergence_score: null       # null = disabled (rank only, don't filter)

# REMOVE from high_octane:
    min_convergence_score: null    # null = disabled
```

- [ ] **Step 2: Remove `min_convergence_score` from strategy config**

Delete from `config/strategies/example_trailing.yaml`:

```yaml
# REMOVE:
  min_convergence_score: 50
```

- [ ] **Step 3: Commit**

```bash
git add config/screener_config.yaml config/strategies/example_trailing.yaml
git commit -m "config: remove min_convergence_score from screener and strategy configs

Convergence scoring is no longer used by trend_screener.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Rewrite Tests

**Files:**
- Modify: `tests/test_trend_screener.py`

- [ ] **Step 1: Read current test file**

```bash
cat tests/test_trend_screener.py
```

- [ ] **Step 2: Remove convergence-specific test methods**

Delete:
- `test_convergence_score_calculation` (if it exists — tests `calculate_convergence_score()` directly)
- `test_convergence_score_invalid_when_no_cluster` (same reasoning)

These belong in `tests/test_ma_convergence.py`.

- [ ] **Step 3: Rewrite ranking tests**

Find tests that construct mock results with `convergence_score` fields and rewrite them.

**Pattern for rewrite:**

```python
# Before:
results = [
    {'ticker': 'A', 'convergence_score': 75, 'stage2_score': 7, 'entry_ready': True, ...},
    {'ticker': 'B', 'convergence_score': 60, 'stage2_score': 5, 'entry_ready': True, ...},
]
ranked = screener.rank_results(results, rank_by='convergence')
assert ranked[0]['ticker'] == 'A'

# After:
results = [
    {'ticker': 'A', 'stage2_score': 7, 'entry_ready': True, 'proximity_pct': 1.0, ...},
    {'ticker': 'B', 'stage2_score': 5, 'entry_ready': True, 'proximity_pct': 2.0, ...},
]
ranked = screener.rank_results(results, rank_by='setup')
# A should be first: entry_ready=True, proximity_pct=1.0 < 2.0
assert ranked[0]['ticker'] == 'A'
```

- [ ] **Step 4: Add new default ranking test**

Add `test_rank_by_setup_sorts_entry_ready_first`:

```python
def test_rank_by_setup_sorts_entry_ready_first(self):
    """setup ranking puts entry_ready=True first."""
    results = [
        {'ticker': 'NOT_READY', 'stage2_score': 8, 'entry_ready': False, 'proximity_pct': 1.0},
        {'ticker': 'READY', 'stage2_score': 6, 'entry_ready': True, 'proximity_pct': 3.0},
    ]
    ranked = self.screener.rank_results(results, rank_by='setup')
    assert ranked[0]['ticker'] == 'READY'
    assert ranked[1]['ticker'] == 'NOT_READY'
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_trend_screener.py -v
```

Expected: All tests pass. Any failures are due to residual convergence references.

- [ ] **Step 6: Commit**

```bash
git add tests/test_trend_screener.py
git commit -m "test: rewrite trend_screener tests for setup ranking

Removes convergence score tests, rewrites ranking tests for setup
and rs criteria, adds test for entry_ready sorting.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Run Trend Screener and Verify Output

**Files:**
- None (verification only)

- [ ] **Step 1: Run with a small ticker list**

```bash
python3 scripts/trend_screener.py --tickers AAPL MSFT GOOGL
```

**Verify:**
- No convergence-related output
- Single table displayed
- No Grade A/B/C grouping
- `--rank-by` default is `setup` (entry-ready stocks first)

- [ ] **Step 2: Run discovery mode (shortened)**

```bash
python3 scripts/trend_screener.py --profile large-cap --top 10
```

**Verify:**
- Runs without errors
- Output shows "Scanning for trending setups..."
- Single candidate table
- No convergence score column

- [ ] **Step 3: Verify `--rank-by convergence` is rejected**

```bash
python3 scripts/trend_screener.py --tickers AAPL --rank-by convergence
```

**Expected:** argparse error: "invalid choice: 'convergence' (choose from 'setup', 'rs')"

- [ ] **Step 4: Commit if all pass**

No code changes in this task — just verification. If any issues, fix in the relevant task and re-verify.

---

## Task 7: Version Bump and Changelog

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

```bash
echo "0.6.19.2" > VERSION
```

- [ ] **Step 2: Update CHANGELOG.md**

Add new section at top:

```markdown
## [0.6.19.2] — 2026-05-31 — Fix — Remove Non-Functional Convergence Scoring

### Removed
- **`scripts/trend_screener.py`** — Removed convergence scoring and grade grouping. The scoring formula was mathematically incompatible with momentum filters, producing zero Grade A results across all profiles. Grade A/B/C grouping and convergence score columns removed from output.
- **CLI args removed:** `--min-convergence-score`, `--cluster-spread-pct`, `--min-cluster-size`, `--hide-grade-c`, `--rank-by convergence`
- **`config/screener_config.yaml`** — Removed `min_convergence_score` from large_cap and high_octane profiles
- **`config/strategies/example_trailing.yaml`** — Removed `min_convergence_score` reference
- **`tests/test_trend_screener.py`** — Removed convergence-specific tests; ranking tests rewritten for `setup` and `rs` criteria

### Changed
- **Default ranking** changed from `convergence` to `setup` (entry-ready stocks first, then proximity, then Stage 2 score)
- **`setup_type` label** changed from `'convergence'` to `'trend'` when no VCP/pivot is detected
- **Output format** is now a single ranked table instead of Grade A/B/C groups

### Preserved
- `calculate_convergence_score()` and `get_convergence_grade()` remain in `traderlib/stage2_utils.py` for use by `entry_signals.py` and other single-ticker analysis tools
- `tests/test_ma_convergence.py` unchanged

---

## [0.6.19.1] — 2026-05-31 — Fix — Sync Merge Position State + Minimal Audit Logging
```

- [ ] **Step 3: Commit**

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: bump version to 0.6.19.2

Remove non-functional convergence scoring from trend screener.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
python3 -m pytest tests/test_trend_screener.py tests/test_ma_convergence.py -v
```

Expected: All pass.

- [ ] **Step 2: Syntax check modified files**

```bash
python3 -m py_compile scripts/trend_screener.py
python3 -m py_compile tests/test_trend_screener.py
```

- [ ] **Step 3: Verify no residual convergence in screener**

```bash
grep -n "convergence\|grade\|Grade" scripts/trend_screener.py
```

Expected: Zero matches (or only in comments/docstrings, which is acceptable).

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Remove convergence imports, calculation, result fields | Task 1 |
| Rename `setup_type` `'convergence'` → `'trend'` | Task 1 |
| Remove grade grouping, show single table | Task 2 |
| Remove convergence columns from output | Task 2 |
| Remove CLI args | Task 3 |
| Change `--rank-by` default to `setup` | Task 3 |
| Update config files | Task 4 |
| Rewrite tests | Task 5 |
| Verify no convergence output | Task 6 |
| Version bump + changelog | Task 7 |
| Full test suite pass | Task 8 |
| `stage2_utils.py` untouched | Out of scope (verified by not touching it) |
| `entry_signals.py` still works | Out of scope (verified by not touching it) |

**No gaps found.**

---

## Placeholder Scan

Search plan for red flags:
- "TBD" — None found
- "TODO" — None found
- "implement later" — None found
- "fill in details" — None found
- "Add appropriate error handling" — None found
- "Write tests for the above" — None found; all test steps show actual code
- "Similar to Task N" — None found; each task is self-contained

**Clean.**

---

## Rollback

If issues arise, the changes are contained to 4 files. A git revert of the commits would restore convergence functionality entirely. The library functions in `stage2_utils.py` were never touched.
