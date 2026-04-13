# Backtesting Guide

*Simulate your strategy against historical data before risking real capital.*

---

## Why Backtest?

Trading without backtesting is like deploying code without running tests. You hope it works, but you don't know until real money is on the line.

The backtesting engine replays the Stage 2 momentum strategy day-by-day through historical data. It uses the same entry logic, exit rules, and position sizing as the live paper trading engine. The difference: simulated fills at T+1 open with deterministic slippage, no real money, and no surprises.

Backtesting answers three questions:
1. **Does this strategy have an edge?** Positive alpha over SPY buy-and-hold suggests yes.
2. **How bad can it get?** Max drawdown tells you the worst peak-to-trough decline.
3. **What happens if I change the parameters?** Risk profiles, position limits, and stop distances all affect results. Backtesting lets you see how.

---

## Quick Start

```bash
# Minimum viable backtest (requires Alpaca API keys)
python3 scripts/backtest.py --start 2025-10-01 --end 2026-04-01

# Use your watchlist instead of a hardcoded ticker list
python3 scripts/backtest.py --start 2025-10-01 --end 2026-04-01 --watchlist data/watchlist.csv

# Export results to CSV for deeper analysis
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --csv backtest_results
```

That's it. The engine fetches historical data from Alpaca, runs the simulation, and prints a metrics report.

---

## How It Works

The engine simulates trading one day at a time. Signals are generated at today's close, orders are filled at tomorrow's open (T+1).

```
For each trading day:
  ┌─────────────────────────────────────────────────────┐
  │ 1. Resolve pending fills from yesterday's signals   │
  │    - Exit fills first (free up capital)              │
  │    - Entry fills second (use freed capital)          │
  │    - Gap rejection: skip if T+1 open <= stop price   │
  │                                                      │
  │ 2. Update trailing stops                             │
  │    - ExitEngine returns new stop levels               │
  │    - Engine applies updates to positions              │
  │                                                      │
  │ 3. Evaluate exits for today                           │
  │    - Hard stop hit?                                   │
  │    - Trailing stop triggered?                         │
  │    - Profit target reached?                           │
  │                                                      │
  │ 4. Mark to market (record equity)                    │
  │                                                      │
  │ 5. Evaluate entries for today                         │
  │    - Scan watchlist tickers                            │
  │    - Score each setup (Stage 2, risk, pivot, RS)      │
  │    - Generate entry signals (queued for T+1 fill)     │
  └─────────────────────────────────────────────────────┘

After last trading day:
  - Liquidate all remaining positions at close
  - Fetch SPY benchmark data
  - Generate report
```

**Anti-look-ahead guarantee:** All data is sliced to `<= sim_date`. The strategy never sees future prices. This is enforced by `DataFrameProvider.get_bars(ticker, as_of)`, which returns only rows on or before the simulation date.

---

## CLI Reference

```bash
python3 scripts/backtest.py --start START --end END [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--start` | *required* | Start date (YYYY-MM-DD) |
| `--end` | *required* | End date (YYYY-MM-DD) |
| `--capital` | $100,000 | Initial capital |
| `--tickers` | None | Space-separated ticker list (overrides watchlist) |
| `--watchlist` | None | Path to CSV watchlist file (expects `Ticker` column) |
| `--risk-profile` | `conservative` | Risk profile: `conservative`, `aggressive`, or `tight_stops` |
| `--slippage` | 5 bps | One-way slippage in basis points |
| `--commission` | $0.005 | Commission per share (Alpaca Pro rate) |
| `--max-positions` | 10 | Maximum concurrent open positions |
| `--csv` | None | Export trade records and equity curve to CSV |
| `--dry-run` | False | Validate config without running the simulation |

**Note:** If neither `--tickers` nor `--watchlist` is provided, the engine uses `data/watchlist.csv` by default.

---

## Risk Profiles

Risk profiles overlay on top of the base configuration in `config/risk_config.yaml`. They change a few key parameters while leaving everything else at defaults.

| Parameter | Base | Conservative | Aggressive | Tight Stops |
|-----------|------|-------------|-----------|-------------|
| Risk per trade | 0.5% | 0.5% | 1.0% | 0.5% (base) |
| Max position size | 10% | 10% | 10% | 15% |
| Max stop distance | 10% | 8% | 15% | 5% |
| Min stop distance | 3% | 3% (base) | 3% (base) | 2% |

**What this means in practice:**

- **Conservative** (default): Smaller positions, tighter stop limits. Lower risk, lower reward.
- **Aggressive**: Double the risk per trade (1% vs 0.5%), allows stops up to 15%. More swings, both up and down.
- **Tight Stops**: For pivot-based setups where you can place stops at 2-5% below entry. The tighter stop lets you take a larger position (15% cap) while risking the same dollar amount.

**To select a profile:**

```bash
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --risk-profile aggressive
```

**To customize beyond the built-in profiles**, edit `config/risk_config.yaml`. Add a new profile under the `profiles:` section and reference it with `--risk-profile your_profile_name`. See the [Risk Configuration Guide](RISK_GUIDE.md) for detailed parameter explanations.

---

## Understanding the Report

After the simulation completes, the engine prints a metrics report. Here's what each section means.

### Returns

| Metric | What It Tells You |
|--------|-------------------|
| **Total Return** | End-to-end return. If you started with $100K and ended with $120K, this is +20%. |
| **Annualized Return** | CAGR, normalized to yearly rate. Useful for comparing across different backtest periods. |
| **Volatility** | Annualized standard deviation of daily returns. Higher = more bumpy ride. |

**What to look for:** A strategy with +15% annualized return and 10% volatility (Sharpe ~1.5) is more usable than one with +25% return and 40% volatility (Sharpe ~0.6). The ride matters, not just the destination.

### Risk

| Metric | What It Tells You |
|--------|-------------------|
| **Max Drawdown** | Worst peak-to-trough decline. If your $100K fell to $80K before recovering, that's -20% drawdown. |
| **Sharpe Ratio** | Risk-adjusted return. Above 1.0 is good, above 2.0 is excellent. Below 0.5 means you're getting paid poorly for the risk. |
| **Sortino Ratio** | Like Sharpe but only penalizes downside volatility. More forgiving of upside swings. |
| **Calmar Ratio** | Annualized return / max drawdown. Above 1.0 means your return exceeds your worst drawdown. |

**What to look for:** Max drawdown tells you the psychological and financial pain. If you can't stomach a -30% drawdown, you need tighter risk controls regardless of the return.

### Trades

| Metric | What It Tells You |
|--------|-------------------|
| **Win Rate** | % of trades that closed in profit. Stage 2 momentum typically wins 40-50% of trades. |
| **Profit Factor** | Gross profit / gross loss. Above 1.5 is solid. Below 1.0 means you're losing money. |
| **Avg R-Multiple** | Average P&L / initial risk. If you risk $500 per trade and average $750 profit, that's 1.5R. |

**What to look for:** A 40% win rate with a 2.5 profit factor works. A 60% win rate with a 0.8 profit factor doesn't. Win rate alone is meaningless. Focus on profit factor and average R-multiple.

### Costs

| Metric | What It Tells You |
|--------|-------------------|
| **Total Commissions** | Sum of all trade commissions paid. Should be a small fraction of total P&L. |
| **Total Slippage** | Currently tracked as $0 in v1. Slippage is embedded in fill prices. |

**What to look for:** If commissions are a large fraction of gross P&L, you're trading too often or your edge is too thin. A $100K account paying $500 in commissions over 6 months is fine. Paying $5,000 means something is wrong.

### Benchmark

| Metric | What It Tells You |
|--------|-------------------|
| **SPY Return** | What you'd get by buying and holding SPY over the same period. |
| **Alpha** | Your strategy's annualized return minus SPY's. Positive alpha means you beat the index. |

**What to look for:** Alpha is the whole point. If your backtest returns 12% but SPY returned 15%, your alpha is -3%. You'd have been better off buying an index fund. Positive alpha is the minimum bar for an active strategy.

### Data Quality

| Metric | What It Tells You |
|--------|-------------------|
| **Tickers Dropped** | How many tickers were excluded due to insufficient historical data. |
| **Gap Rejections** | Entry signals that were rejected because the next day's open gapped below the stop price. |

High ticker drops mean your watchlist includes stocks without enough history. High gap rejections mean the strategy is generating signals on volatile stocks where the stop is too tight.

---

## Entry Logic in Backtests

The `Stage2MomentumStrategy` mirrors the paper trading engine's entry logic. For each trading day, it:

1. **Scans watchlist tickers** that are not currently held
2. **Fetches historical data** up to `sim_date` (anti-look-ahead)
3. **Scores each ticker** using the same system as `entry_signals.py`

The entry score combines four factors:

| Component | Weight | What Measures |
|-----------|--------|---------------|
| Stage 2 Score | 30 pts | Technical health (MA stacking, proximity to highs) |
| Risk % | 30 pts | Stop distance as % of entry (tighter = better) |
| Distance to Pivot | 25 pts | How close to the breakout level |
| 6M Return + RS | 15 pts | Momentum and relative strength vs SPY |

**Minimum to trade:** The `min_entry_score` threshold is 60 by default. Only Tier 1 setups (score >= 60) generate entry signals.

**How to adjust:** In `config/risk_config.yaml`, change `entry.min_entry_score`. Lowering it to 50 generates more trades but with lower-quality setups. Raising it to 70 generates fewer trades with stronger setups.

---

## Exit Logic in Backtests

Exits use the same `ExitEngine` as the live paper trading engine. The engine evaluates every held position each day.

### Hard Stop

If the current price hits the stop, the position is closed. This is non-negotiable. The stop is set at entry using `max(2x ATR, recent 10-day low)`, bounded by 3-10% from the entry price (varies by risk profile).

### Trailing Stops

As a position moves into profit, the stop ratchets up. It never moves down.

| R-Multiple | Action | New Stop |
|-----------|--------|----------|
| +1.0R | Move to breakeven | `entry_price` |
| +1.5R | Trail EMA10 | 10-day exponential moving average |
| +3.0R | Trail EMA21 | 21-day exponential moving average |

**How it works in the backtest:** `ExitEngine.evaluate_exit()` returns an `ExitSignal` with `new_stop` and `new_stop_type` fields. The engine applies these updates to the position. The position itself is never mutated inside `evaluate_exit()`, unlike the older paper trading code. This separation keeps the backtest deterministic and testable.

### Profit Target

Two conditions trigger a profit-taking exit:
1. Current price >= `target_price` (calculated as 2R above entry at entry time)
2. R-multiple >= 2.0

Either condition closes the position with reason `TARGET_HIT` or `TARGET_HIT_X.XR`.

---

## Gap Rejections

When an entry signal is generated at day T, the order fills at day T+1's open. But if T+1 opens at or below the stop price, the stop would trigger immediately. Instead of opening a position that's immediately stopped out, the engine rejects the entry.

```bash
# Example output
Gap rejections: 3 entries skipped (stop would trigger at open)
  AAPL: signal at $150.00, stop at $142.50, T+1 open at $141.80
  NVDA: signal at $880.00, stop at $810.00, T+1 open at $805.20
  LITE: signal at $62.00, stop at $58.50, T+1 open at $57.90
```

Gap rejections are a feature, not a bug. They prevent the simulation from opening positions that would instantly lose money. In real trading, you'd cancel such orders too.

**If you see many gap rejections:** Your stops might be too tight, or you're trading volatile stocks around earnings/events. Try the `tight_stops` profile with a wider stop range, or filter out stocks with upcoming earnings.

---

## Tuning Parameters

### More Trades vs Better Trades

| Goal | Change | Effect |
|------|--------|--------|
| More trades | Lower `min_entry_score` to 50 | More signals, lower average quality |
| Fewer, better trades | Raise `min_entry_score` to 70 | Fewer signals, stronger setups |
| Larger positions | Use `aggressive` profile (1% risk/trade) | Bigger wins, bigger losses |
| Smaller positions | Use `conservative` profile (0.5% risk/trade) | Smaller swings |
| Tighter stops | Use `tight_stops` profile (2-5% range) | Larger position sizes, stopped out more often |
| Wider stops | Set `max_stop_distance_pct: 0.15` | Smaller position sizes, more room to breathe |

### Capital and Position Limits

```bash
# Small account simulation
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --capital 25000 --max-positions 3

# Large account simulation
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --capital 500000 --max-positions 20
```

`--max-positions` is the portfolio capacity. With 3 positions, you're concentrated. With 20, you're diversified but each position is smaller. The sweet spot for Stage 2 momentum is usually 5-10 positions.

### Slippage and Commissions

```bash
# Zero-friction simulation (optimistic baseline)
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --slippage 0 --commission 0

# High-friction simulation (pessimistic)
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --slippage 20 --commission 0.02
```

Default is 5bps slippage and $0.005/share commission (Alpaca Pro pricing). If your backtest is profitable at 20bps slippage, the edge is probably real. If it only works at 0bps, you're cutting it close.

---

## Exporting Results

```bash
# Export trade records and equity curve
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --csv backtest_output
```

This creates two files:
- `backtest_output.csv` - Trade records (ticker, entry/exit dates, prices, P&L, exit reason)
- `backtest_output_equity.csv` - Daily equity curve (date, equity value)

Open in a spreadsheet, plot in Python, or feed into your own analysis pipeline.

---

## Limitations

Every backtest has limitations. This engine is no exception. Knowing them prevents overconfidence.

### Survivorship Bias

The backtest runs on a static watchlist. Stocks that went bankrupt, were delisted, or dropped out of Stage 2 are not included unless they were in your watchlist at the time. In practice, this means the backtest may overstate returns because it doesn't account for stocks that failed.

The report includes a survivorship bias disclaimer. Take it seriously.

### Deterministic Slippage

Real slippage varies with liquidity, time of day, and market conditions. The engine applies a fixed 5bps. During high volatility, real slippage could be 10-20bps. During calm markets, it might be 1-2bps. The fixed assumption is a reasonable midpoint but won't match reality exactly.

### T+1 Fill Timing

All orders fill at the next day's open. In real trading, you might get partial fills, rejections, or better/worse prices depending on order type and market conditions. The engine doesn't model order book dynamics.

### Missing Features (v1)

These features exist in the paper trading engine but are not yet in the backtester:
- **Re-entry cooldown** - No cooldown after losses on the same ticker
- **Daily loss limit** - No halt after hitting -2% daily loss
- **Volume confirmation** - Entry signals don't filter by volume ratio
- **Market regime filter** - No SPY decline or VIX check before entries

These will be added in future versions. For now, the backtest is slightly more permissive than the live engine.

---

## Troubleshooting

### "No tickers passed validation"

The `AlpacaDataProvider` drops tickers with fewer than 252 trading days of history. If your watchlist contains recent IPOs or stocks that Alpaca doesn't have data for, they'll be excluded.

**Fix:** Check `data/watchlist.csv` for recently listed stocks. Remove them or use `--tickers` with a curated list of stocks that have at least 1 year of history.

### InsufficientDataError

If a ticker has data but not enough history (fewer than 252 rows), the data provider raises `InsufficientDataError`. This is logged during prefetch and the ticker is dropped from the simulation.

**Fix:** Either remove the ticker from your watchlist, or shorten the backtest period with `--start` set to a date after the ticker's IPO.

### Rate Limiting During Prefetch

The `AlpacaDataProvider` fetches data for each ticker individually, with a rate limit of 200 requests per minute. With a 30-ticker watchlist, prefetch takes about 10 seconds. With 100+ tickers, it could take a minute.

**Fix:** Use `--tickers` to limit to the stocks you care about. Or wait. The engine handles rate limiting automatically.

### "Cannot fetch SPY data"

The SPY benchmark fetch happens after the simulation. If Alpaca's API is rate-limited at that point, the benchmark return will show as N/A and alpha will be unavailable.

**Fix:** Wait a few minutes and retry. SPY data is also prefetched with the watchlist, so this error should be rare.

### All Trades Are Stopped Out

If every position hits the hard stop, check your risk profile. The `tight_stops` profile with 2-5% stop range can be too tight for volatile stocks. Switch to `conservative` (3-8% range) or `aggressive` (3-15% range).

```bash
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --risk-profile conservative
```

### Zero Alpha or Negative Alpha

The strategy isn't magic. In a strong bull market, SPY buy-and-hold often beats active strategies because the index captures everything. Alpha tends to show up in sideways or mildly bearish markets where stock selection matters.

**What to do:** Check if the Sharpe ratio is still above 1.0. A low-alpha, high-Sharpe strategy is still valuable because it takes less risk per unit of return. If both alpha and Sharpe are negative, the strategy parameters need adjustment. Try different risk profiles or raise `min_entry_score`.

---

## Quick Reference

```
# Basic backtest
python3 scripts/backtest.py --start YYYY-MM-DD --end YYYY-MM-DD

# With watchlist and risk profile
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 \
  --watchlist data/watchlist.csv --risk-profile conservative

# Export results
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --csv results

# Validate config without running
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --dry-run
```

**Key metrics to watch:**
- Sharpe > 1.0 = risk-adjusted edge exists
- Max drawdown < 20% = survivable
- Alpha > 0% = beats SPY
- Profit factor > 1.5 = winners outweigh losers

**Further reading:**
- [Risk Configuration Guide](RISK_GUIDE.md) for detailed parameter explanations
- [Development Guide](DEVELOPMENT.md) for contributing to the backtest module
- [Backtesting Feasibility Analysis](BACKTESTING_ENGINE_FEASIBILITY.md) for design rationale