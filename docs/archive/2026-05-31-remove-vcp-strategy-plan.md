# Plan: Remove VCP Strategy Plugin System

## Context

The `traderlib/strategies/` module contains a strategy plugin architecture (`Strategy` ABC, registry, `StrategyContext`, `EntrySignal`, `CompositeStrategy`) plus two VCP strategy implementations (`vcp_large_cap`, `vcp_high_octane`). Investigation shows:

- **The VCP strategies are unused in production.** The running paper engine (`pid 13207`) was started without `--strategy`. The backtest default is `stage2_momentum` (a separate class in `traderlib/backtest/strategy.py`).
- **The VCP strategies duplicate existing systems.** Entry scanning is already done by `scripts/entry_signals.py` + `watchlist_manager.py populate`. Exit management is already done by `ExitEngine` (`paper_exits.py`) with hybrid mode from `risk_config.yaml`.
- **The plugin architecture has caused bugs.** The R-calculation bug (using `stop_price` instead of `initial_stop_price`) and the exit override issue (strategy `manage_exits()` skipping legacy `ExitEngine`) both stem from this unused code.
- **The backtest system genuinely uses the shared types.** `Stage2MomentumStrategy` subclasses `Strategy` ABC, and `BacktestStrategyContext` subclasses `StrategyContext`. These must survive in some form.

**Goal:** Remove the VCP strategy module and the plugin registry while keeping the backtest system functional.

---

## Approach

### 1. Move shared types into backtest (self-contained)

Move `EntrySignal`, `StrategyContext`, and `Strategy` ABC from `traderlib/strategies/__init__.py` into `traderlib/backtest/strategy.py`. The backtest system becomes self-contained — no dependency on a separate strategies module.

- `ExitAction` and `ExitActionType` already live in `traderlib/paper_exits.py`; `traderlib/backtest/strategy.py` should import them from there instead of from `traderlib.strategies`.
- `EntrySignal` and `StrategyContext` dataclasses move into `traderlib/backtest/strategy.py`.
- `Strategy` ABC moves into `traderlib/backtest/strategy.py`.
- Update `traderlib/backtest/__init__.py` re-exports.
- Update `traderlib/backtest/engine.py` imports (it already imports from `traderlib.backtest.strategy`).

### 2. Delete `traderlib/strategies/` directory

Remove:
- `traderlib/strategies/__init__.py`
- `traderlib/strategies/vcp_breakout.py`
- `traderlib/strategies/composite.py`

### 3. Simplify `scripts/paper_engine_alpaca.py`

Remove all strategy plugin code:
- Remove imports: `Strategy`, `StrategyContext`, `get_strategy`, `list_strategies`
- Remove `_load_strategy()` method
- Remove `_build_context()` method
- Remove `_process_exit_action()` method
- Remove strategy branch in `_check_exits()` (lines 969-977)
- Remove `--strategy` CLI argument
- Remove `strategy` parameter from `__init__`
- Remove `self.strategy` attribute

The engine will use only the legacy `ExitEngine` path for exits, which is what already happens in production.

### 4. Simplify `scripts/backtest.py`

Remove the plugin fallback path:
- Remove imports: `get_strategy`, `list_strategies`, `StrategyContext`
- Remove `_AVAILABLE_STRATEGIES = list_strategies()`
- Remove plugin instantiation path (the `else` branch after `if args.strategy == 'stage2_momentum'`)
- Keep only the direct `Stage2MomentumStrategy` instantiation
- Error message for unknown strategy should say "Only stage2_momentum is supported"

### 5. Delete VCP config files

Remove:
- `config/strategies/vcp_large_cap.yaml`
- `config/strategies/vcp_high_octane.yaml`

Keep `config/strategies/stage2_momentum.yaml` and `example_trailing.yaml`.

### 6. Delete tests

Remove:
- `tests/test_strategy_abc.py` (375 lines — tests registry and ABC)
- `tests/test_vcp_strategy.py` (421 lines — tests VCP strategies)
- `tests/test_composite_strategy.py` (436 lines — tests CompositeStrategy)
- `tests/test_vcp_breakout.py` (8 lines — minimal VCP test)

Update:
- `tests/test_backtest_cli.py` — remove strategy plugin references
- `tests/test_rdw_regression.py` — delete or rewrite to only test dashboard frozen indicator (move those tests into `test_dashboard.py`)

### 7. Update documentation

- `docs/strategies/OVERVIEW.md` — delete (or move to `docs/archive/`)
- `docs/strategies/VCP_BREAKOUT.md` — delete (or move to `docs/archive/`)
- `docs/ARCHITECTURE.md` — remove "Strategy Plugin Architecture" section
- `docs/README.md` — remove link to strategy plugin docs
- `TOOLS.md` — remove `--strategy` references for backtest
- `CLAUDE.md` — remove `strategies/` from core library section

### 8. Update `risk_config.yaml`

Remove the `strategy.manage_exits` toggle added in the previous fix (it becomes unnecessary when strategy plugins are gone).

---

## Architect Review Modifications

The following modifications were identified during architect review and should be applied during implementation:

### Mod 1: `scripts/backtest.py` — Deprecate `--strategy` instead of removing

Keep the `--strategy` CLI flag but make it a no-op. Always instantiate `Stage2MomentumStrategy` regardless of the flag value. Print a deprecation warning:
```
⚠️  --strategy is deprecated; only stage2_momentum is supported
```

**Why:** Avoids breaking existing scripts or muscle memory that passes `--strategy stage2_momentum`. The flag can be fully removed in a future release.

### Mod 2: Explicit preservation note — `traderlib/vcp_utils.py` and `traderlib/pivot_detection.py`

These modules contain VCP pattern detection used by `scripts/entry_signals.py` and `scripts/trend_screener.py`. They are actively used and must survive. The plan should explicitly state this to prevent accidental deletion during implementation.

### Mod 3: `traderlib/strategy_config.py` — Remove stale VCP references

The module-level docstring and `get_strategy_config` examples hardcode `vcp_large_cap` and `vcp_high_octane`. After removal, these become misleading. Update docstrings to use `stage2_momentum` as the example.

### Mod 4: Verify `config/strategies/example_trailing.yaml` is still needed

Check if `example_trailing.yaml` is referenced anywhere outside the strategy plugin system. If it was only for VCP strategy documentation, delete it alongside the VCP YAML files.

### Mod 5: `traderlib/backtest/strategy.py` — Clean up `__all__`

After inlining, `BaseStrategy` alias is unnecessary. Remove it from `__all__`. `Stage2MomentumStrategy` subclasses `Strategy(ABC)` directly.

### Mod 6: `traderlib/backtest/__init__.py` — Verify re-exports

After inlining, verify that re-exports still make sense. `ExitDecision` alias may still be needed for backward compatibility with tests. Remove any re-exports that are no longer defined in the module.

### Mod 7: CHANGELOG — Note temporary toggle removal

The `strategy.manage_exits` toggle was added in `0.6.18.2` as a safety mechanism to disable strategy exit overrides while the VCP bug was being fixed. It was always intended as a short-term guardrail, not a permanent configuration option. Now that the strategy plugin system itself is being removed, the toggle is naturally obsolete. The CHANGELOG should state this clearly: the toggle was a temporary safety measure that served its purpose and is removed because the feature it gated no longer exists.

### Mod 8: Explicit order of operations

The plan MUST be executed in this exact sequence to avoid broken imports:

1. **Inline types** into `traderlib/backtest/strategy.py` (make backtest self-contained)
2. **Update** `traderlib/backtest/__init__.py` re-exports
3. **Update** `scripts/paper_engine_alpaca.py` (remove strategy imports/code)
4. **Update** `scripts/backtest.py` (remove plugin path)
5. **Update tests** (`test_backtest_cli.py`, `test_dashboard.py`, etc.)
6. **ONLY THEN** delete `traderlib/strategies/` directory
7. **Delete** VCP config files
8. **Update** docs

**Why:** If you delete `traderlib/strategies/` before updating the scripts that import from it, `import` statements will fail immediately.

### Mod 9: `tests/test_backtest_cli.py` — Analyze before deleting

Read `tests/test_backtest_cli.py` before making changes. If it tests the `--strategy` plugin fallback path (e.g., `--strategy vcp_large_cap`), update or remove that test case. The test may need to be simplified to only test `--strategy stage2_momentum`.

### Mod 10: `traderlib/backtest/strategy.py` — Add circular import guard

After inlining, `traderlib/backtest/strategy.py` imports `ExitAction`/`ExitActionType` from `traderlib/paper_exits.py`. Add a defensive comment:

```python
# NOTE: This module imports from traderlib.paper_exits. Do NOT add imports
# from this module back into paper_exits to avoid circular dependencies.
```

**Why:** Prevents future developers from accidentally creating a circular dependency.

### Mod 11: `config/strategies/example_trailing.yaml` — Verify before keeping

Search the entire codebase for references to `example_trailing` before deciding to keep it. If unreferenced, delete it. If referenced by `stage2_momentum` or docs, keep it.

### Mod 12: Verification — Add `test_risk_config.py`

The verification list is missing `tests/test_risk_config.py`. Add:

```bash
python3 -m pytest tests/test_risk_config.py -v
```

**Why:** The plan removes `StrategyConfig` from `traderlib/risk_config.py`. Existing risk config tests may reference it.

### Mod 13: Backtest exit logic — Note independence

The backtest engine (`traderlib/backtest/engine.py`) uses `strategy.manage_exits()` and processes `ExitAction` objects internally. It does NOT use `ExitEngine` from `paper_exits.py`. This is pre-existing behavior and does not need changes. `Stage2MomentumStrategy.manage_exits()` will continue to work after inlining.

**Why:** Clarifies that the backtest exit system is independent from the paper engine's `ExitEngine`, and no exit logic changes are needed in the backtest.

---

## Files to Modify

| File | Action | Details |
|------|--------|---------|
| `traderlib/backtest/strategy.py` | **Edit** | Inline `EntrySignal`, `StrategyContext`, `Strategy` ABC; import `ExitAction`/`ExitActionType` from `paper_exits.py` |
| `traderlib/backtest/__init__.py` | **Edit** | Update re-exports |
| `traderlib/backtest/engine.py` | **Edit** | Verify imports still work (should be automatic) |
| `scripts/paper_engine_alpaca.py` | **Edit** | Remove all strategy plugin code (~50 lines) |
| `scripts/backtest.py` | **Edit** | Remove plugin path, keep only `Stage2MomentumStrategy` |
| `config/risk_config.yaml` | **Edit** | Remove `strategy.manage_exits` section |
| `traderlib/risk_config.py` | **Edit** | Remove `StrategyConfig` dataclass and parsing logic |
| `tests/test_dashboard.py` | **Edit** | Add dashboard frozen indicator tests (moved from `test_rdw_regression.py`) |
| `tests/test_backtest_cli.py` | **Edit** | Remove strategy plugin references |
| `traderlib/strategies/__init__.py` | **Delete** | |
| `traderlib/strategies/vcp_breakout.py` | **Delete** | |
| `traderlib/strategies/composite.py` | **Delete** | |
| `config/strategies/vcp_large_cap.yaml` | **Delete** | |
| `config/strategies/vcp_high_octane.yaml` | **Delete** | |
| `tests/test_strategy_abc.py` | **Delete** | |
| `tests/test_vcp_strategy.py` | **Delete** | |
| `tests/test_composite_strategy.py` | **Delete** | |
| `tests/test_vcp_breakout.py` | **Delete** | |
| `tests/test_rdw_regression.py` | **Delete** | (dashboard tests moved to `test_dashboard.py`) |
| `docs/strategies/OVERVIEW.md` | **Delete** | |
| `docs/strategies/VCP_BREAKOUT.md` | **Delete** | |
| `docs/ARCHITECTURE.md` | **Edit** | Remove strategy plugin section |
| `docs/README.md` | **Edit** | Remove strategy plugin link |
| `TOOLS.md` | **Edit** | Remove `--strategy` references |
| `CLAUDE.md` | **Edit** | Remove `strategies/` from core library |

---

## Verification

1. **Syntax check:** `python3 -m py_compile` on all modified `.py` files
2. **Backtest tests:** `python3 -m pytest tests/test_backtest_*.py -v` must pass
3. **Paper engine tests:** `python3 -m pytest tests/test_paper_engine_*.py -v` must pass
4. **Dashboard tests:** `python3 -m pytest tests/test_dashboard.py -v` must pass
5. **Integration tests:** `python3 -m pytest tests/test_integration_paper_engine.py -v` must pass
6. **Run paper engine:** `python3 scripts/paper_engine_alpaca.py --help` should show no `--strategy` flag
7. **Run backtest:** `python3 scripts/backtest.py --help` should show `--strategy` with only `stage2_momentum`

---

## Rollback

If issues arise, the commit can be reverted. The strategy plugin code is entirely self-contained in `traderlib/strategies/`; no other system depends on it except the backtest types (which will be inlined). A git revert would restore everything.
