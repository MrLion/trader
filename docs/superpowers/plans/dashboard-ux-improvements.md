# Dashboard UX Improvements Plan

**Status:** Draft  
**Created:** 2026-04-29  
**Source:** UI/UX specialist review of `traderlib/dashboard.py` + `scripts/paper_engine_alpaca.py` + `scripts/demo_dashboard.py`

---

## Problem Statement

The current dashboard is a **data-dense Rich TUI** that prioritizes information volume over trader scanability. Trading is a risk-management sport; the UI should elevate metrics that prevent losses (heat, at-risk positions, cooldowns, R-multiples) above metrics that merely describe the account (equity, cash). Right now they are given equal visual weight — that is the core UX gap.

---

## Quick Wins (1–2 hours each)

### 1. R-Multiple Column + Color Bands
**File:** `traderlib/dashboard.py` — `_positions()`  
**What:** Add an `R` column to the positions table. Color the entire row by R-level:
- **Red:** < 0R (losing, before breakeven)
- **Yellow:** 0R–1R (breakeven zone, initial stop still active)
- **Green:** 1R–2R (healthy profit)
- **Bright green:** 2R+ (significant profit, trailing stop active)

**Why:** R is the universal language of risk-adjusted returns. The dashboard should speak it natively.

---

### 2. At-Risk Banner
**File:** `traderlib/dashboard.py` — new `_at_risk_banner()`  
**What:** Add a dedicated banner above the positions table showing tickers within 0.5R of their stop or below entry.

```
  ⚠️  AT RISK:  NVDA (-0.3R)  |  TSLA (stop $195.00, current $196.10)
```

**Why:** The most important question a trader asks is *"am I about to get stopped out?"* This should be answered in <100ms.

---

### 3. Portfolio Heat Gauge
**File:** `traderlib/dashboard.py` — `_stats()` or new `_heat_gauge()`  
**What:** Add a single-line heat indicator:

```
  HEAT:  ████████░░  3.2% / 6.0% max    (5 positions, avg stop 4.1%)
```

**Why:** Surfaces the "portfolio heat check" rule from `AGENTS.MD` directly in the UI.

---

### 4. Today's Closed Trades Summary
**File:** `traderlib/dashboard.py` — new `_today_summary()`  
**What:** Add a "Today's Results" micro-section:

```
  TODAY:  3 wins / 1 loss  |  +$1,240  |  avg +1.8R  |  win rate 75%
```

**Why:** Behavioral feedback loop. Traders perform better when they can see their edge in real time.

---

### 5. Cooldown Visibility
**File:** `traderlib/dashboard.py` — `_footer()` or `_stats()`  
**What:** Add a small "Cooldowns" section:

```
  COOLDOWNS:  FLY (12min)  |  META (45min)
```

**Why:** Prevents the exact mistake the cooldown feature was built to stop — the trader needs to see it.

---

## Medium Effort (half day each)

### 6. Sector Exposure Bar Chart  ✅
**File:** `traderlib/dashboard.py` — new `_sector_exposure()`  
**What:** Replace the bottom half of the activity log (or add as a toggle) with a horizontal bar chart:

```
  SECTOR EXPOSURE          % of Equity
  Technology    ████████░░  18% (2 pos)
  Healthcare    ███░░░░░░░   8% (1 pos)
  Financials    ░░░░░░░░░░   0%
```

**Why:** Sector rotation is a core part of the Stage 2 methodology. The dashboard should reflect it.

---

### 7. Activity Log  ✅ → Scrollable Timeline
**File:** `traderlib/dashboard.py` — `_activity()`  
**What:** Convert the two-column event grid into a single-column, scrollable timeline with severity icons and minute grouping:

```
  10:32  ▶ ENTRY   AAPL  $187.45  x100  (Tier 1, S2=9/10)
  10:28  ▲ EXIT    TSLA  $245.00  +$450 (+2.3R)
  10:15  ● STOP    MSFT  → $400.00  (TRAIL, +1.5R)
  10:05  ○ SKIP    FLY   cooldown active (23min remaining)
```

**Why:** Chronological flow reads faster than two-column zig-zag. Icons give instant event-type recognition.

---

### 8. Stats Visual Hierarchy  ✅
**File:** `traderlib/dashboard.py` — `_stats()`  
**What:** Use larger/bolder text for the two numbers that matter most (Equity, Day P&L). Dim the rest.

```
  EQUITY      $103,420.50          DAY P&L     +$420.50 ▲
  CASH        $45,200.00           UNREALIZED  +$1,150.00
  OPEN        3                    PENDING     0
```

- **Equity** and **Day P&L** are bold/large
- **Day P&L** is green/red with an up/down arrow
- Other stats are dimmer

**Why:** Fitt's Law + visual hierarchy. Most-checked items get the most visual weight.

---

### 9. Market Regime Indicator  ✅
**File:** `traderlib/dashboard.py` — `_header()`  
**What:** Add a single-word regime badge in the header:

```
  PAPER ENGINE    10:32:01 ET    MARKET OPEN    REGIME: 🟢 BULL    VIX: 16.4
```

Derived from: SPY vs 50 MA, VIX level, breadth.

**Why:** Not just data display — computed interpretation of market state.

---

## Larger Effort (1–2 days)

### 10. Keyboard Shortcuts / Interactive Mode
**File:** `traderlib/dashboard.py` + `scripts/paper_engine_alpaca.py`  
**What:** Add a minimal interactive layer (Rich supports keyboard input):

```
  [q] quit  [p] pause entries  [f] flush log  [r] force scan  [s] show stats
```

This turns the dashboard from a **monitor** into a **control panel**.

**Why:** Currently the user must Ctrl+C and run a separate script to take action.

---

### 11. WebSocket Health Sparkline
**File:** `traderlib/dashboard.py` — `_header()` or `_footer()`  
**What:** Show latency sparkline or "last tick" age:

```
  WS: ● connected  (last tick: 0.3s ago)
```

If >5s: yellow. If >30s: red + "STALE" label.

**Why:** Binary connected/disconnected doesn't show recent reconnects or data freshness.

---

### 12. Dashboard Layout Modes
**File:** `traderlib/dashboard.py` — `Dashboard` class  
**What:** Support layout modes toggled via key or CLI flag:

| Mode | Focus |
|------|-------|
| `trading` | Positions, heat, cooldowns, at-risk alerts |
| `scanning` | Watchlist signals, tier breakdown, volume confirmation |
| `post` | P&L summary, trade journal, R-multiple stats |

**Why:** Pre-market, market hours, and post-market have different information needs.

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | R-multiple column + row coloring | 1h | High |
| P0 | At-risk banner | 1h | High |
| P0 | Heat gauge | 1h | High |
| P1 | Today's results summary | 1h | Medium |
| P1 | Cooldown visibility | 1h | Medium |
| P2 | Sector exposure bars | 4h | Medium |
| P2 | Activity log → timeline | 4h | Medium |
| P2 | Stats visual hierarchy | 2h | Low |
| P2 | Regime indicator | 4h | Medium |
| P3 | Keyboard shortcuts | 1–2d | High |
| P3 | WS health sparkline | 4h | Low |
| P3 | Layout modes | 1–2d | Medium |

---

## Notes

- All changes stay inside `traderlib/dashboard.py` unless interactive mode requires touching `scripts/paper_engine_alpaca.py`.
- The dashboard already falls back gracefully when `rich` is unavailable; keep that behavior.
- No emojis in final output per codebase convention; use ASCII symbols (`+`, `-`, `*`, `>`) or Rich color coding instead.
