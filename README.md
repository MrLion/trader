# Trader

A systematic stock trading workflow system for momentum-driven swing trading, built on Python with Alpaca API (real-time) and yfinance fallback.

## Overview

This is a command center for Stage 2 trading methodology (Mark Minervini's approach). The system helps you:

1. **Scan** markets for Stage 2 candidates (stocks in uptrends with strong relative strength)
2. **Manage** a tiered watchlist (A=actionable, B=developing, C=radar)
3. **Generate** pre-market and post-market reports
4. **Execute** with discipline via entry/exit protocols

## Quick Start

### One-Command Setup

```bash
# Run the setup script (creates directories, installs deps, copies .env, installs pre-commit hooks)
./setup.sh

# Or use Make
make setup
```

### Manual Setup

```bash
# 1. Install package in editable mode (recommended)
pip install -e .

# Or install dependencies only
pip install -r requirements.txt

# 2. Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys (optional, for Telegram and Alpaca)

# 3. Create required directories
mkdir -p data/config scans reports memory

# 4. (Optional) Install pre-commit hooks
pre-commit install

# 5. Run your first analysis
python3 scripts/entry_signals.py --ticker AAPL
```

## Repository Structure

```
scripts/          - Python CLI tools for analysis, scanning, and trading
traderlib/        - Library modules (alpaca_client, order_manager, etc.)
data/             - watchlist.csv, portfolio, and trade logs
scans/            - Daily CSV outputs from sector/stock screens
reports/          - Generated HTML market reports
memory/           - Daily logs and curated memories
.gstack/          - QA reports and analysis (gitignored)
AGENTS.MD         - Complete trading playbook
CLAUDE.md         - Development operations guide
```

## Scripts by Function

### Market Analysis

Deep analysis of individual stocks and your watchlist.

| Script | Purpose | Example Command |
|--------|---------|-----------------|
| `entry_signals.py` | Find tickers meeting entry criteria (no execution) | `python3 scripts/entry_signals.py` |

**Entry Signals Scanner:**
```bash
# Scan watchlist for Tier 1 entry signals
python3 scripts/entry_signals.py

# Include Tier 2 signals (score 40-59)
python3 scripts/entry_signals.py --min-tier 2

# Deep analysis on single ticker
python3 scripts/entry_signals.py --ticker AAPL

# Scan specific tickers
python3 scripts/entry_signals.py --tickers AAPL MSFT NVDA

# Export to CSV
python3 scripts/entry_signals.py --export-csv

# Export to HTML report
python3 scripts/entry_signals.py --export-html
```

**Entry Criteria:**
- Entry Score >= 60 (Tier 1) or >= 40 (Tier 2)
- Distance to Pivot within +/-1.0%
- Market condition: SPY >= -0.3%

---

### Market Scans

Broad market screening for Stage 2 candidates and sector performance.

| Script | Purpose | Example Command |
|--------|---------|-----------------|
| `sector_scan.py` | Daily sector ETF performance ranking | `python3 scripts/sector_scan.py` |
| `sector_scan_comprehensive.py` | Extended sector scan with comprehensive data | `python3 scripts/sector_scan_comprehensive.py` |
| `stage2_rs_screen.py` | Screen universe for Stage 2 + RS candidates | `python3 scripts/stage2_rs_screen.py` |

---

### Reports

Generate pre-market and post-market briefings (console or HTML).

| Script | Purpose | Example Command |
|--------|---------|-----------------|
| `premarket_report.py` | Pre-market briefing with futures, VIX, economic calendar | `python3 scripts/premarket_report.py --html` |
| `postmarket_report.py` | Post-market analysis and trade logging | `python3 scripts/postmarket_report.py --html` |
| `deliver_report.py` | Deliver HTML reports via Telegram | `python3 scripts/deliver_report.py --file report.html` |

**Pre-Market Report Features:**
- Overnight futures (ES, NQ, RTY, YM, CL, GC)
- VIX level classification (Low <18, Elevated 18-28, High >28)
- Crypto tracking (BTC, ETH)
- Economic calendar with risk assessment
- Major indices vs 20/50/200 MA
- Sector leaders from scan data
- Watchlist entry scores (Tier 1/2/3)

**Post-Market Report Features:**
- Market close summary (SPY, QQQ, IWM) with intraday ranges
- VIX analysis with level classification
- Regime Assessment with signal grid
- Watchlist performance (change %, volume, distance to pivot)
- Gap detection (>3% moves) with volume confirmation
- Dynamic action items based on today's action

**Report Delivery:**
```bash
# Deliver via Telegram (requires TELEGRAM_BOT_TOKEN env var)
python3 scripts/deliver_report.py --file reports/premarket_report.html --caption "Morning briefing"

# Test delivery without sending
python3 scripts/deliver_report.py --file report.html --dry-run --verbose
```

---

### Data & Watchlist

Manage your trading universe and import external ideas.

| Script | Purpose | Example Command |
|--------|---------|-----------------|
| `watchlist_manager.py` | Add, remove, list watchlist items | `python3 scripts/watchlist_manager.py add AAPL "Notes"` |
| `mcstock_scraper.py` | Scrape trade ideas from MC Stock Charts | `python3 scripts/mcstock_scraper.py --populate-watchlist` |

**Watchlist Management:**
```bash
# Add ticker with notes
python3 scripts/watchlist_manager.py add AAPL "Pullback to 21 EMA"

# Remove ticker
python3 scripts/watchlist_manager.py remove AAPL

# List all tickers
python3 scripts/watchlist_manager.py list

# Populate from scan CSV
python3 scripts/watchlist_manager.py populate /path/to/scan.csv
```

**MC Stock Charts Scraper:**
```bash
python3 scripts/mcstock_scraper.py
python3 scripts/mcstock_scraper.py --populate-watchlist
python3 scripts/mcstock_scraper.py --date 2026-04-06 --output data/mc_ideas.csv
```

---

### Automated Trading (Alpaca)

Execute trades automatically via Alpaca API with real-time WebSocket data.

| Script | Purpose | Example Command |
|--------|---------|-----------------|
| `paper_engine_alpaca.py` | Main trading engine (auto-entry/exit) | `python3 scripts/paper_engine_alpaca.py` |
| `paper_portfolio.py` | Monitor positions and P&L | `python3 scripts/paper_portfolio.py status` |
| `setup_alpaca.py` | Configure Alpaca credentials | `python3 scripts/setup_alpaca.py` |
| `validate_alpaca.py` | Test connection and validation | `python3 scripts/validate_alpaca.py` |

**Setup:**
```bash
# Configure credentials
python3 scripts/setup_alpaca.py

# Test connection
python3 scripts/setup_alpaca.py --test

# Validate everything
python3 scripts/validate_alpaca.py
```

**Or set environment variables:**
```bash
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
```

**Start Trading:**
```bash
# Paper trading (default)
python3 scripts/paper_engine_alpaca.py

# With custom starting capital
python3 scripts/paper_engine_alpaca.py --capital 500000

# For live trading (real money)
python3 scripts/paper_engine_alpaca.py --mode live
```

**Monitor Positions:**
```bash
# View account status (cash, equity, day P&L, unrealized P&L, open positions)
python3 scripts/paper_portfolio.py status

# Real-time positions with current prices
python3 scripts/paper_portfolio.py live

# Today's trades
python3 scripts/paper_portfolio.py today

# Full trade history
python3 scripts/paper_portfolio.py history

# Performance report
python3 scripts/paper_portfolio.py report

# Emergency close position
python3 scripts/paper_portfolio.py close AAPL --reason "manual"
```

**Status Report Fields:**
- **Cash:** Available buying power
- **Account Value:** Cash + position values
- **Day P&L:** Realized gains from closed positions today
- **Unrealized P&L:** Current gains/losses from open positions

---

## Trading Framework

### Stage 2 Criteria (7-Point System)

| Criterion | Points | Description |
|-----------|--------|-------------|
| Price > 50 MA | 1 pt | Short-term trend confirmation |
| Price > 100 MA | 1 pt | Medium-term trend confirmation |
| Price > 200 MA | 1 pt | Long-term trend confirmation |
| MA Stacking (50 > 100 > 200) | 1 pt | Proper moving average alignment |
| 200 MA Rising (20+ days) | 1 pt | Sustained uptrend confirmation |
| Within 25% of 52-week high | 1 pt | Proximity to highs |
| >= 1.25x 52-week low | 1 pt | Recovery from lows |

**Compliance Thresholds:**
- 6-7 pts: Excellent Stage 2 (Tier 1 quality)
- 4-5 pts: Good Stage 2 (Tier 2 quality)
- <4 pts: Developing (Tier 3)

### Universe Filter

- Price >= $10
- Average daily dollar volume >= $20M
- Market cap >= $1B
- NYSE/NASDAQ only

### Entry Score Tiers

Calculated using scoring formulae (max 110 pts):

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Stage 2 Score | 30 pts | >=6/7 = +30, >=5/7 = +25, >=4/7 = +20, >=3/7 = +10, >=2/7 = +5, <2 = +0 |
| Risk % | 30 pts | <10% = +30, <15% = +20, <20% = +10, <25% = +5, >=25% = +0 |
| Proximity | 25 pts | Within +/-3% of pivot = +25, +/-5% = +15, +/-10% = +5 |
| Momentum | 15 pts | 6M return >50% = +15, >25% = +10, <=25% = +0 |
| Relative Strength | 10 pts | RS 6M >20% = +10, >10% = +5, <=10% = +0 |

| Tier | Score | Stage 2 Min | Meaning |
|------|-------|-------------|---------|
| Tier 1 | >= 60 pts | 6/7 | Best entry setups -- ready now |
| Tier 2 | 40-59 pts | 4/7 | Good setups -- wait for better entry |
| Tier 3 | < 40 pts | <4/7 | Monitor only -- too far or too wide |

### Entry Protocol (Manual)

1. **Trigger:** Price within +/-1% of pivot
2. **Volume:** Tracking >= 1.5x 50-day average
3. **Market:** SPY/QQQ green or <= 0.3% down
4. **Risk Calc:** Account risk = 0.75% equity; Shares = Account risk / Risk per share
5. **Execute:** Limit buy with stop-market placed immediately

### Auto-Entry Rules (Alpaca Engine)

The engine enters when **ALL** conditions are met:

| Rule | Threshold |
|------|-----------|
| Entry Score | >= 60 (Tier 1) |
| Distance to Pivot | +/- 1% (symmetric) |
| Volume | >= 1.5x average |
| Market Condition | SPY >= -0.3% |
| Sector Limit | < 3 positions/sector |
| Position Size | < 20% equity |
| Daily Entries | <= 5 per day (circuit breaker) |
| Daily Loss | > -2% equity (stop trading) |

### Auto-Exit Rules

| R Multiple | Stop Type | Trigger |
|------------|-----------|---------|
| +1R | BREAKEVEN | Move to entry price |
| +1.5-2R | EMA10 | Trail 10-day EMA |
| +3R+ | EMA21 | Trail 21-day EMA |
| Hard Stop | Initial | Price hits 2xATR stop |
| Target | 2R+ | Profit target hit |

### Position Management

- Max 3 positions per GICS sector
- Position size < 20% of equity
- Trailing stops: +1R -> breakeven, +1.5-2R -> 10 EMA, +3R+ -> 21 EMA
- Profit target: Min 2R
- Account risk per trade: 0.75%

## Data Model

The watchlist (`data/watchlist.csv`) tracks:
- Ticker, Stage (0-7), RS_Rank
- Pivot_Price, Stop_Level, ATR, Risk_%
- Sector, Industry, Pattern_Type
- Notes, Added_Date

## Development Commands

Use the Makefile for common development tasks:

```bash
# Setup (run once)
make setup              # Full setup (directories, deps, .env, pre-commit hooks)

# Testing
make test               # Run test suite with coverage
make test-coverage      # Generate HTML coverage report

# Code Quality (pre-commit hooks)
pre-commit run          # Run hooks on staged files
pre-commit run --all-files  # Run hooks on all files
make lint               # Run linter (flake8)
make format             # Format code with black

# Maintenance
make clean              # Remove cache files
```

### Pre-commit Hooks

Pre-commit hooks automatically check code quality before each commit:

```bash
# Install hooks (one-time setup)
pre-commit install

# Run manually
pre-commit run

# Skip hooks for a specific commit (emergency only)
git commit -m "message" --no-verify
```

Hooks configured:
- **trailing-whitespace** - Removes trailing whitespace
- **end-of-file-fixer** - Ensures files end with a newline
- **black** - Python code formatting
- **isort** - Import sorting
- **flake8** - Python linting
- **check-yaml/json/toml** - Syntax validation

## Configuration

### Environment Variables (.env)

All API credentials can be configured via a `.env` file in the project root (copied from `.env.example`):

```bash
# Alpaca API (required for paper/live trading)
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here

# Telegram (optional - for report delivery)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=-4872065090

# MC Stock Charts (optional - for scraper)
MCSTOCK_USER=your_username_here
MCSTOCK_PASS=your_password_here
```

### Other Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PAPER_TRADING_DATA_DIR` | Data directory for paper trading state | `./data` |
| `TRADER_WATCHLIST` | Path to custom watchlist CSV | `./data/watchlist.csv` |
| `TRADER_OUTPUT` | Path to custom output directory | `./reports` |

**Example:**
```bash
# Use custom data directory (useful for testing)
export PAPER_TRADING_DATA_DIR=/path/to/test/data
python3 scripts/paper_engine_alpaca.py
```

## CI/CD

This project uses **GitHub Actions** for automated testing.

### Workflow Features
- **Multi-version testing:** Python 3.11, 3.12, 3.13
- **Coverage enforcement:** Fails if coverage drops below 50%
- **Automatic triggers:** Runs on every push to `main`/`develop` and all pull requests
- **Artifacts:** Coverage reports uploaded for each run

### Viewing Results
Check the **Actions** tab in GitHub to see:
- Test results per Python version
- Coverage reports
- Build status

### Coverage Reporting
Coverage reports are uploaded to:
- **Codecov** (if configured)
- **GitHub Artifacts** (retained for 7 days)

To generate coverage locally:
```bash
pytest tests/ --cov=traderlib --cov=scripts --cov-branch --cov-report=html
open htmlcov/index.html
```

## External Integrations

- **Primary Data**: Alpaca API (WebSocket + REST) for real-time prices
- **Fallback Data**: Yahoo Finance via `yfinance` (when Alpaca unavailable)
- **Automated Trading**: Alpaca paper/live accounts
- **Communications**: Telegram via `deliver_report.py` or `openclaw message send`
- **Broker**: Alpaca (automated) or manual execution

## Documentation

- `AGENTS.MD` - Complete trading playbook with operating rhythm, entry/exit protocols, and journaling guidelines
- `CLAUDE.md` - Development operations and architecture notes
- `TOOLS.md` - Technical documentation for yfinance and script usage

## Operational Runbooks

Failure mode documentation for production incidents:

- [API Outage](docs/runbooks/api_outage.md) - Alpaca API down, connection timeouts
- [Partial Fill](docs/runbooks/partial_fill.md) - Position size doesn't match order
- [Stuck Position](docs/runbooks/stuck_position.md) - Can't exit, ticker halted/delisted
- [Data Quality](docs/runbooks/data_quality.md) - Entry scores wrong, Stage 2 miscalculated

## Recent Changes

See [CHANGELOG.md](CHANGELOG.md) for a complete history of changes.

## License

See LICENSE file for details.
