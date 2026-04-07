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
AGENTS.MD         - Complete trading playbook
CLAUDE.md         - Development operations guide
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `analyze_ticker.py` | Full technical breakdown on a single stock |
| `analyze_watchlist.py` | Scan entire watchlist for setups |
| `watchlist_manager.py` | Add, promote, remove, list watchlist items |
| `sector_scan.py` | Daily sector ETF performance ranking |
| `stage2_rs_screen.py` | Screen universe for Stage 2 + RS candidates |
| `premarket_report.py` | Generate pre-market briefing |
| `premarket_report_comprehensive.py` | Extended version with breadth data |
| `postmarket_report.py` | Post-market analysis and trade logging |
| `midday_scan.py` | Intraday scan for leading stocks |

## Common Commands

```bash
# Analyze a single ticker
python3 scripts/analyze_ticker.py AAPL

# Analyze entire watchlist
python3 scripts/analyze_watchlist.py

# Watchlist management
python3 scripts/watchlist_manager.py add AAPL B "Pullback to 21 EMA"
python3 scripts/watchlist_manager.py promote AAPL A
python3 scripts/watchlist_manager.py remove AAPL
python3 scripts/watchlist_manager.py list A

# Market scans
python3 scripts/sector_scan.py
python3 scripts/sector_scan_comprehensive.py
python3 scripts/stage2_rs_screen.py

# Reports
python3 scripts/premarket_report.py
python3 scripts/postmarket_report.py
```

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

### Watchlist Tiers (Manual Classification)
| Tier | Description | Max | Criteria |
|------|-------------|-----|----------|
| A | Actionable | 5 | Mature setup, pivot defined, entry within 1-3 days |
| B | Developing | 10 | Constructive base forming, not at buy point yet |
| C | Radar | 15 | Strong RS, interesting story, early stage |

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
- Ticker, Tier (A/B/C), Stage (0-4), RS_Rank
- Pivot_Price, Stop_Level, ATR, Risk_%
- Sector, Industry, Pattern_Type
- Notes, Added_Date, Promoted_Date

## External Integrations

- **Data Source**: Yahoo Finance via `yfinance`
- **Communications**: Telegram via `openclaw message send`
- **Broker**: Manual execution (alerts feed into broker platform)

## Documentation

- `AGENTS.MD` - Complete trading playbook with operating rhythm, entry/exit protocols, and journaling guidelines
- `CLAUDE.md` - Development operations and architecture notes
- `TOOLS.md` - Technical documentation for yfinance and script usage

## License

See LICENSE file for details.
