# VCP Breakout Strategy

**Module:** `traderlib/strategies/vcp_breakout.py`

VCP (Volatility Contraction Pattern) breakout strategy with large-cap and high-octane profiles.

---

## Overview

The VCP Breakout strategy identifies stocks undergoing volatility contraction and enters on breakout above the pivot price. Based on Minervini/O'Neil methodology.

**Philosophy:**
- Supply is absorbed through progressive contractions
- Volume dries up as sellers exhaust
- Breakout on heavy volume signals institutional buying
- Tight stops possible due to defined support

---

## Strategy Profiles

Two profiles tuned for different stock types:

### Large-Cap Profile

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Min Dollar Volume | $80M+ | Institutional liquidity |
| Min Share Volume | 1M+ | Adequate float turnover |
| Contraction Ranges | 15-25% → 8-12% → 3-8% | Typical large-cap volatility |
| Volume Dry-up | < 60% of average | Moderate drying up |
| Breakout Volume | 1.4x average | Confirmation threshold |
| Trailing EMA | 20-period | Wider trail for stability |

**Best for:** MSFT, AAPL, NVDA, GOOGL — stable, liquid names

### High-Octane Profile

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Min Dollar Volume | $20M+ | More names in universe |
| Min Share Volume | 400K+ | Accepts smaller floats |
| Contraction Ranges | 30-35% → 15% → 3-6% | Deeper initial contraction |
| Volume Dry-up | < 50% of average | More aggressive drying up |
| Breakout Volume | 2.0x average | Higher confirmation bar |
| Trailing EMA | 10-period | Tighter trail for volatility |

**Best for:** Growth names, momentum stocks, smaller caps

---

## Entry Logic

### Step 1: VCP Detection

```python
from traderlib.vcp_utils import detect_vcp_pattern

pattern = detect_vcp_pattern(hist, min_contractions=2)

if not pattern.valid:
    return None  # No valid VCP pattern
```

### Step 2: Proximity Check

```python
# Must be near pivot for entry
distance_pct = abs(current_price - pattern.pivot_high) / pattern.pivot_high * 100

if distance_pct > params['max_pivot_proximity_pct']:  # 5%
    return None  # Too extended or too far below
```

### Step 3: Volume Confirmation

```python
# Breakout day volume must exceed threshold
volume_ratio = current_volume / volume_50d_avg

if volume_ratio < params['breakout_volume_min']:  # 1.4x or 2.0x
    return None  # No institutional confirmation
```

### Step 4: Convergence Score Check

```python
from traderlib.stage2_utils import calculate_convergence_score

convergence = calculate_convergence_score(current_price, s2_details)

if convergence['score'] < params['min_convergence_score']:  # 50
    return None  # MA support not optimal
```

### Step 5: Position Sizing

```python
from traderlib.risk_config import calculate_position_size_with_constraints

shares, risk_pct = calculate_position_size_with_constraints(
    equity=context.equity,
    entry_price=pattern.pivot_high,
    stop_price=pattern.stop_low,
    risk_config=self.risk_config,
    available_cash=context.cash
)

if shares < params['min_share_volume']:
    return None  # Position too small
```

### Step 6: Generate Signal

```python
return EntrySignal(
    ticker=ticker,
    side='LONG',
    entry_price=pattern.pivot_high,
    stop_price=pattern.stop_low,
    target_price=pattern.pivot_high * 1.10,  # 10% initial target
    shares=shares,
    sector=self._get_sector(ticker),
    entry_score=convergence['score'],
    stage2_score=stage2['score'],
    metadata={
        'vcp_pattern': pattern,
        'convergence': convergence,
        'volume_ratio': volume_ratio,
        'phase': len(pattern.contractions)
    }
)
```

---

## Exit Management

### Initial Stop

Set at VCP pattern failure point:

```python
initial_stop = pattern.stop_low  # Below final contraction
```

### Trailing Logic

The strategy uses EMA-based trailing stops:

```python
# After +1R: Trail at breakeven
if r_multiple >= 1.0:
    return ExitAction(
        action=ExitActionType.UPDATE_STOP,
        new_stop_price=entry_price,
        new_stop_type='BREAKEVEN'
    )

# After +1.5R: Trail at EMA10 (high-octane) or EMA20 (large-cap)
if r_multiple >= 1.5:
    ema_period = self.params['trail_ema_period']  # 10 or 20
    return ExitAction(
        action=ExitActionType.UPDATE_STOP,
        new_stop_price=ema_value,
        new_stop_type=f'TRAIL_EMA{ema_period}'
    )

# After +2R: Profit target reached
if r_multiple >= 2.0:
    return ExitAction(
        action=ExitActionType.EXIT,
        reason='PROFIT_TARGET_2R'
    )
```

### Phase 2+ Trailing

For patterns with 3+ contractions (Phase 2+):

```python
# More aggressive trailing for mature patterns
if len(pattern.contractions) >= 3 and r_multiple >= self.params['phase2_start_r']:
    return ExitAction(
        action=ExitActionType.UPDATE_STOP,
        new_stop_price=ema_value,
        new_stop_type='TRAIL_EMA10_AGGRESSIVE'
    )
```

---

## Configuration

Parameters in `config/risk_config.yaml`:

```yaml
vcp:
  large_cap:
    min_dollar_volume: 80000000
    min_share_volume: 1000000
    contraction_ranges:
      - [15, 25]   # First contraction depth
      - [8, 12]    # Second contraction
      - [3, 8]     # Third contraction
    volume_dry_up_threshold: 0.60
    breakout_volume_min: 1.4
    trail_ema_period: 20
    phase2_start_r: 2.0
    max_pivot_proximity_pct: 5.0
    min_convergence_score: 50
    
  high_octane:
    min_dollar_volume: 20000000
    min_share_volume: 400000
    contraction_ranges:
      - [30, 35]
      - [15, 15]
      - [3, 6]
    volume_dry_up_threshold: 0.50
    breakout_volume_min: 2.0
    trail_ema_period: 10
    phase2_start_r: 2.0
    max_pivot_proximity_pct: 5.0
    min_convergence_score: 50
```

---

## Usage

### Paper Trading

```bash
# Large-cap VCP breakouts
python3 scripts/paper_engine_alpaca.py --strategy vcp_large_cap

# High-octane VCP breakouts
python3 scripts/paper_engine_alpaca.py --strategy vcp_high_octane
```

### Backtesting

```bash
# Backtest large-cap profile
python3 scripts/backtest.py --strategy vcp_large_cap \
  --start 2024-01-01 --end 2025-01-01 --capital 100000

# Backtest high-octane profile
python3 scripts/backtest.py --strategy vcp_high_octane \
  --start 2024-01-01 --end 2025-01-01 --capital 100000

# Compare profiles
python3 scripts/backtest.py --strategy vcp_large_cap --csv results/large_cap.csv
python3 scripts/backtest.py --strategy vcp_high_octane --csv results/high_octane.csv
```

### Discovery Mode

```bash
# Find VCP candidates in market
python3 scripts/trend_screener.py --profile large-cap --detect-vcp --top 30

# Analyze specific VCP candidate
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp --show-ma-data
```

---

## Performance Metrics

Expected characteristics (varies by market conditions):

| Metric | Large-Cap | High-Octane |
|--------|-----------|-------------|
| Win Rate | 45-55% | 40-50% |
| Avg Winner | 2.5R | 3.0R |
| Avg Loser | 1.0R | 1.0R |
| Profit Factor | 1.5-2.0 | 1.4-1.8 |
| Trades/Month | 5-10 | 10-20 |
| Max Drawdown | 10-15% | 15-20% |

**Note:** Past performance does not guarantee future results.

---

## Risk Management

### Position Sizing

Triple-constraint system:

```python
# 1. Account risk constraint
risk_shares = int((equity * risk_per_trade_pct) / (entry - stop))

# 2. Position cap constraint
max_shares = int((equity * max_position_pct) / entry)

# 3. Cash constraint
cash_shares = int(available_cash / entry)

# Final: minimum of all three
shares = min(risk_shares, max_shares, cash_shares)
```

### Stop Loss

- **Initial:** VCP pattern failure point (below final contraction)
- **Breakeven:** +1R achieved
- **Trailing:** EMA10/EMA20 after +1.5R
- **Target:** 2R minimum, trailed after

### Position Limits

```yaml
account:
  max_sector_positions: 10      # Max 10 positions per sector
  max_entries_per_day: 10       # Max 10 new entries per day
  
position:
  max_position_pct: 10          # Max 10% in single position
  min_position_pct: 5           # Min 5% allocation
```

---

## Pattern Phases

| Phase | Contractions | Typical Depth | Action |
|-------|--------------|---------------|--------|
| **Phase 1** | 1 | 15-25% (large), 30-35% (high-oct) | Watch |
| **Phase 2** | 2 | 8-12% (large), 15% (high-oct) | Prepare |
| **Phase 3** | 3+ | 3-8% (large), 3-6% (high-oct) | Ready |

**Phase 2+** patterns get more aggressive trailing (EMA10 vs EMA20).

---

## Examples

### Valid Setup

```
NVDA — VCP Breakout Setup
  Profile: large-cap
  Price: $125.40
  Pivot: $126.50 (1% away)
  Stop: $118.20 (6% risk)
  
  Contractions: 3
  Depths: 22% → 11% → 5% ✓
  Volume: Drying up ✓
  Convergence: 85 (Grade A) ✓
  
  Action: BUY above $126.50 on 1.4x+ volume
```

### Invalid Setup (Extended)

```
AAPL — Extended from Pivot
  Price: $185.00
  Pivot: $175.00
  Distance: +5.7% (too extended)
  
  Action: WAIT for pullback or new base
```

### Invalid Setup (Poor Volume)

```
TSLA — No Volume Confirmation
  Breakout Volume: 1.1x (need 2.0x for high-octane)
  
  Action: WAIT for volume confirmation
```

---

## Troubleshooting

### No Signals Generated

**Possible causes:**
- Market conditions not favorable (check SPY trend)
- Universe too restrictive (try high-octane profile)
- Volume thresholds too high (adjust `breakout_volume_min`)
- No valid VCP patterns in current market

**Solutions:**
```bash
# Check market regime
python3 scripts/premarket_report.py

# Try high-octane profile
python3 scripts/paper_engine_alpaca.py --strategy vcp_high_octane

# Lower volume threshold in config
# Edit config/risk_config.yaml: vcp.high_octane.breakout_volume_min
```

### Too Many False Breakouts

**Possible causes:**
- Volume confirmation too low
- Pivot proximity too loose
- Market in distribution

**Solutions:**
```bash
# Increase breakout volume requirement
# Edit config/risk_config.yaml: vcp.large_cap.breakout_volume_min: 1.8

# Tighten pivot proximity
# Edit config/risk_config.yaml: vcp.large_cap.max_pivot_proximity_pct: 3.0
```

### Stops Hit Too Frequently

**Possible causes:**
- Initial stop too tight
- Trailing too aggressive
- Entry timing off (chasing)

**Solutions:**
```bash
# Use conservative profile
python3 scripts/paper_engine_alpaca.py --risk-profile conservative

# Adjust trailing parameters
# Edit config/risk_config.yaml: vcp.large_cap.trail_ema_period: 21
```

---

## Related Documentation

- [OVERVIEW.md](OVERVIEW.md) — Strategy plugin architecture
- [../patterns/VCP.md](../patterns/VCP.md) — VCP pattern detection
- [../trend_screener/USER_GUIDE.md](../trend_screener/USER_GUIDE.md) — Discovery with VCP
- [../RISK_GUIDE.md](../RISK_GUIDE.md) — Risk management
- [traderlib/strategies/vcp_breakout.py](../../traderlib/strategies/vcp_breakout.py) — Source code
