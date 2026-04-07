# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## 📈 yfinance - Market Data

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

## 📋 Watchlist Manager

**Script:** `scripts/watchlist_manager.py`  
**Data file:** `data/watchlist.csv`

### Commands

```bash
# Populate from scan results
python3 scripts/watchlist_manager.py populate /path/to/scan.csv

# Manual add a stock
python3 scripts/watchlist_manager.py add TICKER [NOTES]
# Example: python3 scripts/watchlist_manager.py add AAPL "Pullback to 21 EMA"

# Remove from watchlist
python3 scripts/watchlist_manager.py remove TICKER

# List all
python3 scripts/watchlist_manager.py list
```

### Entry Score Tiers

Entry scores are calculated automatically by `analyze_watchlist.py` (max 100 points):

| Component | Criteria | Points |
|-----------|----------|--------|
| **Stage 2 Score** | 4/4 🟢 | +30 |
| | 3/4 🟢 | +20 |
| | 2/4 🟡 | +10 |
| **Risk %** | < 10% | +30 |
| | < 15% | +20 |
| | < 20% | +10 |
| **Distance to Pivot** | < 3% | +25 |
| | < 5% | +15 |
| | < 10% | +5 |
| **6M Momentum** | > 50% | +15 |
| | > 25% | +10 |

**Tier Thresholds:**
- **Tier 1 (≥60 pts):** Best entry setups — ready now
- **Tier 2 (40-59 pts):** Good setups — wait for better entry
- **Tier 3 (<40 pts):** Monitor only — too far or too wide

### Watchlist Schema

```
Ticker, Stage, RS_Rank, Base_Count, Pattern_Type,
Pivot_Price, Stop_Level, Target_1, Target_2, R_Ratio,
Avg_Volume_50d, Market_Cap, Sector, Industry, Notes,
Added_Date, Alert_Set
```

---

## 🔬 Stock Analysis Tool

**Script:** `scripts/analyze_ticker.py`

**Purpose:** Generate detailed technical analysis for any ticker in standard format

**Usage:**
```bash
python3 scripts/analyze_ticker.py TICKER
# Example: python3 scripts/analyze_ticker.py AAPL
```

**Features:**
- Pulls company info (name, sector, industry)
- Calculates returns (1M, 3M, 6M)
- Stage 2 score (4 criteria)
- Entry/stop/risk calculation using 2 ATR
- Uses manual pivot price from watchlist if available

**Output Format:**
```
TICKER (Company Name) — $PRICE

| Metric | Value |
|:-------|:------|
| Company | ... |
| Sector | ... |
| Industry | ... |
| 1M Return | +X% |
| 3M Return | +X% |
| 6M Return | +X% |
| Stage 2 Score | X/4 🟢 |
| From 52W High | X% |
| Above All MAs | ✓ ✓ ✓ ✓ 20/50/150/200 |

---

ENTRY SETUP

| Level | Price |
|:------|:------|
| Entry | $X.XX (break above $X.XX) |
| Stop | $X.XX (2 ATR / below support) |
| Risk | X.X% |

Assessment:
- **Momentum** — ...
- **Stage 2** — ...
- **Distance from highs** — ...
- **Risk level** — ...

Verdict: [TIER]
```

---

## 📊 Watchlist Analysis Tool

**Script:** `scripts/analyze_watchlist.py`

**Purpose:** Analyze entire watchlist and rank stocks by entry favorability

**Usage:**
```bash
python3 scripts/analyze_watchlist.py
```

**Scoring System (Max: 100 points):**

| Component | Criteria | Points |
|-----------|----------|--------|
| **Stage 2 Score** | 4/4 🟢 | +30 |
| | 3/4 🟢 | +20 |
| | 2/4 🟡 | +10 |
| **Risk %** | < 10% | +30 |
| | < 15% | +20 |
| | < 20% | +10 |
| **Distance to Pivot** | < 3% | +25 |
| | < 5% | +15 |
| | < 10% | +5 |
| **6M Momentum** | > 50% | +15 |
| | > 25% | +10 |

**Tier Thresholds:**
- **Tier 1 (≥60 pts):** Best entry setups — ready now
- **Tier 2 (40-59 pts):** Good setups — wait for better entry
- **Tier 3 (<40 pts):** Monitor only — too far or too wide

**Output:**
- Ranked table by entry score (descending)
- Tier 1 / Tier 2 / Tier 3 sections
- Summary count
- Top 3 recommendations

**When to Run:**
- Weekly: After populating new watchlist
- Daily: Pre-market to identify ready setups
- After adding new stocks to watchlist

**Action Rules:**
- Tier 1 + within 2% + risk <10% = Ready for immediate entry
- Tier 1 + 2-5% from pivot = Set price alert at pivot
- Tier 2 = Wait for pullback or base formation
- Tier 3 = Remove or monitor only

---

### Posting Reports with HTML Attachment

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

## 🔄 Mid-Day Scan

**Script:** `scripts/midday_scan.py`

**Purpose:** Intraday scan of Stage 2+ candidates with entry setup calculations.

### Features

- **Curated universe** — 60+ liquid tickers across leading sectors
- **Stage 2 scoring** — 0-4 score based on technical criteria
- **Entry calculations** — Breakout levels and 2 ATR stops
- **Dynamic sectors** — Load today's leading sectors from scan
- **Watchlist integration** — Include your watchlist tickers
- **HTML reports** — Visual output for midday review

### Usage

```bash
# Basic scan (full universe)
python3 scripts/midday_scan.py

# Include your watchlist
python3 scripts/midday_scan.py --include-watchlist

# Focus only on today's leading sectors
python3 scripts/midday_scan.py --leading-sectors-only

# Generate HTML report
python3 scripts/midday_scan.py --html

# Custom dollar volume filter (e.g., 50M+)
python3 scripts/midday_scan.py --min-dollar-vol 50000000

# Custom Stage 2 minimum (e.g., only score 4)
python3 scripts/midday_scan.py --stage2-min 4

# Custom output paths
python3 scripts/midday_scan.py --output /path/to/output.csv --html-output /path/to/output.html
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--min-dollar-vol` | Minimum dollar volume filter | 20,000,000 |
| `--entry-score-min` | Minimum entry score to include | 0 |
| `--include-watchlist` | Add watchlist.csv tickers | False |
| `--leading-sectors-only` | Scan only today's leading sectors | False |
| `--output` | Custom CSV output path | scans/leading_stocks_YYYY-MM-DD.csv |
| `--html` | Generate HTML report | False |
| `--html-output` | Custom HTML output path | reports/midday_scan_YYYY-MM-DD.html |

### Output Format

**Console:**
```
🟢 TIER A — Stage 2 Score 4 (8 candidates)
--------------------------------------------------
XOM    | Exxon Mobil Corp        | $114.52 | 6M: +12.5% | From High: 3.2% | 📈 TRENDING
       Entry: $115.50 | Stop: $110.25 | Risk: 4.6%

🟡 TIER B — Stage 2 Score 3 (15 candidates)
--------------------------------------------------
CVX    | Chevron Corp            | $155.30 | 6M:  +8.3% | From High: 5.1%
```

**CSV Columns:**
- Ticker, Name, Sector, Industry, Price
- Stage2, 6M_%, 3M_%, 1M_%
- From_52W_High_%, ATR
- Entry_Breakout, Stop, Risk_%
- $Vol_M (dollar volume in millions)

### Common Workflows

**Midday check after sector rotation:**
```bash
python3 scripts/midday_scan.py --leading-sectors-only --html
```

**Full scan including your watchlist:**
```bash
python3 scripts/midday_scan.py --include-watchlist --html
```

**High liquidity only (50M+ dollar volume):**
```bash
python3 scripts/midday_scan.py --min-dollar-vol 50000000
```

---

## 📊 Comprehensive Pre-Market Report

**Script:** `scripts/premarket_report_comprehensive.py`

**Purpose:** Generate a complete pre-market briefing with futures, indices, regime assessment, economic calendar, sector leaders, and watchlist rankings.

### Usage

```bash
# Console output (default)
python3 scripts/premarket_report_comprehensive.py

# Generate HTML report (saved to reports/)
python3 scripts/premarket_report_comprehensive.py --html

# Custom output path
python3 scripts/premarket_report_comprehensive.py --html --output ~/Desktop/premarket.html
```

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

### HTML Report Features

| Section | Description |
|---------|-------------|
| **Overnight Futures** | ES, NQ, RTY, YM, CL, GC with change indicators |
| **VIX** | Current level with risk classification |
| **Regime Assessment** | 4-signal checklist with visual progress bar |
| **Economic Calendar** | US events with impact indicators (🔴 high, 🟡 medium) |
| **Major Indices** | SPY, QQQ, IWM vs 20/50/200 MAs |
| **Sector Leaders** | Top 20 ETFs ranked by overall performance |
| **Watchlist** | All stocks sorted by entry score, tier badges |
| **Ready Setups** | Auto-highlighted Tier 1 within 3% of pivot |
| **Action Items** | Interactive checklist for the trading day |

### Telegram Integration

Post the HTML report with a summary:

```bash
openclaw message send --channel telegram --account trader --target -4872065090 \
  --message "🌅 Pre-Market Report — $(date +%Y-%m-%d)\n\nRegime: 🔴 Bear (0/4 signals)\nTier 1 Ready: NVDA, TSLA\n\nFull report attached." \
  --media /Users/mintmrlion/.openclaw/workspaces/trader/reports/premarket_report_$(date +%Y-%m-%d).html \
  --force-document
```

---

## 🚀 Report Delivery

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
python3 scripts/premarket_report_comprehensive.py --html && \
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

## 📬 Telegram Posting

**Bot:** @tradermintbot  
**Account ID:** `trader`  
**Status:** ✅ Admin in channel + member in discussion group

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
