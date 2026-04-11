# Trader

A systematic stock trading workflow system for momentum-driven swing trading, built on Python with Alpaca API (real-time) and yfinance fallback.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Usage](#usage)
- [Repository Structure](#repository-structure)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [License](#license)

## Features

- **Real-time Trading Engine** - Automated entry/exit via Alpaca API with WebSocket data
- **Stage 2 Screening** - 7-point momentum scoring system for trend identification
- **Risk Management** - Position sizing, sector limits, trailing stops, daily loss limits
- **Entry Signal Scanner** - Tier 1/2/3 rankings with proximity to pivot analysis
- **Pre/Post Market Reports** - HTML reports with futures, VIX, economic calendar
- **Watchlist Management** - Tier A/B/C tracking with automated scoring
- **Paper Trading** - Test strategies with simulated or Alpaca paper accounts

## Prerequisites

- Python 3.11+
- pip or uv package manager
- Make (optional, for convenience commands)
- Alpaca API keys (only for automated trading - scanners work without)

## Quick Start

### One-Command Setup

```bash
# Clone and setup
git clone https://github.com/MrLion/trader.git
cd trader
./setup.sh        # Or: make setup
```

### Manual Setup

<details>
<summary>Click to expand manual setup steps</summary>

```bash
# 1. Install package
pip install -e .

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (optional)

# 3. Create directories
mkdir -p data scans reports memory

# 4. Run first analysis
python3 scripts/entry_signals.py --ticker AAPL
```
</details>

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

The system follows Mark Minervini's Stage 2 methodology. See [AGENTS.MD](AGENTS.MD) for complete trading playbook.

### Quick Reference

**Stage 2 Criteria (7-Point):** Price > 50/100/200 MA, MA stacking, rising 200 MA, within 25% of high, 1.25x from low

**Entry Score Tiers:**
- **Tier 1 (>=60 pts):** Best setups - Price within +/-1% of pivot, Stage 2 >=6/7, Volume >=1.5x avg
- **Tier 2 (40-59 pts):** Good setups - Wait for better entry
- **Tier 3 (<40 pts):** Monitor only

**Risk Rules:**
- 0.75% account risk per trade
- Max 3 positions per sector
- Position size < 20% equity
- Trailing stops: +1R breakeven, +1.5R EMA10, +3R EMA21

## Data Model

The watchlist (`data/watchlist.csv`) tracks:
- Ticker, Stage (0-7), RS_Rank
- Pivot_Price, Stop_Level, ATR, Risk_%
- Sector, Industry, Pattern_Type
- Notes, Added_Date

## Development

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup instructions, testing commands, CI/CD workflow details, and contribution guidelines.

## Configuration

Copy `.env.example` to `.env` and configure:

**Required for Trading:**
```bash
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
```

**Optional:**
- `TELEGRAM_BOT_TOKEN` - For report delivery
- `MCSTOCK_USER/PASS` - For MC Stock Charts scraper

**Other Variables:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `PAPER_TRADING_DATA_DIR` | `./data` | Data directory for state |
| `TRADER_WATCHLIST` | `./data/watchlist.csv` | Custom watchlist path |
| `TRADER_OUTPUT` | `./reports` | Output directory |

## FAQ

**Do I need Alpaca API keys to use the scanners?**
No. Scanners and reports work with Yahoo Finance data. Only automated trading requires Alpaca.

**What's the difference between paper trading and the scanners?**
Scanners analyze stocks and generate reports. The paper trading engine (`paper_engine_alpaca.py`) executes trades automatically based on scanner signals.

**How do I reset my paper trading data?**
Delete `data/paper_positions.json` and restart the engine. It will sync fresh data from Alpaca.

**Where are my trade logs stored?**
All trades are logged to `data/paper_trades.jsonl` (JSON Lines format, append-only).

**Can I run this on a server?**
Yes. The engine runs headless. Use `python3 scripts/paper_engine_alpaca.py` with environment variables set.

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
- `docs/DEVELOPMENT.md` - Development setup, testing, and CI/CD guide
- `docs/RISK_GUIDE.md` - Risk management configuration and position sizing

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
