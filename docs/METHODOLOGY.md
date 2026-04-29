# Stage 2 Trading Methodology

## Overview

This document explains the **Stage 2 momentum trading framework** used by the Trader system. Based on Mark Minervini's trend template, Stage 2 identifies stocks in sustained uptrends with institutional accumulation.

A stock in Stage 2 has:
- Price above rising key moving averages
- Proper MA stacking (50 > 100 > 200)
- Strong relative strength vs market
- Tight consolidation patterns (VCP) forming before breakouts

---

## The 10-Point Stage 2 Scoring System

Each stock is scored on 10 criteria. Score range: **0-10 points**.

### Scoring Criteria

| # | Criterion | Points | Description |
|---|-----------|--------|-------------|
| 1 | Price > 20 MA | 1 | Short-term trend positive |
| 2 | Price > 50 MA | 1 | Medium-term trend positive |
| 3 | Price > 100 MA | 1 | Intermediate trend positive |
| 4 | Price > 150 MA | 1 | Long intermediate trend positive |
| 5 | Price > 200 MA | 1 | Long-term trend positive |
| 6 | MA Stacking | 1 | 50 > 100 > 200 (proper order) |
| 7 | Extended MA Stacking | 1 | 50 > 100 > 150 > 200 |
| 8 | 200 MA Rising | 1 | Sustained uptrend (20+ days) |
| 9 | Within 25% of 52W High | 1 | Not extended, room to run |
| 10 | Above 1.25x 52W Low | 1 | Strong recovery from lows |

### Score Interpretation

```
Score: 0-4   → Stage 0 (Not in Stage 2) — Avoid
Score: 5-6   → Stage 2 with penalty — Use caution
Score: 7-8   → Full Stage 2 — Good candidates
Score: 9-10  → Excellent Stage 2 — Ideal candidates
```

### Visual Scoring Example

```
AAPL Stage 2 Analysis (Score: 10/10)
═══════════════════════════════════════════════════════════════

Price: $175.50

Moving Averages:
  20 MA:  $170.25  ✓ (Price above)
  50 MA:  $165.80  ✓ (Price above)
  100 MA: $158.40  ✓ (Price above)
  150 MA: $152.00  ✓ (Price above)
  200 MA: $145.20  ✓ (Price above, rising)

MA Stacking: 50 > 100 > 200 ✓
Extended Stacking: 50 > 100 > 150 > 200 ✓
200 MA Rising (20 days): ✓

52-Week Range:
  High: $185.00
  Low: $125.00
  Current vs High: -5.1% (< 25%) ✓
  Current vs Low: +40.4% (> 25%) ✓

SCORE: 10/10 — Full Stage 2 Compliant
═══════════════════════════════════════════════════════════════
```

---

## Entry Score System (0-100)

Beyond Stage 2 compliance, the system calculates an **entry attractiveness score** to prioritize setups.

The raw component sum is 110 points, but penalties for weakness (below key MAs) are applied immediately, capping the final score at 100.

### Score Components

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Stage 2 Score | 30 | 7-8 pts = 30, 6 pts = 25, 5 pts = 20, etc. |
| Risk % | 30 | < 10% = 30, < 15% = 20, < 20% = 10, < 25% = 5 |
| Distance to Pivot | 25 | Within ±3% = 25, ±5% = 15, ±10% = 5 |
| 6M Return | 15 | > 50% = 15, > 25% = 10 |
| RS vs SPY | 10 | > 20% = 10, > 10% = 5 |

### Penalties

| Condition | Penalty |
|-----------|---------|
| Below 50 MA | -20 points |
| Below 20 MA | -10 points |

### Tier Classification

```
Entry Score ≥60 AND Stage 2 ≥8 → Tier 1 (Actionable now)
Entry Score ≥40 AND Stage 2 ≥6 → Tier 2 (Developing)
Otherwise                        → Tier 3 (Radar only)
```

---

## Stop Loss Calculation

### Dual Stop System

The system uses the **tighter** of two stop calculations:

1. **ATR Stop**: 2x ATR below entry (volatility-based)
2. **MA Support Stop**: Below clustered moving averages (technical support)

### ATR Stop Calculation

```
ATR(14) = Average True Range over 14 days
True Range = max(High - Low, |High - Close_prev|, |Low - Close_prev|)

ATR Stop = Entry Price - (2 × ATR)
```

Example:
```
Entry: $100.00
ATR(14): $2.50
ATR Stop = $100.00 - (2 × $2.50) = $95.00 (5% stop)
```

### MA Support Stop Calculation

When moving averages converge below price, they form a natural support zone. The MA support stop uses this cluster.

**Algorithm:**
```
1. Collect all MAs below current price (10, 20, 50, 100, 150, 200)
2. Require at least 2 MAs in cluster (min_cluster_size)
3. Check spread: (highest - lowest) / highest ≤ 5% (cluster_spread_pct)
4. Stop = lowest_ma × (1 - 1%) (buffer_pct)
```

**Example:**
```
Price: $100.00
MAs below price:
  - 10 MA:  $97.50
  - 20 MA:  $96.80
  - 50 MA:  $95.20
  - 100 MA: $94.10

Cluster: 10, 20 MA ($97.50, $96.80)
Spread: ($97.50 - $96.80) / $97.50 = 0.7% (< 5% ✓)

MA Support Stop = $96.80 × (1 - 0.01) = $95.83
```

### Final Stop Selection

```
Final Stop = max(ATR Stop, MA Support Stop)

Example:
  ATR Stop: $95.00
  MA Support Stop: $95.83
  Final Stop: $95.83 (higher = tighter risk)
```

### Stop Distance Constraints

| Constraint | Value | Purpose |
|------------|-------|---------|
| Minimum | 3% | Prevents oversized positions from tiny stops |
| Maximum | 10% | Rejects wide stops (invalidates risk/reward) |

---

## Position Sizing: Triple Constraint System

Position size is the **minimum** of three constraints:

### Constraint 1: Account Risk

```
Shares = (Account Equity × Risk Per Trade %) / Risk Per Share

Example:
  Equity: $100,000
  Risk Per Trade: 0.5% = $500
  Entry: $100.00
  Stop: $95.00
  Risk Per Share: $5.00
  
  Shares = $500 / $5.00 = 100 shares
  Position Value = $10,000 (10% of equity)
```

### Constraint 2: Position Cap

```
Max Shares = (Account Equity × Max Position %) / Entry Price

Example:
  Equity: $100,000
  Max Position: 5%
  Entry: $100.00
  
  Max Shares = ($100,000 × 0.05) / $100 = 50 shares
  Position Value = $5,000
```

### Constraint 3: Available Cash

```
Max Shares = Available Cash / Entry Price

Example:
  Available Cash: $3,000
  Entry: $100.00
  
  Max Shares = $3,000 / $100 = 30 shares
```

### Final Position Size

```
Shares = min(
    Account Risk Constraint,    # 100 shares
    Position Cap Constraint,    # 50 shares
    Cash Constraint            # 30 shares
)

Final: 30 shares ($3,000 position)
Note: Partial position due to cash limitation
```

### Position Size Rounding

- Shares < 10: Round to nearest integer
- Shares ≥ 10: Round to nearest 10

---

## Exit Management

### Exit Hierarchy

```
1. Hard Stop (initial stop hit)
   ↓
2. Profit Target (2R minimum)
   ↓
3. Trailing Stop (progressive ratcheting)
```

### Trailing Stop Progression

| R Multiple | Action | Stop Location | Mode |
|------------|--------|---------------|------|
| +2R | Move to breakeven | Entry price | Trailing/Hybrid |
| +3R | Begin trailing + sell 33% | 10 EMA | Hybrid only |
| +4R | Sell 50% of remainder | 21 EMA trail | Hybrid only |

**Exit Modes:**
- **Target Mode (Default):** Fixed 2R profit target - simple and consistent
- **Trailing Mode:** Dynamic stops that ratchet up - for trending markets
- **Hybrid Mode:** Scale-out partials + trail remainder - balanced approach

Configure via `profit_target.mode` in your risk config. See RISK_GUIDE.md for details.

### Exit Signals

**Hard Stop Hit:**
```
Current Price: $94.50
Stop Price: $95.00
→ EXIT: STOP_HIT at $94.50
```

**Profit Target Hit:**
```
Target: 2R minimum
Current R: 2.3R
→ EXIT: TARGET_HIT_2.3R
```

**Trailing Stop Update:**
```
At +2R:
  Current Stop: $95.00
  → New Stop: $100.00 (breakeven)

At +3R:
  Current Stop: $100.00
  10 EMA: $103.00
  → New Stop: $103.00 (EMA10)
  → Scale out: sell 33% of position

At +4R:
  Current Stop: $103.00
  21 EMA: $106.00
  → New Stop: $106.00 (EMA21)
  → Scale out: sell 50% of remaining position
```

---

## Entry Protocol

### The 5-Step Entry Checklist

```
1. TRIGGER: Price breaks above pivot
   - Within 1-2% of buy point
   - >3% past pivot = PASS

2. VOLUME: Confirming accumulation
   - Tracking ≥1.5x 50-day average
   - Formula: (volume / min_elapsed) × 390
   - Below avg = PASS or half size

3. MARKET: Regime alignment
   - SPY/QQQ green or ≤0.3% down → proceed
   - Down >0.5% → only if RS independent
   - Bear regime → no longs

4. RISK CALC: Triple constraint sizing
   - Risk/share = Entry - Stop
   - Account risk = 0.5% equity (default)
   - Confirm: position < 5% of equity, sector < 3 positions

5. EXECUTE: Order placement
   - Limit buy order
   - IMMEDIATELY place stop-market
   - Stop goes in BEFORE anything else
```

### Entry Example

```
NVDA Entry Analysis
═══════════════════════════════════════════════════════════════

Setup: VCP Breakout
Pivot: $875.00
Current: $880.50 (0.6% past pivot ✓)

Stage 2 Score: 8/8 (Full compliance)
Entry Score: 72/100 (Tier 1)

Volume Check:
  Current pace: 2.3x 50-day avg ✓
  
Market Context:
  SPY: +0.4% ✓
  QQQ: +0.6% ✓
  Regime: Bull

Risk Calculation:
  Entry: $880.50
  ATR Stop: $850.20 (3.4%)
  MA Support Stop: $858.40 (2.5%)
  Final Stop: $858.40 (max of both)
  Risk/Share: $22.10
  
  Account: $100,000
  Risk: 0.5% = $500
  Position: $500 / $22.10 = 22.6 → 20 shares
  
  Constraint Check:
    - Account risk: 20 shares ✓
    - Position cap: 10% = 10 shares (LIMITING)
    - Available cash: 50 shares
    
  FINAL: 10 shares ($8,805 position, 8.8% of equity)

EXECUTE: Buy 5 NVDA @ $880.50, Stop $858.40
═══════════════════════════════════════════════════════════════
```

---

## Risk Management Rules

### Daily Limits

| Metric | Limit | Action When Hit |
|--------|-------|-----------------|
| Daily Loss | 2% of equity | Halt trading |
| Portfolio Heat | 6% unrealized loss | No new positions |
| Consecutive Stops | 3 | Halve size for next 3 trades |
| Weekly Drawdown | 3% | Halt entries for week |

### Sector Constraints

- **Max 10 positions per GICS sector**
- No longs in sectors with ETF below 50 SMA
- No longs in sectors underperforming SPY (1-month)

### Position Management

**Stops:**
- Set at entry, NEVER moved lower
- Logical levels only (VCP low, MA + buffer, base midpoint)

**Profit Taking:**
- Minimum 2R target
- Trim into strength, not weakness
- Don't sell tight consolidation above rising MAs
- Sell all on climax signals

**Time Exits:**
- No progress 5-8 days → reassess
- Flat within 2% and dead volume → sell
- Exception: tight flag → give up to 15 days

---

## Configuration Reference

### Risk Profiles

| Profile | Risk/Trade | Max Position | Stop Method | Use Case |
|---------|------------|--------------|-------------|----------|
| Default | 0.5% | 10% | atr_or_ma_support | Balanced |
| Conservative | 0.5% | 10% | atr_or_ma_support | Lower volatility |
| Aggressive | 1.0% | 10% | atr_or_ma_support | Higher conviction |
| Tight Stops | 0.5% | 15% | atr_or_support | Pivot-based entries |

### Key Parameters

```yaml
# Account Risk
risk_per_trade_pct: 0.005      # 0.5% of equity per trade
daily_loss_limit_pct: 0.02      # 2% daily stop
max_sector_positions: 10        # Per sector limit

# Position Sizing
max_position_pct: 0.10          # 10% max position
min_position_pct: 0.05          # 5% min position

# Stop Loss
method: "atr_or_ma_support"   # Dual stop calculation
atr_multiplier: 2.0           # 2x ATR
min_stop_distance_pct: 0.03     # 3% minimum
max_stop_distance_pct: 0.10    # 10% maximum

# MA Support
ma_support:
  enabled: true
  buffer_pct: 0.01              # 1% below cluster
  cluster_spread_pct: 0.05      # 5% max spread
  min_cluster_size: 2           # Need 2+ MAs
```

---

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) — System component overview
- [RISK_GUIDE.md](RISK_GUIDE.md) — Risk configuration details
- [AGENTS.md](../../AGENTS.md) — Trading operations & workflow
- [BACKTESTING_GUIDE.md](BACKTESTING_GUIDE.md) — Backtest methodology

---

## References

- Minervini, Mark. *Trade Like a Stock Market Wizard*
- Minervini, Mark. *Think and Trade Like a Champion*
- Stage 2 concept from Stan Weinstein's *Secrets for Profiting in Bull and Bear Markets*
