# Dashboard UX Improvements — Design Spec

**Date:** 2026-06-06
**Status:** Approved
**Approach:** Responsive Terminal Height — extend existing `dashboard.py` patterns
**Reference mockup:** [`2026-06-06-dashboard-mockup.html`](./2026-06-06-dashboard-mockup.html) — authoritative visual reference

---

## Problem Statement

1. **Scrollable in terminal** — Content pushes below the fold
2. **No recent trades visible** — Activity log shows raw events, not trades in dashboard.py's icon format
3. **No total balance when market closed** — No historical context (initial, all-time, YTD, month, week)
4. **No equity curve** — No visual representation of portfolio value over time
5. **No performance stats** — Missing win rate, Sharpe, max drawdown, profit factor, expectancy

## Design Principle

**Extend the existing `dashboard.py` visual language.** Do not redesign. Match current patterns:

- Header: `PAPER ENGINE    HH:MM:SS ET    MARKET OPEN    BULL    VIX 22.4    WS: connected    API: 12/200`
- Stats: 3-line EQUITY/DAY P&L, CASH/UNREALIZED/OPEN, PENDING/HEAT
- Activity icons: `+` ENTRY, `x` EXIT/SCALE, `*` STOP — icons dim, text colored by P&L
- Rules: `─` × terminal width between every section, dim style
- No box borders, no two-column layout
- Positions/trades: show all when space allows, subset + `+N more` cutoff when height requires it

## Constraints

- Terminal-only, ~80 columns
- Non-scrolling — content adapts to terminal height
- Rich TUI (existing dependency)
- Market-state adaptive (OPEN vs POST)

---

## Responsive Layout

Detect `self.console.height` at render time. Show as much content as fits. Reference mockup is authoritative for exact per-size layout.

### 24-Row Terminal
Header + Stats + Today + top positions + Footer
(Post-market adds Total Balance between Stats and Today)

### 35-Row Terminal
+ more positions + recent activity + equity sparkline
(Post-market adds Total Balance (2-line) between Stats and Today, replaces activity with closed trades)

### 50-Row Terminal (full)
Market-open: all positions + all activity + equity sparkline + today stats + sectors
Post-market: Total Balance (2-line) + all positions + all closed trades + equity sparkline + lifetime stats + sectors

---

## Market-Open Layout

### Header (existing, unchanged)

```
  PAPER ENGINE    14:32:17 ET    MARKET OPEN    BULL    VIX 22.4    WS: connected    API: 12/200
```

### Stats (existing format, values from engine state)

```
  EQUITY      $124,892.34          DAY P&L     ▲ +$1,247
  CASH          $8,234.00           UNREALIZED    +$3,179.00          OPEN      12
  PENDING           0          HEAT        ███░░░░░░░   1.8%
```

Values from `state_data` dict built by engine (equity, cash, day_pnl, unrealized_pnl, open_positions, pending_orders). Heat gauge: 10-char `█/░` bar, max 6% = full bar.

### Today (existing format, values from engine state)

```
  TODAY:  6W / 2L  |  +$1,247  |  avg +0.45R  |  75% WR
```

Data from `state.get("today_stats")` — a dict with `wins`, `losses`, `total_pnl`, `avg_r` computed by `AlpacaPaperEngine._get_today_trade_stats()`. Avg R formatted to 2 decimal places (`+.2f`).

### Positions (existing format, add max_rows support)

```
  TICKER  ENTRY     CURRENT   STOP      TYPE   UNREAL       R
  ──────  ─────     ───────   ────      ────   ──────  ─────
  AAPL    187.50    192.30    185.00    H         +960  +2.4R
  ...
```

Existing Rich Table (no borders, no lines, separator row). R-multiple coloring: red (<0), yellow (<1), green (<2), bold green (≥2). `_positions()` accepts optional `max_rows`; when positions exceed max_rows, show top N sorted by `|unrealized P&L|` descending, append cutoff row `+N more positions`. No hard cap — truncation only when terminal height requires it.

### Activity (extend existing format with max_events + R-multiple)

```
  x 14:31  SCALE   TSLA              -$120   -0.4R
  + 13:52  ENTRY   AAPL    long
  * 11:45  STOP    INTC              -$140   -0.9R
```

Extends existing `_activity()` icon system:
- Icons are dim (`+`, `x`, `*`)
- Event type text colored: ENTRY=cyan, EXIT/SCALE=green if P&L≥0 else red, STOP=yellow if negative else red
- ENTRY events show detail field (e.g., `long`)
- EXIT/SCALE/STOP events show P&L + R-multiple (adds R to current format)
- Accepts optional `max_events`; truncates with `+N more events` when exceeded

### Equity Sparkline (NEW)

```
  EQUITY (30D)
  ▁▂▃▅▆▇████▇▆▅▃▂▁▁▂▃▄▆▇█▇▅▃▂  $124.9K
```

- 30 Unicode block characters — one per trading day
- Reconstructed from `data/paper_trades.jsonl` via `StatsCalculator.reconstruct_daily_equities()`
- Green sparkline, right-aligned `$XXX.XK` label
- In-memory cache; invalidated each render by checking trade log file mtime

### Today Stats (NEW, 50-row only)

```
  Win Rate: 75.0%    Avg R: +0.45R    Win/Loss: 3.8
```

Computed by `StatsCalculator.today_stats()` from today's closed trades. Same data as Today line, expanded format.

### Sectors (existing, 50-row only)

Existing `_sector_exposure()`. Gated behind terminal height check — not rendered at 24/35 rows.

### Footer (existing, market-state adaptive)

```
  Next scan: 23s    Market closes in: 1h 28m    WebSocket: connected    Rate limit: 12/200
```

When `market_status == "POST"` or `"CLOSED"`, replaces with:
```
  Market closed. Next open: 09:30 ET tomorrow.  WebSocket: disconnected    Rate limit: 0/200
```

---

## Post-Market Layout

### Header (existing pattern, values adapt to post-market)

```
  PAPER ENGINE    16:05:32 ET    POST-MARKET SUMMARY    NEUTRAL    VIX 21.8    WS: disconnected    API: 0/200  |  Data frozen since 16:00:00
```

### Stats (same format, recalculated values)

Post-market values differ from market-open because fully-exited positions are removed:
- UNREALIZED drops (`$2,811` vs `$3,179`) — only remaining 9 positions
- OPEN drops (`9` vs `12`) — TSLA, META, GOOGL fully exited during the day
- HEAT recalculates (`1.2%` vs `1.8%`) — fewer open positions = lower total at-risk

### Total Balance (NEW, all post-market sizes)

```
  INITIAL   $100,000    ALL-TIME   +$24,892 (+24.9%)
  YTD  +$15,340 (+15.3%)  |  Month  +$3,210 (+2.6%)  |  Week  +$1,247 (+1.0%)
```

- **Current equity**: `state.get("equity")`
- **Initial capital**: Engine must add `initial_capital` to `state_data` dict (currently not passed)
- **All-time P&L**: `current - initial`
- **YTD/Month/Week**: `StatsCalculator.reconstruct_daily_equities()` to find equity at period start, compare to current
- **24-row**: 1-line (Initial + All-time only)
- **35-row+**: 2-line (adds YTD/Month/Week)
- No data for period → `--`

### Positions (same format, post-market adaptations)

- Column header: `CURRENT` → `CLOSE`
- Shows closing prices from last snapshot before market close
- Fully exited positions removed from table (only still-open positions remain)
- Open count reflects actual remaining count

### Closed Trades (NEW, extends activity format)

```
  * 15:58  STOP    TSLA    245.00→243.20    -$180   -0.6R
  x 15:45  EXIT    META    485.00→492.00    +$560   +2.0R
  x 14:15  SCALE   AAPL    187.50→190.00    +$250   +1.0R
```

Extends activity icon format with entry→exit price detail. Shows all positions closed today (EXIT=full, STOP=stop loss, SCALE=partial). `_closed_trades()` reads today's closed trades from `paper_trades.jsonl`, matching trades with `exit_price` field.

### Today (recalculated from closed trades)

```
  TODAY:  6W / 2L  |  +$1,247  |  avg +0.66R  |  75% WR
```

Post-market recalculates from today's closed trades only (not scale-outs). Avg R is 0.66R because the full exits (TSLA -0.6, META +2.0, GOOGL +1.6) produce different R totals than the mid-day scale-out values. The mockup is authoritative for example values.

### Lifetime Stats (NEW, 50-row only)

```
  Win Rate:    62.3%          Avg R:      +0.9R
  Sharpe:      1.42           Max DD:     -8.4%
  Profit Factor: 1.9          Expectancy: +0.4R
  Total Trades: 847
```

`StatsCalculator.lifetime_stats()` from full `paper_trades.jsonl` history. Require ≥30 days for Sharpe/Max DD, ≥1 loss for Profit Factor — else `--`.

### Footer

```
  Market closed. Next open: 09:30 ET tomorrow.  WebSocket: disconnected    Rate limit: 0/200
```

---

## StatsCalculator Utility

New `traderlib/stats_calculator.py`:

```python
class StatsCalculator:
    def __init__(self, trades_jsonl_path: str = "data/paper_trades.jsonl"):
        ...

    def reconstruct_daily_equities(self, initial_capital: float) -> list[tuple[str, float]]:
        """Replay trade log → [(date_str, end_of_day_equity), ...]. Used by sparkline and lifetime stats."""

    def today_stats(self, trades: list[dict]) -> dict:
        """Compute wins, losses, total_pnl, avg_r, win_rate, profit_factor from today's closed trades.
        Input: list of trade dicts from paper_trades.jsonl with entry_price, exit_price, r_multiple, pnl."""

    def lifetime_stats(self, daily_equities: list[tuple[str, float]]) -> dict:
        """Compute win_rate, avg_r, sharpe, max_dd, profit_factor, expectancy, total_trades from full history."""
```

**Trade dict format** (from `paper_trades.jsonl`):
```python
{
    "timestamp": "2026-06-06T14:31:00",
    "ticker": "TSLA",
    "action": "SCALE",       # ENTRY | EXIT | SCALE | STOP
    "entry_price": 245.00,
    "exit_price": 243.20,    # None for ENTRY
    "shares": 66,
    "pnl": -118.80,
    "r_multiple": -0.4,
}
```

---

## Data Sources

| Data | Source | Notes |
|------|--------|-------|
| Equity, cash, positions, day P&L | `state_data` dict from `paper_engine_alpaca.py` | Existing `update()` path |
| Today's stats (wins/losses/avg_r) | `state.get("today_stats")` | Computed by `AlpacaPaperEngine._get_today_trade_stats()` |
| Trade history | `data/paper_trades.jsonl` | Read directly by `StatsCalculator` |
| Market status, VIX, regime | `state` dict from engine | Existing keys |
| Sectors | `SectorResolver` (existing) | Unchanged |
| Cooldowns | `state.get("cooldowns")` | Market-open only; not in post-market state |
| **Initial capital** | `state.get("initial_capital")` | **Must be added to engine's `state_data` dict** |
| WebSocket status | `state.get("ws_connected")` | Existing |
| API usage | `state.get("api_requests")` / `state.get("api_max")` | Existing; None → renders as `--` |

---

## Engine Changes Required

`paper_engine_alpaca.py` must add `initial_capital` to the `state_data` dict passed to `dashboard.update()`:

```python
# In _print_status() and _load_post_market_state(), add:
"initial_capital": self.state.initial_capital if hasattr(self.state, 'initial_capital') else 0.0,
```

---

## Implementation Scope

### Changes to `traderlib/dashboard.py`

1. `_render()` — detect `self.console.height`, select layout density, gate optional sections
2. `_header()` — unchanged (already handles frozen timestamp for non-OPEN markets)
3. `_stats()` — unchanged (values come from state dict, recalculated by engine)
4. `_today_summary()` — change avg_r format to 2 decimal places
5. `_positions()` — add optional `max_rows` parameter, sort by |unrealized P&L| desc, append cutoff row
6. `_activity()` — add optional `max_events` parameter, add R-multiple to exit/stop lines, show trade detail
7. `_sector_exposure()` — gate behind height check (render only if rows ≥ 50)
8. `_footer()` — market-status conditional: scan timer for OPEN, next-open message for POST/CLOSED
9. `_equity_sparkline()` — NEW
10. `_total_balance()` — NEW (post-market only)
11. `_lifetime_stats()` — NEW (post-market, 50-row only)
12. `_closed_trades()` — NEW (post-market only)
13. `_today_stats()` — NEW (market-open, 50-row only)

### New File

- `traderlib/stats_calculator.py` — trade history replay, today/lifetime metrics, shared by dashboard and sparkline

### Existing Behavior Preserved

- All current sections render identically at default terminal sizes
- Fallback: `rich` unavailable → dashboard no-op
- Fallback: `paper_trades.jsonl` missing/empty → sparkline shows flat `░` line, stats show `--`
- Fallback: terminal height < 24 → render minimal view (header + stats + footer only)
