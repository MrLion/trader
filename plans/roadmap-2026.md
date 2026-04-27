# Product Roadmap 2026

**Created:** 2026-04-26
**Latest Shipped:** 0.6.13.2

**Note:** This roadmap uses 4-digit versioning `WW.XX.YY.ZZ`. All planned work appears in the **Version Summary** table below.

---

## Overview

This roadmap outlines the strategic direction for the trader project from its current state through v0.6.18.0. The progression prioritizes:

1. **Safety (v0.6.14.0)** — FMP Economic Calendar (ready to implement)
2. **Safety (v0.6.15.0)** — Live state isolation
3. **Insight (v0.6.16.0)** — Analytics & journaling
4. **Capability (v0.6.17.0)** — Config + new capabilities
5. **Accessibility (v0.6.18.0)** — Wrap proven features in approachable web UI

---

## Version Summary

**Format:** `WW.XX.YY.ZZ` — WW=Super, XX=Major, YY=Minor, ZZ=Patch

| Version | Status | Phase | Theme | Focus | Plan |
|---------|--------|-------|-------|-------|------|
| 0.6.12.1 | ✅ Shipped | — | — | Trailing exits | — |
| 0.6.13.0 | ✅ Shipped | — | — | Backtest config tracking | [plan](plans/archive/plan-backtest-config-tracking.md) |
| 0.6.13.1 | ✅ Shipped | — | — | Equity CSV fix | — |
| 0.6.13.2 | ✅ Shipped | — | — | Test order UUID fix | — |
| **0.6.14.0** | 📋 Ready | 1 | **Safety** | FMP Economic Calendar | [spec](plans/spec-fmp-economic-calendar.md) / [impl](docs/superpowers/plans/impl-fmp-economic-calendar.md) |
| 0.6.15.0 | ⏳ TBD | 2 | **Safety** | Live state isolation | — |
| 0.6.16.0 | ⏳ TBD | 3 | **Insight** | Analytics & journaling | — |
| 0.6.17.0 | ⏳ TBD | 4 | **Capability** | Config + capabilities | — |
| 0.6.18.0 | ⏳ TBD | 5 | **Accessibility** | Web dashboard | — |

---

## Decision Log

- **Web UI last (not first):** Trading engine must be proven before building UIs around it
- **FastAPI + HTMX (not React):** Simpler stack for personal dashboard; can migrate to React later if needed
- **4-digit versioning:** Follows project convention (0.XX.YY.ZZ)

---

## Next Steps

When ready to begin:
1. Pick Phase 1 (0.6.14.0) for implementation — FMP Economic Calendar is ready
2. Create implementation plan for Phase 2 with the `writing-plans` skill
3. Execute phase-by-phase

---

*This roadmap is a living document. Update as priorities shift or new insights emerge.*
