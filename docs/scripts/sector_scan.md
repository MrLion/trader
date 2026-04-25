# Sector Scan

Comprehensive ETF sector scan with full ranking system.

---

## Overview

`scripts/sector_scan_comprehensive.py` scans 131 ETFs across sectors, factors, commodities, bonds, and international markets. It calculates 1-week through 6-month returns, moving average status, Stage 2 scores, and produces a weighted composite ranking.

**Output:** `scans/YYYY-MM-DD_sector_scan.csv`

---

## Usage

```bash
# Default: scan all ETFs and show top 15
python3 scripts/sector_scan_comprehensive.py

# Show top 5 only
python3 scripts/sector_scan_comprehensive.py --top 5

# Show top 25
python3 scripts/sector_scan_comprehensive.py --top 25
```

---

## CSV Output Columns

| Column | Description |
|--------|-------------|
| `Ticker` | ETF symbol |
| `Name` | Description |
| `1W` | 1-week return (%) |
| `1M` | 1-month return (%) |
| `3M` | 3-month return (%) |
| `6M` | 6-month return (%) |
| `Above_20` | Price above 20-day MA |
| `Above_50` | Price above 50-day MA |
| `Above_200` | Price above 200-day MA |
| `From_High` | Distance from 52-week high (%) |
| `Stage2_Score` | Stage 2 score (0-10) |
| `Rank_Score` | Weighted rank composite |
| `Rank_6M` | 6-month performance rank |
| `Rank_3M` | 3-month performance rank |
| `Rank_1M` | 1-month performance rank |
| `Overall_Rank` | Final composite rank (1 = best) |

---

## Rank Score Weights

```
Rank Score = (Rank_6M * 0.4) + (Rank_3M * 0.3) + (Rank_1M * 0.2) + (Rank_1W * 0.1)
```

---

## Data Source

- **Primary:** Yahoo Finance via `yfinance`
- **History:** 1 year of daily data per ticker
- **Minimum bars:** 130 (approx. 6 months) required for inclusion

---

## Scheduling

Recommended cron for daily pre-market scan:

```
50 7 * * 1-5 cd /path/to/trader && python3 scripts/sector_scan_comprehensive.py
```

---

## Related

- [Trend Screener](trend_screener/USER_GUIDE.md) — Stock-level trend discovery
- [AGENTS.MD](../AGENTS.MD) — Sector rotation rules
- [Reports](reports/README.md) — Pre-market report integrates sector data
