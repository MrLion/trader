# Trading Modes: Paper vs Live

Introduced in **v0.6.16.0**, the trading engine supports two fully isolated modes.
State files, risk configs, and trade logs never cross-contaminate between modes.

---

## Quick Reference

| Aspect | Paper Mode | Live Mode |
|--------|-----------|-----------|
| Flag | `--mode paper` (default) | `--mode live` |
| Data directory | `data/paper/` | `data/live/` |
| Risk config | `config/paper/risk_config.yaml` | `config/live/risk_config.yaml` |
| Risk/trade | 0.5% (standard) | 0.25% (conservative) |
| Daily loss limit | 2% | 1% |
| Max position | 10% | 5% |
| Dashboard badge | Blue **PAPER** | Green **LIVE** |

---

## Starting the Engine

```bash
# Paper mode (default — explicit is clearer)
python3 scripts/paper_engine_alpaca.py --mode paper

# Live mode — requires live Alpaca API keys
python3 scripts/paper_engine_alpaca.py --mode live
```

The engine reads its mode from the `--mode` flag and routes all file I/O to the
corresponding `data/{mode}/` and `config/{mode}/` directories.

---

## Data Isolation

Each mode gets its own directory structure under `data/`:

```
data/paper/                # Paper trading state
├── positions.json         # Open positions
├── trades.jsonl           # Trade log (append-only)
├── orders.json            # Order history
└── daily_tracker.json     # Daily stats

data/live/                 # Live trading state
├── positions.json
├── trades.jsonl
├── orders.json
└── daily_tracker.json
```

Files shared across modes stay at the root level:
- `data/watchlist.csv`
- `data/ticker_sectors_cache.json`
- `config/screener_config.yaml`
- `data/backtests/`, `data/logs/`, `data/universes/`

---

## Risk Config Separation

Each mode has its own risk configuration file.
They are fully independent — no inheritance or merging.

| File | Purpose |
|------|---------|
| `config/paper/risk_config.yaml` | Standard settings (same as pre-v0.6.16.0 defaults) |
| `config/live/risk_config.yaml` | Conservative defaults tuned for real capital |

To customize either, edit the file directly:

```bash
# Edit paper risk profile
vim config/paper/risk_config.yaml

# Edit live risk profile (start conservatively!)
vim config/live/risk_config.yaml
```

---

## API Key Separation

Alpaca credentials are already mode-separated at the environment variable level:

| Variable | Purpose |
|----------|---------|
| `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` | Paper trading |
| `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` | Live trading |

Fallback: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (used when mode-specific vars
are not set).

---

## Dashboard Mode Badge

When the dashboard is running, the header shows a color-coded badge so you
always know which account is active:

- **PAPER ENGINE** (blue) — Paper trading, no real money at risk
- **LIVE ENGINE** (green) — Real capital, positions matter

---

## Migration from v0.6.15.x

On the first startup after upgrading to v0.6.16.0+, the engine automatically
migrates old flat files into `data/paper/`:

| Old Path | New Path |
|----------|----------|
| `data/paper_positions.json` | `data/paper/positions.json` |
| `data/paper_trades.jsonl` | `data/paper/trades.jsonl` |
| `data/alpaca_orders.json` | `data/paper/orders.json` |
| `data/daily_tracker.json` | `data/paper/daily_tracker.json` |

The migration runs once and never checks again. Backup copies are left in place
as `.bak` files for a manual undo path.

---

## Running Both Modes Simultaneously

You can run paper and live engines at the same time in separate terminal windows.
Because each mode writes to its own directory, they cannot interfere:

```bash
# Terminal 1: Paper engine
python3 scripts/paper_engine_alpaca.py --mode paper

# Terminal 2: Live engine
python3 scripts/paper_engine_alpaca.py --mode live
```

Each engine manages its own:
- Positions and trade log
- Order submission and fill tracking
- Cooldown state and entry signals
- Dashboard display

---

## Safety Guardrails

- **No cross-mode reads**: The paper engine never reads `data/live/` and vice versa
- **Independent risk configs**: A mistake in `config/paper/risk_config.yaml` cannot affect live trades
- **Dashboard badge**: The mode is always visible in the header
- **Separate API keys**: Paper/live Alpaca credentials are distinct env vars

---

## See Also

- [Getting Started](getting-started.md) — First-time setup and daily workflow
- [Risk Guide](RISK_GUIDE.md) — Risk configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture and file organization
- [CHANGELOG](../CHANGELOG.md) — Version history
