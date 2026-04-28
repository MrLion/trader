# Getting Started

A quick-start guide for new users of the trading system.

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.11+** — Check with `python3 --version`
- **pip or uv** — For package management
- **Git** — To clone the repository

Optional for automated trading:
- **Alpaca API keys** — Only needed for live/paper trading automation

---

## Installation

### Step 1: Clone and Setup

```bash
git clone https://github.com/MrLion/trader.git
cd trader
./setup.sh
```

The setup script will:
- Create necessary directories (`data/`, `scans/`, `reports/`, `memory/`)
- Install Python dependencies
- Set up configuration files

### Step 2: Verify Installation

```bash
# Run the test suite
make test

# Or run a quick verification
python3 scripts/entry_signals.py --help
```

You should see the help output without errors.

---

## Your First Workflow

### 1. Build Your Watchlist

The watchlist is your trading universe. Start by adding a few tickers:

```bash
# Add a single ticker
python3 scripts/watchlist_manager.py add AAPL

# Add with notes
python3 scripts/watchlist_manager.py add NVDA "Semiconductor leader, Stage 2"

# View your watchlist
python3 scripts/watchlist_manager.py list
```

**Empty watchlist?** The system will guide you with:
- How to populate from scan CSV files
- How to run market scans
- Direct links to documentation

### 2. Run Your First Scan

Scan your watchlist for entry signals:

```bash
# Scan for Tier 1 signals only (score ≥60)
python3 scripts/entry_signals.py

# Include Tier 2 signals (score ≥40)
python3 scripts/entry_signals.py --min-tier 2

# Export to CSV
python3 scripts/entry_signals.py --export-csv
```

**What you're looking for:**
- **🔥 READY NOW**: Score ≥60, within ±1% of pivot
- **⏳ CLOSE TO PIVOT**: Score ≥60, 1-3% from pivot (watch for breakout)
- **📈 EXTENDED**: Score ≥60, but >3% from pivot (wait for pullback)

Each signal shows:
- Entry score (0-100)
- Tier (1/2/3)
- Stage 2 score (0-8)
- Distance to pivot
- Risk percentage
- **Age** (how fresh the signal is)

### 3. Analyze a Single Ticker

Deep dive on a specific stock:

```bash
python3 scripts/entry_signals.py --ticker AAPL
```

This shows:
- Current price vs pivot/stop/target
- Stage 2 score breakdown
- Risk-adjusted position size
- Recent performance metrics

---

## Daily Workflow

### Pre-Market (6:00–9:30 ET)

```bash
# Generate pre-market briefing
python3 scripts/premarket_report.py --html

# Check sector performance
python3 scripts/sector_scan_comprehensive.py
```

**Review:**
- Overnight futures action
- VIX level (volatility gauge)
- Economic calendar events
- Your watchlist entry scores

### Market Hours (9:30–16:00 ET)

**Paper Trading (Automated):**

```bash
# Start paper trading engine
python3 scripts/paper_engine_alpaca.py
```

The engine will:
- Monitor your watchlist for entry signals
- Automatically enter positions on confirmed breakouts
- Manage trailing stops (breakeven at +1R, EMA10 at +1.5R, EMA21 at +3R)
- Log all trades to `data/paper_trades.jsonl`

**Monitor positions:**

```bash
# View account status
python3 scripts/paper_portfolio.py status

# Real-time position values
python3 scripts/paper_portfolio.py live

# Today's trades
python3 scripts/paper_portfolio.py today
```

### Post-Market (After 16:00 ET)

```bash
# Generate post-market analysis
python3 scripts/postmarket_report.py --html

# Sector scan for new ideas
python3 scripts/sector_scan_comprehensive.py
```

---

## Setting Up Automated Trading

### Option 1: .env File (Recommended)

```bash
cp .env.example .env
# Edit .env with your keys
```

The `.env` file uses mode-specific key names:
- `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` — Paper trading
- `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` — Live trading
- `FMP_API_KEY` — Optional, for earnings/economic calendar

### Option 2: Interactive Setup

```bash
python3 scripts/setup_alpaca.py
```

This saves credentials to `config/secrets/alpaca_config.json`.

### Option 3: Environment Variables

```bash
export ALPACA_PAPER_API_KEY="your_paper_api_key"
export ALPACA_PAPER_SECRET_KEY="your_paper_secret_key"

# Optional: FMP API key for earnings/economic calendar in pre-market reports
# Get key at: https://financialmodelingprep.com/developer/docs
export FMP_API_KEY="your_fmp_key"
```

### Validate Your Setup

```bash
# Test API connection
python3 scripts/setup_alpaca.py --test

# Full validation
python3 scripts/validate_alpaca.py
```

---

## Understanding the System

### Entry Score Components

| Component | Max Points | Criteria |
|-----------|-----------|----------|
| Stage 2 Score | 30 | Buckets: 7-8/8 → 30, 6/8 → 25, 5/8 → 20, 4/8 → 15, 3/8 → 10, 2/8 → 5 |
| Risk % | 30 | <10% = +30, <15% = +20, etc. |
| Proximity to Pivot | 25 | <3% = +25, <5% = +15 |
| Momentum | 15 | 6M return >50% = +15 |
| RS | 10 | Beating SPY by >20% = +10 |
| **MA Penalties** | **-30** | -20 if below 50 MA, -10 if below 20 MA (floor at 0) |

**Tier Classification:**
- **Tier 1 (≥60 pts, stage2 ≥6)**: Immediate action if within pivot range
- **Tier 2 (40-59 pts, stage2 ≥5)**: Developing setups, watch closely
- **Tier 3 (<40 pts)**: Not ready, monitor from distance

### Stage 2 Criteria (8-Point System, 1 point each)

1. Price above 20-day SMA (short-term trend)
2. Price above 50-day SMA (medium-term trend)
3. Price above 100-day SMA (intermediate trend)
4. Price above 200-day SMA (long-term trend)
5. 50 SMA > 100 SMA > 200 SMA (proper stacking, 20 MA excluded as too volatile)
6. 200-day SMA rising (≥1% over 20 days)
7. Within 25% of 52-week high
8. Price ≥ 1.25x 52-week low (strong recovery)

### Risk Management Rules

- **Position Size**: Max 1% account risk per trade
- **Sector Limit**: Max 3 positions per sector
- **Daily Loss Limit**: Stop trading if down >2% in a day
- **Trailing Stops**:
  - +1R: Move to breakeven
  - +1.5R: Trail 10 EMA
  - +3R: Trail 21 EMA

---

## Common Commands Reference

### Watchlist Management

```bash
# Add ticker
python3 scripts/watchlist_manager.py add TSLA "EV leader"

# Remove ticker
python3 scripts/watchlist_manager.py remove TSLA

# List with portfolio overlap indicator
python3 scripts/watchlist_manager.py list

# Populate from scan CSV
python3 scripts/watchlist_manager.py populate scans/leading_stocks_2026-04-11.csv
```

### Market Analysis

```bash
# Entry signals (Tier 1 only)
python3 scripts/entry_signals.py

# Include Tier 2
python3 scripts/entry_signals.py --min-tier 2

# Single ticker deep dive
python3 scripts/entry_signals.py --ticker AAPL

# Sector scan
python3 scripts/sector_scan_comprehensive.py

# Entry signals scan
python3 scripts/entry_signals.py
```

### Reports

```bash
# Pre-market HTML report
python3 scripts/premarket_report.py --html

# Post-market HTML report
python3 scripts/postmarket_report.py --html

# Deliver via Telegram
python3 scripts/deliver_report.py --file reports/premarket_report.html
```

### Paper Trading

```bash
# Start automated trading
python3 scripts/paper_engine_alpaca.py

# With custom capital
python3 scripts/paper_engine_alpaca.py --capital 500000

# Monitor positions
python3 scripts/paper_portfolio.py status
python3 scripts/paper_portfolio.py live
python3 scripts/paper_portfolio.py today

# Manual operations
python3 scripts/paper_portfolio.py close AAPL --reason "manual"
python3 scripts/sync_state.py
```

---

## Troubleshooting

### "Alpaca API keys not configured"

**Problem:** The system can't find your API credentials.

**Solutions:**
1. Set environment variables:
   ```bash
   export ALPACA_API_KEY="your_key"
   export ALPACA_SECRET_KEY="your_secret"
   ```
2. Run setup script: `python3 scripts/setup_alpaca.py`
3. Create `.env` file with credentials

### "Watchlist is empty"

The system will show you how to populate it:
1. From scan CSV: `watchlist_manager.py populate scans/FILE.csv`
2. Add manually: `watchlist_manager.py add TICKER`
3. Run scans: `sector_scan_comprehensive.py`

### "No entry signals found"

Common reasons:
- Market filter blocking (SPY down >0.3%)
- No tickers meeting Tier 1 criteria
- Watchlist is empty or all stocks extended

Try: `python3 scripts/entry_signals.py --min-tier 2` to see Tier 2 setups.

### Import Errors

```bash
# Ensure you're in the project root
cd /path/to/trader

# Reinstall if needed
pip install -e .
```

---

## Next Steps

1. **Read the Risk Guide**: `docs/RISK_GUIDE.md`
2. **Review Runbooks**: `docs/runbooks/` for operational guides
3. **Study AGENTS.MD**: Trading framework and daily rhythm
4. **Backtest Strategy**: See `docs/BACKTESTING_ENGINE_FEASIBILITY.md`

---

## Support

- **Documentation**: Check `docs/` directory
- **Issues**: Review `TODOS.md` for known items
- **Changelog**: See `CHANGELOG.md` for recent updates

---

*Last updated: 2026-04-15*
