# Test Isolation Hardening — Plan

**Goal:** Make pytest runs provably safe for production data. Three classes of path-resolution sites in production code currently ignore `PAPER_TRADING_DATA_DIR` and write to the real `data/`, `logs/`, `reports/`, `scans/`, or `backtests/` directories during tests. Fix all three classes, add a conftest guardrail that catches any future regression, and pin the invariant with tests.

**Approach:** One canonical helper module (`traderlib/paths.py`) that every path-resolution site uses. The helper has a no-side-effect, no-mkdir, no-import-time-I/O contract. A conftest fixture snapshots the production data tree recursively and fails the test run if anything changed. Three new test files pin the invariants: the helper itself, the no-import-time-write guarantee, and the safety-net fixture. No changes to the public surface of any module — `DATA_DIR`, `POSITIONS_FILE`, etc. remain importable; they just call the helper.

**Why this is structural, not tactical:** The May 6 incident (commit `0fa7bd0`) restored `positions.json` and `trades.jsonl` from backup after a test run corrupted production data. That fix patched two test files but did not change the production code. The same pattern of `Path(__file__).parent.parent` at module import time persisted across 13+ sites. A separate class — 17 hardcoded absolute paths to `/Users/mintmrlion/.openclaw/workspaces/trader/...` — was never addressed at all. This plan closes all three classes of bugs once, for current and future modules.

## Data flow

```
test setup
   │
   ▼
conftest loads → os.environ['PAPER_TRADING_DATA_DIR'] = tmp
   │
   ▼
test imports module → module imports traderlib.paths → data_dir() reads env var → returns tmp
   │
   ▼
test calls function → function writes to data_dir() / 'foo.json' → file lands in tmp
   │
   ▼
test session ends
   ├── conftest asserts production data/ unchanged (mtime + size + sha256 for files <1MB)
   └── conftest asserts no new top-level subdirs under data/
   │
   ▼
if any change detected → hard fail with diff report:
   "Production data modified: data/logs/trading_exceptions.log gained 12 lines"
```

---

## Pre-work: worktree relocation (must happen before Task 1)

**Who:** Whoever runs Task 1.

**Why:** The current worktree is registered to git as a *nested* worktree at `dashboard-ux/.claude/worktrees/test-isolation/`. Any new files created in it land on the dashboard-ux filesystem under that path. If the dashboard-ux worktree is later removed, the new files are deleted from disk. A separate orphan directory at `trader/.claude/worktrees/test-isolation/` (no `.git` file, not a registered worktree) is leftover from a prior session and must be cleaned up.

**What:**
1. From main worktree at `/Users/mintmrlion/.openclaw/workspaces/trader/`, run `git worktree remove .claude/worktrees/dashboard-ux/.claude/worktrees/test-isolation --force` to unregister the nested worktree.
2. Delete the orphan directory: `rm -rf /Users/mintmrlion/.openclaw/workspaces/trader/.claude/worktrees/test-isolation/`.
3. Create a clean sibling worktree: `git worktree add -b claude/test-isolation-fix-v2 .claude/worktrees/test-isolation main` from main. New branch off current `main` (commit `6d3c5ce`).
4. Copy the plan file into the new worktree: `cp .claude/worktrees/dashboard-ux/.claude/worktrees/test-isolation/docs/superpowers/plans/2026-06-06-test-isolation-hardening.md .claude/worktrees/test-isolation/docs/superpowers/plans/`.
5. Verify: `git worktree list` shows the new worktree as a sibling of `dashboard-ux`, not nested.
6. Verify: `git -C .claude/worktrees/test-isolation status` shows only the plan file as untracked, on branch `claude/test-isolation-fix-v2`.

**Definition of done:** New worktree is a sibling of `dashboard-ux`, the plan file is present, the orphan is gone, the nested registration is gone. The plan is now ready to implement.

---

## File map

| File | Action | Class | Responsibility |
|------|--------|-------|----------------|
| `traderlib/paths.py` | CREATE | helper | `project_root()` and `data_dir()`. Honors `PAPER_TRADING_DATA_DIR`. The single source of truth for path resolution. |
| `traderlib/paper_state.py` | MODIFY | env-var | Existing pattern; convert to helper call, keep module-level constants (`DATA_DIR`, `POSITIONS_FILE`, etc.) as computed names for backward compat. |
| `traderlib/order_manager.py` | MODIFY | env-var | Same. |
| `scripts/paper_portfolio.py` | MODIFY | env-var | Same. |
| `scripts/paper_engine_alpaca.py` | MODIFY | env-var | Same; also migrate the post-market loader's `Path(__file__).parent.parent` (line ~1584). |
| `traderlib/trading_exceptions.py` | MODIFY | eager | Lazy-init the logger. Move `mkdir` and `FileHandler` setup into `_ensure_logger()`. Import alone creates no files. |
| `traderlib/alpaca_client.py` | MODIFY | relative | Replace `PROJECT_ROOT` constant and the absolute path on line 109. |
| `traderlib/sector_resolver.py` | MODIFY | relative | Replace `_PROJECT_ROOT`. |
| `traderlib/earnings_calendar.py` | MODIFY | relative | Replace `_PROJECT_ROOT`. |
| `traderlib/economic_calendar.py` | MODIFY | relative | Replace `_PROJECT_ROOT`. |
| `traderlib/strategy_config.py` | MODIFY | relative | Replace `_CONFIG_DIR`. |
| `traderlib/risk_config.py` | MODIFY | relative | Replace `repo_root` in `__init__`. |
| `traderlib/universe_builder.py` | MODIFY | relative | Replace `UNIVERSES_DIR` and `config_path`. |
| `traderlib/rate_limiter.py` | MODIFY | relative + absolute | Replace both: line 251 (relative) and line 246 (absolute). |
| `traderlib/backtest/earnings_provider.py` | MODIFY | relative | Replace `cache_dir`. |
| `scripts/setup_alpaca.py` | MODIFY | relative | Replace `PROJECT_ROOT`. |
| `scripts/sector_scan_comprehensive.py` | MODIFY | relative + absolute | Replace `_CONFIG_PATH` and line 127 absolute. |
| `scripts/clean_test_trades.py` | MODIFY | relative + absolute | Replace both. |
| `scripts/deliver_report.py` | MODIFY | relative | Replace `PROJECT_ROOT`. |
| `scripts/entry_signals.py` | MODIFY | relative | Replace `DATA_DIR` and `SCANS_DIR`. |
| `scripts/backtest.py` | MODIFY | relative | Replace `PROJECT_ROOT` (line 19). |
| `scripts/doctor.py` | MODIFY | relative | Replace `PROJECT_ROOT`. |
| `scripts/mcstock_scraper.py` | MODIFY | relative | Replace `PROJECT_ROOT` (line 78). |
| `scripts/premarket_report.py` | MODIFY | absolute | Replace 3 absolute paths (lines 27, 880, 1019). |
| `scripts/postmarket_report.py` | MODIFY | absolute | Replace 2 absolute paths (lines 28-29). |
| `scripts/watchlist_manager.py` | MODIFY | absolute | Replace 3 absolute paths (lines 91-92, 251). |
| `scripts/sync_state.py` | MODIFY | absolute | Replace 3 absolute paths (lines 12-13, 95). |
| `tests/conftest.py` | MODIFY | test infra | Add `assert_clean_production_data` session-scope fixture. |
| `tests/_isolation_check.py` | CREATE | test infra | Helper module: recursive snapshot, diff, report. Private to tests. |
| `tests/test_paths.py` | CREATE | test infra | Pins the helper's contract. |
| `tests/test_no_import_writes.py` | CREATE | test infra | Subprocess-based test that `import traderlib.trading_exceptions` writes nothing. |
| `tests/test_isolation_check.py` | CREATE | test infra | Pins the conftest safety-net fixture's contract. |
| `tests/test_no_hardcoded_paths.py` | CREATE | test infra | Grep-as-test: any new `Path(__file__).parent.parent` or `/Users/mintmrlion/.openclaw/workspaces/trader` in production code fails the test. |

**Total: 7 new files, 21 modified files.** The 21 modifications split as: 4 sites that already use the env var (consolidation), 13 sites with relative-path pollution (the original plan scope), 4 scripts with absolute-path pollution (the gap found in review).

---

## Task 1 — Create the helper module

**Who:** New file `traderlib/paths.py`.

**Why:** Centralizing path resolution means every module gets `PAPER_TRADING_DATA_DIR` for free. The leading-underscore convention is wrong here — this is the public import path for all path resolution. A new contributor should be able to `from traderlib.paths import data_dir` without thinking.

**What:** A module with two functions, no global state, no module-level path constants, no I/O at import time.

**How (behavior, not code):**
- `project_root()` returns the repo root, computed as `Path(__file__).resolve().parent.parent`. The `.resolve()` call matters: it follows symlinks. The result is fixed — no env var influence.
- `data_dir()` returns the writable data directory, computed as `Path(os.environ['PAPER_TRADING_DATA_DIR'])` if the env var is set, else `project_root() / 'data'`. The env var is read on every call (no caching). No `mkdir`, no side effects.
- No global module state. The two functions are pure reads of the env var at call time.
- This is the only new file in Task 1.

**Files:**
- Create: `traderlib/paths.py`
- Create on demand: nothing

**Definition of done:** `tests/test_paths.py` passes 6 assertions:
1. With `PAPER_TRADING_DATA_DIR` unset, `data_dir()` returns `<project_root>/data`.
2. With `PAPER_TRADING_DATA_DIR` set to a tmp path, `data_dir()` returns that tmp path.
3. `project_root()` does not depend on the env var (set/unset produces same result).
4. Calling `data_dir()` does not create any directory (no side effects).
5. Calling `data_dir()` twice with the env var changed between calls returns the new value (not cached).
6. `project_root()` follows symlinks (`.resolve()` semantics): if `traderlib/paths.py` is reached via a symlink, `project_root()` returns the resolved path, not the symlink path.

---

## Task 2 — Migrate `trading_exceptions.py` (the worst offender)

**Who:** `traderlib/trading_exceptions.py`.

**Why:** This module runs `mkdir` and attaches a `FileHandler` at **import time** to a hardcoded production log path. Even `with patch.dict(os.environ, ...)` at test time can't fix it because the import has already happened. This is the source of every `trading_exceptions.log` pollution line in the recent git diff.

**What:** Replace module-level `LOG_DIR`/`LOG_FILE` constants and the eager `TimedRotatingFileHandler` attachment with a lazy initializer. The logger is set up the first time any logging method runs, not at import time.

**How (behavior, not code):**
- Move the `TimedRotatingFileHandler` setup into a `_ensure_logger()` function that runs once, lazily.
- `_ensure_logger()` computes `LOG_DIR = data_dir() / 'logs'` and `LOG_FILE = LOG_DIR / 'trading_exceptions.log'` on first call.
- The `mkdir(parents=True, exist_ok=True)` moves into `_ensure_logger()` — it creates the dir under `data_dir()`, which is the test tmp when conftest sets the env var.
- Existing `critical()` / `error()` / `warning()` decorators and `TradingExceptionHandler` class methods keep their public signatures.
- An `import traderlib.trading_exceptions` call creates no files and attaches no handlers.

**Files:**
- Modify: `traderlib/trading_exceptions.py`
- Modify: `tests/test_trading_exceptions.py` (if it exists; add minimal test if not)

**Definition of done:** Three invariants, each with a test:

1. **No-import-time-write invariant:** A subprocess test in `tests/test_no_import_writes.py` runs `import traderlib.trading_exceptions` in a fresh Python interpreter with `PAPER_TRADING_DATA_DIR` unset. It asserts that no file was created in `<production>/data/logs/` and that no `FileHandler` is attached to the `trading` logger.

2. **Lazy-init on first call:** `tests/test_trading_exceptions.py` calls `trading_exceptions.log_exception("op", ValueError("x"))` with `PAPER_TRADING_DATA_DIR` set to tmp, asserts a file at `data_dir() / 'logs' / 'trading_exceptions.log'` and zero files at `<production>/data/logs/`.

3. **No double-init:** Calling `log_exception` twice in the same process results in exactly one `FileHandler` on the logger (not two). Test inspects `len(logging.getLogger('trading').handlers)`.

---

## Task 3 — Migrate the 20 remaining path-resolution sites

**Who:** Each of the 20 files in the file map.

**Why:** Every site that does `Path(__file__).parent.parent` at module import time, or hardcodes `/Users/mintmrlion/.openclaw/workspaces/trader/...`, is a potential pollution point. Centralizing them via `data_dir()` means the env var is honored everywhere and the code becomes portable (no more `/Users/mintmrlion/` baked in).

**What:** For each site, replace the hardcoded path with a call to the helper.

**How (behavior, not code):**
- For **module-level constants** (e.g., `DATA_DIR = Path(__file__).parent.parent / 'data'`): replace with a function call at module scope. The helper itself does no I/O, so import-time calls are safe. Keep the constant name and assignment: `DATA_DIR = data_dir()`. This preserves the public surface (importers of `DATA_DIR` still work).
- For **local `repo_root = Path(__file__).parent.parent` inside a method**: replace with a call to `data_dir().parent` or `project_root()`, whichever is appropriate. (For the 4 sites that already use the env-var pattern, just call `data_dir()` directly.)
- For **the post-market loader in `paper_engine_alpaca.py`** (line ~1584, currently a free function): replace `Path(__file__).parent.parent` with `data_dir().parent` or `project_root()`, then use `data_dir() / mode / 'positions.json'`.
- For **the 17 absolute-path sites** in `scripts/premarket_report.py`, `scripts/postmarket_report.py`, `scripts/watchlist_manager.py`, `scripts/sync_state.py`, `scripts/sector_scan_comprehensive.py`, `scripts/clean_test_trades.py`, `scripts/paper_portfolio.py`, `scripts/paper_engine_alpaca.py`, `scripts/rate_limiter.py`, `scripts/alpaca_client.py`: replace `/Users/mintmrlion/.openclaw/workspaces/trader/...` with `data_dir() / ...` (for the data subtree) or `project_root() / ...` (for the rest). The existing `DEFAULT_DATA_DIR` constants in 4 of these files become `data_dir()` at module scope — but where the constant was used as a fallback for the env var, the helper now provides the fallback natively.
- For **constant `DEFAULT_DATA_DIR = Path('/Users/mintmrlion/...')` in 4 scripts** (`paper_engine_alpaca.py:42`, `paper_portfolio.py:25`, `clean_test_trades.py:36`, `paper_state.py:41`): remove the absolute path, rely on the helper's built-in fallback. The fallback goes from `/Users/.../data` to `project_root() / 'data'`, which is portable. The 4 files that already use the env-var pattern can drop their `DEFAULT_DATA_DIR` constants entirely.
- The `mkdir(parents=True, exist_ok=True)` calls move with the path — they stay where they are now, just with a different base.
- Public function signatures and behavior do not change.
- `sys.path.insert(0, str(Path(__file__).parent.parent))` lines are **out of scope** for this task — they affect import resolution, not data path resolution.

**Files:** See file map. 20 files.

**Definition of done:** Two tests pin this invariant:

1. `tests/test_no_hardcoded_paths.py` greps `traderlib/` and `scripts/` for `Path(__file__).parent.parent` and `/Users/mintmrlion/.openclaw/workspaces/trader`. The grep must return zero matches. The test runs as part of the regular suite (no opt-out marker).

2. The 26 pre-existing test failures from the baseline (`commit 6d3c5ce`) are allowed to change in count and content. The plan does not require parity. The plan requires: (a) no test imports a module that writes to production data, (b) the conftest safety net reports zero changes to production data. The two metrics are reported separately in the verification report.

---

## Task 4 — Conftest safety net

**Who:** `tests/conftest.py` and a new `tests/_isolation_check.py`.

**Why:** Even with all path-resolution sites migrated, a future contributor can write a new module that hardcodes a path. The `test_no_hardcoded_paths.py` test catches that, but only for the specific patterns we grep for. A safety net that observes *runtime behavior* (was anything in `data/` actually written?) is the second line of defense.

**What:** A session-scope fixture that recursively snapshots the production data tree at session start and asserts the snapshot is unchanged at session teardown.

**How (behavior, not code):**
- The fixture runs once per `pytest` invocation, before any test.
- Snapshot: walk `<project_root>/data/` recursively. For each file, record `(relpath, mtime_ns, size, sha256)`. For each directory, record `(relpath, listing)`. Store the snapshot in a module-level variable in `tests/_isolation_check.py`.
- At teardown, after all tests: walk the tree again, diff against the snapshot. Any change is a hard failure with a clear message: "Test run modified production data: `data/logs/trading_exceptions.log` gained 12 lines (was 0 bytes, now 0 bytes + content). Use `@pytest.mark.allow_production_writes` on tests that intentionally touch production paths."
- Hash only files <1MB. For files ≥1MB, compare `(mtime, size)` only. Hash algorithm: sha256 (cryptographic, future-proof; md5 would be faster but not worth the audit surface).
- New top-level subdirs under `data/` are also a failure. The fixture snapshots the top-level listing at start; any new entry at end is a failure.
- The `@pytest.mark.allow_production_writes` marker opts a test out. The marker is registered in `tests/conftest.py`. Opting out means the test *itself* is allowed to write, but the fixture still runs at session scope — other tests are still protected.
- The fixture is opt-out via a CLI flag for ad-hoc debugging: `pytest --no-isolation-check`. The flag is read from `sys.argv` in conftest.
- The orphan top-level worktree directory at `/Users/mintmrlion/.openclaw/workspaces/trader/.claude/worktrees/test-isolation/` is not under `data/`, so the fixture does not see it. (Cleaned up in the pre-work step.)

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/_isolation_check.py`

**Definition of done:** `tests/test_isolation_check.py` passes 4 assertions:

1. The fixture passes when no test touches production data. Test: run the fixture directly with a clean data tree, assert no diff.
2. The fixture fails when a test creates a file under `data/`. Test: monkeypatch a fake test that writes to `data/_isolation_test_artifact.txt`, run the fixture, assert it reports the new file.
3. The `@pytest.mark.allow_production_writes` marker bypasses the check. Test: mark a test that writes to `data/`, run the fixture, assert no failure from that test (other tests still subject).
4. The `--no-isolation-check` CLI flag disables the fixture. Test: invoke `pytest` in a subprocess with the flag, assert the fixture's setup function was not called.

---

## Task 5 — Baseline verification

**Who:** Full test suite.

**Why:** The plan changes path resolution in 21+ files. Mechanical but broad. Need to confirm the conftest safety net reports zero pollution and that no production code still hardcodes a path.

**What:** Run the full test suite, capture three separate reports, and commit them alongside the patch.

**How (behavior, not code):**
- Run `pytest tests/ -q --no-cov`. Capture: (a) the standard pass/fail report, (b) the conftest safety-net report, (c) the `test_no_hardcoded_paths.py` report.
- The pass/fail report: count of unique failures. Allowed to differ from the 26-baseline, as long as no failure is caused by pollution reaching production data.
- The conftest safety-net report: must be "0 production data changes."
- The `test_no_hardcoded_paths.py` report: must be "0 matches for `Path(__file__).parent.parent` in `traderlib/` and `scripts/`."
- The `data/logs/trading_exceptions.log` last-line timestamp must be older than the test run start time, proving no log lines were appended.
- A `verify/2026-06-06-test-isolation-hardening.md` file is written with the three reports and the timestamp check.

**Files:**
- Create: `verify/2026-06-06-test-isolation-hardening.md`

**Definition of done:** `verify/2026-06-06-test-isolation-hardening.md` exists and contains:
1. The pytest summary line (e.g., "53 passed, 26 failed in 12.3s").
2. The conftest safety-net line (e.g., "Production data unchanged: 0 changes across 47 files in 5 subdirs.").
3. The grep result (e.g., "0 matches for `Path(__file__).parent.parent` in `traderlib/` and `scripts/`.").
4. The timestamp check (e.g., "data/logs/trading_exceptions.log mtime: 2026-04-29 14:32:00, test run start: 2026-06-06 16:45:12. No log lines appended during run.").
5. A one-line note acknowledging that 26 unique failures from the pre-existing baseline may change in count and content, and that's expected.

---

## Out of scope

- The dashboard UX plan (`docs/superpowers/plans/2026-06-06-dashboard-ux-improvements.md`). It can resume after this plan lands.
- The `data/paper_positions.json.backup` and `data/paper_trades.jsonl.backup` files left over from the May 6 incident. They predate this plan.
- The 26 pre-existing test failures. They are out of scope for this plan; they get their own investigation. Their count and content are allowed to change after this plan lands.
- Performance. The helper functions add no measurable cost — they are env-var reads at call time. The conftest's recursive walk is bounded by the size of `data/` (~50 files today, sub-second on macOS).
- `sys.path.insert(0, str(Path(__file__).parent.parent))` lines. They affect import resolution, not data path resolution, and they do not write to disk.
- Public API stability. The plan **preserves** the public surface — `DATA_DIR`, `POSITIONS_FILE`, `TRADES_FILE`, `DAILY_TRACKER_FILE` remain importable from `traderlib.paper_state`. They are now computed via the helper. Importers do not change. (This resolves the contradiction the previous draft had between "no public-surface change" and "importers will break.")

---

## Risk register

- **Helper import cycle risk:** `traderlib/paths.py` imports nothing from `traderlib/`. It only uses stdlib (`os`, `pathlib`). No cycle risk.
- **Module-level state migration:** The plan keeps module-level constants like `DATA_DIR` and `POSITIONS_FILE` importable, so no importer breaks. The constants now compute their value via the helper. The lazy initialization in `trading_exceptions` is the only place that breaks module-level eager behavior.
- **Eager vs lazy initialization in `trading_exceptions`:** The current code attaches the file handler at import time. After the migration, the first log call sets things up. This is functionally equivalent for production. For tests, it means the conftest's env-var setup must run before any module-level `trading_exceptions` import (which it does, since conftest loads at conftest-load time, before any test imports). Verified by the new `test_no_import_writes.py` test.
- **Conftest fixture timing:** The isolation check runs at session scope. If a test uses a subprocess that writes to production paths, the fixture won't catch it. Subprocess-based pollution is rare. The `test_no_import_writes.py` test uses subprocess deliberately and asserts no write happens — but it's testing `trading_exceptions`, not the safety net. The `--no-isolation-check` flag covers the case where a developer wants to skip the check for ad-hoc debugging.
- **Test data dir cleanup:** The conftest's existing `_cleanup_test_data` removes the test data temp dir at process exit. The new isolation check runs before cleanup, so it sees the production repo as it was at session start. No interaction.
- **Worktree relocation is a prerequisite:** If Task 1 is run from the nested worktree, files land in the wrong place on disk. The pre-work step is mandatory.
- **Helper's env-var read at call time vs. import time:** The helper re-reads on every call. A test that mutates `os.environ` mid-run gets fresh values. Verified by the new test in `test_paths.py` assertion 5.
- **Hashing large files:** The conftest hashes only files <1MB. For files ≥1MB, it compares `(mtime, size)`. A test that writes a large file to `data/` and resets its mtime would slip through. This is an acceptable trade-off: large files in `data/` are intentional, and a developer who writes a 1MB+ file to `data/` is a much louder signal than a 12-line log append. The `test_no_hardcoded_paths.py` test is the structural defense.

---

## Plan sequence

1. **Pre-work** — worktree relocation. Mandatory before any code is written.
2. **Task 1** (helper) — unblocks every other task. Run `tests/test_paths.py` to verify.
3. **Task 2** (`trading_exceptions`) — the worst offender; migrating it alone is a meaningful safety improvement. Run `tests/test_no_import_writes.py` and `tests/test_trading_exceptions.py` to verify.
4. **Task 3** (the 20 remaining sites) — bulk mechanical migration. Run `tests/test_no_hardcoded_paths.py` to verify.
5. **Task 4** (conftest safety net) — guards against future regressions. Run `tests/test_isolation_check.py` to verify.
6. **Task 5** (baseline verification) — confirms the change is behavior-preserving. Run full suite, write `verify/2026-06-06-test-isolation-hardening.md`.

Each task's test must pass before the next task starts. The 21 file modifications in Task 3 can be split into 4 sub-batches if useful (env-var consolidation → relative-path migration → absolute-path migration → conftest-side), but the order within Task 3 is flexible.

---

## Parallelization strategy

Three workstreams can run in parallel after Task 1 completes:

| Workstream | Modules | Files | Depends on |
|------------|---------|-------|------------|
| A: helper + tests | `traderlib/paths.py`, `tests/test_paths.py` | 2 new | nothing |
| B: lazy init | `traderlib/trading_exceptions.py`, `tests/test_no_import_writes.py`, `tests/test_trading_exceptions.py` | 1 new test, 1 modify | A |
| C: site migrations (env-var) | `traderlib/paper_state.py`, `traderlib/order_manager.py`, `scripts/paper_portfolio.py`, `scripts/paper_engine_alpaca.py` | 4 modify | A |
| D: site migrations (relative) | 11 files in `traderlib/` and `scripts/` | 11 modify | A |
| E: site migrations (absolute) | 4 scripts | 4 modify | A |
| F: safety net | `tests/conftest.py`, `tests/_isolation_check.py`, `tests/test_isolation_check.py`, `tests/test_no_hardcoded_paths.py` | 3 new, 1 modify | A |

Lanes (run in parallel where worktrees allow):
- **Lane 1:** A
- **Lane 2 (after A):** B, C, D, E in parallel
- **Lane 3 (after B, C, D, E, F):** F (safety net catches anything missed in B-E)
- **Lane 4 (after F):** Task 5 verification

Lane 1 must complete first (everyone imports the helper). Lane 2's four workstreams touch different files, so they can run in separate worktrees. Lane 3 needs everything merged because the safety net's test must observe all migration work. Lane 4 is sequential verification.

---

## Implementation tasks

Synthesized from this review. Each task derives from a specific finding. Run with Claude Code or Codex; checkbox as you ship.

- [ ] **T1 (P0, human: ~15min / CC: ~2min)** — Pre-work — Move worktree to sibling location, clean up orphan
  - Surfaced by: A1 (Architecture) — worktree nested in dashboard-ux, files would land in wrong place
  - Files: `git worktree` operations; no source files
  - Verify: `git worktree list` shows the new worktree as a sibling of `dashboard-ux`; orphan is gone
- [ ] **T2 (P0, human: ~30min / CC: ~5min)** — Task 1 — Create `traderlib/paths.py` and `tests/test_paths.py`
  - Surfaced by: Architecture, Code Quality (C1, C2) — centralize env-var pattern, name the helper without leading underscore
  - Files: `traderlib/paths.py` (CREATE), `tests/test_paths.py` (CREATE)
  - Verify: `pytest tests/test_paths.py -v` passes 6 assertions
- [ ] **T3 (P0, human: ~1h / CC: ~10min)** — Task 2 — Lazy-init `trading_exceptions` and pin the invariant
  - Surfaced by: Architecture (A7), Tests (T2) — the no-import-time-write invariant is the whole point of the task
  - Files: `traderlib/trading_exceptions.py` (MODIFY), `tests/test_no_import_writes.py` (CREATE), `tests/test_trading_exceptions.py` (CREATE if missing)
  - Verify: subprocess test asserts `import traderlib.trading_exceptions` creates no files in production
- [ ] **T4 (P0, human: ~3h / CC: ~30min)** — Task 3 — Migrate 20 sites (4 env-var + 13 relative + 4 absolute)
  - Surfaced by: Architecture (A2) — 17 absolute-path sites missed by the original plan
  - Files: 4 env-var files (paper_state, order_manager, paper_portfolio, paper_engine_alpaca), 13 relative-path files, 4 absolute-path files (premarket_report, postmarket_report, watchlist_manager, sync_state, sector_scan_comprehensive, clean_test_trades, rate_limiter, alpaca_client, mcstock_scraper, doctor, entry_signals, deliver_report, setup_alpaca, paper_engine_alpaca, paper_portfolio, paper_state, backtest, clean_test_trades, rate_limiter, alpaca_client) — see file map
  - Verify: `pytest tests/test_no_hardcoded_paths.py -v` passes; conftest safety net reports 0 changes
- [ ] **T5 (P0, human: ~1h / CC: ~15min)** — Task 4 — Conftest safety net
  - Surfaced by: Architecture (A4, A6), Tests (T3) — the safety net needs a self-test; metric separation
  - Files: `tests/conftest.py` (MODIFY), `tests/_isolation_check.py` (CREATE), `tests/test_isolation_check.py` (CREATE), `tests/test_no_hardcoded_paths.py` (CREATE — duplicates the one in T4, consolidate)
  - Verify: `pytest tests/test_isolation_check.py -v` passes 4 assertions
- [ ] **T6 (P0, human: ~30min / CC: ~5min)** — Task 5 — Baseline verification
  - Surfaced by: Architecture (A4) — test failures and data pollution are different metrics
  - Files: `verify/2026-06-06-test-isolation-hardening.md` (CREATE)
  - Verify: file contains the three separate reports and the timestamp check
- [ ] **T7 (P2, human: ~10min / CC: ~2min)** — Documentation — Update TOOLS.md and CLAUDE.md to mention the helper and the safety net
  - Surfaced by: Code Style (CLAUDE.md) — "After adding or modifying any feature, always update the corresponding documentation file"
  - Files: `TOOLS.md`, `CLAUDE.md`
  - Verify: `grep -n "traderlib.paths\|allow_production_writes" TOOLS.md CLAUDE.md` finds both
- [ ] **T8 (P2, human: ~10min / CC: ~2min)** — Changelog — Add entry to CHANGELOG.md
  - Surfaced by: Code Style (CLAUDE.md) — version bump convention
  - Files: `CHANGELOG.md`, `VERSION`
  - Verify: a new entry exists under the next version number
