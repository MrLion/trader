# Market Reports

Pre-market and post-market briefing tools.

---

## Quick Start

```bash
# Pre-market report (console)
python3 scripts/premarket_report.py

# Pre-market report (HTML)
python3 scripts/premarket_report.py --html

# Post-market report
python3 scripts/postmarket_report.py --html

# Deliver to Telegram
python3 scripts/deliver_report.py --file reports/premarket_report.html
```

---

## Pre-Market Report

**Purpose:** Morning briefing with overnight action, futures, and watchlist setups.

**Features:**
- Overnight futures (ES, NQ, RTY, YM, CL, GC)
- VIX level classification (Low <18, Elevated 18-28, High >28)
- Crypto tracking (BTC, ETH)
- Economic calendar with risk assessment
- Major indices vs 20/50/200 MA
- Sector leaders from scan data
- Watchlist entry scores (Tier 1/2/3)

**Usage:**
```bash
# Console output
python3 scripts/premarket_report.py

# HTML report
python3 scripts/premarket_report.py --html

# Custom output path
python3 scripts/premarket_report.py --html --output ~/Desktop/premarket.html
```

---

## Post-Market Report

**Purpose:** End-of-day analysis with market close summary and action items.

**Features:**
- Market close summary (SPY, QQQ, IWM) with intraday ranges
- VIX analysis with level classification
- Regime Assessment with signal grid
- Watchlist performance (change %, volume, distance to pivot)
- Gap detection (>3% moves) with volume confirmation
- Dynamic action items based on today's action
- Key levels for tomorrow

**Usage:**
```bash
# Console output
python3 scripts/postmarket_report.py

# HTML report
python3 scripts/postmarket_report.py --html

# Custom output with timestamp
python3 scripts/postmarket_report.py --html --output reports/postmarket_$(date +%Y%m%d_%H%M).html
```

---

## Report Delivery

**Script:** `scripts/deliver_report.py`

Deliver HTML reports via Telegram bot.

**Setup:**
```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="-4872065090"  # Default: Trading Sandbox
```

**Usage:**
```bash
# Basic delivery
python3 scripts/deliver_report.py --file reports/premarket_report.html

# With caption
python3 scripts/deliver_report.py --file report.html --caption "Morning briefing"

# Dry run (test without sending)
python3 scripts/deliver_report.py --file report.html --dry-run --verbose
```

**See [TOOLS.md](../../TOOLS.md#report-delivery) for detailed delivery documentation.**

---

## Workflow Integration

### Pre-Market Routine (6:00-9:30 AM ET)

```bash
# 1. Generate pre-market report
python3 scripts/premarket_report.py --html

# 2. Deliver to Telegram
python3 scripts/deliver_report.py --file reports/premarket_report_$(date +%Y-%m-%d).html

# 3. Run entry signals scan
python3 scripts/entry_signals.py

# 4. Review Tier 1 setups
python3 scripts/entry_signals.py --min-tier 1
```

### Post-Market Routine (4:00-6:00 PM ET)

```bash
# 1. Generate post-market report
python3 scripts/postmarket_report.py --html

# 2. Deliver to Telegram
python3 scripts/deliver_report.py --file reports/postmarket_report_$(date +%Y-%m-%d).html

# 3. Run trend screener for new candidates
python3 scripts/trend_screener.py --profile large-cap --export-csv scans/trend_$(date +%Y-%m-%d).csv
```

---

## Configuration

Report configuration in `config/scraper_config.yaml`:

```yaml
reports:
  include_futures: true
  include_crypto: true
  include_economic_calendar: true
  vix_levels:
    low: 18
    high: 28
```

---

## Related Documentation

- [TOOLS.md](../../TOOLS.md) — yfinance usage, detailed script commands
- [entry_signals/TIER_SCORING.md](../entry_signals/TIER_SCORING.md) — Tier classification
- [trend_screener/USER_GUIDE.md](../trend_screener/USER_GUIDE.md) — Trend screener
- [AGENTS.MD](../../AGENTS.MD) — Trading rhythm and protocols
