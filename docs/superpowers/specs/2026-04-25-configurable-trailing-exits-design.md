# Configurable Trailing Exit Strategies

## Overview
Design a YAML-configurable exit system that lets winning trades run with dynamically adjusting trailing stops, replacing the current fixed 2R profit target system.

---

## Motivation

The current system takes profit at fixed 2R minimum targets (e.g., AMD Apr 20 trade exited at 2.8R for +$1,114, but could have captured more with a trailing approach). This design enables backtesting of various trailing stop strategies to optimize for extended trends.

---

## Goals

1. **Let winners run** — No fixed profit targets; exit on trailing stop breach
2. **Protect capital** — Move to breakeven at +2R
3. **Progressive tightening** — Trail with tighter MAs early, wider MAs later
4. **Configurable via YAML** — Backtest different strategies without code changes
5. **Compatible with scale-out** — Option to sell partial positions at R-levels

---

## Proposed Approaches

### Approach A: Stage-Based Trailing (Recommended)

Explicit stages trigger stop adjustments at R-multiple thresholds.

```yaml
exit:
  mode: "trailing"  # vs "target" for current system
  
  stages:
    - trigger_r: 2.0
      action: "move_stop_to"
      stop_price: "breakeven"
      
    - trigger_r: 3.0
      action: "trail_with"
      method: "ema"
      period: 10
      
    - trigger_r: 5.0
      action: "trail_with"
      method: "ema"
      period: 20
      
    - trigger_r: 8.0
      action: "trail_with"
      method: "swing_low"
```

**Pros:** Clear, explicit, easy to backtest permutations  
**Cons:** Discrete steps vs smooth transitions

### Approach B: Continuous Trailing

Smooth band transitions with configurable width.

```yaml
exit:
  mode: "trailing"
  breakeven_at_r: 2.0
  trail_activation_r: 2.5
  
  trail_bands:
    - from_r: 2.5
      to_r: 4.0
      method: "atr_multiple"
      atr_mult: 1.5
      
    - from_r: 4.0
      to_r: 6.0
      method: "ema10"
      
    - from_r: 6.0
      method: "ema21"
```

**Pros:** Handles gradual transitions  
**Cons:** More complex configuration

### Approach C: Hybrid Scale-Out + Trail

Combines partial profit-taking with trailing remaining position.

```yaml
exit:
  mode: "hybrid"
  
  stages:
    - trigger_r: 2.0
      action: "move_stop"
      stop_price: "breakeven"
      
  scale_out:
    enabled: true
    steps:
      - trigger_r: 3.0
        fraction: 0.33  # Sell 1/3
      - trigger_r: 4.0
        fraction: 0.50  # Sell 1/2 of remaining
        
  trailing_stop:
    - trigger_r: 3.0
      method: "ema"
      period: 10
      apply_to: "remaining"
```

**Pros:** Most flexible  
**Cons:** More code paths

---

## Design Decisions

### 1. R-Multiple as Trigger

All triggers based on R-multiple (current gain / initial risk) — universal across different priced stocks.

### 2. Stop Never Moves Lower

Trailing stops only ratchet up, never down. Protects against volatility giving back gains.

### 3. Method Options

| Method | Description | Best For |
|--------|-------------|----------|
| `breakeven` | Move stop to entry price | Protecting capital |
| `ema` | Trail below N-period EMA | Trend following |
| `swing_low` | Trail below recent swing low | Volatile stocks |
| `atr_multiple` | Trail at Nx ATR below price | Custom width |
| `fixed_pct` | Trail at fixed % below price | Simple rules |

### 4. Configuration Location

- Per-strategy: `config/strategies/<strategy>.yaml`
- Global default: `config/risk_config.yaml` (for strategies without explicit exit config)

---

## Example: AMD Apr 9 Trade

With user-preferred strategy:

| Stage | Trigger | Action | Stop Location |
|-------|---------|--------|---------------|
| Entry | — | Initial stop | $217.81 (ATR-based) |
| Breakeven | 2.0R ($252.48) | Move stop | $229.33 (entry) |
| Early trail | 3.0R ($263.89) | Trail 10 EMA | ~$255 (dynamic) |
| Late trail | 5.0R ($286.93) | Trail 20 EMA | ~$275 (dynamic) |
| Exit | When price hits trailing stop | — | Final price |

**Result:** Position runs until momentum exhausts, not fixed target.

---

## Implementation Notes

1. **Backward compatibility:** Existing `target` mode remains default
2. **Validation:** YAML must validate against schema (stage R-values must increase)
3. **Performance:** Cache EMA calculations per ticker
4. **Logging:** Record each stop adjustment in trade log

---

## Open Questions

1. Should scale-out fractions be based on original position or remaining?
2. How to handle gap-down openings below trailing stop?
3. Should trailing stop ever be "paused" (e.g., during earnings)?
4. How to visualize trailing stop history in reports?

---

## Related Files

- `traderlib/paper_exits.py` — Exit engine (modify)
- `traderlib/risk_config.py` — Config loading (extend)
- `config/strategies/*.yaml` — Strategy configs (add exit sections)
- `traderlib/backtest/` — Backtest compatibility (ensure)

---

*Design approved for implementation planning.*
