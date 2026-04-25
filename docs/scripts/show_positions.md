# Show Positions

Quick open-positions viewer for paper trading.

---

## Overview

`scripts/show_positions.py` fetches current prices for all open paper trading positions and displays holdings with P&L.

---

## Usage

```bash
# Show all open positions
python3 scripts/show_positions.py
```

---

## Output

Console table with:

| Column | Description |
|--------|-------------|
| `Ticker` | Position symbol |
| `Shares` | Number of shares held |
| `Entry` | Average entry price |
| `Current` | Last fetched price |
| `P&L $` | Unrealized P&L in dollars |
| `P&L %` | Unrealized P&L percentage |
| `R-Multiple` | Current R-multiple if stop defined |
| `Days Held` | Calendar days since entry |

---

## Data Source

- **State:** `data/paper_positions.json`
- **Prices:** Yahoo Finance via `yfinance`

---

## Related

- [Paper Portfolio](paper_portfolio.md) — Full portfolio management CLI
- [AGENTS.MD](../AGENTS.MD) — Position management rules
