# Plan: Paper Engine TUI Dashboard

**Date:** 2026-04-27
**Status:** In Progress -- design approved, ready for implementation
**Design Doc:** [docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md](docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md)
**Demo Script:** [scripts/demo_dashboard.py](scripts/demo_dashboard.py)

---

## Background

The paper engine (`paper_engine_alpaca.py`) outputs status via `print()` statements that scroll off-screen. A trader running the engine cannot glance at terminal state -- they must scroll back through hundreds of lines or run `paper_portfolio.py status` separately. This is a daily friction point.

The TUI dashboard replaces the scroll with a single-screen, full-width, color-coded dashboard using the `rich` library. No vertical dividers. No emojis. Horizontal rules only.

---

## Goals

1. Engine state visible at a glance while it runs
2. No new infrastructure -- terminal-only, `rich` dependency only
3. Graceful fallback to plain text if `rich` unavailable
4. No changes to trading logic -- purely display layer

---

## Implementation Phases

### Phase 1 -- Core Dashboard Module (traderlib/dashboard.py)
- `Dashboard` class with `rich.live.Live` screen mode
- `update(state_dict)` -- refreshes all sections
- `log_event(event_dict)` -- adds event to bounded queue (stores 20, displays 8)
- Section renderers: `HeaderRenderer`, `StatsRenderer`, `PositionsRenderer`, `ActivityLogRenderer`, `FooterRenderer`
- Fallback: if `rich` import fails, methods become no-ops

### Phase 2 -- Engine Integration (scripts/paper_engine_alpaca.py)
- Initialize `self.dashboard` in `AlpacaPaperEngine.__init__`
- Modify `_print_status()`: build `state_data` dict and call `self.dashboard.update(state_data)`. If dashboard unavailable, fall back to original `print()` logic.
- Modify event logging: call `self.dashboard.log_event(...)` first, then still `print()` the event line as fallback. If dashboard unavailable, only `print()` executes.
- Wrap all dashboard calls in try/except to prevent engine crash
- Add `Ctrl+C` cleanup: `Live` context manager must exit cleanly. Ensure `signal.signal(SIGINT)` handler calls `live.stop()` before shutting down.

**Why dual path:** The dashboard and plain-text output coexist. If `rich` is missing or terminal is non-TTY, the `print()` calls still fire. This is safer than replacing `print()` entirely.

### Phase 3 -- Testing
- `test_dashboard_render()` -- mock state, verify sections render
- `test_color_coding()` -- verify green/red for profit/loss
- `test_responsive_columns()` -- verify column collapse at breakpoints
- `test_fallback_mode()` -- mock missing `rich`, verify engine still prints
- `test_ctrl_c_graceful_shutdown()` -- verify `Live` context manager exits cleanly on SIGINT
- Integration: run engine for 5 minutes, verify no screen corruption

### Phase 4 -- Dependency Update
- Add `rich >= 13.0.0` to `pyproject.toml`

### Phase 5 -- Documentation
- Update `docs/TOOLS.md` to document the dashboard output and `--no-dashboard` flag (if any)
- Update `docs/getting-started.md` to mention the new dashboard experience

---

## Files Affected

| File | Change |
|---|---|
| `traderlib/dashboard.py` | **New** -- Dashboard class and all renderers |
| `scripts/paper_engine_alpaca.py` | Modify -- Wire dashboard into engine lifecycle; keep print fallback |
| `tests/test_dashboard.py` | **New** -- Unit and integration tests |
| `pyproject.toml` | Add `rich >= 13.0.0` dependency |
| `docs/TOOLS.md` | Update -- Document dashboard behavior |
| `scripts/demo_dashboard.py` | **Keep** -- Demo script for future reference |

---

## Rollback Plan

If the dashboard causes issues in production:
1. Remove `self.dashboard` initialization from `AlpacaPaperEngine.__init__`
2. Revert `_print_status()` to original `print()` logic
3. Revert event logging to original `print()` statements
4. The `traderlib/dashboard.py` file can remain -- it is harmless if not instantiated

---

## Acceptance Criteria

- [ ] Dashboard renders all sections with real engine data
- [ ] Colors update live (green/red for P&L, current vs entry)
- [ ] Activity log shows last 8 events in 2 columns
- [ ] Engine runs normally if `rich` is not installed (fallback mode)
- [ ] No vertical dividers anywhere in output
- [ ] Full terminal width used (no narrow centered boxes)
- [ ] `Ctrl+C` still shuts down engine gracefully; terminal restored to normal state
- [ ] Documentation updated (`TOOLS.md`, `getting-started.md`)
