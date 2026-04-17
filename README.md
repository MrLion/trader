# Trader

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()

A systematic stock trading workflow system for momentum-driven swing trading, built on Python with Alpaca API (real-time trading) and yfinance for reports/analysis.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Scripts by Function](#scripts-by-function)
- [Repository Structure](#repository-structure)
- [Trading Framework](#trading-framework)
- [Data Model](#data-model)
- [Configuration](#configuration)
- [Development](#development)
- [External Integrations](#external-integrations)
- [FAQ](#faq)
- [Documentation](#documentation)
- [License](#license)

## Features

- **Real-time Trading Engine** - Automated entry/exit via Alpaca API with resilient WebSocket (health watchdog, exponential backoff, graceful shutdown)
- **Stage 2 Screening** - 8-point momentum scoring system with MA penalties for trend identification
- **Risk Management** - Position sizing, sector limits, trailing stops, daily loss limits
- **Entry Signal Scanner** - Tier 1/2/3 rankings with proximity to pivot analysis
- **Pre/Post Market Reports** - HTML reports with futures, VIX, economic calendar
- **Watchlist Management** - Tier A/B/C tracking with automated scoring
- **Backtesting Engine** - Simulate strategies against historical data with execution modeling
- **Paper Trading** - Test strategies with simulated or Alpaca paper accounts
- **Strategy Plugins** - Pluggable strategy architecture with auto-discovery registry (VCP, Stage 2, Composite)
- **Trend Screener** - MA convergence detection with MarketSurge-style filters

## Prerequisites

- Python 3.11+
- pip or uv package manager
- Make (optional, for convenience commands)
- Alpaca API keys (only for **automated trading** — scanners and reports work without them)

## Quick Start

**New user?** See the [Getting Started Guide](docs/getting-started.md) for complete onboarding with first workflow, daily rhythm, and troubleshooting.

### One-Command Setup

```bash
# Clone and setup
git clone https://github.com/MrLion/trader.git
cd trader
./setup.sh        # Or: make setup
```

### Verify Setup

```bash
# Check everything is configured
make doctor       # GS-002: Config validation

# Run tests to verify everything works
make test

# Check entry signals scanner
python3 scripts/entry_signals.py --help
```

**Next steps:** See [docs/getting-started.md](docs/getting-started.md) for your first workflow.

## Scripts by Function

### Market Analysis

Deep analysis of individual stocks and your watchlist.

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `entry_signals.py` | Find tickers meeting entry criteria | `python3 scripts/entry_signals.py` |

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

### Market Scans

Broad market screening for Stage 2 candidates and sector performance.

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `sector_scan.py` | Daily sector ETF performance ranking | `python3 scripts/sector_scan.py` |
| `sector_scan_comprehensive.py` | Extended sector scan | `python3 scripts/sector_scan_comprehensive.py` |
| `stage2_rs_screen.py` | Stage 2 + RS candidates screen | `python3 scripts/stage2_rs_screen.py` |
| `trend_screener.py` | MA convergence detection + VCP patterns | `python3 scripts/trend_screener.py --profile large-cap` |

**Trend Screener:**
```bash
# Discovery mode - find stocks with MA convergence
python3 scripts/trend_screener.py --profile large-cap --rank-by convergence

# Entry timing - rank existing watchlist by setup readiness
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

# Single ticker detail with MA data
python3 scripts/trend_screener.py --tickers AAPL --show-ma-data

# Show VCP pattern detection
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp
```

**Trend Screener Features:**
- MA convergence scoring (0-100) based on cluster tightness, size, price distance
- MarketSurge-style trend filters (MA stacking, price above MAs)
- VCP pattern detection with contraction progression validation
- Volume metrics (volume ratio, trend detection)
- Entry timing modes: VCP breakout, pivot proximity, volume surge
- Profile-based filtering: large-cap ($80M+ vol) vs high-octane ($20M+ vol)

### Reports

Generate pre-market and post-market briefings (console or HTML).

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `premarket_report.py` | Pre-market briefing | `python3 scripts/premarket_report.py --html` |
| `postmarket_report.py` | Post-market analysis | `python3 scripts/postmarket_report.py --html` |
| `deliver_report.py` | Deliver reports via Telegram | `python3 scripts/deliver_report.py --file report.html` |

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

### Data & Watchlist

Manage your trading universe and import external ideas.

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `watchlist_manager.py` | Manage watchlist items | `python3 scripts/watchlist_manager.py add AAPL` |
| `mcstock_scraper.py` | Scrape MC Stock Charts daily report | `python3 scripts/mcstock_scraper.py` |
| `mcstock_historical_scraper.py` | Scrape MC Stock Charts historical archives | `python3 scripts/mcstock_historical_scraper.py --weeks 10` |

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
python3 scripts/mcstock_scraper.py --config config/scraper_config.yaml
```

**MC Stock Charts Historical Scraper:**
```bash
# Scrape last 10 weeks of historical watchlists
python3 scripts/mcstock_historical_scraper.py --weeks 10

# Scrape specific date range
python3 scripts/mcstock_historical_scraper.py --start 2024-01-01 --end 2025-04-01

# Scrape all available history
python3 scripts/mcstock_historical_scraper.py

# Output to custom path
python3 scripts/mcstock_historical_scraper.py --output data/mc_historical.csv
```

### Backtesting

Simulate strategies against historical data.

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `backtest.py` | Run backtests with configurable parameters | `python3 scripts/backtest.py` |

**Quick Start:**
```bash
# Run backtest with defaults (last 6 months, $100K capital)
python3 scripts/backtest.py

# Custom date range and capital
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --capital 500000

# Use specific strategy (registered strategies: vcp_large_cap, vcp_high_octane, composite)
python3 scripts/backtest.py --strategy vcp_large_cap --start 2024-01-01 --end 2025-04-01

# Use a specific watchlist and risk profile
python3 scripts/backtest.py --watchlist data/watchlist.csv --risk-profile conservative

# Use historical watchlists for time-varying ticker universe
python3 scripts/backtest.py --start 2024-01-01 --end 2025-04-01 --watchlist mc_historical_watchlists.csv

# Show all trades in the report
python3 scripts/backtest.py --start 2025-01-01 --end 2025-03-31 --trades

# Limit concurrent positions
python3 scripts/backtest.py --max-positions 5
```

**Backtest Features:**
- Day-by-day simulation with next-bar fill and gap rejection
- Deterministic slippage (5bps), no commissions
- Rich-formatted terminal report with color, exit breakdown, top winners/losers, equity sparkline
- SPY benchmark comparison with alpha calculation
- Historical watchlist support for time-varying ticker universes (`mc_historical_watchlists.csv`)
- Configurable via risk profiles (conservative, aggressive, tight_stops)
- `--trades` flag to show all trade details
- `--strategy` flag to use registered strategy plugins (VCP, Composite)
- `--alpaca-mode data-only` (default) connects only to data endpoint, never trading
- Survivorship bias disclaimer in reports

**Data Isolation:** Backtest runs in `data-only` mode by default — connects only to Alpaca's shared data endpoint (`data.alpaca.markets`), never to trading sub-accounts. Use `--alpaca-mode paper` to restore old behavior.

### Automated Trading (Alpaca)

Execute trades automatically via Alpaca API with real-time WebSocket data.

| Script | Purpose | Example Command |
|----------------------|--------------------------------------|----------------------------------------|
| `paper_engine_alpaca.py` | Trading engine (auto-entry/exit) | `python3 scripts/paper_engine_alpaca.py` |
| `paper_portfolio.py` | Monitor positions and P&L | `python3 scripts/paper_portfolio.py status` |
| `setup_alpaca.py` | Configure credentials | `python3 scripts/setup_alpaca.py` |
| `validate_alpaca.py` | Test connection | `python3 scripts/validate_alpaca.py` |
| `sync_state.py` | Sync local state | `python3 scripts/sync_state.py` |

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

**WebSocket Resilience:**
- Keepalive ping tuned for Alpaca IEX feed (30s interval, 60s timeout)
- Health watchdog force-stops stuck connections after 90s, enabling exponential backoff
- Graceful shutdown in ~2s; second Ctrl+C force-exits immediately

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

## Repository Structure

```
scripts/          - Python CLI tools for analysis, scanning, and trading
traderlib/        - Library modules (alpaca_client, order_manager, etc.)
traderlib/backtest/ - Backtesting engine (data, execution, state, strategy, report)
data/             - watchlist.csv, portfolio, and trade logs
scans/            - Daily CSV outputs from sector/stock screens
reports/          - Generated HTML market reports
config/           - Configuration files (risk_config.yaml, scraper_config.yaml)
memory/           - Daily logs and curated memories
.gstack/          - QA reports and analysis (gitignored)
AGENTS.MD         - Complete trading playbook
CLAUDE.md         - Development operations guide
```

## Trading Framework

The system follows Mark Minervini's Stage 2 methodology. See [AGENTS.MD](AGENTS.MD) for complete trading playbook.

### Quick Reference

**Stage 2 Criteria (8-Point):** Price > 20/50/100/200 MA, MA stacking (50>100>200), rising 200 MA, within 25% of high, 1.25x from low. MA penalties: -20 pts if below 50 MA, -10 pts if below 20 MA.

**Entry Score Tiers:**
- **Tier 1 (>=60 pts, stage2 >=6):** Best setups - Price within +/-1% of pivot, strong trend
- **Tier 2 (40-59 pts, stage2 >=5):** Good setups - Wait for better entry
- **Tier 3 (<40 pts):** Monitor only

**Risk Rules:**
- 0.5% account risk per trade
- Max 3 positions per sector
- Position size < 5% equity (min 0.5%)
- Trailing stops: +1R breakeven, +1.5R EMA10, +3R EMA21
- Partial positions when cash is limited (no rejection for insufficient buying power)

**Exit Action Pattern (Unified Exit Handling):**
- `ExitActionType.EXIT` — Full position exit (stop hit, target hit)
- `ExitActionType.UPDATE_STOP` — Stop loss update only (trailing stop)
- `ExitActionType.HOLD` — No action needed
- Exit hierarchy: Hard stop > Profit target > Trailing stop > HOLD
- Backtest/paper parity: Same exit logic in both engines

**MA Support Stop (Dual Risk Parameter):**
- Calculates alternative stop based on clustered MAs below price (ma10, ma20, ma50, ma100, ma200)
- Requires minimum 2 MAs within 5% spread to form a valid cluster
- Final stop = `max(ATR stop, MA support stop)` — tighter risk wins
- Enabled by default; configure via `config/risk_config.yaml` `ma_support` section
- Profile overrides: conservative (1.5% buffer), aggressive (0.5% buffer), tight_stops (3% spread, min 3 MAs)

**Strategy Plugins:**
- Pluggable strategy architecture with auto-discovery registry
- Built-in strategies: `stage2_momentum`, `vcp_large_cap`, `vcp_high_octane`
- Composite strategy support (union/intersection modes)
- Use via `--strategy` flag in backtest: `python3 scripts/backtest.py --strategy vcp_large_cap`

See [docs/RISK_GUIDE.md](docs/RISK_GUIDE.md) for detailed risk explanations with examples.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for ExitAction, Strategy ABC, and MA convergence documentation.

## Data Model

The system uses the following data files:

| File | Purpose | Format |
|----------------------------------|--------------------------------------|----------------------------------------|
| `data/watchlist.csv` | Trading universe | CSV |
| `data/paper_positions.json` | Current positions | JSON |
| `data/paper_trades.jsonl` | Trade log (entries/exits) | JSON Lines |
| `data/daily_tracker.json` | Daily reset tracking | JSON |

**Watchlist columns:** Ticker, Stage (0-8), RS_Rank, Pivot_Price, Stop_Level, ATR, Risk_%, Sector, Industry, Pattern_Type, Notes, Added_Date

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

**Config Files:**
| File | Purpose | Overrides |
|----------------------------------|--------------------------------------|----------------------------------------|
| `config/risk_config.yaml` | Position sizing, stop loss, profit targets | Env vars (`RISK_*`) |
| `config/scraper_config.yaml` | Scraper validation thresholds | `--config` CLI flag |

**Other Variables:**
| Variable | Default | Purpose |
|----------------------------------|--------------------------------------|----------------------------------------|
| `PAPER_TRADING_DATA_DIR` | `./data` | Data directory |
| `TRADER_WATCHLIST` | `./data/watchlist.csv` | Watchlist path |
| `TRADER_OUTPUT` | `./reports` | Output directory |

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup instructions, testing commands, CI/CD workflow details, and contribution guidelines.

## External Integrations

| Integration | Purpose | Data Quality |
|----------------------------------|--------------------------------------|----------------------------------------|
| **Alpaca API** | Real-time prices, trading engine | Live, real-time |
| **Yahoo Finance** | Reports, scanners, analysis | 15-min delayed |
| **Telegram** | Report delivery | — |
| **Alpaca Broker** | Order execution | — |

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

## Documentation

### Essential Trading Guides

| File | Purpose | Read Before |
|----------------------------------|--------------------------------------|----------------------------------------|
| **[AGENTS.MD](AGENTS.MD)** | Complete trading playbook | **Start here** |
| **[docs/RISK_GUIDE.md](docs/RISK_GUIDE.md)** | Risk management, sizing, stops | Configuring engine |
| **[docs/BACKTESTING_GUIDE.md](docs/BACKTESTING_GUIDE.md)** | Backtesting user guide | Running backtests |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | System architecture, ExitAction, Strategy plugins, MA convergence | Development, strategy authoring |

### Operational Runbooks

Troubleshooting guides for production issues:

| Issue | Guide | Reference |
|----------------------------------|--------------------------------------|----------------------------------------|
| API failures, timeouts | [API Outage](docs/runbooks/api_outage.md) | Connection issues |
| Position size mismatch | [Partial Fill](docs/runbooks/partial_fill.md) | Order fills |
| Ticker halted/delisted | [Stuck Position](docs/runbooks/stuck_position.md) | Exit problems |
| Wrong scores, bad data | [Data Quality](docs/runbooks/data_quality.md) | Data validation |

### Developer Resources

| File | Purpose | Audience |
|----------------------------------|--------------------------------------|----------------------------------------|
| [CLAUDE.md](CLAUDE.md) | Dev operations, architecture | Developers |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, testing, CI/CD | Contributors |
| [docs/BACKTESTING_ENGINE_FEASIBILITY.md](docs/BACKTESTING_ENGINE_FEASIBILITY.md) | Backtesting design rationale | Developers |
| [TOOLS.md](TOOLS.md) | yfinance documentation (reports/scanners) | Users |

### Reference

- [CHANGELOG.md](CHANGELOG.md) - Version history and recent changes

## License

See LICENSE file for details.
