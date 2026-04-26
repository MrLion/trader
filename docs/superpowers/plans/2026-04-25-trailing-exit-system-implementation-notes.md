# Trailing Exit System - Implementation Notes

## Quick Start

### Using Stage-Based Mode

Add to your `config/risk_config.yaml`:

```yaml
profit_target:
  mode: "trailing"
  trailing_mode: "stage_based"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21
```

### Running Backtest

```bash
python scripts/backtest.py
```

The trailing configuration will be used automatically.

---

## How It Works

### Entry → Exit Flow

```
Entry at $100
  |
  v
+2R ($120): Stop moves to $100 (breakeven)
  |
  v
+3R ($130): Trail with 10 EMA
  |
  v
+5R ($150): Switch to 21 EMA (wider trail)
  |
  v
Price hits EMA21 → EXIT
```

---

## Configuration Examples

### Example 1: Stage-Based (Recommended)

```yaml
profit_target:
  mode: "trailing"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
    - trigger_r: 3.0
      action: "trail_ema"
      period: 10
    - trigger_r: 5.0
      action: "trail_ema"
      period: 21
```

### Example 2: Hybrid (Scale-Out)

```yaml
profit_target:
  mode: "hybrid"
  trailing_stages:
    - trigger_r: 2.0
      action: "breakeven"
  scale_out_steps:
    - trigger_r: 3.0
      fraction: 0.33
    - trigger_r: 4.0
      fraction: 0.50
```

### Example 3: Continuous

```yaml
profit_target:
  mode: "trailing"
  trailing_mode: "continuous"
  continuous_bands:
    - from_r: 2.5
      to_r: 4.0
      method: "ema10"
    - from_r: 4.0
      method: "ema21"
```

---

## AMD Trade Example

With stage-based configuration:

| Price | R | Action | Stop | Notes |
|-------|---|--------|------|-------|
| $281.83 | 0R | Entry | $267.74 | Initial ATR stop |
| $313.93 | 2R | Breakeven | $281.83 | Capital protected |
| $345.73 | 3R | Trail 10EMA | ~$340 | Following trend |
| $409.33 | 5R | Trail 21EMA | ~$390 | Widened for volatility |
| $380.00 | — | Exit | $380 | 21EMA breached |

**Result:** Captured full trend instead of fixed 2R exit.

---

## Running Tests

```bash
# All trailing tests
python3 -m pytest tests/test_trailing*.py -v

# Specific test files
python3 -m pytest tests/test_trailing_exits.py -v
python3 -m pytest tests/test_trailing_integration.py -v
python3 -m pytest tests/test_backtest_trailing.py -v
```

---

## Files Created/Modified

| File | Change |
|------|--------|
| `traderlib/risk_config.py` | Extended ProfitTargetConfig with trailing modes |
| `traderlib/trailing_exits.py` | New - Core trailing engine |
| `traderlib/paper_state.py` | Added scale_out_history to Position |
| `traderlib/paper_exits.py` | Integrated trailing into ExitEngine |
| `config/strategies/example_trailing.yaml` | Example configuration |
| `tests/test_trailing_exits.py` | Engine tests (21 tests) |
| `tests/test_trailing_integration.py` | Integration tests (3 tests) |
| `tests/test_backtest_trailing.py` | Backtest tests (2 tests) |

---

## Backward Compatibility

Default mode remains `target` (fixed 2R profit). To enable trailing, explicitly set:

```yaml
profit_target:
  mode: "trailing"  # or "hybrid"
```

Without this setting, the system behaves exactly as before.

---

## Migration to Per-Strategy Configs

See plan document for migration path from global to per-strategy configurations.

---

## Known Limitations

1. **Short positions not supported** — Raises `NotImplementedError`
2. **EMA periods limited** — Currently supports 10 and 21 (others use nearest)
3. **Scale-out doesn't reduce risk** — Initial R-calculation unchanged after scale-out

---

## Implementation Complete ✅

All tasks finished. System ready for use.
