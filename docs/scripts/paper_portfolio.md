# Paper Portfolio

Paper trading portfolio management and monitoring.

---

## Overview

`scripts/paper_portfolio.py` provides a CLI for managing and monitoring the paper trading portfolio.

---

## Commands

### Status

```bash
# Current portfolio summary
python3 scripts/paper_portfolio.py status
```

Shows:
- Open positions with P&L
- Account equity
- Cash available
- Sector allocation
- Daily/weekly P&L

### Live Monitor

```bash
# Real-time position monitoring
python3 scripts/paper_portfolio.py live
```

Updates prices every 30 seconds with:
- Current P&L
- R-multiples
- Distance to stops
- Time held

### Trade History

```bash
# Today's trades
python3 scripts/paper_portfolio.py today

# Full history
python3 scripts/paper_portfolio.py history

# Last N trades
python3 scripts/paper_portfolio.py history --limit 20
```

### Generate Report

```bash
# HTML portfolio report
python3 scripts/paper_portfolio.py report

# Custom output
python3 scripts/paper_portfolio.py report --output reports/portfolio_$(date +%Y%m%d).html
```

### Close Position

```bash
# Close a position
python3 scripts/paper_portfolio.py close AAPL

# Close with confirmation
python3 scripts/paper_portfolio.py close AAPL --confirm
```

---

## Data Files

| File | Purpose |
|------|---------|
| `data/paper/positions.json` | Open positions state (paper mode) |
| `data/paper/trades.jsonl` | Trade log (append-only, paper mode) |
| `data/paper_account.json` | Account equity tracking |

---

## Related

- [Show Positions](show_positions.md) — Quick position viewer
- [AGENTS.MD](../../AGENTS.MD) — Portfolio management rules
- [RISK_GUIDE.md](../RISK_GUIDE.md) — Risk configuration
- [Runbooks](../runbooks/partial_fill.md) — Troubleshooting fills
