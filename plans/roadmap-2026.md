# Product Roadmap 2026

**Created:** 2026-04-26
**Latest Shipped:** 0.6.14.1

**Note:** This roadmap uses 4-digit versioning `WW.XX.YY.ZZ`. All planned work appears in the **Version Summary** table below.

---

## Overview

This roadmap outlines the strategic direction for the trader project from its current state through v0.6.19.0. The progression prioritizes:

1. **Safety (v0.6.14.0)** -- FMP Economic Calendar (ready to implement)
2. **UX (v0.6.15.0)** -- TUI Dashboard for Paper Engine (in progress)
3. **Safety (v0.6.16.0)** -- Live state isolation
4. **Insight (v0.6.17.0)** -- Analytics & journaling
5. **Capability (v0.6.18.0)** -- Config + new capabilities
6. **Accessibility (v0.6.19.0)** -- Wrap proven features in approachable web UI

---

## Version Summary

**Format:** `WW.XX.YY.ZZ` -- WW=Super, XX=Major, YY=Minor, ZZ=Patch

| Version | Status | Theme | Focus | Plan |
|---------|--------|-------|-------|------|
| 0.6.12.0 | Shipped | -- | Trailing exits | -- |
| 0.6.13.0 | Shipped | -- | Backtest config tracking + fixes | [plan](plans/archive/plan-backtest-config-tracking.md) |
| **0.6.14.0** | Shipped | **Safety** | FMP Economic Calendar | [spec](plans/spec-fmp-economic-calendar.md) / [impl](docs/superpowers/plans/impl-fmp-economic-calendar.md) |
| **0.6.15.0** | In Progress | **UX** | TUI Dashboard for Paper Engine | [design](docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md) / [plan](plans/plan-paper-engine-dashboard.md) |
| 0.6.16.0 | TBD | **Safety** | Live state isolation | -- |
| 0.6.17.0 | TBD | **Insight** | Analytics & journaling | -- |
| 0.6.18.0 | TBD | **Capability** | Config + new capabilities | -- |
| 0.6.19.0 | TBD | **Accessibility** | Web dashboard | -- |

---

## Decision Log

- **Web UI last (not first):** Trading engine must be proven before building UIs around it
- **FastAPI + HTMX (not React):** Simpler stack for personal dashboard; can migrate to React later if needed
- **4-digit versioning:** Follows project convention (0.XX.YY.ZZ)

---

## Why TUI Dashboard (v0.6.15.0)

The paper engine currently dumps status via `print()` into an endless scroll. A trader running the engine cannot glance at terminal state -- they must scroll back through hundreds of lines or run `paper_portfolio.py status` separately. This is a daily friction point for anyone using the engine during market hours.

A TUI dashboard solves this without adding web infrastructure. It is:
- **Immediate** -- engine state visible at a glance while it runs
- **Self-contained** -- no browser, no server, no dependencies beyond `rich`
- **Consistent** -- same visual language as existing reports (backtest output, etc.)
- **Fallback-safe** -- if `rich` is unavailable, the engine falls back to plain text

This is a UX investment that pays off every trading session. It does not change trading logic -- it makes the existing logic observable.

---

## Next Steps

When ready to begin:
1. Phase 1 (0.6.14.0) -- FMP Economic Calendar is ready to implement
2. Phase 2 (0.6.15.0) -- TUI Dashboard is in progress; see [plan](plans/plan-paper-engine-dashboard.md)
3. Execute phase-by-phase

---

*This roadmap is a living document. Update as priorities shift or new insights emerge.*
