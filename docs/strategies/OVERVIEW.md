# Strategy Plugin Architecture

**Module:** `traderlib/strategies/__init__.py`

Unified strategy architecture that works across backtest, paper, and live trading modes with auto-discovery registry for pluggable strategies.

---

## Overview

The strategy plugin system provides a single interface for:
- **Backtesting** — Deterministic, historical simulation
- **Paper trading** — Real-time, simulated execution
- **Live trading** — Real-time, real execution

Strategies auto-register via decorator and can be combined using `CompositeStrategy`.

---

## Core Components

### Strategy ABC

All strategies inherit from the `Strategy` abstract base class:

```python
from traderlib.strategies import Strategy, StrategyContext, EntrySignal, ExitAction

class MyStrategy(Strategy):
    @property
    def name(self) -> str:
        return "my_strategy"
    
    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        """Find entry opportunities."""
        pass
    
    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        """Manage position exits."""
        pass
```

### Required Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `name` | Strategy identifier | `str` |
| `evaluate_entries(context)` | Scan for entry opportunities | `List[EntrySignal]` |
| `manage_exits(context)` | Manage position exits | `List[ExitAction]` |

### Optional Lifecycle Hooks

```python
def on_day_start(self, context: StrategyContext):
    """Called at start of each trading day."""
    pass

def on_day_end(self, context: StrategyContext):
    """Called at end of trading day."""
    pass

def on_market_regime_change(self, old_regime, new_regime, context):
    """Called when market regime changes (BULL ↔ BEAR)."""
    pass

def on_position_opened(self, position, context):
    """Called when a position is opened."""
    pass

def on_position_closed(self, position, pnl, context):
    """Called when a position is closed."""
    pass
```

---

## Strategy Context

`StrategyContext` provides all data and dependencies a strategy needs:

```python
@dataclass
class StrategyContext:
    # Data provider (authoritative source)
    data_provider: DataFrameProvider
    
    # Market data
    sim_date: date                    # Backtest: simulation date; Paper: today
    spy_data: Optional[pd.DataFrame]  # SPY history for RS calculations
    spy_current: Optional[float]      # Current SPY price
    vix_current: Optional[float]      # Current VIX
    
    # Portfolio state
    positions: Dict[str, Any]         # ticker -> Position
    cash: float
    equity: float
    day_pnl: float
    
    # Risk configuration
    risk_config: Optional[RiskConfig]
    execution_config: Optional[Any]
    
    # Helper methods
    def get_bars(self, ticker: str, lookback_days: int = 200) -> Optional[pd.DataFrame]
    def get_current_price(self, ticker: str) -> Optional[float]
```

### Usage Example

```python
def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
    # Get historical data
    hist = context.get_bars('AAPL', lookback_days=200)
    
    # Get current price
    price = context.get_current_price('AAPL')
    
    # Access portfolio state
    current_positions = context.positions
    available_cash = context.cash
    
    # Calculate signals using your logic
    if self._is_breakout(hist, price):
        return [EntrySignal(ticker='AAPL', entry_price=price, ...)]
    
    return []
```

---

## Signal Dataclasses

### EntrySignal

```python
@dataclass(frozen=True)
class EntrySignal:
    ticker: str
    side: str = 'LONG'
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    shares: int = 0
    sector: str = 'Unknown'
    entry_score: int = 0
    stage2_score: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ExitAction

```python
@dataclass(frozen=True)
class ExitAction:
    ticker: str
    action: ExitActionType  # EXIT, UPDATE_STOP, or HOLD
    reason: str
    exit_price: Optional[float] = None
    r_multiple: float = 0.0
    new_stop_price: Optional[float] = None
    new_stop_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### ExitActionType

```python
class ExitActionType(Enum):
    EXIT = "exit"              # Full position exit
    UPDATE_STOP = "update_stop"  # Stop loss update only
    HOLD = "hold"              # No action
```

---

## Strategy Registry

Strategies auto-register via decorator:

```python
from traderlib.strategies import register_strategy, get_strategy, list_strategies

@register_strategy('my_strategy')
class MyStrategy(Strategy):
    ...

# Retrieve strategy
strategy = get_strategy('my_strategy', risk_config=config)

# List all registered strategies
available = list_strategies()
print(available)  # ['my_strategy', 'vcp_large_cap', 'vcp_high_octane', ...]
```

### Registered Strategies

| Strategy | Description | Profile |
|----------|-------------|---------|
| `vcp_large_cap` | VCP breakout for large-cap stocks | $80M+ dollar volume |
| `vcp_high_octane` | VCP breakout for momentum stocks | $20M+ dollar volume |
| `composite` | Combine multiple strategies | Union/Intersection modes |

---

## Composite Strategy

Run multiple strategies together with configurable modes:

```python
from traderlib.strategies import CompositeStrategy

# Union mode: Enter if ANY strategy signals
composite = CompositeStrategy(
    strategies=[vcp_strategy, momentum_strategy],
    mode='union'
)

# Intersection mode: Enter only if ALL strategies agree
composite = CompositeStrategy(
    strategies=[vcp_strategy, momentum_strategy],
    mode='intersection'
)
```

### Entry Combination Logic

| Mode | Behavior | Use Case |
|------|----------|----------|
| `union` | Deduplicate by ticker, keep highest score | Broader opportunity set |
| `intersection` | Only tickers where ALL strategies signal | Higher conviction trades |

### Exit Conflict Resolution

When multiple strategies manage the same position:

1. **EXIT wins** — Safety first (any EXIT → EXIT)
2. **Tightest stop wins** — For multiple UPDATE_STOP, highest stop price wins (for longs)
3. **HOLD** — If no action needed

```python
# Exit resolution example:
# Strategy A: UPDATE_STOP to $150
# Strategy B: UPDATE_STOP to $152
# Result: UPDATE_STOP to $152 (tighter/more conservative)
```

---

## Usage Examples

### Paper Trading

```bash
# Run paper engine with VCP strategy
python3 scripts/paper_engine_alpaca.py --strategy vcp_large_cap

# Run with high-octane profile
python3 scripts/paper_engine_alpaca.py --strategy vcp_high_octane
```

### Backtesting

```bash
# Backtest VCP strategy
python3 scripts/backtest.py --strategy vcp_large_cap --start 2024-01-01 --end 2025-01-01

# Backtest composite strategy
python3 scripts/backtest.py --strategy composite --start 2024-01-01 --end 2025-01-01
```

### Custom Strategy

```python
# custom_strategy.py
from traderlib.strategies import Strategy, StrategyContext, EntrySignal, ExitAction, register_strategy

@register_strategy('my_custom_strategy')
class MyCustomStrategy(Strategy):
    @property
    def name(self) -> str:
        return "my_custom_strategy"
    
    def evaluate_entries(self, context: StrategyContext) -> List[EntrySignal]:
        # Your entry logic here
        return []
    
    def manage_exits(self, context: StrategyContext) -> List[ExitAction]:
        # Your exit logic here
        return []

# Usage
python3 scripts/paper_engine_alpaca.py --strategy my_custom_strategy
```

---

## Data Isolation Principle

**Backtest Data Isolation:** Backtest code must NOT import yfinance. All data must be provided via `DataFrameProvider`:

```python
# Correct: Uses provided data
def _get_sector(self, ticker: str) -> str:
    # Uses watchlist_df sector column, returns 'Unknown' if not available
    return 'Unknown'

# Incorrect: Network call during backtest
import yfinance as yf  # NOT ALLOWED in backtest code
```

This ensures:
- Deterministic backtests (no network calls)
- Reproducible results
- Fast execution (cached data)

---

## Configuration

Strategy parameters in `config/risk_config.yaml`:

```yaml
vcp:
  large_cap:
    min_dollar_volume: 80000000
    min_share_volume: 1000000
    contraction_ranges: [[15, 25], [8, 12], [3, 8]]
    volume_dry_up_threshold: 0.60
    breakout_volume_min: 1.4
    max_pivot_proximity_pct: 5.0
    
  high_octane:
    min_dollar_volume: 20000000
    min_share_volume: 400000
    contraction_ranges: [[30, 35], [15, 15], [3, 6]]
    volume_dry_up_threshold: 0.50
    breakout_volume_min: 2.0
    max_pivot_proximity_pct: 5.0
```

---

## ExitAction Migration

**Status:** Implemented (v0.6.1.0)

The `ExitAction` pattern replaced the older `ExitSignal` pattern:

| Before (ExitSignal) | After (ExitAction) |
|---------------------|--------------------|
| `should_exit: bool` flag | Explicit `action: ExitActionType` |
| Separate stop update logic | Atomic `UPDATE_STOP` action |
| Coordination needed | Type-safe enum |

### Migration Example

**Before:**
```python
def evaluate_exit(self, position, price):
    if price <= position.stop_price:
        return ExitSignal(should_exit=True, reason="STOP_HIT")
    return ExitSignal(should_exit=False, reason="HOLD")
```

**After:**
```python
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

See [docs/ARCHITECTURE.md](../ARCHITECTURE.md#unified-exit-action-pattern) for full migration guide.

---

## Related Documentation

- [VCP_BREAKOUT.md](VCP_BREAKOUT.md) — VCP breakout strategy details
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — System architecture, ExitAction pattern
- [../BACKTESTING_GUIDE.md](../BACKTESTING_GUIDE.md) — Backtesting with strategies
- [traderlib/strategies/__init__.py](../../traderlib/strategies/__init__.py) — Source code
