# Earnings Filter Plan (Live/Paper) — DRAFT

## Rules
| Rule | Condition | Action |
|---|---|---|
| No earnings-day entry | Today == earnings date | Skip signal, regardless of timing |
| Force exit — BMC | Earnings is tomorrow, reports pre-market | Exit today |
| Force exit — AMC | Today == earnings date, reports after close | Exit today (before close) |
| Re-entry post-earnings | Earnings passed, signal still valid | No restriction — enter normally |

Unknown timing → conservative default → treat as BMC (exit the day before).

## Proposed Architecture

### New file: `traderlib/earnings_calendar.py`
- `EarningsCalendar` class with in-memory daily cache keyed by `(ticker, fetch_date)`
- `get_next_earnings(ticker)` → `(date, timing)` where timing = 'amc' | 'bmc' | 'unknown'
- `is_earnings_blackout(ticker, today)` → bool — blocks new entry
- `should_force_exit(ticker, today)` → bool — triggers mandatory exit

### Integration: `paper_engine_alpaca.py`
- Exit loop: check `should_force_exit()` before normal stop/target logic → EXIT reason='EARNINGS_EXIT'
- Entry scan (`_analyze_ticker`): check `is_earnings_blackout()` before signaling

### Integration: `entry_signals.py`
- `_analyze_ticker()`: check `is_earnings_blackout()` after existing filters

## Open Questions
1. Data source: yfinance (original plan) vs FMP API (user has key — exploring)
2. yfinance date range handling: if yfinance returns a range instead of single date:
   - Option A: use earlier date (conservative)
   - Option B: skip gate until confirmed date available

## Status
COMPLETED — v0.6.2.9 (2026-04-18)
- FMP chosen as data source (paid plan, 300 calls/min, no daily cap)
- `traderlib/earnings_calendar.py` created
- `paper_engine_alpaca.py` wired: force exit + entry blackout
- `entry_signals.py` wired: entry blackout
- Backtest earnings gating deferred (needs historical FMP query pattern)
