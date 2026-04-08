# Paper Trading Engine - Implementation Plan

**Status:** Phase 1 Complete ✅ — Core engine built, Phase 2 ready  
**Created:** 2026-04-08  
**Priority:** High

---

## System Overview

**Architecture:** Single daemon with event loop  
**Mode:** Fully automated (no prompts)  
**Polling:** Every 30 seconds during market hours (9:30-16:00 ET)  
**State Management:** JSON files (no database)

---

## Phase 1: Core Engine ✅ COMPLETE

### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/paper_engine.py` | ~400 | Main daemon with event loop |
| `scripts/paper_state.py` | ~260 | Position state management |
| `scripts/paper_exits.py` | ~250 | Exit rule engine |

### Phase 1 Commands

```bash
# Start the paper trading engine
python3 scripts/paper_engine.py --capital 500000

# Run single iteration (for testing)
python3 scripts/paper_engine.py --capital 500000 --once
```

### Data Files

| File | Format | Purpose |
|------|--------|---------|
| `data/paper_positions.json` | JSON | Live open positions |
| `data/paper_account.json` | JSON | Account state (cash, equity, P&L) |
| `data/paper_trades.jsonl` | JSONL | Trade history (append-only) |

---

## Phase 2: Entry Rules (Auto-Execute)

### Trigger Conditions (ALL must pass)

```python
1. Price >= pivot * 0.99              # Within 1% of breakout
2. Volume >= avg_50d * 1.5            # Volume confirmation
3. SPY >= -0.3%                        # Market condition
4. Sector positions < 3                # Sector limit
5. Position value <= equity * 0.20     # Size limit
6. Cash >= position_value              # Buying power
```

### Auto-Execution

- No confirmation prompt
- Immediate execution on signal
- Calculate shares: `account_risk / (price - stop)`
- Initial stop: `price - 2*ATR`
- Log to console and trade history

---

## Phase 3: Exit Engine (Auto-Close)

### Exit Types

**1. Hard Stop (Initial)**
- Fixed at entry: `price - 2*ATR`
- Never moves backward

**2. Trailing Stop (Dynamic)**

| R Multiple | Action | Stop Location |
|------------|--------|---------------|
| +1R | Move to breakeven | `entry_price` |
| +1.5-2R | Trail 10 EMA | `max(stop, EMA10)` |
| +3R+ | Trail 21 EMA | `max(stop, EMA21)` |

**3. Profit Target**
- Minimum 2R from entry
- Extendable if momentum continues

---

## Phase 4: Data Models

### Position Object

```json
{
  "ticker": "KEYS",
  "status": "OPEN",
  "entry_date": "2026-04-08T10:30:00",
  "entry_price": 317.50,
  "shares": 150,
  "stop_price": 293.50,
  "target_price": 365.50,
  "initial_risk": 3600,
  "current_stop_type": "EMA10",
  "sector": "Technology",
  "unrealized_pnl": 1250,
  "r_multiple": 0.35
}
```

### Account State

```json
{
  "initial_capital": 500000,
  "cash": 452375,
  "equity": 503750,
  "open_positions": 3,
  "day_pnl": 3750,
  "month_pnl": 12500,
  "sector_exposure": {
    "Technology": 2,
    "Healthcare": 1
  }
}
```

---

## Phase 5: Risk Management (Hardcoded)

### Position Constraints

| Rule | Value | Enforcement |
|------|-------|-------------|
| Account risk per trade | 0.75% | Position sizing |
| Position size limit | <20% equity | Entry validation |
| Max positions per sector | 3 | Entry validation |
| Max new entries per day | 5 | Circuit breaker |
| Daily loss limit | -2% | Stop trading |

---

## Phase 6: CLI Commands

### Start Engine

```bash
python3 scripts/paper_engine.py --capital 500000
```

### View Status

```bash
python3 scripts/paper_portfolio.py live     # Real-time positions
python3 scripts/paper_portfolio.py today    # Today's trades
python3 scripts/paper_portfolio.py report   # Performance report
```

### Control

```bash
python3 scripts/paper_portfolio.py stop       # Graceful shutdown
python3 scripts/paper_portfolio.py close KEYS --reason "manual"  # Emergency close
```

---

## Phase 7: Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1 | Day 1 | Core engine, market hours, basic entry |
| Phase 2 | Day 2 | Volume confirmation, market conditions |
| Phase 3 | Day 3 | Trailing stops, EMA calculations |
| Phase 4 | Day 4 | CLI tools, reporting, testing |

**Total: ~950 lines across 4 files**

---

## Execution Flow Example

**Morning Startup:**
```
✓ Loaded watchlist: 23 tickers
✓ Account: $500,000 cash ready
🟢 ENGINE STARTED - Auto-trading enabled
```

**Auto-Entry:**
```
🚀 AUTO-ENTRY: KEYS at $317.50 x 150 shares
   Stop: $293.50 | Target: $365.50 | Risk: 0.72%
```

**Trailing Update:**
```
📈 KEYS +1.5R → Stop moved to 10 EMA ($312.00)
```

**Auto-Exit:**
```
🎯 KEYS stopped at $312.00 | P&L: +$6,675 (+1.85R)
```

---

## Open Questions (To Resolve)

1. **Data Source:** yfinance (free, 15min delay) or Alpaca (real-time, possible cost)?
2. **Notifications:** Telegram alerts on entries/exits or console-only?
3. **Pre-market:** Check for gap-up entries before 9:30 open?
4. **Partial Positions:** Auto-trim if position grows >20% of equity?

---

## Dependencies

- yfinance (market data)
- pandas (calculations)
- pytz (timezone handling)
- schedule (market hours)

---

**Next Action:** Build Phase 1 - Core engine with basic entry/exit logic
