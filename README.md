# Trader

A systematic stock trading workflow system for momentum-driven swing trading, built on Python and Yahoo Finance data.

## Overview

This is a command center for Stage 2 trading methodology (Mark Minervini's approach). The system helps you:

1. **Scan** markets for Stage 2 candidates (stocks in uptrends with strong relative strength)
2. **Manage** a tiered watchlist (A=actionable, B=developing, C=radar)
3. **Generate** pre-market and post-market reports
4. **Execute** with discipline via entry/exit protocols

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
Calculated using scoring formulae (max 100 pts):

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
# View account status
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
# Run all unit tests
python3 tests/test_alpaca_integration.py

# Run validation suite
python3 scripts/validate_alpaca.py
```

**Unit Tests (15/15 passing):**
- Rate limiter tracking and backoff
- Circuit breaker activation
- Health monitoring and failover
- Order lifecycle management
- Position synchronization

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

## Recent Fixes

### 2026-04-08
- **Fixed proximity scoring bug** - Entry score now correctly awards proximity points for stocks both above and below pivot (symmetric ±3%/5%/10% scoring)
- **Fixed countdown timer overwriting logs** - Removed `\r` carriage return that was erasing entry check output
- **Fixed empty orders file error** - Order manager now handles empty/corrupted JSON gracefully
- **Fixed historical data requirements** - Lowered minimum bars from 50 to 30 and increased request from 60 to 90 days. Stage 2 scoring now works with limited history (conditionally checks MAs based on available data)

## License

See LICENSE file for details.
