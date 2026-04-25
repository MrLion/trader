# Watchlist Manager

Automated watchlist population and management.

---

## Overview

`scripts/watchlist_manager.py` manages the `data/watchlist.csv` file — the core trading universe. Supports adding, removing, populating from scan CSVs, and listing with filtering.

---

## Commands

### Populate from Scan

```bash
# Import tickers from a scan CSV
python3 scripts/watchlist_manager.py populate /path/to/scan.csv
```

### Add Single Ticker

```bash
# Add with notes
python3 scripts/watchlist_manager.py add AAPL "Pullback to 21 EMA"

# Skip data validation
python3 scripts/watchlist_manager.py add AAPL "Quick add" --force
```

### Remove Ticker

```bash
# Remove single ticker
python3 scripts/watchlist_manager.py remove AAPL

# Preview removal
python3 scripts/watchlist_manager.py remove AAPL --dry-run

# Remove all tickers (interactive)
python3 scripts/watchlist_manager.py remove-all

# Force remove all without confirmation
python3 scripts/watchlist_manager.py remove-all --force
```

### List Watchlist

```bash
# List all tickers
python3 scripts/watchlist_manager.py list
```

---

## Watchlist Schema

```
Ticker, Stage, RS_Rank, Pivot_Price, Current_Price, Stop_Level,
ATR, Risk_%, $Vol_M, Sector, Industry, Notes,
Added_Date, Alert_Set, Base_Count, Pattern_Type, Target_1,
Target_2, R_Ratio, Avg_Volume_50d, Market_Cap
```

---

## Entry Score Calculation

Entry scores are calculated by `entry_signals.py` (max 100 points).

**Quick Reference:**

| Component | Criteria | Points |
|-----------|----------|--------|
| **Stage 2 Score** | 7-8/8 | +30 |
| | 6/8 | +25 |
| | 5/8 | +20 |
| **Risk %** | < 10% | +30 |
| | < 15% | +20 |
| | < 20% | +10 |
| **Distance to Pivot** | < 3% | +25 |
| | < 5% | +15 |
| | < 10% | +5 |
| **6M Momentum** | > 50% | +15 |
| **RS vs SPY** | > 20% | +10 |
| **MA Penalties** | Below 50 MA | -20 |
| | Below 20 MA | -10 |

---

## Related

- [Entry Signals](../entry_signals/TIER_SCORING.md) — Complete tier scoring documentation
- [TOOLS.md](../../TOOLS.md) — yfinance usage notes
