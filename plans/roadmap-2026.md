# Product Roadmap 2026

**Created:** 2026-04-26
**Updated:** 2026-04-30
**Latest Shipped:** 0.6.15.0 (partially)

---

## Version Summary

**Format:** `WW.XX.YY.ZZ` — WW=Super, XX=Major, YY=Minor, ZZ=Patch

| Version | Status | Theme | Focus | Design | Plan |
|---------|--------|-------|-------|--------|------|
| **0.6.15.0** | Partially Shipped | **UX** | TUI Dashboard for Paper Engine | [spec](docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md) | [impl](plans/plan-paper-engine-dashboard.md) · [ux](docs/superpowers/plans/dashboard-ux-improvements.md) |
| 0.6.16.0 | TBD | **Safety** | Live state isolation | [spec](docs/superpowers/specs/2026-04-28-live-state-isolation-design.md) | [plan](docs/superpowers/plans/2026-04-28-live-state-isolation.md) |
| 0.6.17.0 | TBD | **Insight** | Analytics & journaling | — | — |
| 0.6.18.0 | TBD | **Capability** | Config + new capabilities | — | — |
| 0.6.19.0 | TBD | **Accessibility** | Web dashboard | — | — |

---

## 0.6.15.0 — TUI Dashboard

**Why:** The paper engine dumps status via `print()` into an endless scroll. A trader can't glance at terminal state — they must scroll back or run a separate status command. This is daily friction during market hours.

**What:** A live TUI dashboard that surfaces engine state at a glance — positions, heat, cooldowns, and risk metrics prioritized over descriptive account stats.

**How:** Built on `rich` for zero-infrastructure delivery. Self-contained, fallback-safe (plain text if `rich` is unavailable), consistent with existing report visuals.

**Status:** Partially shipped. Core dashboard is live. 9 of 12 UX improvements done.

**Shipped:** R-multiple column + color bands, at-risk banner, portfolio heat gauge, today's results summary, cooldown visibility, sector exposure bars, activity log timeline, stats visual hierarchy, market regime badge.

**Remaining (P3):** Keyboard shortcuts, WebSocket health sparkline, layout modes (trading/scanning/post).

Full breakdown: [dashboard UX improvements plan](docs/superpowers/plans/dashboard-ux-improvements.md)

---

## 0.6.16.0 — Live State Isolation

**Why:** A trader running paper and live engines side by side risks cross-contaminating state — a live order could leak into paper logs, or a paper config could silently override live settings. One mistake in the wrong environment is catastrophic.

**What:** Strict isolation between paper, backtest, and live engine states — separate directories, configs, and data paths that cannot bleed across boundaries.

**How:** Isolated state directories per engine mode, environment-specific config loading, and guardrails that prevent a live engine from reading paper state (and vice versa).

**Status:** TBD.

- [Design spec](docs/superpowers/specs/2026-04-28-live-state-isolation-design.md)
- [Implementation plan](docs/superpowers/plans/2026-04-28-live-state-isolation.md)

---

## 0.6.17.0 — Analytics & Journaling

**Why:** Manual journaling is inconsistent and biased. Without automated performance analytics, the trader can't see which setups, sectors, or regime conditions produce their edge — gut feel replaces data.

**What:** Automated trade journaling and performance analytics — every trade logged, every R-multiple computed, every pattern surfaced.

**How:** Hooks into the engine's trade lifecycle to capture entry/exit/stop events, compute stats (win rate, expectancy, avg R, MAE/MFE), and generate weekly/monthly performance reports.

**Status:** TBD. No plan yet.

---

## 0.6.18.0 — Config + New Capabilities

**Why:** Hard-coded settings (position sizing, risk limits, sector caps) limit experimentation. The trader can't A/B test strategies or adapt rules without editing source code.

**What:** An external configuration system that makes the engine's rules tunable, plus new trading capabilities unlocked by that flexibility.

**How:** YAML/TOML config files decoupled from engine code, runtime reload, and strategy parameters exposed as config knobs rather than buried in logic.

**Status:** TBD. No plan yet.

---

## 0.6.19.0 — Web Dashboard

**Why:** The TUI dashboard requires terminal access. A trader away from their machine — on mobile, traveling, or simply in another room — has zero visibility into engine state.

**What:** A browser-based dashboard accessible from any device on the local network.

**How:** FastAPI backend serving live engine state over WebSocket, HTMX frontend for lightweight interactivity without a JavaScript framework. Follows the same risk-first visual hierarchy established in 0.6.15.0.

**Status:** TBD. No plan yet.

---

## Decision Log

- **0.6.15.0 (UX):** TUI dashboard first — proves the engine before building browser UIs
- **0.6.19.0 (Accessibility):** FastAPI + HTMX (not React) — simpler stack for personal dashboard; can migrate later if needed
- **Project-wide:** 4-digit versioning — follows convention `0.XX.YY.ZZ`

---

*This roadmap is a living document. Update as priorities shift or new insights emerge.*
