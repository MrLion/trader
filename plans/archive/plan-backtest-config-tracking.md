# Plan: Backtest Configuration Tracking

**Status:** Approved — Ready for implementation  
**Date:** 2026-04-27  
**Priority:** High

---

## Problem

Current backtest output (`--csv`) only contains trade data. No way to know which configuration (risk profile, strategy, profit target mode, etc.) produced the results. Cannot compare runs or track what works.

---

## Solution

Auto-save backtest runs to `data/backtests/` with distinct folders and self-identifying files.

---

## Folder Structure

```
data/backtests/
├── 2026-04-27_094523_847_conservative_hybrid_stage2/
│   ├── 2026-04-27_094523_847_trades.csv
│   └── 2026-04-27_094523_847_config.txt
├── 2026-04-27_101245_203_aggressive_trailing_vcp/
│   ├── 2026-04-27_101245_203_trades.csv
│   └── 2026-04-27_101245_203_config.txt
└── 2026-04-28_090015_491_conservative_target_stage2/
    ├── 2026-04-28_090015_491_trades.csv
    └── 2026-04-28_090015_491_config.txt
```

### Folder Naming

`YYYY-MM-DD_HHMMSS_MMM_risk_profile_profit_mode_strategy/`

- **Timestamp:** Date + time + milliseconds (collision-resistant)
- **Risk profile:** conservative/aggressive/tight_stops
- **Profit mode:** target/trailing/hybrid
- **Strategy:** stage2/vcp/etc.

### Files

**trades.csv** — Clean trade data:
```csv
ticker,entry_date,exit_date,entry_price,exit_price,shares,pnl,r_multiple,exit_reason,pivot_price
AAPL,2024-01-15,2024-01-25,180.50,195.20,277,4066.74,2.5,scale_out,178.00
```

**config.txt** — Human-readable configuration + results:
```
Backtest Run: 2026-04-27 at 09:45:23
Version: 0.6.12.1

Risk Profile: conservative
  Risk per trade: 0.5%
  Max position: 10%
  Daily loss limit: 2%

Strategy: stage2_momentum
Profit Target: hybrid
  Scale out at 3R: 50%
  Scale out at 4R: 30%

Stop Loss: atr_or_support
  ATR multiplier: 2x

Execution:
  Slippage: 5 bps
  Earnings filter: enabled

Backtest:
  Date range: 2024-01-01 to 2024-12-31
  Initial capital: $100,000
  Max positions: 10

Results:
  Total Return: 23.5%
  Win Rate: 68.9%
  Avg R-Multiple: 1.85
  Sharpe: 1.65
  Trades: 45
```

---

## Usage

Run backtest:
```bash
python3 scripts/backtest.py --start 2024-01-01 --end 2024-12-31
# Creates: data/backtests/2026-04-27_094523_847_conservative_hybrid_stage2/
```

Find runs:
```bash
ls data/backtests/
# Shows: 2026-04-27_094523_847_conservative_hybrid_stage2/
```

View trades:
```bash
open data/backtests/2026-04-27_094523_847_conservative_hybrid_stage2/2026-04-27_094523_847_trades.csv
```

View config:
```bash
cat data/backtests/2026-04-27_094523_847_conservative_hybrid_stage2/2026-04-27_094523_847_config.txt
```

---

## CLI Changes

- **Default:** Auto-save to `data/backtests/YYYY-MM-DD_HHMMSS_MMM_risk_profile_profit_mode_strategy/`
- Add `--no-save` flag to skip saving (for quick testing)

---

## Benefits

| Benefit | How It's Achieved |
|---------|-------------------|
| No overwritten files | Timestamp + milliseconds in folder name |
| Know which config | Risk profile + profit mode + strategy in folder name |
| Full config details | config.txt with all settings |
| Clean trade data | Simple CSV without config clutter |
| R-multiple tracking | Added as column in CSV |

---

## User Value

- **For you:** Track what works. Compare conservative vs aggressive, hybrid vs trailing.
- **For future you:** Know what you ran 3 months ago without guessing.
- **For other traders:** Self-documenting backtests. No manual note-taking.

---

## Implementation Notes

- Modify `scripts/backtest.py` to auto-call save function
- Create folder with timestamp + key config
- Write trades.csv (clean columns)
- Write config.txt (human-readable)
- Ensure distinct filenames using timestamp

---

*Next step: Create implementation plan when ready to build.*
