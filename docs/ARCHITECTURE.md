# System Architecture

## Overview

The Trader system is a Python-based momentum trading platform for swing trading stocks using the Stage 2 methodology. It combines real-time trading via Alpaca API with comprehensive analysis tools.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TRADER SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │   Analysis   │  │   Trading    │  │   Reports    │  │ Backtest │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘  │
│         │                 │                 │              │        │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐  ┌───▼────────┐│
│  │entry_signals │  │paper_engine  │  │pre/postmarket│  │ backtest   ││
│  │sector_scan   │  │alpaca_client │  │deliver_report│  │   engine   ││
│  │mcstock_      │  │order_manager│  │              │  │            ││
│  │  scraper     │  │              │  │              │  │            ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      traderlib/ (Core Library)                   │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  alpaca_client  │  paper_state   │  paper_exits  │  stage2    │   │
│  │  order_manager  │  risk_config   │  rate_limiter │  utils     │   │
│  │  market_hours   │  trading_      │  validation   │  backtest/ │   │
│  │                 │    exceptions    │               │            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      External APIs                               │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │   │
│  │  │ Alpaca   │  │ Yahoo    │  │ MC Stock │  │ Telegram     │   │   │
│  │  │ (Trading)│  │ Finance  │  │ Charts   │  │ (Alerts)     │   │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Modules

### 1. Data Layer

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Alpaca API ──────┐     yfinance ──────┐     Scrapers ──────┐     │
│   (Real-time)      │     (Reports)       │     (Screens)      │     │
│         │          │          │          │          │         │     │
│         ▼          │          ▼          │          ▼         │     │
│   ┌──────────┐     │   ┌──────────┐     │   ┌──────────┐     │     │
│   │alpaca_   │     │   │ Reports  │     │   │ Watchlist│     │     │
│   │client.py │◄────┼───│ (15m lag)│     │   │ Screens  │     │     │
│   └──────────┘     │   └──────────┘     │   └──────────┘     │     │
│         │          │          │          │          │         │     │
│         ▼          │          ▼          │          ▼         │     │
│   ┌─────────────────────────────────────────────────────────┐   │     │
│   │                    data/ Directory                       │   │     │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────────┐    │   │     │
│   │  │watchlist   │  │portfolio   │  │ticker_sectors_ │    │   │     │
│   │  │.csv        │  │.json       │  │cache.json      │    │   │     │
│   │  └────────────┘  └────────────┘  └────────────────┘    │   │     │
│   └─────────────────────────────────────────────────────────┘   │     │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Components:**

| Module | Purpose | Data Sources |
|--------|---------|--------------|
| `alpaca_client.py` | Real-time trading data | Alpaca API (WebSocket + REST) |
| `market_hours.py` | Trading calendar | pandas_market_calendars (NYSE) |
| `mcstock_scraper.py` | Minervini screens | MC Stock Charts website |
| `yfinance` | Historical/research data | Yahoo Finance |

### 2. Trading Engine

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TRADING ENGINE FLOW                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌───────────────┐         ┌───────────────┐         ┌──────────┐ │
│   │  Entry Logic   │         │   Position    │         │   Exit   │ │
│   │  (paper_engine │────────▶│   Management  │────────▶│  Logic   │ │
│   │   _alpaca.py)  │         │  (paper_state │         │(paper_  │ │
│   └───────────────┘         │   .py)        │         │ exits)  │ │
│           │                 └───────────────┘         └──────────┘ │
│           │                           │                            │
│           ▼                           ▼                            │
│   ┌───────────────┐         ┌───────────────┐                      │
│   │  Stage 2      │         │   Order       │                      │
│   │  Screening    │         │   Manager     │                      │
│   │ (stage2_      │         │ (order_       │                      │
│   │  utils.py)    │         │  manager.py)  │                      │
│   └───────────────┘         └───────────────┘                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Entry Flow:**
1. `entry_signals.py` - Scan watchlist for Tier 1/2/3 setups
2. `paper_engine_alpaca.py` - Evaluate entries during market hours
3. `paper_state.py` - Manage open positions
4. `paper_exits.py` - Calculate stops and targets

### 3. Risk Management System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RISK MANAGEMENT                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  risk_config.py                              │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │  │
│  │  │ Account  │ │ Position │ │ Stop     │ │ MA Support   │  │  │
│  │  │ Risk     │ │ Risk     │ │ Loss     │ │ Config       │  │  │
│  │  │ (0.5%)   │ │ (5%)     │ │ (3-10%)  │ │ (1% buffer)  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │            Position Size Calculation                          │  │
│  │                                                               │  │
│  │   Position Size = min(                                      │  │
│  │     AccountRisk / RiskPerShare,          ← Risk-based        │  │
│  │     MaxPositionValue / EntryPrice,         ← Position cap      │  │
│  │     AvailableCash / EntryPrice           ← Cash limit         │  │
│  │   )                                                           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Risk Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade_pct` | 0.5% | Max loss per trade |
| `max_position_pct` | 5% | Max position size |
| `min_position_pct` | 0.5% | Min position size |
| `daily_loss_limit_pct` | 2% | Stop trading if exceeded |
| `min_stop_distance_pct` | 3% | Minimum stop distance |
| `max_stop_distance_pct` | 10% | Maximum stop distance |

### 4. Stage 2 Scoring System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    STAGE 2 SCORING (8 Points)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Current Price > 150 SMA (1 pt)                                    │
│   Current Price > 200 SMA (1 pt)                                    │
│   50 SMA > 150 SMA (1 pt)                                           │
│   150 SMA > 200 SMA (1 pt)                                          │
│   200 SMA Rising (1 pt)                                             │
│   Price within +25% of 52-week low (1 pt)                         │
│   Price within +25% of 52-week high (1 pt)                          │
│   RS Rating > 80 vs SPY (1 pt)                                       │
│                                                                     │
│   Score: 0-8 → Stage 0 (Not in Stage 2)                           │
│   Score: 6-7 → Stage 2 with penalty                                 │
│   Score: 8/8 → Full Stage 2                                         │
│                                                                     │
│   Entry Score (Max 100):                                            │
│   - Stage 2 Score: 30 pts                                           │
│   - Risk %: 30 pts                                                  │
│   - Distance to Pivot: 25 pts                                       │
│   - Volume Ratio: 15 pts                                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5. Backtesting Engine

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKTEST ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐              │
│   │   Data      │   │   Strategy  │   │  Execution  │              │
│   │   Provider  │──▶│   Engine    │──▶│   Model     │              │
│   └─────────────┘   └─────────────┘   └─────────────┘              │
│          │                 │                 │                     │
│          ▼                 ▼                 ▼                     │
│   ┌─────────────────────────────────────────────────────────┐       │
│   │                    backtest/                             │       │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │       │
│   │  │engine.py   │  │strategy.py │  │data_provider.py    │  │       │
│   │  │(simulate)  │  │(signals)   │  │(Alpaca/yfinance)  │  │       │
│   │  └────────────┘  └────────────┘  └────────────────────┘  │       │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │       │
│   │  │state.py    │  │execution.py│  │report.py           │  │       │
│   │  │(positions) │  │(fills)     │  │(results/analytics)  │  │       │
│   │  └────────────┘  └────────────┘  └────────────────────┘  │       │
│   └─────────────────────────────────────────────────────────┘       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Backtest Flow:**
1. `data_provider.py` - Fetch historical data from Alpaca/yfinance
2. `strategy.py` - Generate entry/exit signals using Stage 2 logic
3. `engine.py` - Simulate day-by-day execution
4. `execution.py` - Model fills (slippage, partial fills)
5. `state.py` - Track positions, cash, P&L
6. `report.py` - Generate metrics (Sharpe, drawdown, win rate)

### 6. Rate Limiting & Resilience

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER & CIRCUIT BREAKER                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                  rate_limiter.py                             │  │
│   │                                                               │  │
│   │   ┌───────────────┐      ┌───────────────┐                   │  │
│   │   │  RateLimiter  │      │APIHealthMonitor│                   │  │
│   │   │               │      │                │                   │  │
│   │   │ • Window:     │      │ • Track        │                   │  │
│   │   │   200 req/60s │      │   failures     │                   │  │
│   │   │ • Backoff:    │      │ • Fallback     │                   │  │
│   │   │   exp         │      │   to yfin      │                   │  │
│   │   │ • Circuit:    │      │ • Health       │                   │  │
│   │   │   5 errors    │      │   status       │                   │  │
│   │   └───────────────┘      └───────────────┘                   │  │
│   │                                                               │  │
│   │   Request Flow:                                              │  │
│   │   1. can_make_request()? → Check window                      │  │
│   │   2. record_request()    → Track in window                   │  │
│   │   3. record_success()    → Reduce backoff                   │  │
│   │   4. record_error()      → Increase backoff                 │  │
│   │                                                               │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flows

### Real-Time Trading Flow

```
Market Hours (9:30-16:00 ET)
│
├─▶ WebSocket receives price updates
│   ├─▶ Price cache updated
│   ├─▶ Exit engine evaluates positions
│   └─▶ Entry engine evaluates watchlist
│
├─▶ Entry signal triggered
│   ├─▶ Risk config validates position size
│   ├─▶ Stop calculated (ATR + MA support)
│   └─▶ Order submitted via OrderManager
│
├─▶ Exit signal triggered
│   ├─▶ OrderManager cancels open orders
│   └─▶ Position closed, P&L recorded
│
└─▶ End of day
    ├─▶ State saved to portfolio.json
    └─▶ Stats logged
```

### Analysis Flow

```
Pre-Market (6:00-9:30 ET)
│
├─▶ premarket_report.py
│   ├─▶ Fetch futures data
│   ├─▶ Fetch VIX
│   └─▶ Generate HTML report
│
├─▶ entry_signals.py
│   ├─▶ Load watchlist
│   ├─▶ Calculate Stage 2 scores
│   ├─▶ Filter by tier
│   └─▶ Output actionable tickers
│
└─▶ Watchlist review
    └─▶ Manual inspection of A-tier setups
```

## File Organization

```
trader/
├── scripts/                    # Entry points (CLI tools)
│   ├── entry_signals.py       # Main scanner
│   ├── paper_engine_alpaca.py # Trading engine
│   ├── premarket_report.py    # Morning report
│   ├── postmarket_report.py   # Evening report
│   ├── backtest.py           # Backtesting
│   ├── watchlist_manager.py  # Watchlist CRUD
│   └── ...
│
├── traderlib/                 # Core library (reusable)
│   ├── alpaca_client.py      # API client
│   ├── paper_state.py        # Position tracking
│   ├── paper_exits.py        # Exit calculations
│   ├── order_manager.py      # Order lifecycle
│   ├── risk_config.py        # Risk parameters
│   ├── stage2_utils.py       # Scoring algorithms
│   ├── rate_limiter.py       # API resilience
│   ├── market_hours.py       # Calendar
│   ├── validation.py         # Input validation
│   └── backtest/             # Backtest engine
│       ├── engine.py
│       ├── strategy.py
│       ├── data_provider.py
│       ├── execution.py
│       ├── state.py
│       └── report.py
│
├── data/                      # Runtime data
│   ├── watchlist.csv         # User watchlist
│   ├── portfolio.json        # Open positions
│   ├── daily_tracker.json    # Daily stats
│   └── ticker_sectors_cache.json
│
├── config/                    # Configuration
│   ├── risk_config.yaml      # Risk profiles
│   ├── scraper_config.yaml   # Scraper settings
│   └── secrets/              # API credentials
│       └── alpaca_config.json
│
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md       # This file
│   ├── getting-started.md    # Onboarding
│   ├── RISK_GUIDE.md         # Risk docs
│   ├── BACKTESTING_GUIDE.md  # Backtest docs
│   └── runbooks/             # Troubleshooting
│
├── memory/                    # Session logs
│   └── YYYY-MM-DD.md         # Daily notes
│
├── scans/                     # Output from scanners
├── reports/                   # Generated HTML reports
└── tests/                     # Test suite
```

## External Integrations

| Service | Purpose | Module |
|---------|---------|--------|
| Alpaca Markets | Trading API | `alpaca_client.py` |
| Yahoo Finance | Historical data (reports) | `yfinance` (external) |
| MC Stock Charts | Screen results | `mcstock_scraper.py` |
| Telegram | Alert delivery | `deliver_report.py` |

## Key Design Patterns

### 1. Triple Constraint System
Position sizing considers three limits simultaneously:
- **Account risk** (0.5% max loss)
- **Position cap** (5% max allocation)
- **Available cash** (prevents over-leverage)

### 2. Dual Stop Calculation
Stop losses use the tighter of:
- **ATR stop** (2x ATR below entry)
- **MA support stop** (clustered MAs - buffer)

### 3. Circuit Breaker Pattern
Rate limiter prevents API bans:
- Track requests in rolling window
- Exponential backoff on errors
- Circuit opens after 5 errors in 60s
- Automatic retry with yfinance fallback

### 4. State Persistence
Portfolio state saved atomically:
- JSON files for positions/stats
- Daily rotation of logs
- Recovery from crash on restart

## Development Guidelines

### Adding a New Script
1. Place in `scripts/` directory
2. Import from `traderlib/` for core logic
3. Add to CLAUDE.md command reference
4. Update README.md if user-facing

### Adding a New Module
1. Place in `traderlib/` directory
2. Follow existing class naming conventions
3. Add tests in `tests/test_<module>.py`
4. Document in ARCHITECTURE.md

### Configuration Changes
1. Update `config/risk_config.yaml` for new profiles
2. Update `RiskConfig` dataclass in `risk_config.py`
3. Add validation in `validation.py`
4. Document in RISK_GUIDE.md

## See Also

- [Getting Started](getting-started.md) - First-time setup
- [Risk Guide](RISK_GUIDE.md) - Risk configuration
- [Backtesting Guide](BACKTESTING_GUIDE.md) - Backtest documentation
- [TOOLS.md](../TOOLS.md) - Tool-specific notes
