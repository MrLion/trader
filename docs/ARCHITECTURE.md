# System Architecture

## Overview

The Trader system is a Python-based momentum trading platform for swing trading stocks using the Stage 2 methodology. It combines real-time trading via Alpaca API with comprehensive analysis tools.

## Unified Exit Action Pattern (ExitAction Migration)

**Status:** Implemented (v0.6.1.0)

### Problem Solved

Prior to v0.6.1.0, exit handling had two separate paths:

1. **Paper engine**: `ExitEngine.evaluate_exit()` returned `ExitSignal` with `should_exit: bool` and optional `new_stop`
2. **Backtest engine**: Called `_update_stops()` separately, then `evaluate_exits()` — lost stop updates

This caused potential divergence between backtest and paper trading stop behavior.

### Solution: ExitAction

Replaced `ExitSignal` with atomic `ExitAction` that has explicit action types:

```python
class ExitActionType(Enum):
    EXIT = "exit"              # Full position exit
    UPDATE_STOP = "update_stop"  # Stop loss update only
    HOLD = "hold"              # No action

@dataclass(frozen=True)
class ExitAction:
    ticker: str
    action: ExitActionType
    reason: str
    exit_price: Optional[float] = None      # For EXIT actions
    r_multiple: float = 0.0                  # Current R multiple
    new_stop_price: Optional[float] = None  # For UPDATE_STOP actions
    new_stop_type: Optional[str] = None     # e.g., 'TRAIL_EMA10', 'BREAKEVEN'
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Exit Hierarchy

1. **Hard stop** (price <= stop) → `EXIT`
2. **Profit target** (2R minimum) → `EXIT`
3. **Trailing stop update** (R threshold + EMA available) → `UPDATE_STOP`
4. **No action needed** → `HOLD`

### Migration Impact

| Component | Before | After |
|-----------|--------|-------|
| `paper_exits.py` | `ExitSignal` with `should_exit` flag | `ExitAction` with explicit action type |
| `paper_engine_alpaca.py` | Check `should_exit`, then check `new_stop` | Switch on `action` enum |
| `backtest/strategy.py` | Return `ExitDecision` list | Return `ExitAction` list |
| `backtest/engine.py` | Separate `_update_stops()` call | Integrated stop updates in exit loop |

### Benefits

1. **Single source of truth**: Exit logic lives in `ExitEngine.evaluate_exit_action()` only
2. **No duplication**: Backtest no longer has separate `_update_stops()` method
3. **Atomic decisions**: EXIT, UPDATE_STOP, or HOLD — no coordination needed
4. **Type safety**: `ExitActionType` enum replaces string literals
5. **Backtest/paper parity**: Identical exit logic in both engines

---

## Strategy Plugin Architecture

**Status:** Implemented (v0.6.1.0)

### Overview

Unified Strategy ABC that works across backtest, paper, and live trading modes with auto-discovery registry for pluggable strategies.

### Core Components

```python
# Strategy ABC
class Strategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @abstractmethod
    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        pass
    
    @abstractmethod
    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        pass

# Strategy Context
@dataclass
class StrategyContext:
    data_provider: DataFrameProvider  # Protocol for data access
    sim_date: date                    # Backtest: simulation date; Paper: today
    positions: Dict[str, Position]
    cash: float
    equity: float
    risk_config: Optional[RiskConfig]
    
    # Helper methods (delegated to data_provider)
    def get_bars(self, ticker: str, lookback_days: int = 200) -> Optional[pd.DataFrame]
    def get_current_price(self, ticker: str) -> Optional[float]
```

### Strategy Registry

Strategies auto-register via decorator:

```python
STRATEGY_REGISTRY: Dict[str, Type[Strategy]] = {}

def register_strategy(name: str):
    """Decorator to auto-register strategy classes."""
    
# Usage
@register_strategy('vcp_large_cap')
class VCPBreakoutStrategy(Strategy):
    ...

# Retrieve strategy
strategy = get_strategy('vcp_large_cap')
```

### Composite Strategy

Run multiple strategies together with configurable modes:

```python
class CompositeStrategy(Strategy):
    """Run multiple strategies together.
    
    Modes:
    - 'union' (OR): Enter if ANY strategy signals
    - 'intersection' (AND): Enter only if ALL strategies agree
    """
```

**Exit Conflict Resolution:**
1. Any `EXIT` → EXIT (safety first)
2. All `HOLD` → HOLD
3. Multiple `UPDATE_STOP` → Tightest stop wins (highest for long positions)

### Data Isolation Principle

**Backtest Data Isolation:** Backtest code must NOT import yfinance. All data must be provided via `DataFrameProvider`:

```python
# Correct: Uses provided data
def _get_sector(self, ticker: str) -> str:
    # Uses watchlist_df sector column, returns 'Unknown' if not available
    return 'Unknown'

# Incorrect: Network call during backtest
import yfinance as yf  # NOT ALLOWED in backtest code
```

---

## MA Convergence Detection

**Status:** Implemented (v0.6.1.0)

### Overview

MA convergence scoring system (0-100) that quantifies the quality of moving average clustering below price. Used by Trend Screener to identify stocks with optimal support zones.

### Scoring Components (100 points total)

| Component | Max Points | Description |
|-----------|------------|-------------|
| Tightness | 30 | Inverse of cluster spread (tighter = better) |
| Cluster Size | 25 | Number of MAs in cluster (more = better) |
| Price Distance | 15 | How close price is to cluster (closer = better) |
| Risk Improvement | 30 | Stop improvement vs ATR-only stop |

### Return Structure

```python
def calculate_convergence_score(current_price: float, s2_details: dict) -> dict:
    """Returns:
    {
        'score': int,  # 0-100
        'components': {
            'tightness': 0-30,
            'cluster_size': 0-25,
            'price_distance': 0-15,
            'risk_improvement': 0-30
        },
        'cluster_data': {
            'cluster_mas': ['ma10', 'ma20', 'ma50', ...],
            'cluster_size': int,
            'cluster_spread_pct': float,
            'lowest_ma': str
        },
        'ma_support_stop': float,  # Alternative stop based on MA cluster
        'atr_risk_pct': float,     # Risk % using ATR stop
        'ma_risk_pct': float       # Risk % using MA support stop
    }
    """
```

### Cluster Detection Algorithm

1. Collect all MAs below current price (ma10, ma20, ma50, ma100, ma200)
2. Require minimum 2 MAs to form valid cluster
3. Check cluster spread: (highest_ma - lowest_ma) / highest_ma ≤ 5%
4. Calculate stop at lowest_ma × (1 - buffer_pct) where buffer = 1%

### Integration Points

- **Trend Screener**: Ranks stocks by convergence score
- **MA Support Stop**: Dual risk parameter uses max(ATR stop, MA support stop)
- **Entry Scoring**: Convergence score contributes to overall entry readiness

---

## VCP Pattern Detection

**Status:** Implemented (v0.6.1.0)

### Overview

Volatility Contraction Pattern (VCP) detection based on Minervini/O'Neil methodology. Identifies stocks with proper contraction progression and volume drying up.

### Core Data Structures

```python
@dataclass
class SwingPoint:
    """A swing high or low point."""
    type: str  # 'high' or 'low'
    price: float
    date: pd.Timestamp
    idx: int

@dataclass
class Contraction:
    """A single contraction within a VCP pattern."""
    start_idx: int
    end_idx: int
    high: float
    low: float
    depth_pct: float  # (high - low) / high * 100
    volume_avg: float
    volume_ratio: float  # vs 50-day average

@dataclass
class VCPPattern:
    """Complete VCP pattern detection result."""
    valid: bool
    contractions: List[Contraction]
    pivot_high: float
    stop_low: float
    total_depth: float
    progression_valid: bool  # Each contraction < 70% of prior
    volume_declining: bool
```

### Detection Algorithm

1. **Swing Detection**: Find local highs/lows using 5% reversal threshold
2. **Contraction Identification**: Measure depth from each swing high to subsequent low
3. **Progression Validation**: Each contraction must be < 70% depth of prior
4. **Volume Analysis**: Check for declining volume through contractions
5. **Pivot/Stop Definition**: Identify pivot high (entry trigger) and stop low (failure point)

### Valid Pattern Criteria

- Minimum 2 contractions
- Contraction progression: each < 70% of prior depth
- Volume declining through pattern
- Price near pivot high (within 1-5%)

### Usage

```python
from traderlib.vcp_utils import detect_vcp_pattern

pattern = detect_vcp_pattern(df, min_contractions=2)
if pattern.valid:
    print(f"VCP detected: pivot at ${pattern.pivot_high}, stop at ${pattern.stop_low}")
```

---

## Strategy Implementations

### Stage2MomentumStrategy

Default momentum strategy using Stage 2 scoring system.

| Feature | Description |
|---------|-------------|
| Entry Criteria | Stage 2 score ≥ 5, entry score ≥ 60 |
| Stop Calculation | Dual: max(ATR stop, MA support stop) |
| Position Sizing | Triple constraint (account risk, position cap, cash) |
| Exit Logic | Delegated to ExitEngine.evaluate_exit_action() |

### VCPBreakoutStrategy

VCP breakout strategy with configurable profiles.

| Profile | Dollar Volume | Min Shares |
|---------|---------------|------------|
| Large-cap | $80M+ | 1M+ |
| High-octane | $20M+ | 400K+ |

---

## Migration Guide

### Migrating to ExitAction (v0.6.1.0)

If you have custom strategies or exit logic, update as follows:

**Before (ExitSignal):**
```python
from traderlib.paper_exits import ExitSignal

def evaluate_exit(self, position, price):
    if price <= position.stop_price:
        return ExitSignal(should_exit=True, reason="STOP_HIT", exit_price=price)
    return ExitSignal(should_exit=False, reason="HOLD", exit_price=price)
```

**After (ExitAction):**
```python
from traderlib.paper_exits import ExitAction, ExitActionType

def evaluate_exit_action(self, position, price):
    if price <= position.stop_price:
        return ExitAction(
            ticker=position.ticker,
            action=ExitActionType.EXIT,
            reason="STOP_HIT",
            exit_price=price
        )
    return ExitAction(
        ticker=position.ticker,
        action=ExitActionType.HOLD,
        reason="HOLD"
    )
```

### Migrating to Strategy ABC (v0.6.1.0)

**Before (backtest-specific):**
```python
from traderlib.backtest.strategy import Strategy

def evaluate_entries(self, sim_date, positions, data_provider, equity):
    # ...
```

**After (unified interface):**
```python
from traderlib.strategies import Strategy, StrategyContext

def evaluate_entries(self, context: StrategyContext):
    # Access data via context
    bars = context.get_bars(context.sim_date)
    price = context.get_current_price(ticker)
    # ...
```

### Backtest Data Isolation

**Breaking Change:** Backtest code can no longer import yfinance. All data must come via `DataFrameProvider`.

**Before:**
```python
import yfinance as yf

def _get_sector(self, ticker):
    return yf.Ticker(ticker).info.get('sector', 'Unknown')
```

**After:**
```python
def _get_sector(self, ticker):
    # Use sector from watchlist_df or return 'Unknown'
    return 'Unknown'
```

For sector data, populate watchlist CSV with `sector` column or use `mc_historical_watchlists.csv` which includes sector information.

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
│   ├── screener_config.yaml   # Scraper settings
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
