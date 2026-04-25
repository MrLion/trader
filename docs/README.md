# Documentation Index

Organized by task and user type.

---

## Quick Navigation

| I want to... | Start Here |
|--------------|------------|
| Set up the project | [Getting Started](getting-started.md) |
| Learn the trading methodology | [METHODOLOGY.md](METHODOLOGY.md) |
| Run my first scan | [Entry Signals](entry_signals/TIER_SCORING.md) |
| Configure risk parameters | [RISK_GUIDE.md](RISK_GUIDE.md) |
| Write a strategy plugin | [Strategy Overview](strategies/OVERVIEW.md) |
| Troubleshoot issues | [Runbooks](runbooks/) |

---

## All Documentation

### Trading & Methodology

| Document | Purpose |
|----------|---------|
| [AGENTS.MD](../AGENTS.MD) | AI assistant instructions & trading reference — operating rhythm, entry protocol, risk rules |
| [METHODOLOGY.md](METHODOLOGY.md) | Stage 2 methodology, MA support stops, position sizing |
| [RISK_GUIDE.md](RISK_GUIDE.md) | Risk management, profiles, configuration examples |

### Scripts & Tools

| Document | Purpose |
|----------|---------|
| [Entry Signals](entry_signals/TIER_SCORING.md) | Tier classification, scoring components, output formats |
| [Trend Screener](trend_screener/USER_GUIDE.md) | Discovery mode, entry timing, VCP detection, convergence scoring |
| [MA Convergence](trend_screener/MA_CONVERGENCE.md) | Scoring algorithm deep dive |
| [Sector Scan](scripts/sector_scan.md) | Comprehensive ETF sector scan with ranking |
| [Watchlist Manager](scripts/watchlist_manager.md) | Watchlist population, add, remove, list |
| [Stage 2 RS Screen](scripts/stage2_rs_screen.md) | Relative strength screen vs SPY |
| [MC Stock Scraper](scripts/mcstock_scraper.md) | Trade ideas and historical archives |
| [Paper Portfolio](scripts/paper_portfolio.md) | Paper trading portfolio management |
| [Show Positions](scripts/show_positions.md) | Quick open-positions viewer |
| [Utility Scripts](scripts/utility_scripts.md) | Doctor, setup, validate, sync, cleanup |
| [Backtesting](BACKTESTING_GUIDE.md) | Backtest engine usage, strategies, reporting |
| [Reports](reports/README.md) | Pre-market and post-market reports |
| [TOOLS.md](../TOOLS.md) | yfinance usage, internal developer notes |

### Patterns & Strategies

| Document | Purpose |
|----------|---------|
| [Strategy Overview](strategies/OVERVIEW.md) | Strategy plugin architecture, registry, CompositeStrategy |
| [VCP Patterns](patterns/VCP.md) | VCP detection algorithm, progression validation |
| [VCP Breakout](strategies/VCP_BREAKOUT.md) | VCP breakout strategy (large-cap and high-octane profiles) |
| [Universe Filtering](universe/DYNAMIC_FILTERING.md) | Dynamic universe building, funnel filtering, ETF exclusion |

### Development

| Document | Purpose |
|----------|---------|
| [DEVELOPMENT.md](DEVELOPMENT.md) | Development setup, CI/CD, contributing guidelines |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, ExitAction pattern, Strategy ABC |
| [Configuration Reference](config/configuration-reference.md) | All configuration options, profiles, environment overrides |
| [Testing Guide](TESTING.md) | Running tests, writing tests, mock patterns, coverage |
| [Deployment Guide](DEPLOYMENT.md) | Production deployment, cron jobs, monitoring |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | PR process, commit format, code style |

### Runbooks (Troubleshooting)

| Document | Purpose |
|----------|---------|
| [API Outage](runbooks/api_outage.md) | API failures, timeouts, connection issues |
| [Partial Fill](runbooks/partial_fill.md) | Order fills, position size mismatch |
| [Stuck Position](runbooks/stuck_position.md) | Ticker halted/delisted, exit problems |
| [Data Quality](runbooks/data_quality.md) | Wrong scores, bad data validation |

---

## Documentation by Audience

### For New Users
1. [Getting Started](getting-started.md) — Setup and first workflow
2. [AGENTS.MD](../AGENTS.MD) — AI assistant instructions & trading reference
3. [Entry Signals](entry_signals/TIER_SCORING.md) — First scan

### For Traders
1. [METHODOLOGY.md](METHODOLOGY.md) — Stage 2 methodology
2. [RISK_GUIDE.md](RISK_GUIDE.md) — Risk configuration
3. [Trend Screener](trend_screener/USER_GUIDE.md) — Discovery tool

### For Strategy Authors
1. [Strategy Overview](strategies/OVERVIEW.md) — Plugin architecture
2. [VCP Breakout](strategies/VCP_BREAKOUT.md) — Example strategy
3. [ARCHITECTURE.md](ARCHITECTURE.md) — System design

### For Developers
1. [DEVELOPMENT.md](DEVELOPMENT.md) — Development setup
2. [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
3. [Runbooks](runbooks/) — Troubleshooting
