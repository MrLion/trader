# Trader

A systematic stock trading workflow system for momentum-driven swing trading, built on Python and Yahoo Finance data.

## Overview

This is a command center for Stage 2 trading methodology (Mark Minervini's approach). The system helps you:

1. **Scan** markets for Stage 2 candidates (stocks in uptrends with strong relative strength)
2. **Manage** a tiered watchlist (A=actionable, B=developing, C=radar)
3. **Generate** pre-market and post-market reports
4. **Execute** with discipline via entry/exit protocols

## Quick Start

### One-Command Setup

```bash
# Run the setup script (creates directories, installs deps, copies .env)
./setup.sh

# Or use Make
make setup
```

### Manual Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys (optional, for Telegram and Alpaca)

# 3. Create required directories
mkdir -p data/config scans reports memory

# 4. Run your first analysis
python3 scripts/analyze_ticker.py AAPL
```

## Repository Structure

```
scripts/          - Python tools for analysis and scanning
data/             - watchlist.csv (live trading universe)
scans/            - Daily CSV outputs from sector/stock screens
reports/          - Generated HTML market reports
memory/           - Daily logs and curated memories
.gstack/          - QA reports and analysis (gitignored)
AGENTS.MD         - Complete trading playbook
CLAUDE.md         - Development operations guide
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `analyze_ticker.py` | Full technical breakdown on a single stock |
| `analyze_watchlist.py` | Scan entire watchlist for setups |
| `watchlist_manager.py` | Add, remove, list watchlist items |
| `sector_scan.py` | Daily sector ETF performance ranking |
| `sector_scan_comprehensive.py` | Extended sector scan with comprehensive data |
| `stage2_rs_screen.py` | Screen universe for Stage 2 + RS candidates |
| `premarket_report.py` | Generate pre-market briefing (console or HTML) |
| `postmarket_report.py` | Post-market analysis and trade logging |
| `midday_scan.py` | Intraday scan for leading stocks |
| `mcstock_scraper.py` | Scrape trade ideas from MC Stock Charts |
| `deliver_report.py` | Deliver HTML reports via Telegram Bot API |

## Common Commands

```bash
# Analyze a single ticker
python3 scripts/analyze_ticker.py AAPL

# Analyze entire watchlist
python3 scripts/analyze_watchlist.py

# Watchlist management
python3 scripts/watchlist_manager.py add AAPL "Pullback to 21 EMA"
python3 scripts/watchlist_manager.py remove AAPL
python3 scripts/watchlist_manager.py list

# Market scans
python3 scripts/sector_scan.py
python3 scripts/sector_scan_comprehensive.py
python3 scripts/stage2_rs_screen.py

# Midday scan (requires --include-watchlist or --tickers-file)
python3 scripts/midday_scan.py --include-watchlist
python3 scripts/midday_scan.py --tickers-file data/my_tickers.txt
python3 scripts/midday_scan.py --include-watchlist --html

# Reports (console output)
python3 scripts/premarket_report.py
python3 scripts/postmarket_report.py

# Reports (HTML output)
python3 scripts/premarket_report.py --html
python3 scripts/premarket_report.py --html --output /path/to/custom.html
python3 scripts/postmarket_report.py --html
python3 scripts/postmarket_report.py --html --output reports/eod_$(date +%Y%m%d_%H%M).html

# Deliver reports via Telegram (with env vars set)
python3 scripts/deliver_report.py --file reports/premarket_report_2026-04-07.html --caption "Morning briefing"

# Test delivery without sending (dry run)
python3 scripts/deliver_report.py --file report.html --dry-run --verbose

# Deliver to different chat
python3 scripts/deliver_report.py --file report.html --chat-id -1001234567890

# Scrape MC Stock Charts ideas
python3 scripts/mcstock_scraper.py
python3 scripts/mcstock_scraper.py --populate-watchlist
python3 scripts/mcstock_scraper.py --date 2026-04-06 --output data/mc_ideas.csv

# Entry Signals Scanner (identifies tickers meeting entry criteria)
python3 scripts/entry_signals.py                    # Scan watchlist for Tier 1 signals
python3 scripts/entry_signals.py --min-tier 2       # Include Tier 2 signals
python3 scripts/entry_signals.py --tickers AAPL MSFT TSLA  # Scan specific tickers
python3 scripts/entry_signals.py --export json      # Export as JSON instead of CSV
```

## Development Commands

Use the Makefile for common development tasks:

```bash
# Setup (run once)
make setup              # Full setup (directories, deps, .env)

# Testing
make test               # Run test suite with coverage
make test-coverage      # Generate HTML coverage report

# Maintenance
make clean              # Remove cache files
make lint               # Run linter
make format             # Format code with black
```

## Comprehensive Reports

Both pre-market and post-market reports now support console and HTML output with dark theme styling.

### Pre-Market Report
```bash
# Console output
python3 scripts/premarket_report.py

# HTML report with dark theme
python3 scripts/premarket_report.py --html

# Custom output path
python3 scripts/premarket_report.py --html --output reports/premarket_$(date +%Y%m%d).html
```

**Features:**
- Overnight futures (ES, NQ, RTY, YM, CL, GC)
- VIX level classification (Low <18, Elevated 18-28, High >28)
- Crypto tracking (BTC, ETH)
- Economic calendar with risk assessment
- Major indices vs 20/50/200 MA
- Sector leaders from scan data
- Watchlist entry scores (Tier 1/2/3)
- Dark theme HTML reports

### Post-Market Report
```bash
# Console output
python3 scripts/postmarket_report.py

# HTML report with dark theme
python3 scripts/postmarket_report.py --html

# Custom output path
python3 scripts/postmarket_report.py --html --output reports/postmarket_$(date +%Y%m%d_%H%M).html
```

**Features:**
- Market close summary (SPY, QQQ, IWM) with intraday ranges
- VIX analysis with level classification
- Regime Assessment with signal grid and progress bar
- Major Indices with MA indicators (20/50/200)
- Crypto performance (BTC, ETH)
- Watchlist performance (change %, volume, distance to pivot)
- Gap detection (>3% moves) with volume confirmation
- Dynamic action items based on today's action
- Key levels for tomorrow (50MA values)
- Dark theme HTML reports
- Mobile responsive design

### Entry Signals Scanner

Scan your watchlist for tickers meeting entry criteria without executing trades.

```bash
# Scan entire watchlist for Tier 1 entry signals
python3 scripts/entry_signals.py

# Include Tier 2 signals (score 40-59)
python3 scripts/entry_signals.py --min-tier 2

# Scan specific tickers
python3 scripts/entry_signals.py --tickers AAPL MSFT NVDA

# Export as JSON
python3 scripts/entry_signals.py --export json

# No export (console output only)
python3 scripts/entry_signals.py --export none
```

**Entry Criteria:**
- Entry Score ≥ 60 (Tier 1) or ≥ 40 (Tier 2)
- Distance to Pivot within ±1.0%
- Market condition: SPY ≥ -0.3%

**Output:**
- Console: Signal details with score, distance, stop/target
- CSV: `scans/entry_signals_YYYYMMDD_HHMM.csv`
- JSON: Full analysis data for each signal

**Use Cases:**
- Pre-market scan before engine starts
- Manual review before auto-entry
- Identify setups for next session
- Validate watchlist candidates

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

**Total: 7 points maximum**

**Compliance Thresholds:**
- 6-7 pts: Excellent Stage 2 (Tier 1 quality)
- 4-5 pts: Good Stage 2 (Tier 2 quality)
- <4 pts: Developing (Tier 3)

### Universe Filter
- Price >= $10
- Average daily dollar volume >= $20M
- Market cap >= $1B
- NYSE/NASDAQ only

### Entry Score Tiers (Automated by `analyze_watchlist.py`)
Calculated using scoring formulae (max 110 pts):

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Stage 2 Score | 30 pts | ≥6/7 = +30, ≥5/7 = +25, ≥4/7 = +20, ≥3/7 = +10, ≥2/7 = +5, <2 = +0 |
| Risk % | 30 pts | <10% = +30, <15% = +20, <20% = +10, <25% = +5, ≥25% = +0 |
| Proximity | 25 pts | Within ±3% of pivot = +25, ±5% = +15, ±10% = +5, beyond ±10% = +0 |
| Momentum | 15 pts | 6M return >50% = +15, >25% = +10, ≤25% = +0 |
| Relative Strength | 10 pts | RS 6M >20% = +10, >10% = +5, ≤10% = +0 |

| Tier | Score | Stage 2 Min | Meaning |
|------|-------|-------------|---------|
| 🟢 Tier 1 | ≥ 60 pts | 6/7 | Best entry setups — ready now |
| 🟡 Tier 2 | 40-59 pts | 4/7 | Good setups — wait for better entry |
| 🔴 Tier 3 | < 40 pts | <4/7 | Monitor only — too far or too wide |

### Entry Protocol
1. **Trigger**: Price within ±1% of pivot (entry zone: -1% below to +1% above breakout level)
2. **Volume**: Tracking >= 1.5x 50-day average
3. **Market**: SPY/QQQ green or <= 0.3% down
4. **Risk Calc**: Account risk = 0.75% equity; Shares = Account risk / Risk per share
5. **Execute**: Limit buy with stop-market placed immediately

### Position Management
- Max 3 positions per GICS sector
- Position size < 20% of equity
- Trailing stops: +1R -> breakeven, +1.5-2R -> 10 EMA, +3R+ -> 21 EMA
- Profit target: Min 2R

## Data Model

The watchlist (`data/watchlist.csv`) tracks:
- Ticker, Stage (0-4), RS_Rank
- Pivot_Price, Stop_Level, ATR, Risk_%
- Sector, Industry, Pattern_Type
- Notes, Added_Date

## Alpaca Paper Trading (Automated)

The system now supports **automated paper trading** via Alpaca API with real-time WebSocket data. This executes trades automatically based on your watchlist setups.

### Setup

```bash
# 1. Configure Alpaca credentials
python3 scripts/setup_alpaca.py

# 2. Test connection
python3 scripts/setup_alpaca.py --test

# 3. Validate everything is working
python3 scripts/validate_alpaca.py
```

**Or set environment variables:**
```bash
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
```

### Start Automated Trading

```bash
# Paper trading (default)
python3 scripts/paper_engine_alpaca.py

# With custom starting capital
python3 scripts/paper_engine_alpaca.py --capital 500000

# For live trading (real money)
python3 scripts/paper_engine_alpaca.py --mode live
```

### Monitor Positions

```bash
# View account status (shows cash, equity, day P&L, unrealized P&L, open positions)
python3 scripts/paper_portfolio.py status

# Real-time positions with current prices (fetches live yfinance data)
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
- **Equity:** Cash + position values
- **Day P&L:** Realized gains from closed positions today
- **Unrealized P&L:** Current gains/losses from open positions (mark-to-market)

### Auto-Entry Rules

The engine automatically enters positions when **ALL** conditions are met:

| Rule | Threshold | Source |
|------|-----------|--------|
| Entry Score | ≥ 60 (Tier 1) | Watchlist analysis |
| Distance to Pivot | ± 1% (symmetric) | Real-time price vs pivot |
| Volume | ≥ 1.5x average | Alpaca real-time data |

**Distance Filter Note:** The engine enters when price is within ±1% of pivot. This means:
- **-1.0% ≤ distance ≤ +1.0%**: ✅ Enter zone (price at or near breakout level)
- **Distance < -1.0%**: ❌ Already broke out (chasing)
- **Distance > +1.0%**: ❌ Too far below pivot (not ready)
| Market Condition | SPY ≥ -0.3% | Alpaca SPY data |
| Sector Limit | < 3 positions/sector | Local state |
| Position Size | < 20% equity | Risk calculation |
| Daily Entries | ≤ 5 per day | Circuit breaker |
| Daily Loss | > -2% equity | Stop trading limit |

### Watchlist to Order Decision Flow

This diagram shows exactly how a stock in your `data/watchlist.csv` becomes an Alpaca order:

```
Watchlist CSV (Ticker + Pivot_Price)
    ↓
Engine loads tickers every 30 seconds
    ↓
For each ticker: _analyze_ticker()
    ├── Fetch 60-day price history (Alpaca)
    ├── Get current price (WebSocket cache)
    ├── Calculate Stage 2 score (0-7)
    ├── Get Pivot_Price from watchlist.csv
    ├── Calculate metrics:
    │   ├── Distance to Pivot: (pivot - price) / price
    │   ├── 6M Return: price vs 130 days ago
    │   ├── ATR: 14-day Average True Range
    │   ├── Stop: price - 2×ATR
    │   └── Entry Score: f(Stage2, Risk%, Distance, Momentum)
    └── Return analysis dict
    ↓
Check Entry Filters (_check_entries)
    ├── Entry Score ≥ 60? (Tier 1)
    ├── Distance to Pivot ≤ 1.0%?
    ├── SPY ≥ -0.3%? (market condition)
    ├── Not already in position?
    └── No pending order for ticker?
    ↓
Risk Validation (can_enter_position)
    ├── Daily entries < 5? (circuit breaker)
    ├── Sector positions < 3?
    ├── Position size < 20% equity?
    ├── Sufficient buying power?
    └── Daily loss > -2%? (stop trading)
    ↓
Position Sizing
    └── Shares = (Equity × 0.0075) / (Entry - Stop)
        (Risks 0.75% of account per trade)
    ↓
Order Submission (order_manager.submit_entry)
    └── Alpaca submit_market_order(ticker, shares, stop_price)
        (Market order with stop-loss bracket)
    ↓
🚀 Position opened
```

**Required watchlist.csv columns:**
- `Ticker` — Stock symbol (e.g., "AAPL")
- `Pivot_Price` — Your breakout entry level (REQUIRED for distance calculation)

**Optional columns:**
- `Sector` — Used for sector limit tracking
- `Stop_Level` — Ignored (engine calculates 2×ATR stop)
- `RS_Rank` — Ignored (engine recalculates)

**Common rejection reasons:**
1. **Entry Score < 60** — Setup not strong enough
2. **Distance > 1%** — Price too far from pivot
3. **SPY down > 0.3%** — Market condition filter
4. **Already signaled today** — Prevents duplicate orders

### Entry Logging & Troubleshooting

The engine provides detailed logging to help debug why positions are or aren't opening:

**Example Output:**
```
⏸️  AAPL: Score 45 < 60 (need Tier 1)
⏸️  TSLA: Distance +5.2% outside ±1.0% (Current $210, Pivot $200)
⏸️  MSFT: Risk validation failed - Daily entry limit reached (5)
⏸️  NVDA: Already signaled today
📐 AMD: Position sizing - Equity $100,000, Entry $150, Stop $140
📐 AMD: Calculated 75 shares, Position value $11,250
✅ AMD: Score 85, Distance -0.5% - EXECUTING
🚀 AMD: Submitting order for 75 shares...
🚀 AUTO-ENTRY: AMD at $150.00 x 75 shares
   Order ID: abc-123
   Stop: $140.00 | Target: $165.00

📊 Checked: 23 | Eligible: 1 | Rejected (score): 15 | Rejected (distance): 7
```

**Status Indicators:**
| Indicator | Meaning |
|-----------|---------|
| ⏸️ | Skipped (rejection reason follows) |
| 📐 | Position sizing calculation |
| ✅ | Passed all filters, executing |
| 🚀 | Order submitted |
| ❌ | Order submission failed |

**Price Source Priority:**
1. Alpaca REST API (primary - most reliable)
2. WebSocket cache (if < 60 seconds old)
3. Stale cache (fallback with warning)

### Auto-Exit Rules

Positions are automatically closed based on trailing stops:

| R Multiple | Stop Type | Trigger |
|------------|-----------|---------|
| +1R | BREAKEVEN | Move to entry price |
| +1.5-2R | EMA10 | Trail 10-day EMA |
| +3R+ | EMA21 | Trail 21-day EMA |
| Hard Stop | Initial | Price hits 2×ATR stop |
| Target | 2R+ | Profit target hit |

### Entry Score Calculation

The entry score (0-100) determines Tier classification:

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Stage 2 Score | 30 pts | ≥6/7 = +30, ≥5/7 = +25, ≥4/7 = +20, ≥3/7 = +10, ≥2/7 = +5, <2 = +0 |
| Risk % | 30 pts | <10% = +30, <15% = +20, <20% = +10, <25% = +5, ≥25% = +0 |
| **Proximity** | **25 pts** | **Within ±3% of pivot = +25, ±5% = +15, ±10% = +5** |
| Momentum | 15 pts | 6M return >50% = +15, >25% = +10, ≤25% = +0 |
| Relative Strength | 10 pts | RS 6M >20% = +10, >10% = +5, ≤10% = +0 |

**Note:** Proximity is symmetric - stocks both above (breakout) and below (approaching) the pivot receive points based on absolute distance.

**Tier Thresholds:**
- 🟢 Tier 1: ≥ 60 points (eligible for auto-entry)
- 🟡 Tier 2: 40-59 points (monitor for better entry)
- 🔴 Tier 3: < 40 points (too far or too wide)

### Architecture

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `alpaca_client.py` | API client | REST + WebSocket, rate limiting, yfinance fallback |
| `paper_engine_alpaca.py` | Main engine | 30s polling loop, auto-entry/exit, WebSocket streaming |
| `order_manager.py` | Order lifecycle | Position sync, order tracking, fill notifications |
| `rate_limiter.py` | Rate management | 200 req/min limit, circuit breaker, exponential backoff |
| `paper_portfolio.py` | CLI monitoring | Status, live prices, reports, emergency close |

### Data Flow

1. **WebSocket Stream** — Real-time price updates (fallback to REST)
2. **Entry Detection** — Scan watchlist every 30 seconds during market hours
3. **Order Submission** — Market orders via Alpaca API
4. **Fill Tracking** — Poll order status, update local state
5. **Exit Monitoring** — WebSocket price updates trigger exit checks
6. **Position Sync** — Two-way sync with Alpaca (handles external changes)

### Risk Management

- **Account Risk**: 0.75% per trade
- **Position Sizing**: `shares = (equity × 0.0075) / (price - stop)`
- **Circuit Breakers**: Daily loss limit (-2%), max 5 entries/day
- **Rate Limiting**: 200 requests/minute with automatic backoff
- **Provider Fallback**: Alpaca → yfinance on failures

### Testing

```bash
# Run all tests
python3 -m pytest tests/

# Run with coverage report
python3 -m pytest tests/ --cov=scripts --cov-report=term-missing

# Run specific test file
python3 -m pytest tests/test_alpaca_client_extended.py -v

# Run validation suite
python3 scripts/validate_alpaca.py
```

**Test Suite Overview:**
| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_alpaca_client_extended.py` | 34 | Config, rate limiting, fallbacks, orders, WebSocket |
| `test_paper_engine_extended.py` | 28 | Market hours, SPY cache, entry filters, execution |
| `test_integration_paper_engine.py` | 5 | Critical path integration (timeouts, sync, sector limits) |
| `test_chaos.py` | 9 | Failure scenarios (cascades, corrupt data, rate storms) |
| `test_paper_state_recovery.py` | 7 | Edge cases (missing files, zero equity, negative P&L) |
| `test_exit_engine.py` | 4 | Trailing stops, breakeven, hard stops, targets |
| `test_alpaca_integration.py` | 15 | Rate limiter, circuit breaker, health monitoring |

**Test Isolation:**
Tests automatically use temporary directories via `PAPER_TRADING_DATA_DIR` environment variable. No production data is modified during testing. See `tests/conftest.py` for implementation.

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
pytest tests/ --cov=scripts --cov-branch --cov-report=html
open htmlcov/index.html
```

## External Integrations

- **Data Source**: Yahoo Finance via `yfinance`
- **Real-Time Data**: Alpaca API (WebSocket + REST)
- **Automated Trading**: Alpaca paper/live accounts
- **Communications**: Telegram via `deliver_report.py` (primary) or `openclaw message send`
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

## Recent Fixes

### 2026-04-09

**Developer Experience (DX) Improvements:**
- **Unified credential management** - All API keys now load from `.env` file using `python-dotenv`. No more manual `export` commands needed. Scripts updated: `alpaca_client.py`, `deliver_report.py`, `mcstock_scraper.py`
- **One-command setup** - Added `setup.sh` script that creates directories, installs dependencies, and copies `.env.example` to `.env`
- **Makefile commands** - Common tasks now available: `make setup`, `make test`, `make clean`, `make lint`, `make format`
- **Updated `.env.example`** - Now includes all credentials (Alpaca, Telegram, MCStock) with clear documentation

**Trading Engine Fixes:**
- **Fixed shutdown message** - Suppressed misleading "Using REST polling" message during Ctrl+C shutdown
- **Improved WebSocket error handling** - Added exponential backoff for reconnects (5s → 60s max), specific handling for ConnectionClosed errors, and delay reset on successful connection
- **Fixed ATR calculation inconsistency** - Paper engine now uses Alpaca data for both ATR display and stop calculation (was using yfinance for stops, causing risk% mismatches)
- **Fixed entry price sync from Alpaca** - Position entry prices now update with actual fill prices from Alpaca (was using theoretical signal prices, causing P&L discrepancies)
- **Fixed Day P&L display** - `day_return_pct` is now persisted to account file, showing correct percentage and 🔴 emoji for negative values
- **Added entry price sync on startup** - Existing positions get their entry prices corrected during Alpaca sync

**Project Infrastructure:**
- **Added `requirements.txt`** - All dependencies with pinned versions for reproducible installs
- **Updated CI/CD** - GitHub Actions now uses `requirements.txt` instead of manual pip installs
- **Added `python-dotenv` dependency** - For `.env` file support across all scripts

### 2026-04-08
- **Test data isolation** - `PAPER_TRADING_DATA_DIR` environment variable prevents tests from polluting production data
- **Extended test coverage** - 62 new tests for `alpaca_client.py` (50% coverage) and `paper_engine_alpaca.py` (54% coverage)
- **Fixed proximity scoring bug** - Entry score now correctly awards proximity points for stocks both above and below pivot (symmetric ±3%/5%/10% scoring)
- **Fixed countdown timer overwriting logs** - Removed `\r` carriage return that was erasing entry check output
- **Fixed empty orders file error** - Order manager now handles empty/corrupted JSON gracefully
- **Fixed historical data requirements** - Lowered minimum bars from 50 to 30 and increased request from 60 to 90 days. Stage 2 scoring now works with limited history (conditionally checks MAs based on available data)
- **Fixed entry score discrepancy** - `paper_engine_alpaca.py` now calculates RS 6M component (fetches SPY data daily), matching `analyze_watchlist.py` max score of 110

## License

See LICENSE file for details.
