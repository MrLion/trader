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

### Stage 2 Criteria
- Price > 100 SMA > 200 SMA
- 200 SMA rising for 1+ month
- Price within 25% of 52-week high
- Price >= 1.25x 52-week low

### Universe Filter
- Price >= $10
- Average daily dollar volume >= $20M
- Market cap >= $1B
- NYSE/NASDAQ only

### Entry Score Tiers (Automated by `analyze_watchlist.py`)
Calculated using scoring formulae (max 100 pts):

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Stage 2 Score | 30 pts | ≥4/4 = +30, ≥3/4 = +20, ≥2/4 = +10, <2 = +0 |
| Risk % | 30 pts | <10% = +30, <15% = +20, <20% = +10, ≥20% = +0 |
| Proximity | 25 pts | <3% = +25, <5% = +15, <10% = +5, ≥10% = +0 |
| Momentum | 15 pts | 6M return >50% = +15, >25% = +10, ≤25% = +0 |

| Tier | Score | Meaning |
|------|-------|---------|
| 🟢 Tier 1 | ≥ 60 pts | Best entry setups — ready now |
| 🟡 Tier 2 | 40-59 pts | Good setups — wait for better entry |
| 🔴 Tier 3 | < 40 pts | Monitor only — too far or too wide |

### Entry Protocol
1. **Trigger**: Price breaks above pivot (within 1-2% of buy point)
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

## External Integrations

- **Data Source**: Yahoo Finance via `yfinance`
- **Communications**: Telegram via `deliver_report.py` (primary) or `openclaw message send`
- **Broker**: Manual execution (alerts feed into broker platform)

## Documentation

- `AGENTS.MD` - Complete trading playbook with operating rhythm, entry/exit protocols, and journaling guidelines
- `CLAUDE.md` - Development operations and architecture notes
- `TOOLS.md` - Technical documentation for yfinance and script usage

## License

See LICENSE file for details.
