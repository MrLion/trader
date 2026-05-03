# Configuration Reference

Complete reference for all Trader system configuration options.

---

## Overview

Configuration is managed through YAML files in the `config/` directory:

| File | Purpose |
|------|---------|
| `paper/risk_config.yaml` | Paper risk parameters (default mode) |
| `screener_config.yaml` | Scraper validation thresholds |
| `secrets/alpaca_config.json` | API credentials |

Configuration can be overridden via environment variables and command-line risk profiles.

---

## Risk Configuration

**Default file:** `config/paper/risk_config.yaml`
**Live file:** `config/live/risk_config.yaml`

### Account-Level Risk Settings

```yaml
account:
  risk_per_trade_pct: 0.005       # Max loss per trade (% of equity)
  daily_loss_limit_pct: 0.02      # Halt trading if reached
  max_sector_positions: 3         # Maximum positions per sector
  max_entries_per_day: 10         # Daily entry limit
```

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `risk_per_trade_pct` | 0.5% | 0.1% - 2% | Your "R" - max loss if stop hit |
| `daily_loss_limit_pct` | 2% | 1% - 5% | Circuit breaker for bad days |
| `max_sector_positions` | 3 | 1 - 10 | Sector concentration limit |
| `max_entries_per_day` | 10 | 3 - 20 | Prevents overtrading |

**Example:**
```yaml
# Aggressive account risk
account:
  risk_per_trade_pct: 0.01    # 1% per trade
  daily_loss_limit_pct: 0.03  # 3% daily max
```

---

### Position-Level Risk Settings

```yaml
position:
  max_position_pct: 0.05        # Max position size (% of equity)
  min_position_pct: 0.005       # Min position size (% of equity)
```

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `max_position_pct` | 5% | 3% - 20% | Hard cap on single position |
| `min_position_pct` | 0.5% | 0.1% - 1% | Prevents tiny positions |

**How it works:**
```
Position Size = min(
    (Equity × risk_per_trade_pct) / (Entry - Stop),
    (Equity × max_position_pct) / Entry,
    AvailableCash / Entry
)
```

---

### Stop Loss Configuration

```yaml
stop_loss:
  method: "atr_or_ma_support"   # Stop calculation method
  fixed_pct: 0.07               # For "percent" method
  atr:
    period: 14                  # ATR lookback
    multiplier: 2.0             # 2x ATR below entry
  min_stop_distance_pct: 0.03   # Minimum stop distance
  max_stop_distance_pct: 0.10   # Maximum stop distance
  fallback_pct: 0.07            # Fallback if calculation fails
```

**Methods:**

| Method | Description | Use Case |
|--------|-------------|----------|
| `atr` | 2x ATR below entry | Standard volatility-based |
| `atr_or_support` | max(2x ATR, recent low) | Includes swing lows |
| `atr_or_ma_support` | max(2x ATR, MA cluster) | Tighter technical stops |
| `percent` | Fixed % below entry | Simple, consistent |
| `pivot_based` | Based on pivot levels | VCP breakouts |

**Stop Distance Constraints:**
- **Minimum 3%**: Prevents oversized positions from ultra-tight stops
- **Maximum 10%**: Rejects wide stops that invalidate risk/reward

---

### MA Support Stop Configuration

```yaml
ma_support:
  enabled: true
  buffer_pct: 0.01                # 1% buffer below cluster
  cluster_spread_pct: 0.05        # 5% max spread
  min_cluster_size: 2             # Need 2+ MAs
```

**How MA Support Stops Work:**

1. Collect MAs below current price (10, 20, 50, 100, 200)
2. Require `min_cluster_size` MAs in cluster
3. Check spread: `(highest - lowest) / highest ≤ cluster_spread_pct`
4. Stop = lowest_ma × (1 - buffer_pct)

**Example:**
```
Price: $100
MAs below: 10 MA ($98), 20 MA ($97), 50 MA ($95)
Cluster: 10, 20 MA ($98, $97) — meets min_cluster_size
Spread: ($98 - $97) / $98 = 1% — within 5% limit
Stop: $97 × (1 - 0.01) = $96.03
```

---

### Profit Target Configuration

```yaml
profit_target:
  min_r_multiple: 2.0             # Minimum 2:1 reward/risk
  fallback_target_pct: 0.10       # 10% if R calc fails
  trailing_stops:
    breakeven_at_r: 1.0           # Move to BE at +1R
    ema10_at_r: 1.5               # Trail 10 EMA at +1.5R
    ema21_at_r: 3.0               # Trail 21 EMA at +3R
  ema_periods:
    short: 10                     # Short EMA period
    long: 21                      # Long EMA period
```

**Trailing Progression:**

| R Multiple | Action | Stop Location |
|------------|--------|---------------|
| +1R | Move to breakeven | Entry price |
| +1.5R | Begin trailing | Short EMA |
| +3R | Widen trail | Long EMA |

---

### Entry Score Configuration

```yaml
entry:
  min_entry_score: 60             # Minimum to trigger trade
  max_dist_to_pivot_pct: 2.0      # Max distance from pivot
  min_volume_ratio: 1.5           # Min volume vs 20-day avg
```

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `min_entry_score` | 60 | Tier 1 threshold (0-100 scale) |
| `max_dist_to_pivot_pct` | 2% | Buy within 2% of pivot |
| `min_volume_ratio` | 1.5x | Confirm accumulation |

---

### Market Filter Configuration

```yaml
market:
  max_spy_decline_pct: -0.5       # Max -0.5% SPY decline
  # max_vix: 35                   # Optional VIX cap
```

**Market Filter Rules:**
- SPY down ≤0.3%: Proceed normally
- SPY down 0.3-0.5%: Reduce size
- SPY down >0.5%: No new entries
- VIX >35 (if enabled): No new entries

---

### Re-Entry Cooldown Configuration

```yaml
cooldown:
  reentry_cooldown_minutes: 60    # Wait 1 hour after exit
  min_loss_to_trigger_cooldown_pct: 0.0  # Any loss triggers
  max_cooldown_minutes: 240       # Cap at 4 hours
  consecutive_loss_multiplier: 2.0  # Double after each loss
```

**Purpose:** Prevents FLY-style double losses from immediate re-entry.

**Example progression:**
```
First loss: 60 minute cooldown
Second consecutive loss: 120 minutes
Third consecutive loss: 240 minutes (capped)
```

---

### Cache Configuration

```yaml
cache:
  ttl_seconds: 300                # 5 minute price cache
```

---

## Risk Profiles

Define preset configurations for different trading styles:

```yaml
profiles:
  conservative:
    account:
      risk_per_trade_pct: 0.005    # 0.5%
    position:
      max_position_pct: 0.03       # 3%
    stop_loss:
      max_stop_distance_pct: 0.08  # 8% max
    ma_support:
      enabled: true
      buffer_pct: 0.015            # 1.5% buffer

  aggressive:
    account:
      risk_per_trade_pct: 0.01     # 1%
    position:
      max_position_pct: 0.10       # 10%
    stop_loss:
      max_stop_distance_pct: 0.15  # 15% max
    ma_support:
      enabled: true
      buffer_pct: 0.005            # 0.5% buffer

  tight_stops:
    stop_loss:
      method: "atr_or_support"
      min_stop_distance_pct: 0.02   # 2%
      max_stop_distance_pct: 0.05   # 5%
    position:
      max_position_pct: 0.15         # Larger positions
    ma_support:
      enabled: true
      buffer_pct: 0.01
      cluster_spread_pct: 0.03     # Tighter cluster
      min_cluster_size: 3            # Require 3 MAs
```

**Usage:**
```bash
# Use aggressive profile
python3 scripts/entry_signals.py --risk-profile aggressive

# Use tight stops for pivot entries
python3 scripts/paper_engine_alpaca.py --risk-profile tight_stops
```

---

## Environment Variable Overrides

All risk parameters can be overridden via environment variables:

| Variable | Maps To | Example |
|----------|---------|---------|
| `RISK_ACCOUNT_RISK_PCT` | `account.risk_per_trade_pct` | `0.01` |
| `RISK_POSITION_MAX_PCT` | `position.max_position_pct` | `0.10` |
| `RISK_STOP_MAX_PCT` | `stop_loss.max_stop_distance_pct` | `0.08` |
| `RISK_STOP_MIN_PCT` | `stop_loss.min_stop_distance_pct` | `0.02` |
| `RISK_DAILY_LOSS_PCT` | `account.daily_loss_limit_pct` | `0.03` |

**Usage:**
```bash
export RISK_ACCOUNT_RISK_PCT=0.01
export RISK_POSITION_MAX_PCT=0.08
python3 scripts/entry_signals.py
```

---

## Scraper Configuration

**File:** `config/screener_config.yaml`

```yaml
validation:
  min_price: 10.0                   # Minimum stock price
  min_dollar_volume: 20000000       # $20M minimum daily volume
  max_spread_pct: 0.02              # 2% max bid-ask spread
  max_slippage_pct: 0.01            # 1% max expected slippage

screens:
  minervini:
    min_stage2_score: 6             # Min 6/8 Stage 2 points
    max_extended_pct: 25            # Within 25% of 52W high
    min_rs_rank: 80                 # RS rank ≥80

filters:
  market_cap:
    min: 1000000000                 # $1B minimum
  sector_exclusions:                # Skip these sectors
    - "Energy"
    - "Utilities"
```

---

## API Credentials

**File:** `config/secrets/alpaca_config.json`

```json
{
  "api_key": "PK_...",
  "api_secret": "...",
  "paper": true,
  "base_url": "https://paper-api.alpaca.markets"
}
```

| Field | Description |
|-------|-------------|
| `api_key` | Your Alpaca API key |
| `api_secret` | Your Alpaca API secret |
| `paper` | `true` for paper trading, `false` for live |
| `base_url` | Paper or live endpoint |

**Endpoints:**
- Paper: `https://paper-api.alpaca.markets`
- Live: `https://api.alpaca.markets`

---

## Configuration Loading Priority

Configuration values are loaded in this priority (highest first):

```
1. Environment variables (RISK_*)
2. Command-line --risk-profile
3. Profile overrides in YAML
4. Base config in YAML
5. Hard-coded defaults
```

**Example:**
```yaml
# Base config
account:
  risk_per_trade_pct: 0.005        # 0.5%

# Profile override
profiles:
  aggressive:
    account:
      risk_per_trade_pct: 0.01    # 1.0%
```

With `RISK_ACCOUNT_RISK_PCT=0.015`:
- Final value: 1.5% (env var wins)

With `--risk-profile aggressive` (no env var):
- Final value: 1.0% (profile wins)

With no env var, no profile:
- Final value: 0.5% (base config)

---

## Validation

The system validates configuration on load:

**Errors (prevent startup):**
- Invalid YAML syntax
- Missing required sections
- Negative percentages
- Percentages >100%

**Warnings (allow startup):**
- Unrecognized profile name
- Unknown environment variables
- Extreme values (>3% risk per trade)

---

## See Also

- [METHODOLOGY.md](METHODOLOGY.md) — Trading framework explanation
- [RISK_GUIDE.md](../RISK_GUIDE.md) — Risk management deep dive
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System architecture
