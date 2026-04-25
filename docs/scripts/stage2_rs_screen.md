# Stage 2 RS Screen

Relative strength screen for Stage 2 candidates.

---

## Overview

`scripts/stage2_rs_screen.py` screens tickers from a file for Stage 2 momentum characteristics with relative strength vs SPY.

---

## Usage

```bash
# Screen a ticker list
python3 scripts/stage2_rs_screen.py --file data/my_tickers.txt

# Output to custom path
python3 scripts/stage2_rs_screen.py --file data/my_tickers.txt --output scans/rs_screen.csv
```

---

## Input Format

Text file with one ticker per line:

```
AAPL
NVDA
MSFT
TSLA
```

---

## Output Columns

| Column | Description |
|--------|-------------|
| `Ticker` | Stock symbol |
| `RS_Rank` | Relative strength percentile vs SPY |
| `Stage2_Score` | Stage 2 score (0-10) |
| `Above_50MA` | Price above 50-day MA |
| `Above_200MA` | Price above 200-day MA |
| `6M_Return` | 6-month return (%) |
| `Vs_SPY` | Return vs SPY (%) |

---

## Criteria

- Price > 100 SMA > 200 SMA
- 200 SMA slope up >= 1 month
- Price >= 1.25x 52-week low
- Price within 25% of 52-week high
- RS line at/near new highs

---

## Related

- [METHODOLOGY.md](../METHODOLOGY.md) — Stage 2 methodology
- [Entry Signals](../entry_signals/TIER_SCORING.md) — Entry scoring
- [Trend Screener](../trend_screener/USER_GUIDE.md) — Automated discovery
