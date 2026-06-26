# Product Roadmap 2026

**Created:** 2026-04-26
**Updated:** 2026-06-26
**Latest Shipped:** 0.6.19.20

---

## Version Summary

**Format:** `WW.XX.YY.ZZ` — WW=Super, XX=Major, YY=Minor, ZZ=Patch

| Version | Status | Theme | Focus | Design | Plan |
|---------|--------|-------|-------|--------|------|
| **0.6.15.0** | ✅ Shipped | **UX** | TUI Dashboard for Paper Engine | [spec](docs/superpowers/specs/2026-04-27-paper-engine-dashboard-design.md) | [impl](plans/plan-paper-engine-dashboard.md) · [ux](docs/superpowers/plans/dashboard-ux-improvements.md) |
| **0.6.16.0** | ✅ Shipped | **Safety** | Live state isolation + trailing exit fixes | [spec](docs/superpowers/specs/2026-04-28-live-state-isolation-design.md) | [plan](docs/superpowers/plans/2026-04-28-live-state-isolation.md) |
| **0.6.17.0** | ✅ Shipped | **Data** | Sector enrichment in universes + scan outputs | — | [impl](docs/superpowers/plans/2026-05-17-enrich-universes-with-sectors.md) |
| **0.6.18.x** | ✅ Shipped | **Stability** | VCP bug fixes, dashboard UX, FMP rate limiting | — | — |
| **0.6.19.0** | ✅ Shipped | **Cleanup + Reliability** | VCP strategy plugin removal + dashboard hardening | — | [plan](plans/plan-remove-vcp-strategy.md) · [CHANGELOG](../CHANGELOG.md) |
| **0.6.19.18** | ✅ Shipped | **UX** | Trend screener setup/buy point 1:1 pairing + interactive HTML | [mockup](scans/mockup-improved.html) | [plan](plans/trend-screener-ux-overhaul.md) · [CHANGELOG](../CHANGELOG.md) |
| **0.6.19.19** | ✅ Shipped | **Fix** | Proximity-based section classification + lower-risk entry selection | [mockup](scans/mockup-improved.html) | [plan](plans/classification-logic-fix.md) · [CHANGELOG](../CHANGELOG.md) |
| **0.6.19.20** | ✅ Shipped | **Fix** | Same-level re-entry rejection for repeat losing trades | — | [plan](plans/prevent-repeat-losing-trades.md) · [CHANGELOG](../CHANGELOG.md) |
| 0.6.20.0 | TBD | **Insight** | Analytics & journaling | — | — |
| 0.6.21.0 | TBD | **Config** | Configurable engine rules | — | — |
| 0.6.22.0 | TBD | **Accessibility** | Web dashboard | — | — |
| 0.6.23.0 | TBD | **Standardization** | Column naming standardization | — | — |

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

**Status:** Shipped — 2026-05-02.

- [Design spec](docs/superpowers/specs/2026-04-28-live-state-isolation-design.md)
- [Implementation plan](docs/superpowers/plans/2026-04-28-live-state-isolation.md)

---

## 0.6.17.0 — Sector Enrichment

**Why:** Scan outputs (`entry_signals`, `trend_screener`) show `"Unknown"` for ~99% of tickers because sector data only exists in the 10-row watchlist. The paper engine cannot enforce `max_sector_positions=3`, the dashboard sector exposure chart collapses, and the backtest has a pre-existing bug where every ticker gets `"Unknown"`. Sector is fundamental to risk management and trade selection — without it, the system is flying blind.

**What:** Add sector data to universe generation (`UniverseBuilder`) via FMP API, build a shared `SectorResolver` with 3-tier fallback (watchlist → universe → FMP), and wire it into all consumers: `entry_signals`, `trend_screener`, `paper_engine`, `paper_portfolio`, `dashboard`, `backtest`, `vcp_breakout`.

**How:** FMP `/stable/profile` calls parallelized with `ThreadPoolExecutor` + thread-safe rate limiter during universe build (after dollar-volume filter, ~600 tickers). `SectorResolver` provides in-memory cache and unified lookup. No column renames in this deploy — deferred to keep blast radius minimal.

**Status:** In progress — plan complete, implementation ready.

- [Implementation plan](docs/superpowers/plans/2026-05-17-enrich-universes-with-sectors.md)

---

## 0.6.18.x — Stability Patches

**Shipped:** 2026-05-18 through 2026-05-26

A series of patch releases addressing production issues discovered during daily use:

- **0.6.17.5–0.6.17.6** — FMP 429 retry logic, reduced concurrency, sector cache poisoning fix
- **0.6.18.0** — Categorized sector scan ETF config (148 tickers, 8 categories)
- **0.6.18.1** — Progress bar + category leaders output in sector scan
- **0.6.18.2** — VCP R-calculation bug fix, dashboard stale data fix, strategy exit toggle

---

## 0.6.19.0 — Cleanup + Reliability

**Why:** The 0.6.19.x series combined planned cleanup with real production hardening. The VCP strategy plugin system had proven unused and bug-prone; meanwhile, post-market dashboard usage exposed repeated state/accounting issues that needed fixes before broader analytics work could be trusted.

**What shipped:**
- Removal of the `traderlib/strategies/` plugin architecture (VCP breakout, composite, registry) and inlining of backtest shared types into `traderlib/backtest/strategy.py`
- Post-market dashboard now sources real Alpaca data for account value, cash, day P&L, and YTD
- YTD P&L fallback from trade log when Alpaca portfolio history is unavailable
- Fix for account value double-counting cash
- Activity panel seeded from disk on engine restart
- Sparkline + lifetime stats (Sharpe / Max DD / total trades)

**How:** See [CHANGELOG](../CHANGELOG.md) for the full 0.6.19.x patch series.

**Status:** ✅ Shipped as of 0.6.19.15.

---

## 0.6.20.0 — Analytics & Journaling

**Why:** Manual journaling is inconsistent and biased. Without automated performance analytics, the trader can't see which setups, sectors, or regime conditions produce their edge — gut feel replaces data.

**What:** Automated trade journaling and performance analytics — every trade logged, every R-multiple computed, every pattern surfaced.

**How:** Hooks into the engine's trade lifecycle to capture entry/exit/stop events, compute stats (win rate, expectancy, avg R, MAE/MFE), and generate weekly/monthly performance reports.

**Status:** TBD. No plan yet.

---

## 0.6.21.0 — Config

**Why:** Hard-coded settings (position sizing, risk limits, sector caps) limit experimentation. The trader can't A/B test strategies or adapt rules without editing source code.

**What:** An external configuration system that makes the engine's rules tunable, plus new trading capabilities unlocked by that flexibility.

**How:** YAML/TOML config files decoupled from engine code, runtime reload, and strategy parameters exposed as config knobs rather than buried in logic.

**Status:** TBD. No plan yet.

---

## 0.6.22.0 — Web Dashboard

**Why:** The TUI dashboard requires terminal access. A trader away from their machine — on mobile, traveling, or simply in another room — has zero visibility into engine state.

**What:** A browser-based dashboard accessible from any device on the local network.

**How:** FastAPI backend serving live engine state over WebSocket, HTMX frontend for lightweight interactivity without a JavaScript framework. Follows the same risk-first visual hierarchy established in 0.6.15.0.

**Status:** TBD. No plan yet.

---

## 0.6.23.0 — Column Standardization

**Why:** Machine-generated CSVs use inconsistent column naming (PascalCase `Ticker, Sector` vs snake_case `ticker, sector`). Every consumer handles both conventions or fails silently. The backtest bug (`'sector'` vs `'Sector'`) is one symptom of a systemic naming drift.

**What:** Standardize all machine-generated CSVs to snake_case. Normalize watchlist reads (PascalCase on disk, snake_case in memory). Audit all test fixtures.

**How:** Mechanical rename across ~13 production files + ~12 test files. Low-risk but broad blast radius — deployed separately from sector enrichment to isolate regressions.

**Status:** TBD. No plan yet.

---

## Decision Log

- **0.6.15.0 (UX):** TUI dashboard first — proves the engine before building browser UIs
- **0.6.17.0 (Data):** Sector enrichment before analytics — accurate sector data is prerequisite for meaningful sector-level P&L attribution
- **0.6.19.0 (Cleanup + Reliability):** Remove dead strategy plugins and harden dashboard/accounting before building analytics on top of it
- **0.6.23.0 (Standardization):** Column naming deferred to separate deploy — bundling with 0.6.17.0 would create unnecessary coupling and ~25-file blast radius
- **0.6.22.0 (Accessibility):** FastAPI + HTMX (not React) — simpler stack for personal dashboard; can migrate later if needed
- **Project-wide:** 4-digit versioning — follows convention `0.XX.YY.ZZ`

---

*This roadmap is a living document. Update as priorities shift or new insights emerge.*