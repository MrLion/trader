# Memory Index

Quick links to project context and daily notes.

## Project Roadmap

**Location:** `plans/roadmap-2026.md`

**Current:** 0.6.13.0 — Backtest config tracking shipped

| Version | Status | Plan |
|---------|--------|------|
| 0.6.13.0 | Completed | [Backtest config tracking](plans/archive/plan-backtest-config-tracking.md) |
| 0.6.14.0 | TBD | Live state isolation |
| 0.6.15.0 | TBD | Analytics & journaling |
| 0.6.16.0 | TBD | Config + capabilities |
| 0.6.17.0 | TBD | Web dashboard |

## Plans Archive (Completed)

| Plan | Date | Status |
|------|------|--------|
| [Backtest config tracking](plans/archive/plan-backtest-config-tracking.md) | Apr 2026 | Completed |
| [Paper trading engine](plans/archive/paper-trading-engine-plan.md) | Apr 2026 | Completed |
| [Earnings filter](plans/archive/plan-earnings-filter.md) | Apr 2026 | Completed |
| [High-octane universe filter](plans/archive/plan-high-octane-universe-filter.md) | Apr 2026 | Completed |

## Active Plans

| Plan | Status | Version |
|------|--------|---------|
| [FMP Economic Calendar](plans/plan-fmp-economic-calendar.md) | Ready | 0.6.14.x |
| [Pivot hybrid config](plans/plan-pivot-hybrid-config.md) | PENDING | — |

## Daily Notes

See `memory/YYYY-MM-DD.md` files for raw session logs.

## Feedback & Context

- `feedback_*.md` — User preferences and corrections
- `project_*.md` — Project decisions and constraints

---

## Structure

```
memory/
├── MEMORY.md                    # Index — links to everything
├── YYYY-MM-DD.md               # Daily session logs (raw)
└── feedback_*.md, project_*.md  # Context & decisions

plans/
├── roadmap-2026.md  # Version timeline
├── plan-*.md                      # Detailed specs (active)
└── archive/
    └── plan-*.md                  # Completed plans
```

## Workflow

1. **Brainstorm** → Add to roadmap as TBD or define plan
2. **Approve** → Write detailed plan to `plans/plan-*.md`
3. **Implement** → Execute plan
4. **Complete** → Move plan to `plans/archive/`
5. **Update** → MEMORY.md always points to current locations

## Key Rules

- **MEMORY.md never contains detailed specs** — only links
- **Roadmap shows versions + status** — links to plans if they exist
- **TBD = not yet defined** — no plan file needed
- **Archive = done** — move completed plans out of active folder
- **Daily notes stay in memory/** — raw context, not curated

*For detailed specs, see `plans/` folder.*
