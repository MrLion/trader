# MC Stock Charts Scraper

Trade ideas and historical report scraper for MC Stock Charts.

---

## Overview

Two scripts for fetching trade ideas and historical archives from `mcstockcharts.com`.

---

## Daily Report: mcstock_scraper.py

Scrapes the latest trade ideas report.

```bash
# Fetch latest report
python3 scripts/mcstock_scraper.py

# Custom output path
python3 scripts/mcstock_scraper.py --output scans/mcstock_latest.csv
```

**Requires:** `MCSTOCK_USER` and `MCSTOCK_PASS` environment variables.

---

## Historical Archives: mcstock_historical_scraper.py

Scrapes historical weekly reports for backtesting.

```bash
# Fetch last 10 weeks
python3 scripts/mcstock_historical_scraper.py --weeks 10

# Fetch last 4 weeks
python3 scripts/mcstock_historical_scraper.py --weeks 4
```

**Output:** CSVs with ticker, setup type, pivot price, stop level.

---

## Output Columns

| Column | Description |
|--------|-------------|
| `Ticker` | Stock symbol |
| `Setup` | Pattern type (VCP, Flat Base, etc.) |
| `Pivot_Price` | Buy point |
| `Stop_Level` | Initial stop loss |
| `Risk_%` | Risk percentage |
| `Notes` | Additional context |

---

## Related

- [Backtesting Guide](../BACKTESTING_GUIDE.md) — Using historical data
- [Watchlist Manager](watchlist_manager.md) — Importing scan results
