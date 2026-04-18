# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

---

## yfinance - Market Data

**Installed:** v1.2.0 (system Python 3.14)
**Usage:** `import yfinance as yf`

### Quick Examples

```python
import yfinance as yf

# Get ticker object
ticker = yf.Ticker("AAPL")

# Historical data (1 month daily)
data = ticker.history(period="1mo")

# Historical data (custom range)
data = ticker.history(start="2024-01-01", end="2024-12-31", interval="1d")
# Intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo

# Current price
price = ticker.info['currentPrice']

# Key stats
market_cap = ticker.info['marketCap']
pe_ratio = ticker.info['trailingPE']
dividend_yield = ticker.info['dividendYield']
eps = ticker.info['trailingEps']

# Financials
income_stmt = ticker.financials  # Income statement
balance_sheet = ticker.balance_sheet
cash_flow = ticker.cashflow

# Analyst recommendations
recs = ticker.recommendations

# Options chain
options = ticker.options  # List of expiration dates
call_options = ticker.option_chain('2025-01-17').calls
put_options = ticker.option_chain('2025-01-17').puts
```

### Common Tickers

**Tech:** AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA  
**Indices:** ^GSPC (S&P 500), ^DJI (Dow), ^IXIC (NASDAQ), ^VIX (Volatility)  
**ETFs:** SPY, QQQ, VOO, VTI, ARKK  
**Crypto:** BTC-USD, ETH-USD, SOL-USD  
**Forex:** EURUSD=X, GBPUSD=X, JPY=X
**Commodities:** CL=F (WTI Crude Oil), GC=F (Gold)

### Pre-Market Standard Checklist

Every session, pull:
1. **Index Futures:** ES=F (S&P), NQ=F (NASDAQ), RTY=F (Russell)
2. **Volatility:** ^VIX
3. **Commodities:** CL=F (Oil)
4. **Crypto:** BTC-USD, ETH-USD
5. **Spot Indices:** SPY, QQQ — check vs 20/50 SMA

### Data Columns Returned

```python
df = ticker.history(period="1mo")
df.columns
# Index(['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume'], dtype='object')
```

### Useful Patterns

```python
# Multiple tickers at once
tickers = yf.Tickers("AAPL MSFT GOOGL")
aapl_data = tickers.tickers['AAPL'].history(period="1mo")

# Download many tickers into one DataFrame
data = yf.download(["AAPL", "MSFT", "GOOGL"], period="1mo")

# Earnings calendar
earnings = ticker.earnings_dates

# Institutional holders
holders = ticker.institutional_holders

# Major holders breakdown
major = ticker.major_holders  # [insiders_percent, institutions_percent, ...]
```

### Notes

- Data is cached locally (clear with `yf.clear_cache()`)
- Rate limited by Yahoo Finance (~2000 requests/hour)
- Pre/post market data: `ticker.history(period="1d", interval="1m", include_prepost=True)`
- Some info fields may be None if not available

---

## Watchlist Manager

**Script:** `scripts/watchlist_manager.py`  
**Data file:** `data/watchlist.csv`

### Commands

```bash
# Populate from scan results
python3 scripts/watchlist_manager.py populate /path/to/scan.csv

# Add a stock
python3 scripts/watchlist_manager.py add TICKER [NOTES]
python3 scripts/watchlist_manager.py add AAPL "Pullback to 21 EMA"
python3 scripts/watchlist_manager.py add AAPL "Quick add" --force   # Skip data validation

# Remove a stock
python3 scripts/watchlist_manager.py remove TICKER
python3 scripts/watchlist_manager.py remove TICKER --dry-run   # Preview removal

# Remove all tickers
python3 scripts/watchlist_manager.py remove-all                 # Interactive (type "DELETE ALL")
python3 scripts/watchlist_manager.py remove-all --force         # Skip confirmation
python3 scripts/watchlist_manager.py remove-all --dry-run       # Preview what would be removed

# List all
python3 scripts/watchlist_manager.py list
```

### Entry Score Calculation

Entry scores are calculated by `entry_signals.py` (max 100 points).

**See [docs/entry_signals/TIER_SCORING.md](docs/entry_signals/TIER_SCORING.md) for complete documentation including:**
- Tier classification logic (dual-requirement: Entry Score AND Stage 2 Score)
- Scoring components table
- Output categories (Ready Now, Close to Pivot, Extended, Tier 2 Watch, Tier 3)
- Console output column reference
- Signal age tracking
- Dual risk parameters (ATR vs MA Support Stop)

**Quick Reference:**

| Component | Criteria | Points |
|-----------|----------|--------|
| **Stage 2 Score** | 7-8/8 | +30 |
| | 6/8 | +25 |
| | 5/8 | +20 |
| | 4/8 | +15 |
| | 3/8 | +10 |
| | 2/8 | +5 |
| **Risk %** | < 10% | +30 |
| | < 15% | +20 |
| | < 20% | +10 |
| | < 25% | +5 |
| **Distance to Pivot** | < 3% | +25 |
| | < 5% | +15 |
| | < 10% | +5 |
| **6M Momentum** | > 50% | +15 |
| | > 25% | +10 |
| **RS vs SPY** | > 20% | +10 |
| | > 10% | +5 |
| **MA Penalties** | Below 50 MA | -20 |
| | Below 20 MA | -10 |

**Tier Thresholds (Dual-Requirement):**
- **Tier 1 (>=60 pts + Stage 2 >= 6):** Best entry setups — ready now
- **Tier 2 (40-59 pts + Stage 2 >= 5):** Good setups — wait for better entry
- **Tier 3 (<40 pts):** Monitor only — too far or too wide

### Watchlist Schema

```
Ticker, Stage, RS_Rank, Pivot_Price, Current_Price, Stop_Level,
ATR, Risk_%, $Vol_M, Sector, Industry, Notes,
Added_Date, Alert_Set, Base_Count, Pattern_Type, Target_1,
Target_2, R_Ratio, Avg_Volume_50d, Market_Cap
```

---

## Entry Signals Scanner

**Script:** `scripts/entry_signals.py`

**Purpose:** Scan watchlist for entry signals and analyze single tickers. Replaces the former `analyze_ticker.py`, `analyze_watchlist.py`, and `midday_scan.py`.

### Modes

1. **Scan mode** (default) — Scans full watchlist or specified tickers, ranks by entry score
2. **Single-ticker mode** (`--ticker`) — Deep dive analysis for one ticker (replaces `analyze_ticker.py`)

### Usage

```bash
# Scan full watchlist
python3 scripts/entry_signals.py

# Deep dive single ticker
python3 scripts/entry_signals.py --ticker AAPL

# Scan specific tickers
python3 scripts/entry_signals.py --tickers AAPL MSFT GOOGL
python3 scripts/entry_signals.py -t AAPL MSFT GOOGL

# Filter by minimum tier
python3 scripts/entry_signals.py --min-tier 1    # Tier 1 only
python3 scripts/entry_signals.py --min-tier 2     # Tier 1 + Tier 2

# Export results
python3 scripts/entry_signals.py --export-csv      # Export to CSV (replaces analyze_watchlist.py --csv)
python3 scripts/entry_signals.py --export-html      # Export to HTML (replaces analyze_watchlist.py --html)
python3 scripts/entry_signals.py --export json      # Export to JSON

# Risk profile override
python3 scripts/entry_signals.py --risk-profile conservative
python3 scripts/entry_signals.py --risk-profile tight_stops

# Alpaca mode
python3 scripts/entry_signals.py --mode live       # Use live data (default: paper)
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tickers`, `-t` | Specific tickers to scan | watchlist |
| `--ticker` | Analyze single ticker in detail | None |
| `--min-tier`, `-m` | Minimum tier (1/2/3) | 3 (all) |
| `--export`, `-e` | Export format (csv/json/none) | none |
| `--export-csv` | Export results to CSV | False |
| `--export-html` | Export results to HTML | False |
| `--mode` | Alpaca mode (paper/live) | paper |
| `--risk-profile` | Risk profile override | None |

### Output Categories

- **Ready Now** — Score >= threshold, within max pivot distance
- **Close to Pivot** — Score >= threshold, 1-3% from pivot
- **Extended** — Score >= threshold, >3% from pivot
- **Tier 2 Watch** — Score 40-59
- **Tier 3 / Below Threshold** — Score < 40

### Integration

Uses Alpaca API for real-time pricing and historical data. Integrates with `traderlib` for Stage 2 scoring and entry score calculation. Uses `config/risk_config.yaml` for entry thresholds.

---

## Paper Trading Engine

**Script:** `scripts/paper_engine_alpaca.py`

**Purpose:** Alpaca-powered paper trading engine with real-time WebSocket data, entry signal evaluation, exit management, and position sizing.

### Architecture

Uses `AlpacaClient` for live data, `OrderManager` for execution, `PaperState` for persistence, and `ExitEngine` for stop management. Integrates with `config/risk_config.yaml` via `RiskConfigManager`.

### Usage

```bash
# Start paper trading (default)
python3 scripts/paper_engine_alpaca.py

# Specify mode
python3 scripts/paper_engine_alpaca.py --mode paper
python3 scripts/paper_engine_alpaca.py --mode live

# Risk profile override
python3 scripts/paper_engine_alpaca.py --risk-profile conservative
python3 scripts/paper_engine_alpaca.py --risk-profile aggressive
python3 scripts/paper_engine_alpaca.py --risk-profile tight_stops

# Print risk config summary and exit
python3 scripts/paper_engine_alpaca.py --risk-summary
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--mode` | Alpaca mode (paper/live) | paper |
| `--risk-profile` | Risk profile name | None (uses default from config) |
| `--risk-summary` | Print risk config summary and exit | False |

### Key Features

- Real-time WebSocket streaming for price data
- Triple-constraint position sizing (account risk, position cap, available cash)
- Cooldown tracking to prevent re-entry after loss
- Exit management: hard stops, breakeven stops, trailing EMA stops
- Daily reset tracking and trade logging
- Signal-based entry with Stage 2 scoring

---

## Paper Portfolio CLI

**Script:** `scripts/paper_portfolio.py`

**Purpose:** CLI tool for paper trading portfolio management and monitoring. Uses Alpaca real-time prices for position values.

### Commands

```bash
# Account overview with Alpaca real-time prices
python3 scripts/paper_portfolio.py status

# Real-time position values with P&L and R-multiples
python3 scripts/paper_portfolio.py live

# Today's trade entries and exits
python3 scripts/paper_portfolio.py today

# Full trade history
python3 scripts/paper_portfolio.py history
python3 scripts/paper_portfolio.py history --limit 50
python3 scripts/paper_portfolio.py history --include-test-data

# Performance statistics (win rate, P&L, R-multiples)
python3 scripts/paper_portfolio.py report
python3 scripts/paper_portfolio.py report --include-test-data

# Manually close a position
python3 scripts/paper_portfolio.py close TICKER
python3 scripts/paper_portfolio.py close TICKER --reason "Stopped out"
python3 scripts/paper_portfolio.py close TICKER --force       # Skip confirmation
python3 scripts/paper_portfolio.py close TICKER --dry-run     # Preview without executing

# Reconcile counters with trade log
python3 scripts/paper_portfolio.py reconcile
```

### CLI Options

| Command | Flags | Description |
|---------|-------|-------------|
| `status` | — | Account overview with live prices |
| `live` | — | Real-time position values |
| `today` | — | Today's trades |
| `history` | `--limit N`, `--include-test-data` | Trade history |
| `report` | `--include-test-data` | Performance statistics |
| `close TICKER` | `--reason`, `--force`, `--dry-run` | Close a position |
| `reconcile` | — | Reconcile counters with trade log |

---

## Market Scanning Tools

### Sector Scan (Quick)

**Script:** `scripts/sector_scan.py`

**Purpose:** Quick scan of 11 sector ETFs + 7 factor ETFs. Uses yfinance for data.

```bash
python3 scripts/sector_scan.py
# Output: scans/YYYY-MM-DD_sector_scan.csv
```

No CLI options — just run it.

### Sector Scan (Comprehensive)

**Script:** `scripts/sector_scan_comprehensive.py`

**Purpose:** Comprehensive 131-ETF scan with weighted ranking system (6M/3M/1M/1W returns + Stage 2 scores). Uses yfinance. Shows TOP 15 by overall rank.

```bash
python3 scripts/sector_scan_comprehensive.py
# Output: scans/YYYY-MM-DD_sector_scan.csv (overwrites basic scan output)
```

No CLI options — just run it.

### Stage 2 RS Screen

**Script:** `scripts/stage2_rs_screen.py`

**Purpose:** Screen a list of tickers for Stage 2 qualification + relative strength vs SPY. Ranks by 6-month return; top 20% flagged as Tier B. Filters: price >= $10, dollar volume >= $20M.

```bash
# Screen from ticker file (one ticker per line, # comments, blank lines ok)
python3 scripts/stage2_rs_screen.py data/weekly_watchlist.txt
# Output: scans/stage2_screen_YYYY-MM-DD.csv
```

Requires a ticker file argument. No other CLI options.

---

## Pre-Market Report

**Script:** `scripts/premarket_report.py`

**Purpose:** Generate a complete pre-market briefing with futures, indices, regime assessment, economic calendar, sector leaders, and watchlist rankings.

### Usage

```bash
# Console output (default)
python3 scripts/premarket_report.py

# Generate HTML report (saved to reports/)
python3 scripts/premarket_report.py --html

# Custom output path
python3 scripts/premarket_report.py --html --output ~/Desktop/premarket.html
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--html` | Generate HTML report | False |
| `--output` | Custom HTML output path | reports/premarket_report_YYYY-MM-DD.html |

### Output Format

**Console Mode:** Plain text with emoji indicators

**HTML Mode:** Self-contained HTML file with:
- Dark theme with visual regime badge
- Futures grid with color-coded changes
- Regime assessment with progress bar
- Economic calendar with impact indicators
- Watchlist table with tier badges and ready setups highlighted
- Key levels dashboard
- Responsive layout (mobile-friendly)

### Telegram Integration

Post the HTML report with a summary:

```bash
openclaw message send --channel telegram --account trader --target -4872065090 \
  --message "🌅 Pre-Market Report — $(date +%Y-%m-%d)\n\nRegime: 🔴 Bear (0/4 signals)\nTier 1 Ready: NVDA, TSLA\n\nFull report attached." \
  --media /Users/mintmrlion/.openclaw/workspaces/trader/reports/premarket_report_$(date +%Y-%m-%d).html \
  --force-document
```

---

## Report Delivery

**Script:** `scripts/deliver_report.py`

**Purpose:** Production-grade delivery of HTML reports to Telegram via Bot API.

### Features

- **Environment-based config** — No hardcoded secrets
- **Retry logic** — Exponential backoff (3 attempts)
- **Dry-run mode** — Test without sending
- **Structured logging** — Timestamps and log levels
- **Type-safe** — Full type hints throughout
- **Exit codes** — Scriptable error handling

### Configuration

Set environment variables (add to `~/.zshrc` or use `.env` file):

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
export TELEGRAM_CHAT_ID="-4872065090"  # Default: Trading Sandbox
```

Or create a `.env` file (copy from `.env.example`):

```bash
cp .env.example .env
# Edit .env with your actual token
```

### Usage

```bash
# Basic delivery
python3 scripts/deliver_report.py --file reports/premarket_report_2026-04-07.html

# With caption
python3 scripts/deliver_report.py --file report.html --caption "🌅 Morning briefing"

# Test without sending (dry run)
python3 scripts/deliver_report.py --file report.html --dry-run --verbose

# Send to different chat
python3 scripts/deliver_report.py --file report.html --chat-id -1001234567890

# Override token from command line
python3 scripts/deliver_report.py --file report.html --bot-token $OTHER_BOT_TOKEN
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file` | Path to HTML report | **Required** |
| `--caption` | Caption text | None |
| `--chat-id` | Target chat ID | `-4872065090` or `TELEGRAM_CHAT_ID` env |
| `--bot-token` | Bot token | `TELEGRAM_BOT_TOKEN` env |
| `--timeout` | Request timeout (seconds) | 60 |
| `--dry-run` | Simulate without sending | False |
| `--verbose`, `-v` | Debug output | False |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | File not found |
| 2 | Authentication failed |
| 3 | Network error |
| 4 | API error |
| 5 | Configuration error |

### Common Workflow

Generate and deliver in one command:

```bash
# Generate HTML report and deliver to Telegram
python3 scripts/premarket_report.py --html && \
python3 scripts/deliver_report.py \
  --file reports/premarket_report_$(date +%Y-%m-%d).html \
  --caption "🌅 Pre-Market Report — $(date +%Y-%m-%d)"
```

### Error Handling

The script provides clear error messages:

- **File not found**: `"❌ File not found: path/to/file"`
- **Auth failed**: `"❌ Authentication failed: Invalid bot token"`
- **Rate limited**: `"❌ Rate limited by Telegram API"`
- **Network**: Retries 3x with exponential backoff before failing

### Output Examples

**Verbose dry-run:**
```
11:05:58 - INFO - 🚀 Report delivery starting
11:05:58 - DEBUG - File validated: /absolute/path/to/report.html
11:05:58 - INFO - File validated: report.html
11:05:58 - INFO - 🔍 DRY RUN MODE — No actual message will be sent
11:05:58 - INFO - [DRY RUN] Would send: report.html to -4872065090
11:05:58 - INFO - [DRY RUN] Caption: Morning briefing
11:05:58 - INFO - ✅ Dry run successful — message would be delivered
```

**Success:**
```
11:06:15 - INFO - 🚀 Report delivery starting
11:06:15 - INFO - File validated: report.html
11:06:15 - INFO - Message sent successfully (ID: 12345)
11:06:15 - INFO - ✅ Report delivered successfully to Trading Sandbox
```

---

## Post-Market Report

**Script:** `scripts/postmarket_report.py`

**Purpose:** Generate comprehensive end-of-day report with market close summary, watchlist performance, gap analysis, and overnight futures.

### Usage

```bash
# Console output (default)
python3 scripts/postmarket_report.py

# Generate HTML report
python3 scripts/postmarket_report.py --html

# Custom output path with timestamp
python3 scripts/postmarket_report.py --html --output reports/postmarket_$(date +%Y%m%d_%H%M).html
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--html` | Generate HTML report | False |
| `--output` | Custom HTML output path | reports/postmarket_report_YYYY-MM-DD_HHMMSS.html |

### Output Format

**Console Mode:** Plain text with emoji indicators

**HTML Mode:** Self-contained HTML file with:
- Dark theme with visual styling
- Market close cards with intraday ranges
- VIX analysis with risk classification
- Overnight futures tracking
- Crypto performance summary
- Watchlist performance table with tier badges
- Gap detection section (>3% moves)
- Action items checklist
- Key levels for tomorrow

### Report Features

| Section | Description |
|---------|-------------|
| **Market Close Summary** | SPY, QQQ, IWM close prices with intraday H/L |
| **VIX Analysis** | Current level with Low/Elevated/High classification |
| **Overnight Futures** | ES, NQ, RTY post-market levels |
| **Crypto** | BTC and ETH 24h performance |
| **Watchlist Performance** | All watchlist stocks with change %, volume ratio, pivot distance |
| **Gap Analysis** | Stocks with >3% gaps, volume confirmation |
| **Action Items** | Dynamic checklist based on today's action |
| **Key Levels** | Support/resistance levels for tomorrow |

### Console Output Example

```
🌙 POST-MARKET REPORT — 2026-04-07

**📊 MARKET CLOSE SUMMARY**
SPY  $654.03 (-4.90, -0.74%) | H: $658.36 L: $651.06
QQQ  $582.60 (-5.90, -1.00%) | H: $587.06 L: $578.40
IWM  $250.88 (-1.48, -0.59%) | H: $253.48 L: $249.52

VIX:  27.34 (+3.17) — Elevated 18-28

**📈 WATCHLIST PERFORMANCE TODAY**
Total: 21 | Gained: 6 | Declined: 14

Ticker   Change     Vol      Close      Pivot      Dist%    Tier
---------------------------------------------------------------------------
POWL     +6.67%     1.0x     $199.18    $207.23    4.0%     🟢 T1
STRL     -4.64%     1.0x     $375.44    $396.61    5.6%     🟢 T1
...

**🚀 GAPS >3%**
📈 POWL: +6.67% (Vol: 1.0x) — News/Driven
📉 STRL: -4.64% (Vol: 1.0x) — News/Driven

**🎯 ACTION ITEMS FOR TOMORROW**
1. ☐ Review today's 5 gaps >3%
2. ☐ Update watchlist pivots for any breakouts
3. ☐ Note: BEAR day - adjust sizing accordingly
4. ☐ Check overnight futures before bed
5. ☐ Review tomorrow's economic calendar

**⚡ KEY LEVELS FOR TOMORROW**
SPY: Support ~$651 | Resistance ~$658
QQQ: Support ~$578 | Resistance ~$587
```

### Telegram Integration

Post the HTML report with summary:

```bash
openclaw message send --channel telegram --account trader --target -4872065090 \
  --message "🌙 Post-Market Report — $(date +%Y-%m-%d)

Market: BEAR day (3/3 indices red)
Gaps >3%: 5 stocks
VIX: Elevated at 27.34

Full report attached." \
  --media /Users/mintmrlion/.openclaw/workspaces/trader/reports/postmarket_report_$(date +%Y%m%d).html \
  --force-document
```

---

## Posting Reports with HTML Attachment

**For EOD/Pre-market reports:** Attach the HTML file alongside the text summary.

```bash
# Post EOD report with HTML attachment to your DM
openclaw message send --channel telegram --account trader --target 47258942 \
  --message "📊 EOD Report — April 6, 2026\n\nRegime: Neutral with bearish tilt\nA-Tier: TSEM, DOCN, LITE, CIEN\n\nFull report attached." \
  --media /Users/mintmrlion/.openclaw/workspaces/trader/reports/EOD_Report_2026-04-06.html \
  --force-document
```

**Note:** Use `--force-document` for HTML files so Telegram doesn't try to preview them as images.

---

## MC Stock Charts Scraper

**Script:** `scripts/mcstock_scraper.py`

**Purpose:** Scrape trade ideas from mcstockcharts.com/latest-report/ and output CSV compatible with watchlist_manager.py.

### Setup

**1. Install dependencies:**
```bash
pip install requests beautifulsoup4
```

**2. Configure credentials** (one of):
- Environment variables: `MCSTOCK_USER`, `MCSTOCK_PASS`
- Or copy `.env.example` to `.env` and fill in

### Configuration

Scraper validation thresholds are configured in `config/screener_config.yaml`:

```yaml
validation:
  min_price: 10                    # Minimum stock price
  min_market_cap: 1000000000       # $1B minimum market cap
  min_history_days: 200            # Minimum trading history (days)
  min_dollar_volume: 20000000     # $20M minimum daily dollar volume
extra_false_positives: []         # Tickers to skip (e.g. ETFs)
```

Override with `--config` flag:
```bash
python3 scripts/mcstock_scraper.py --config config/screener_config.yaml
```

### Usage

```bash
# Basic scrape (today's report)
python3 scripts/mcstock_scraper.py

# Scrape specific date
python3 scripts/mcstock_scraper.py --date 2026-04-06

# Custom output path
python3 scripts/mcstock_scraper.py --output data/mc_ideas.csv

# Populate watchlist directly
python3 scripts/mcstock_scraper.py --populate-watchlist

# Preview without saving
python3 scripts/mcstock_scraper.py --dry-run

# Skip YF validation (faster)
python3 scripts/mcstock_scraper.py --skip-validation
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--date` | Specific date (YYYY-MM-DD) | Latest report |
| `--output` | Custom CSV output path | scans/mcstock_ideas_YYYY-MM-DD.csv |
| `--populate-watchlist` | Auto-populate watchlist | False |
| `--skip-validation` | Skip Yahoo Finance validation | False |
| `--config` | Custom scraper config path | config/screener_config.yaml |
| `--dry-run` | Preview without saving | False |
| `--verbose`, `-v` | Debug logging | False |

### Workflow

```bash
# 1. Scrape ideas
python3 scripts/mcstock_scraper.py

# 2. Populate watchlist
python3 scripts/watchlist_manager.py populate scans/mcstock_ideas_2026-04-07.csv

# 3. Analyze
python3 scripts/entry_signals.py
```

Or combine steps 1-2:
```bash
python3 scripts/mcstock_scraper.py --populate-watchlist
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Auth failed (check credentials) |
| 2 | Report not found |
| 3 | Network error |
| 4 | Parse error |
| 5 | Config error (missing credentials) |

---

## MC Stock Charts Historical Scraper

**Script:** `scripts/mcstock_historical_scraper.py`

**Purpose:** Scrape historical weekly watchlist data from mcstockcharts.com/report-archives/ for backtesting with rotation.

### Setup

**1. Install dependencies:**
```bash
pip install requests beautifulsoup4
```

**2. Configure credentials** (same as regular scraper):
- Environment variables: `MCSTOCK_USER`, `MCSTOCK_PASS`
- Or copy `.env.example` to `.env` and fill in

### How It Works

The scraper:
1. Iterates through archive pages (9 reports per page)
2. Groups daily reports (Mon-Fri) by week
3. Accumulates tickers across the week (if a ticker appears on Tuesday, it stays for the week)
4. Outputs a time-series CSV with `week_start` as the key

Report URL format: `/members/pre-market-report-{weekday}-{month}-{day}-{year}-{time}/`

### Usage

```bash
# Scrape ALL available history
python3 scripts/mcstock_historical_scraper.py

# Scrape with date filter (e.g., last 6 months)
python3 scripts/mcstock_historical_scraper.py \
  --start 2024-10-01 --end 2025-04-01

# Scrape last 10 weeks only
python3 scripts/mcstock_historical_scraper.py --weeks 10

# Limit pages for testing
python3 scripts/mcstock_historical_scraper.py --max-pages 2

# Custom output path
python3 scripts/mcstock_historical_scraper.py --output data/my_historical.csv
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start` | Filter: Start date (YYYY-MM-DD) | None (all) |
| `--end` | Filter: End date (YYYY-MM-DD) | None (all) |
| `--output` | Output CSV path | data/mc_historical_watchlists.csv |
| `--max-pages` | Max archive pages to scrape | All pages |
| `--weeks` | Limit to N most recent weeks | None (all) |
| `--delay` | Seconds between requests | 2.0 |
| `--verbose`, `-v` | Debug logging | False |

### Output Format

```csv
week_start,ticker,list_type,first_seen_date,scraped_date
2025-01-06,AAPL,ready,2025-01-06,2026-04-15
2025-01-06,MSFT,ready,2025-01-06,2026-04-15
2025-01-06,NVDA,watch,2025-01-08,2026-04-15
```

- `week_start`: Monday date for the week (YYYY-MM-DD)
- `ticker`: Stock symbol
- `list_type`: 'ready' or 'watch' (first list type seen)
- `first_seen_date`: When ticker first appeared that week
- `scraped_date`: When this record was scraped

### Workflow

```bash
# 1. Scrape historical data (one-time setup)
python3 scripts/mcstock_historical_scraper.py --output data/mc_historical.csv

# 2. Future: Use in backtest with weekly rotation
python3 scripts/backtest.py \
  --start 2024-01-01 --end 2025-12-31 \
  --weekly-watchlist data/mc_historical.csv
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Auth failed (check credentials) |
| 2 | Network error |
| 3 | Config error (missing credentials) |

### Output Format

CSV with columns compatible with `watchlist_manager.py populate`:
- `Ticker`, `Name`, `Sector`, `Industry`
- `Stage2`, `6M_%`, `3M_%`, `1M_%`
- `Entry_Breakout`, `Stop`, `Risk_%`
- `$Vol_M` (dollar volume in millions), `Source_Note`

---

## Backtesting Engine

**Script:** `scripts/backtest.py`
**Module:** `traderlib/backtest/`

**Purpose:** Simulate the Stage 2 momentum strategy against historical data to validate edge before live trading.

### Architecture

The backtesting engine mirrors the paper trading engine but replaces real-time data with historical simulation:

| Module | Purpose |
|--------|---------|
| `data_provider.py` | `DataFrameProvider` protocol, `AlpacaDataProvider` (rate-limited), `DictDataProvider` (synthetic) |
| `execution.py` | `ExecutionModel` with deterministic slippage (5bps) and commissions ($0.005/share, $1 min) |
| `state.py` | `BacktestState` with sim_date clock, side-aware P&L, sector limits, max positions |
| `strategy.py` | `Strategy` ABC, `Stage2MomentumStrategy` (mirrors paper engine entry logic) |
| `engine.py` | `BacktestEngine` day-by-day simulation with next-bar fill and gap rejection |
| `report.py` | `BacktestReporter` with return/risk metrics, alpha vs SPY, survivorship bias disclaimer |

### Usage

```bash
# Backtest with date range (required)
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31

# With specific capital
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --capital 500000

# Specific tickers
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --tickers AAPL MSFT NVDA

# From watchlist
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --watchlist data/watchlist.csv

# Risk profile (conservative, aggressive, tight_stops)
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --risk-profile conservative

# Custom slippage and commission
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --slippage 3.0 --commission 0.01

# Export trades to CSV
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --csv backtest_trades.csv

# Validate config without running
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --dry-run

# Limit concurrent positions
python3 scripts/backtest.py --start 2025-06-01 --end 2026-03-31 --max-positions 5
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start` | Start date (YYYY-MM-DD) | **Required** |
| `--end` | End date (YYYY-MM-DD) | **Required** |
| `--capital` | Starting capital | $100,000 |
| `--tickers` | Ticker symbols to backtest | None |
| `--watchlist` | Path to watchlist CSV | None |
| `--risk-profile` | Risk profile (conservative/aggressive/tight_stops) | conservative |
| `--slippage` | Slippage in basis points | 5.0 |
| `--commission` | Commission per share | $0.005 |
| `--max-positions` | Maximum concurrent positions | 10 |
| `--csv` | Export trades to CSV file | None |
| `--dry-run` | Validate config without running | False |
| `--alpaca-mode` | Alpaca connection mode (data-only/paper) | data-only |

### Report Output

The backtest generates a summary including:
- Total return, CAGR, max drawdown
- Win rate, profit factor, Sharpe ratio
- Average win/loss, avg holding period
- Alpha vs SPY benchmark
- Survivorship bias disclaimer

**Note:** Backtesting results have inherent limitations. Past performance does not guarantee future results. The simulation uses deterministic slippage and next-bar fills, which may not reflect real market conditions.

**Data-only mode:** By default, backtests run in `data-only` mode, which connects only to Alpaca's data endpoint (`data.alpaca.markets`) and never to any trading sub-account. Use `--alpaca-mode paper` to also create a paper trading client (not recommended for backtests).

---

## Utility Scripts

### Doctor — System Validation

**Script:** `scripts/doctor.py`

**Purpose:** Configuration validation checks — Python version, dependencies, Alpaca credentials, directories, watchlist, Telegram config, git hooks.

```bash
python3 scripts/doctor.py
# Exit code: 0 if all pass, 1 otherwise
# Also available via: make doctor
```

### Validate Alpaca — Full Integration Check

**Script:** `scripts/validate_alpaca.py`

**Purpose:** Full Alpaca integration validation — dependencies, credentials, account status, data access, order manager, rate limiter, unit tests. More thorough than `doctor.py` for Alpaca-specific checks.

```bash
python3 scripts/validate_alpaca.py
```

### Setup Alpaca — Interactive Credential Setup

**Script:** `scripts/setup_alpaca.py`

**Purpose:** Interactive Alpaca API configuration. Saves credentials to `config/secrets/alpaca_config.json` with 600 permissions (owner read/write only).

```bash
python3 scripts/setup_alpaca.py           # Interactive setup
python3 scripts/setup_alpaca.py --test     # Test connection only
```

### Sync State — Reconcile with Alpaca

**Script:** `scripts/sync_state.py`

**Purpose:** Force sync local state files with live Alpaca API. Reconciles positions and daily tracker. Use when local state drifts from API reality (e.g., after test runs).

```bash
python3 scripts/sync_state.py
```

### Show Positions — Quick Position Display

**Script:** `scripts/show_positions.py`

**Purpose:** Quick position display with yfinance prices. Uses hardcoded ticker list. For dynamic data, prefer `paper_portfolio.py live`.

```bash
python3 scripts/show_positions.py
```

### Clean Test Trades — Cleanup Utility

**Script:** `scripts/clean_test_trades.py`

**Purpose:** Remove test/development entries from `paper_trades.jsonl`. Always creates backup before modifying.

```bash
python3 scripts/clean_test_trades.py --dry-run    # Preview changes
python3 scripts/clean_test_trades.py --auto        # Non-interactive (auto-backup + no confirmation)
python3 scripts/clean_test_trades.py --strict       # Aggressive filtering
python3 scripts/clean_test_trades.py --file PATH   # Custom trades file path
```

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Preview changes without modifying | False |
| `--auto` | Non-interactive mode | False |
| `--strict` | Use stricter filtering criteria | False |
| `--file` | Path to trades file | data/paper_trades.jsonl |

### Risk Config Demo — Configuration Demo

**Script:** `scripts/risk_config_demo.py`

**Purpose:** Demo the flexible risk configuration system — position sizing, profile comparison, environment overrides.

```bash
python3 scripts/risk_config_demo.py                    # All demos
python3 scripts/risk_config_demo.py --profile conservative  # Show profile summary
python3 scripts/risk_config_demo.py --demo sizing      # Position sizing demo
python3 scripts/risk_config_demo.py --demo profiles    # Profile comparison
python3 scripts/risk_config_demo.py --demo env         # Environment overrides
```

| Option | Description | Default |
|--------|-------------|---------|
| `--profile` | Risk profile to use | None |
| `--demo` | Which demo (sizing/profiles/env/all) | all |

---

## traderlib/ Library Reference

The core trading library (`traderlib/`) provides reusable components used by all scripts. This is a brief reference — see individual modules for full API details.

| Module | Purpose |
|--------|---------|
| `__init__.py` | Package entry; exports `calculate_stage2_score`, `get_entry_score`, `get_stage2_tier`, `get_stage2_details`, `RiskConfig`, `RiskConfigManager`, `calculate_position_size_with_constraints` |
| `stage2_utils.py` | Canonical 8-point Stage 2 scoring (Minervini trend template + short-term trend); entry score calculator (0-100) with RS bonus and MA penalties; tier classification |
| `risk_config.py` | `RiskConfig` dataclass hierarchy + `RiskConfigManager` (YAML loader with profile support + env var overrides); `calculate_position_size_with_constraints()` triple-constraint position sizer |
| `alpaca_client.py` | Alpaca API wrapper (REST + WebSocket); paper/live mode switching; rate-limited data fetching; position management; health monitoring |
| `order_manager.py` | Order lifecycle management (submit, track, fill); pending/filled tracking in `alpaca_orders.json`; TPS-limited submission queue |
| `paper_state.py` | Paper trading state persistence — `PaperState`, `Position`; reads/writes `paper_positions.json` and `paper_trades.jsonl` |
| `paper_exits.py` | Exit engine (`ExitEngine`); hard stops, breakeven (+1R), trailing EMA10 (+1.5R), trailing EMA21 (+3R); profit targets; initial stop calculation (ATR/support/pct/pivot) |
| `market_hours.py` | Market hours helpers: `market_hours()`, `is_market_open()`, `is_trading_day()`, `format_market_status()`; uses `pandas_market_calendars` for holiday calendar |
| `rate_limiter.py` | `RateLimiter` (200 req/min with exponential backoff + circuit breaker); `APIHealthMonitor` for Alpaca/yfinance failover; thread-safe |
| `trading_exceptions.py` | `TradingExceptionHandler` centralized logging with severity (CRITICAL/WARNING/INFO); `@critical`/`@error`/`@warning` decorators; `APIKeyError` with actionable messages; daily-rotating file handler |
| `validation.py` | Ticker validation (`validate_ticker`, `validate_tickers`, `is_valid_ticker`); `NO_COLOR` env var support; color/emoji constants for CLI output |
| `backtest/` | Subpackage: `data_provider.py`, `execution.py`, `state.py`, `strategy.py`, `engine.py`, `report.py` (see Backtesting Engine section) |

### Key Imports

```python
from traderlib import calculate_stage2_score, get_entry_score, get_stage2_tier, get_stage2_details
from traderlib.risk_config import RiskConfigManager, calculate_position_size_with_constraints
from traderlib.alpaca_client import AlpacaClient
from traderlib.paper_state import PaperState, Position
from traderlib.paper_exits import ExitEngine, ExitSignal
from traderlib.order_manager import OrderManager
from traderlib.market_hours import market_hours, is_market_open, is_trading_day
from traderlib.trading_exceptions import TradingExceptionHandler, critical, error, warning
from traderlib.validation import validate_ticker, validate_tickers
```

---

## Risk Configuration

**Config file:** `config/risk_config.yaml`  
**Loaded by:** `RiskConfigManager` (used by paper engine, entry signals, backtest)

### Sections

| Section | Key Settings |
|---------|-------------|
| `account` | `risk_per_trade_pct` (0.5%), `daily_loss_limit_pct` (2%), `max_sector_positions` (10), `max_entries_per_day` (10) |
| `position` | `max_position_pct` (10%), `min_position_pct` (5%) |
| `stop_loss` | Method (`atr_or_support`), ATR period 14 / multiplier 2.0, min stop 3%, max stop 10%, fallback 7% |
| `profit_target` | Min R-multiple (2.0), trailing stops: breakeven at +1R, EMA10 at +1.5R, EMA21 at +3R |
| `entry` | `min_entry_score` (60), `max_dist_to_pivot_pct` (2.0), `min_volume_ratio` (1.5) |
| `market` | `max_spy_decline_pct` (-0.5%) |
| `cooldown` | `reentry_cooldown_minutes` (60), `consecutive_loss_multiplier` (2.0), `max_cooldown_minutes` (240) |
| `cache` | `ttl_seconds` (300 / 5 minutes) |

### Risk Profiles

Use with `--risk-profile <name>` on paper engine, entry signals, or backtest:

| Profile | Key Overrides |
|---------|---------------|
| `conservative` | risk_per_trade 0.5%, max_position 10%, max_stop 8% |
| `aggressive` | risk_per_trade 1.0%, max_position 10%, max_stop 15% |
| `tight_stops` | min_stop 2%, max_stop 5%, max_position 15% |

### Environment Variable Overrides

Override any config value with `RISK_` prefix + uppercase key:
```bash
RISK_ACCOUNT_RISK_PCT=0.01 python3 scripts/paper_engine_alpaca.py   # 1% risk per trade
RISK_POSITION_MAX_PCT=0.15 python3 scripts/paper_engine_alpaca.py   # 15% max position
```

### Alpaca Credentials

Alpaca API keys are stored in `config/secrets/alpaca_config.json` (created by `scripts/setup_alpaca.py`). A template is at `config/secrets/example.alpaca_config.json`. Set up with:

```bash
python3 scripts/setup_alpaca.py           # Interactive setup
python3 scripts/setup_alpaca.py --test     # Test connection
```

---

## Data Persistence Files

All state files live in `data/`. Written by traderlib modules and scripts.

| File | Format | Written By | Purpose |
|------|--------|-----------|---------|
| `data/watchlist.csv` | CSV | watchlist_manager.py | Master watchlist (see schema in Watchlist Manager section) |
| `data/paper_positions.json` | JSON dict | paper_state.py, sync_state.py | Open positions keyed by ticker; fields: ticker, status, entry_date, entry_price, shares, stop_price, target_price, initial_risk, sector, current_stop_type, initial_stop_price |
| `data/paper_trades.jsonl` | JSONL | paper_state.py | Append-only trade event log; events: ENTRY, EXIT; includes realized_pnl, exit_reason, stop_type, optional `_meta` dict |
| `data/alpaca_orders.json` | JSON dict | order_manager.py | Order tracking: `pending` (by order ID), `filled` (by order ID), `timestamp` |
| `data/daily_tracker.json` | JSON dict | paper_state.py, sync_state.py | Daily reset tracking: `last_entry_reset` (date string), `timestamp` (ISO) |
| `data/logs/trading_exceptions.log` | Text log | trading_exceptions.py | Rotating exception log (severity-tagged); 30-day retention; rotated as `trading_exceptions.log.YYYY-MM-DD` |

Backup files are auto-created before cleanup operations:
- `data/paper_trades.jsonl.backup` — Created by `clean_test_trades.py`
- `data/watchlist_backup_*.csv` — Timestamped backups from `watchlist_manager.py`

---

## Telegram Posting

**Bot:** @tradermintbot  
**Account ID:** `trader`  
**Status:** Admin in channel + member in discussion group

### Destinations

| Target | Chat ID | Use Case |
|--------|---------|----------|
| **Trading Sandbox** | `-4872065090` | Main trading channel for reports and analysis |
| **Channel** | `-1002556195363` | Дневник трейдера (legacy) |
| **Discussion Group** | `-1002652699578` | Posts forward to channel automatically |

### How to Post

**Use the `openclaw message send` command via `exec` tool:**

```bash
# Post to channel (direct)
openclaw message send --channel telegram --account trader --target -1002556195363 --message "Your analysis here"

# Post to discussion group (forwards to channel)
openclaw message send --channel telegram --account trader --target -1002652699578 --message "Your analysis here"

# With media (chart/screenshot from workspace)
openclaw message send --channel telegram --account trader --target -1002556195363 --media /Users/mintmrlion/.openclaw/workspaces/trader/chart.png --force-document
```

### When to Post

**Good reasons:**
- Daily market summary (pre-market or EOD)
- Significant price movements (>5% in major holdings)
- Earnings surprises
- Technical breakouts/breakdowns
- Sector rotation alerts
- Economic data releases (CPI, jobs, Fed decisions)

**Don't post:**
- Every single analysis (use DM for detailed back-and-forth)
- Speculative/unconfirmed rumors
- Overly frequent updates (max 3-5 posts/day)

### Post Templates

**Pre-Market Summary:**
```
🌅 Pre-Market Update

Indices:
• S&P 500 (ES=F): +0.3%
• NASDAQ (NQ=F): +0.5%
• VIX: 14.2 (-2%)

Movers:
• NVDA +2.1% (earnings beat)
• TSLA -1.4% (delivery miss)

Oil (CL=F): $78.45 (+0.8%)
Gold (GC=F): $2,034 (-0.2%)
BTC: $67,890 (+1.2%)

Key events today: CPI data @ 8:30 AM ET
```

**Stock Analysis:**
```
📊 $AAPL Analysis

Current: $178.45 (+1.2%)

Technical:
• Above 20-day SMA ($175)
• RSI: 58 (neutral)
• Support: $172, Resistance: $182

Fundamentals:
• P/E: 29.4
• Market Cap: $2.8T
• Next earnings: Apr 25

Verdict: HOLD — waiting for breakout above $182
```

**Alert:**
```
🚨 $NVDA Alert

Breaking above resistance at $485
Volume: 2.3x average
Target: $500
Stop: $475

Position: Watching for confirmation
```

### Notes

- Always use `--account trader` flag (not default)
- Channel posts are permanent and visible to all subscribers
- Discussion group posts show comment count on channel
- Images must be in workspace directory (`~/.openclaw/workspaces/trader/`)
- Use `--force-document` for charts to prevent compression