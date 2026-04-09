# Runbook: Partial Order Fill

**Last Updated:** 2026-04-08  
**Severity:** High - Position mismatch  
**Estimated Recovery Time:** 2-5 minutes

---

## Symptoms

- Order shows as "filled" in local state
- Position size in engine doesn't match Alpaca
- `⚠️ Position discrepancy: AAPL - Alpaca: 50, Local: 100`
- P&L calculations showing incorrect values
- Risk calculations based on wrong position size

## Diagnosis

### Step 1: Check Local vs Alpaca

```bash
# Check local position
python3 scripts/paper_portfolio.py status

# Compare with Alpaca dashboard
# Open: https://app.alpaca.markets/trade
```

### Step 2: Check Order Status

```bash
# View pending orders
python3 -c "
from order_manager import OrderManager
from alpaca_client import AlpacaClient
om = OrderManager(AlpacaClient())
print(om.get_orders_summary())
"
```

Look for:
- Status: `partially_filled`
- Filled qty < Order qty

### Step 3: Identify the Gap

```python
# Calculate discrepancy
local_shares = engine.state.positions['TICKER'].shares
alpaca_position = engine.alpaca.get_position('TICKER')
alpaca_shares = alpaca_position['qty'] if alpaca_position else 0

discrepancy = local_shares - alpaca_shares
print(f"Gap: {discrepancy} shares")
```

## Recovery

### Option A: Automatic Sync (Recommended)

The engine syncs with Alpaca every 30 seconds. Wait one cycle:

```
📊 Entry Check Summary: Checked 23 | Eligible 1 | Synced 1 position
```

**If sync doesn't happen:**

```bash
# Force manual sync
python3 -c "
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')
engine._sync_with_alpaca()
print('Sync complete')
"
```

### Option B: Manual Position Adjustment

If automatic sync fails:

```python
# Adjust local position to match Alpaca
import json
from pathlib import Path

positions_file = Path('data/paper_positions.json')
with open(positions_file) as f:
    positions = json.load(f)

# Correct the share count
positions['AAPL']['shares'] = 50  # Actual from Alpaca

with open(positions_file, 'w') as f:
    json.dump(positions, f, indent=2)

print("✅ Position corrected")
```

### Option C: Emergency Close and Re-enter

If position is severely misaligned:

```bash
# Close entire position in Alpaca
python3 scripts/paper_portfolio.py close AAPL --reason "partial_fill_recovery"

# Wait for confirmation
sleep 5

# Re-enter with correct size if still valid
# (Manual decision required)
```

## Prevention

### 1. Enable Strict Fill Tracking

Add to `paper_engine_alpaca.py` config:

```python
# In _process_pending_orders()
CHECK_FILL_PERCENTAGE = True
MIN_FILL_THRESHOLD = 0.95  # 95% filled = consider complete
```

### 2. Alert on Partial Fills

```python
# Add to order_manager.py
if order.filled_qty < order.qty * 0.95:
    print(f"🚨 PARTIAL FILL: {order.ticker} only {order.fill_pct}% filled")
```

### 3. Pre-trade Liquidity Check

```python
# Before submitting large orders
dollar_volume = avg_volume * price
if dollar_volume < 1000000:  # $1M daily volume
    print(f"⚠️ Low liquidity stock - partial fill risk")
```

## Common Scenarios

| Scenario | Local | Alpaca | Action |
|----------|-------|--------|--------|
| Normal partial fill | 100 | 75 | Wait for completion |
| Stuck partial | 100 | 75 for >5min | Adjust to 75, retry 25 |
| Over-fill (rare) | 100 | 100+ | Accept extra, log warning |
| Cancelled | 100 | 0 | Delete local position |

## Related

- [Stuck Position Runbook](./stuck_position.md)
- [API Outage Runbook](./api_outage.md)
- Alpaca Orders: https://app.alpaca.markets/trade/orders
