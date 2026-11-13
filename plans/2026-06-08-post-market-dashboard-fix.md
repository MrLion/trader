# Fix Post-Market Dashboard: Show Real Account Data

**Date:** 2026-06-08  
**Status:** Implemented (v0.6.19.9)  
**Version target:** 0.6.19.9 (patch — bug fix, not feature)

## The Problem

When the market closes, the dashboard fabricates numbers instead of showing what Alpaca actually knows about the account. The result is confusing and untrustworthy:

| What you see | What's real | Why it hurts |
|---|---|---|
| CASH $0.00 | Alpaca's live cash balance | Looks like the account is empty |
| ACCOUNT VALUE = positions only | Full equity (cash + positions) | Understates account value |
| DAY P&L $0.00 | Today's realized P&L from closed trades | Looks like nothing happened |
| YTD $0 (0.0%) | Actual YTD from trade history | Zero is a false statement |
| TODAY: no closed trades yet | Actually had trades today | Direct contradiction with the closed trades list below |
| Total Trades: 0 | Actual count from trade history | Makes the "LIFETIME" panel look broken |

## The Fix

Replace the fabricated numbers with real data from **three sources the engine already has access to:**

1. **Alpaca REST API** (`get_account()`, `get_latest_prices_batch()`) — fetch live cash, equity, and current position prices
2. **Alpaca REST API** (`get_portfolio_history(period='YTD')`) — fetch YTD profit/loss and equity sparkline data
3. **Trade log on disk** (`trades.jsonl`) — count today's closed trades, compute realized P&L, count lifetime trades

## Refresh Cadence

Fetch once when entering post-market, then freeze. The dashboard header already shows "Data frozen since XX:XX:XX." No recurring API calls needed. This means:

- User opens the terminal after hours → sees correct numbers immediately
- Numbers stay frozen for the duration of post-market viewing
- Inconsistencies across refreshes (e.g. yfinance price changing 2 cents vs Alpaca) are avoided

## What Changes

### Architecture: `_load_post_market_state()` creates its own AlpacaClient

`_load_post_market_state(mode: str)` is a standalone function called before the engine exists. It currently reads `positions.json` and yfinance only. Instead:

- Create `AlpacaClient(mode=mode)` at the top of the function (same as the engine does at line 88)
- Make 4 Alpaca API calls, then dispose
- If all 4 calls fail, fall back to current yfinance-based behavior
- If some calls succeed and some fail, keep partial Alpaca data and fall back only the failed fields

This is one AlpacaClient instantiation + 4 API calls total, once per post-market entry.

### Data changes in `_load_post_market_state()` return dict

Fields the function will now produce in its return dict (previous hardcoded or missing fields are replaced):

| Return dict key | Source | Was | Fallback |
|---|---|---|---|
| `cash` | `account['cash']` from Alpaca | `0.0` | `0.0` (unchanged) |
| `equity` | `account['equity']` from Alpaca | position-sum (cashless) | position-sum (recalculated) |
| `day_pnl` | Trade log — today's EXIT events realized P&L sum | `0.0` | `0.0` |
| `unrealized_pnl` | `(current_price - entry_price) * shares` per position | yfinance prices | entry_price as current |
| `positions[N]['current_price']` | `get_latest_prices_batch()` | yfinance close | entry_price |
| `today_stats` | Trade log — today's EXIT events: wins, losses, total_pnl, avg_r | missing entirely | empty stats dict |
| `ytd_pnl` | `get_portfolio_history(period='YTD').profit_loss[-1]` | missing | trade log sum of 2026 EXIT realized_pnl |
| `ytd_pnl_pct` | `get_portfolio_history(period='YTD').profit_loss_pct[-1]` | missing | computed from trade log sum / initial capital |
| `lifetime_trade_count` | Count EXIT events in trade log (excludes SCALE/STOP) | missing | `0` |
| `equity_30d` | Last ~22 data points from `get_portfolio_history().equity` | empty `[]` | empty `[]` |
| `equity_all` | Full `get_portfolio_history().equity` list | empty `[]` | empty `[]` |
| `regime` | `get_historical_bars("SPY")` → 50-day SMA crossover | missing | `"UNKNOWN"` |

**Mapping notes:**
- **Trade log path:** `data_dir() / mode / 'trades.jsonl'` — same path the engine uses internally (`_get_today_trade_stats` at line 733, `_prefetch_lifetime_stats` at line 1614).
- **"Today" timezone:** `datetime.now().strftime('%Y-%m-%d')` — matches the engine's existing convention (system local = ET in practice).
- **SCALE inflation guard:** SCALE events (partial exits) are excluded from trade count and today_stats — they double-count exits. STOP events are excluded too, as they're system markers, not trade outcomes.
- **YTD second fallback:** If both Alpaca portfolio history and trade log fail, omit the YTD line from the dashboard entirely (dashboard conditional on the key being present and non-zero).
- **Regime computation refactoring note:** The 50-day SMA crossover logic currently lives inline in `_print_status()` (engine method). For use in the standalone `_load_post_market_state()`, it needs to be extracted as a small helper function (`_compute_regime(spy_bars)`) callable from both paths, or duplicated (~10 lines). Extract-to-helper is preferred to avoid drift.

### Fallback granularity

If Alpaca is partially reachable, keep what succeeds:
- `get_account()` fails → fall back to current position-sum for equity, hardcode cash=0
- `get_latest_prices_batch()` fails → fall back to yfinance for position prices
- `get_portfolio_history()` fails → fall back to trade log for YTD, skip sparkline
- `get_historical_bars()` fails → show `UNKNOWN` regime

If all 4 fail → run current yfinance-only logic as-is.

### Dashboard: no visual changes

- Dashboard is NOT dimmed in post-market — the header already says "POST-MARKET SUMMARY" in yellow and "Data frozen since XX:XX:XX" in red. That's sufficient.
- YTD line shown with real value from Alpaca portfolio history. Falls back to hidden only if Alpaca and trade log both fail.
- No other dashboard layout changes

### What stays untouched

- Open market behavior — no change
- The `account_value = cash + equity` formula (already fixed in v0.6.19.8)
- Dashboard layout, responsiveness, scrolling — no change
- Positions table, closed trades list, sector exposure — no change

## Cost

- 4 Alpaca API calls once when entering post-market (get_account, get_latest_prices_batch, get_portfolio_history, get_historical_bars)
- All code changes isolated to `_load_post_market_state()` in `scripts/paper_engine_alpaca.py`
- Dashboard changes: one field-hide conditional for YTD

## Testing

**Approach:** Test `_load_post_market_state()` as a standalone function with `AlpacaClient` mocked — no engine instantiation needed. Conftest already routes `data_dir()` to a temp directory so tests can write synthetic `positions.json` and `trades.jsonl` without touching production data. The existing `test_paper_engine_prefetch.py` is the template (same mocking patterns).

### Test cases

| # | Test | What it verifies | How |
|---|------|------------------|-----|
| 1 | Returns correct cash/equity from Alpaca | `state["cash"]` == mock account cash, `state["equity"]` == mock account equity | Patch `AlpacaClient`, stub `get_account()` returning `{"cash": 54200.0, "equity": 110500.0}`, write synthetic `positions.json`, call `_load_post_market_state("paper")`, assert return dict. |
| 2 | Position prices come from Alpaca, not yfinance | Each position's `current_price` matches Alpaca's latest price | Stub `get_latest_prices_batch()` returning `{"AAPL": 190.50, "NVDA": 900.00}`, assert position dict entries. |
| 3 | TODAY stats from trade log | `state["today_stats"]["total_pnl"]` matches sum of today's EXIT events | Write `trades.jsonl` with 3 today-EXIT events (+$50, -$100, +$150) in the test-visible data dir, assert `total_pnl == 100.0`, `wins == 2`, `losses == 1`. |
| 4 | Lifetime count from trade log | `state["lifetime_trade_count"]` counts all EXIT events (excludes SCALE/STOP) | Same trades.jsonl with 2 SCALE events + 5 EXIT events, assert count == 5. |
| 5 | YTD from portfolio history | `state["ytd_pnl"]` matches mock portfolio history's last profit_loss | Stub `get_portfolio_history(period="YTD")` returning synthetic payload. |
| 6 | Sparkline from portfolio history | `state["equity_30d"]` contains 22 equity data points | Same stub returns 22-element equity list. |
| 7 | Regime from SPY bars | `state["regime"]` is `"BULLISH"`/`"BEARISH"`/`"NEUTRAL"` based on SPY 50-day SMA | Stub `get_historical_bars("SPY")` returning 60 synthetic bars above/below 50-SMA. |
| 8 | Regime fallback when SPY < 50 bars | `state["regime"]` is `"UNKNOWN"` | Stub returning 30 bars only. |
| 9 | All-Alpaca-failure fallback | Same behavior as current yfinance path | All 4 Alpaca calls raise. **Also mock yfinance** (the fallback calls `yf.download()`) so the test is deterministic and doesn't hit the network. Assert output matches the old yfinance-based pattern. |
| 10 | Partial failure — portfolio history fails | YTD is computed from trade log, sparkline is empty | `get_account()` and `get_latest_prices_batch()` succeed, `get_portfolio_history()` raises. Assert sparkline empty, YTD from trade log. |
| 11 | Missing positions.json | Returns `None` | Don't write positions.json, assert `None`. |
| 12 | Dashboard: YTD hidden when $0 | YTD line not rendered in dashboard | Dashboard test (existing `test_dashboard.py` pattern): feed state with `ytd_pnl=0`, assert text doesn't contain "YTD". |

### What does NOT need tests

- Dashboard layout/rendering — unchanged, already covered by `test_dashboard.py`
- Open market behavior — unchanged
- AlpacaClient itself — already tested in `test_alpaca_client_extended.py` and `test_alpaca_integration.py`
- Engine lifecycle / main() loop — not changing

### Test location

New file: `tests/test_post_market_state.py` — mirrors the pattern from `test_paper_engine_prefetch.py` (same mocking approach, no engine instantiation needed since `_load_post_market_state` is a standalone function).

## Remaining Inconsistencies (Known)

- **DAY P&L means different things in open vs post-market.** Open market: accumulated session P&L since engine start. Post-market: today's realized P&L from closed trades only. Same label, different calculation. Fixing this requires a separate change to the open market path ("SESSION P&L" relabeling or daily reset logic). Out of scope for this patch.
- **Position prices will slightly lag.** Alpaca REST gives the latest trade price, which may differ from the real-time WebSocket feed by a few cents. Acceptable for post-market viewing.