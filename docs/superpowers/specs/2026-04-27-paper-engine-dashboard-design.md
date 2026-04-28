# Paper Engine TUI Dashboard Design

## Status: Approved

## Overview

Replace the paper engine's endless-scroll text output with a full-width, single-screen TUI dashboard using the `rich` library. No vertical dividers. No emojis. Color-coded text only. Horizontal rules separate sections. The dashboard updates in-place every cycle while the engine runs.

## Motivation

The current `paper_engine_alpaca.py` outputs status via `print()` statements that scroll off-screen. A trader running the engine cannot glance at terminal state — they must scroll back or run `paper_portfolio.py status` separately. A dashboard makes the engine's current state instantly readable.

## Design Principles

1. **Full terminal width** — no narrow centered boxes. Every row stretches edge-to-edge.
2. **No vertical dividers** — no `|`, no table vertical borders, no column dividers. Whitespace alignment only.
3. **Color-coded text** — green for profit/good, red for loss/bad, yellow for warnings, cyan for entries. No emoji blobs.
4. **Horizontal rules only** — single `─` lines separate sections. No double borders.
5. **Read-only monitor** — the dashboard displays state. All interaction remains via engine signals (Ctrl+C, etc.).

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Dashboard (rich.live.Live screen mode)                     │
│  ├─ HeaderRenderer                                         │
│  ├─ StatsRenderer                                          │
│  ├─ PositionsRenderer                                      │
│  ├─ ActivityLogRenderer                                    │
│  └─ FooterRenderer                                         │
└────────────────────────────────────────────────────────────┘
         ↑
         │ update(state, events)
┌────────────────────────────────────────────────────────────┐
│  AlpacaPaperEngine                                         │
│  ├─ Replaces _print_status() with dashboard.update()       │
│  ├─ Replaces event print()s with dashboard.log_event()      │
│  └─ Falls back to old output if rich unavailable           │
└────────────────────────────────────────────────────────────┘
```

## Component Design

### Dashboard Class

- **Location**: `traderlib/dashboard.py` (new file)
- **Responsibilities**:
  - Own `rich.live.Live` instance in `screen=True` mode
  - Assemble renderables from section renderers
  - Maintain a bounded event queue (last 20 events)
  - Provide `update(state_dict)` and `log_event(event_dict)` public API
- **Fallback**: If `rich` is not installed, methods become no-ops and engine falls back to original `print()` logic

### Section Renderers

Each renderer is a pure function: `render(data) -> rich.renderable`.

#### Header Band

**Content**: Engine name, timestamp, market status, VIX, WebSocket status, API usage.
**Style**: Bold white text. Horizontal rules above and below.
**Full-width**: Yes.

Example:
```
────────────────────────────────────────────────────────────────────────────────
  PAPER ENGINE    10:32:32 ET    MARKET OPEN    VIX 16.4    WS: connected    API: 12/500 2%
────────────────────────────────────────────────────────────────────────────────
```

**Color rules**:
- Timestamp: white
- MARKET OPEN: green (red if closed)
- VIX value: white (yellow if > 20, red if > 30)
- WS: connected: green (red if disconnected)
- API usage: white (yellow if > 80%)

#### Stats Block

**Content**: 2 rows × 3 columns of key metrics.
**Style**: Labels in dim grey, values in white or color-coded.
**Layout**: Space-separated columns. Responsive: 3-col if ≥100 cols, 2-col if ≥60 cols, 1-col if <60 cols.

Example (3-column):
```
  EQUITY        $103,420.50          DAY P&L       $+420.50          OPEN POS      3
  CASH          $45,200.00           UNREALIZED    $+1,150.00         PENDING       0
```

**Metrics**:
- EQUITY: white
- DAY P&L: green if > 0, red if < 0
- OPEN POS: white
- CASH: white
- UNREALIZED: green if > 0, red if < 0
- PENDING: white

**Data sources**:
- EQUITY: `state.get_equity()`
- CASH: `state.cash`
- DAY P&L: `state.get_day_pnl()`
- UNREALIZED: calculated from positions + Alpaca prices
- OPEN POS: `len(state.positions)`
- PENDING: `order_manager.get_pending_count()`

#### Positions Table

**Content**: All open positions with ticker, phase, entry, current, stop, type, unrealized P&L, R-multiple.
**Style**: `rich.Table` with `box=None` — absolutely no vertical lines. Header bold white. Columns whitespace-separated.

Example:
```
TICKER   PHASE   ENTRY     CURRENT   STOP      TYPE    UNREAL       R
AAPL     P1      185.00    187.45    180.00    HARD    +245.00      +0.5
MSFT     P2      405.00    412.30    400.00    TRAIL   +365.00      +1.5
NVDA     P1      895.00    892.10    850.00    HARD    -72.50       -0.1
```

**Color rules**:
- CURRENT column: green if ≥ entry, red if < entry
- UNREAL column: green if ≥ 0, red if < 0
- R column: green if ≥ 0, red if < 0
- PHASE: cyan
- TYPE: yellow

**Responsive behavior**:
- If positions > terminal height allows, the table body scrolls (header stays fixed)
- If terminal < 100 cols, R column is dropped
- If terminal < 80 cols, TYPE column is dropped

**Data source**: `state.positions` dict, live Alpaca prices via `alpaca.get_current_price()`

#### Activity Log

**Content**: Last 8 events, displayed in 2 columns (4 rows).
**Style**: Plain text, no tables. Events separated by spacing only.

Example:
```
  [10:32:01] ENTRY  AAPL  $187.45  x100          [10:28:45] EXIT  TSLA  +$450
  [10:15:22] STOP   MSFT  → $400.00 TRAIL        [10:05:00] SKIP  FLY   cooldown
```

**Event types and colors**:
- ENTRY: cyan
- EXIT: green if profit, red if loss
- STOP: yellow
- SKIP: dim grey
- ERROR: red
- WARN: yellow

**Data source**: Bounded queue (max 20 events) maintained by Dashboard. Events pushed by engine via `dashboard.log_event()`.

#### Footer Band

**Content**: Next scan countdown, market close time, WebSocket status, rate limit.
**Style**: Single line, dim grey. Horizontal rules above and below.

Example:
```
────────────────────────────────────────────────────────────────────────────────
  Next scan: 28s    Market closes in: 3h 28m    WebSocket: connected    Rate limit: 12/500
────────────────────────────────────────────────────────────────────────────────
```

**Color rules**:
- Next scan: white
- Market closes in: white (yellow if < 30 min, red if < 5 min)
- WebSocket: green if connected, red if disconnected
- Rate limit: white (yellow if > 80%, red if circuit open)

## Data Flow

### Update Cycle (every ~30s)

1. Engine calls `dashboard.update(state_data)`
2. Dashboard fetches:
   - Live prices for all open positions via Alpaca
   - Day P&L from trade log
   - Pending order count
   - Rate limiter status
   - WebSocket health
3. Dashboard re-renders all sections
4. `Live.update()` redraws the screen

### Event Logging (async)

1. Engine fires entry/exit/stop/skip
2. Engine calls `dashboard.log_event(type, data)`
3. Dashboard appends to bounded queue (drops oldest if > 20)
4. Dashboard triggers immediate re-render (no waiting for next cycle)

## Integration Points

### Engine Modifications

In `paper_engine_alpaca.py`:

1. **Replace `_print_status()`**: Instead of `print()` statements, call `self.dashboard.update(state_data)`
2. **Replace event prints**: Instead of `print(f"🚀 AUTO-ENTRY: {ticker}...")`, call `self.dashboard.log_event("ENTRY", {...})`
3. **Add `self.dashboard` initialization**: Create in `__init__` after state setup
4. **Graceful fallback**: Wrap dashboard calls in try/except; if rich missing or terminal non-TTY, use old prints

The demo script (`scripts/demo_dashboard.py`) already validates the rendering approach. The real implementation extracts the renderers into `traderlib/dashboard.py` and wires them into the engine.

### State Data Contract

`Dashboard.update()` accepts a dict (or dataclass) with:

```python
{
    "equity": float,
    "cash": float,
    "day_pnl": float,
    "unrealized_pnl": float,
    "open_positions": int,
    "pending_orders": int,
    "positions": Dict[str, Position],
    "market_status": str,          # "OPEN" | "CLOSED" | "PRE"
    "vix": Optional[float],
    "ws_connected": bool,
    "api_requests": int,
    "api_max": int,
    "rate_limit_pct": float,
    "next_scan_seconds": int,
    "market_close_seconds": Optional[int],
}
```

`Dashboard.log_event()` accepts:

```python
{
    "type": str,       # "ENTRY" | "EXIT" | "STOP" | "SKIP" | "ERROR" | "WARN"
    "timestamp": str,  # ISO format or HH:MM:SS
    "ticker": Optional[str],
    "message": str,
    "detail": Optional[str],   # e.g. "$187.45 x100"
    "pnl": Optional[float],    # for EXIT events
}
```

## Error Handling

- **rich not installed**: Dashboard methods no-op. Engine falls back to `print()`.
- **Terminal non-TTY** (piped output): Dashboard auto-detects and disables screen mode, falls back to plain text.
- **Terminal resize**: Dashboard re-flows on next update. `rich` handles this automatically.
- **Price fetch failure**: Current price shown as `--` in dim grey. UNREAL P&L blanked.
- **Engine crash during dashboard update**: Exception logged, dashboard disabled for remainder of session.

## Testing

1. **Unit test**: `test_dashboard_render()` — mock state data, verify output contains expected sections.
2. **Color test**: Verify green/red text appears for positive/negative values.
3. **Responsive test**: Verify columns collapse at 100/80/60 col breakpoints.
4. **Fallback test**: Uninstall rich (mock import failure), verify engine still runs with print output.
5. **Integration test**: Run engine with dashboard for 5 minutes, verify no screen corruption.

## Files Changed

- **NEW**: `traderlib/dashboard.py` — Dashboard class and section renderers
- **MODIFY**: `scripts/paper_engine_alpaca.py` — Wire dashboard into engine lifecycle
- **NEW**: `tests/test_dashboard.py` — Unit tests
- **MODIFY**: `requirements.txt` or `pyproject.toml` — Add `rich` dependency

## Dependencies

- `rich >= 13.0.0` (for `Live` screen mode and stable table rendering)

## Out of Scope

- Interactive keyboard controls (switching views, drill-down) — read-only display only
- Web-based dashboard — this is terminal-only
- Historical charts or sparklines — table-based only
- Persistence — dashboard is ephemeral, state lives in JSON files

## Future Considerations

- If position count grows > 20, consider a scrollable positions pane
- If activity log needs filtering, add event-type toggles (out of scope for v1)
- If multiple strategies run, add a strategy indicator to header
