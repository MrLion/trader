# Product Roadmap 2026

**Created:** 2026-04-26
**Latest Shipped:** 0.6.15.0

---

## Version Summary

**Format:** `WW.XX.YY.ZZ` -- WW=Super, XX=Major, YY=Minor, ZZ=Patch

| Version | Status | Theme | Focus | Plan |
|---------|--------|-------|-------|------|
| **0.6.15.0** | Shipped | **UX** | TUI Dashboard for Paper Engine | [design](docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md) / [plan](plans/plan-paper-engine-dashboard.md) |
| **0.6.15.10** | Shipped | **UX** | Dashboard UX improvements | [plan](docs/superpowers/plans/dashboard-ux-improvements.md) |
| 0.6.16.0 | TBD | **Safety** | Live state isolation | [design](docs/superpowers/specs/2026-04-28-live-state-isolation-design.md) / [plan](docs/superpowers/plans/2026-04-28-live-state-isolation.md) |
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

## Dashboard UX Improvements (v0.6.17.0)

The shipped TUI dashboard (v0.6.15.0) is data-dense but prioritizes volume over scanability. Trading is a risk-management sport; the UI should elevate loss-prevention metrics (heat, at-risk positions, cooldowns, R-multiples) above descriptive account metrics (equity, cash).

Planned improvements:
- **R-multiple column + row color bands** — risk-adjusted returns at a glance
- **At-risk banner** — tickers within 0.5R of stop, surfaced above the positions table
- **Portfolio heat gauge** — total risk exposure vs 6% max limit
- **Today's closed trades summary** — win rate, avg R, behavioral feedback loop
- **Cooldown visibility** — active re-entry cooldowns surfaced in UI
- **Sector exposure bars** — concentration breakdown by GICS sector
- **Activity log timeline** — single-column chronological flow with event icons
- **Stats visual hierarchy** — equity + day P&L bolded; other stats dimmed
- **Market regime badge** — computed bull/neutral/bear from SPY/VIX/breadth
- **Keyboard shortcuts** — turn the dashboard from a monitor into a control panel
- **WebSocket health sparkline** — latency + data freshness, not just connected/disconnected
- **Layout modes** — trading / scanning / post-market views

See full plan: [docs/superpowers/plans/dashboard-ux-improvements.md](docs/superpowers/plans/dashboard-ux-improvements.md)

---

## Next Steps

When ready to begin:
1. Phase (0.6.16.0) -- Live state isolation
2. Execute phase-by-phase

---

*This roadmap is a living document. Update as priorities shift or new insights emerge.*
