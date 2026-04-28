# Trader

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A systematic stock trading workflow for momentum-driven swing trading using Stage 2 methodology, built on Python with Alpaca API.

---

## Quick Start

```bash
# Clone and setup (30 seconds)
git clone https://github.com/MrLion/trader.git && cd trader
./setup.sh

# Verify setup
make doctor && make test

# Run your first scan
python3 scripts/entry_signals.py
```

**New user?** See [Getting Started Guide](docs/getting-started.md) for complete onboarding.

---

## What It Does

- **Real-time Trading Engine** — Automated entry/exit via Alpaca API with resilient WebSocket
- **Stage 2 Screening** — 8-point momentum scoring with MA convergence detection
- **Trend Screener** — Find stocks with optimal MA clusters and VCP patterns
- **Pre/Post Market Reports** — HTML briefings with futures, VIX, economic calendar
- **Backtesting Engine** — Simulate strategies against historical data
- **Strategy Plugins** — Pluggable architecture (VCP Breakout, Stage 2 Momentum, Composite)

---

## Scripts by Category

| Category | Scripts | Documentation |
|----------|---------|---------------|
| **Analysis** | `entry_signals.py` | [Entry Signals](docs/entry_signals/TIER_SCORING.md) |
| **Scans** | `sector_scan_comprehensive.py`, `trend_screener.py` | [Trend Screener](docs/trend_screener/USER_GUIDE.md) |
| **Reports** | `premarket_report.py`, `postmarket_report.py`, `deliver_report.py` | [Reports](docs/reports/) |
| **Backtesting** | `backtest.py` | [Backtesting Guide](docs/BACKTESTING_GUIDE.md) |
| **Trading** | `paper_engine_alpaca.py`, `paper_portfolio.py`, `show_positions.py` | [AGENTS.MD](AGENTS.MD) |
| **Watchlist** | `watchlist_manager.py`, `mcstock_scraper.py` | [TOOLS.md](TOOLS.md) |
| **Setup** | `setup_alpaca.py`, `validate_alpaca.py`, `doctor.py` | [docs/getting-started.md](docs/getting-started.md) |
| **Utilities** | `sync_state.py`, `clean_test_trades.py`, `risk_config_demo.py` | [docs/scripts/utility_scripts.md](docs/scripts/utility_scripts.md) |

---

## Repository Structure

```
trader/
├── scripts/          # CLI tools for analysis, scanning, trading
├── traderlib/        # Core library (alpaca_client, order_manager, strategies)
├── traderlib/backtest/  # Backtesting engine
├── data/             # watchlist.csv, positions, trade logs
├── docs/             # All documentation
├── config/           # Configuration files (risk_config.yaml, screener_config.yaml)
└── AGENTS.MD         # AI assistant instructions & trading reference
```

---

## Trading Framework

The system follows Mark Minervini's Stage 2 methodology with MA convergence scoring and VCP pattern detection.

**Entry Tiers:**
- **Tier 1** (≥60 pts, Stage 2 ≥6): Best setups — ready now
- **Tier 2** (40-59 pts, Stage 2 ≥5): Good setups — wait for better entry
- **Tier 3** (<40 pts): Monitor only

**Risk Rules:** 0.5% account risk per trade, max 3 positions/sector, trailing stops (+1R breakeven, +1.5R EMA10, +3R EMA21)

→ See [METHODOLOGY.md](docs/METHODOLOGY.md) for complete methodology and [RISK_GUIDE.md](docs/RISK_GUIDE.md) for risk configuration.

---

## Configuration

**Recommended:** Create a `.env` file in the project root:

```bash
cp .env.example .env
# Edit .env with your keys
```

**Required for Trading:**
- `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` — Paper trading (from https://app.alpaca.markets/paper)
- `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` — Live trading (from https://app.alpaca.markets)

**Optional:**
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — Report delivery
- `MCSTOCK_USER` / `MCSTOCK_PASS` — MC Stock Charts scraper
- `FMP_API_KEY` — Earnings/economic calendar in pre-market reports (fail-open)

→ See [Configuration Reference](docs/config/configuration-reference.md) for all options and environment overrides.

---

## FAQ

**Do I need Alpaca API keys to use scanners?**  
No. Scanners and reports work with Yahoo Finance data. Only automated trading requires Alpaca.

**How do I reset paper trading data?**  
Delete `data/paper_positions.json` and restart the engine.

**Can I run this on a server?**  
Yes. The engine runs headless with environment variables set.

**Where are trade logs stored?**  
`data/paper_trades.jsonl` (JSON Lines format, append-only).

**More questions?** See [docs/getting-started.md](docs/getting-started.md#faq) for troubleshooting.

---

## Documentation

| For... | Start Here |
|--------|------------|
| New users | [Getting Started](docs/getting-started.md) |
| Traders | [AGENTS.MD](AGENTS.MD) — AI assistant instructions & trading reference |
| Strategy authors | [Strategy Overview](docs/strategies/OVERVIEW.md) |
| Developers | [DEVELOPMENT.md](docs/DEVELOPMENT.md) |

**Full index:** [docs/README.md](docs/README.md) — All documentation organized by task.

---

## License

MIT License — see [LICENSE](LICENSE) file.
