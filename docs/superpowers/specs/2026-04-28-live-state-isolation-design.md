# Live State Isolation Design

**Created:** 2026-04-28
**Version:** 0.6.16.0
**Theme:** Safety

## Problem

The paper trading engine shares local state files between paper and live modes. Running `--mode live` reads and writes the same `paper_positions.json`, `paper_trades.jsonl`, and other state files as `--mode paper`. API credentials are already separated (`ALPACA_PAPER_*` vs `ALPACA_LIVE_*`), but local state is not.

## Scope

Full isolation across three axes:
- **Accidental cross-contamination**: Switching modes can't mix real and simulated data
- **Simultaneous execution**: Paper and live engines running at the same time can't clobber each other
- **Post-hoc clarity**: Trade history is unambiguously attributable to paper or live

## Design

### Directory Structure

```
data/
  paper/                   # Paper trading state
    positions.json
    trades.jsonl
    orders.json
    daily_tracker.json
  live/                    # Live trading state
    positions.json
    trades.jsonl
    orders.json
    daily_tracker.json
  watchlist.csv            # Shared
  ticker_sectors_cache.json
  backtests/               # Shared
  logs/                    # Shared
  universes/               # Shared

config/
  paper/
    risk_config.yaml       # Paper risk profile
  live/
    risk_config.yaml       # Live risk profile (conservative)
  screener_config.yaml     # Shared
  backtest_config.yaml     # Shared
  strategies/              # Shared
```

Files that are mode-independent (watchlists, caches, backtests, logs, screeners, strategies) stay at the root level. Only trading state and risk config are partitioned.

### Risk Config Separation

`config/paper/risk_config.yaml` and `config/live/risk_config.yaml` are independent files — no inheritance or merging. The existing `config/risk_config.yaml` becomes `config/paper/risk_config.yaml`. The live variant starts as a conservative copy (tighter stops, lower position sizing, lower daily loss limit) that the user tunes before going live.

`RiskConfigManager` already accepts a config path; the engine passes `config/{mode}/risk_config.yaml`.

### Code Changes

All changes are internal path construction — no logic changes to state management, order handling, or trading:

- **`traderlib/paper_state.py`**: `PaperState` already accepts `data_dir`. Engine constructs it as `data/{mode}/`. File basenames simplify: `paper_positions.json` → `positions.json`, etc. `PAPER_TRADING_DATA_DIR` env var continues to override the root.

- **`traderlib/order_manager.py`**: Same pattern — engine passes `data/{mode}/`.

- **`traderlib/alpaca_client.py`**: No changes. Already handles mode-based API key selection.

- **`scripts/paper_engine_alpaca.py`**: Renamed to `trading_engine.py`. Class `AlpacaPaperEngine` → `TradingEngine`. Mode determines all paths.

- **`traderlib/risk_config.py`**: No signature changes — engine passes mode-specific config path.

### User-Facing Changes

1. **Commands stay the same**: `--mode paper` (default) reads/writes from `data/paper/`. `--mode live` reads/writes from `data/live/`.
2. **Dashboard**: Header shows a colored badge — blue "PAPER" or green "LIVE" — so the active account is always visible.
3. **Risk configs**: A separate `config/live/risk_config.yaml` to tune before going live.

### Migration

On first startup after upgrade:

1. Detect old layout: if `data/paper_positions.json` exists, migration is needed.
2. Create `data/paper/` directory.
3. Move: `paper_positions.json` → `positions.json`, `paper_trades.jsonl` → `trades.jsonl`, `alpaca_orders.json` → `orders.json`, `daily_tracker.json` stays. Same for `.backup` files.
4. Leave `.bak` copies of originals as an undo path.
5. One-time: after migration, the engine never checks again.
6. Fresh installs skip migration and start clean.

### API Key Separation

Alpaca requires separate API keys per account (paper, live). This is already handled — `alpaca_client.py` selects `ALPACA_PAPER_*` or `ALPACA_LIVE_*` based on mode, with fallback to `ALPACA_API_KEY`. The `TradingClient(paper=True/False)` routes to the correct Alpaca endpoint. No changes needed here.

## Non-Goals

- Simultaneous paper + live execution in one process (each mode gets its own process)
- Live trading features beyond isolation
- Strategy differences between paper and live (same strategies, different risk configs)
