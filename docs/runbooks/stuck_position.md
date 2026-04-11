# Runbook: Stuck Position (Cannot Exit)

**Last Updated:** 2026-04-11
**Severity:** Critical - Risk exposure
**Estimated Recovery Time:** 5-30 minutes

---

## Symptoms

- Exit order rejected: `❌ AAPL: Order submission failed`
- Position remains open despite stop hit
- `⏸️ Exit already pending for AAPL` (but no fill)
- Ticker shows as "halted" or "delisted"
- No market makers / zero volume

## Diagnosis

### Step 1: Check Ticker Status

```bash
# Check if ticker is trading
python3 -c "
from traderlib.alpaca_client import AlpacaClient
client = AlpacaClient()
price = client.get_latest_price('TICKER')
print(f'Price: {price}')
"

# If None: Ticker may be halted
```

### Step 2: Check Market Status

```bash
# Check Alpaca asset status
curl -s "https://paper-api.alpaca.markets/v2/assets/TICKER" \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" | jq '.status'

# Expected: "active"
# If "inactive": Trading halted
```

### Step 3: Check for Pending Orders

```bash
# List pending orders
python3 -c "
from traderlib.order_manager import OrderManager
from traderlib.alpaca_client import AlpacaClient
om = OrderManager(AlpacaClient())
pending = om.get_pending_for_ticker('TICKER')
print(f'Pending orders: {len(pending)}')
for o in pending:
    print(f'  {o.id}: {o.status}')
"
```

## Recovery

### Scenario A: Order Stuck in Pending

**Symptoms:** Order submitted but not filling

```bash
# Cancel pending order first
python3 -c "
from traderlib.alpaca_client import AlpacaClient
client = AlpacaClient()
# Get order ID from logs or dashboard
client.cancel_order('ORDER_ID')
print('Pending order cancelled')
"

# Retry with market order (accept slippage)
python3 scripts/paper_portfolio.py close AAPL --reason "stuck_recovery" --order-type market
```

### Scenario B: Ticker Halted

**Symptoms:** No price updates, "halted" status

```bash
# Check halt status via Alpaca API
python3 -c "
from traderlib.alpaca_client import AlpacaClient
client = AlpacaClient()
# Get asset status from Alpaca
try:
    from alpaca.trading.client import TradingClient
    trading_client = TradingClient(client.api_key, client.secret_key, paper=(client.mode == 'paper'))
    asset = trading_client.get_asset('TICKER')
    print(f'Status: {asset.status}')
    print(f'Tradeable: {asset.tradable}')
except Exception as e:
    print(f'Could not get status: {e}')
"
```

**Actions:**
1. Note the halt in trading journal
2. Set alert for when trading resumes
3. Prepare market order for immediate exit on resumption

### Scenario C: Ticker Delisted

**Symptoms:** Ticker no longer exists, position shows $0 value

```bash
# Check if ticker exists via Alpaca
python3 -c "
from traderlib.alpaca_client import AlpacaClient
client = AlpacaClient()
try:
    price = client.get_latest_price('TICKER')
    if price:
        print('Ticker exists and trading')
    else:
        print('No price data - may be delisted')
except Exception as e:
    print(f'Ticker issue: {e}')
"
```

**Actions:**
1. Contact Alpaca support: `support@alpaca.markets`
2. Document cost basis for tax purposes
3. Manually mark position as "STUCK" in records

### Scenario D: Position Won't Close via API

**Last resort - Manual intervention:**

```bash
# 1. Log into Alpaca web interface
# 2. Navigate to: https://app.alpaca.markets/trade
# 3. Find position manually
# 4. Submit market order
# 5. Update local state

python3 -c "
from traderlib.paper_state import PaperState
state = PaperState()
if 'TICKER' in state.positions:
    state.close_position('TICKER', exit_price=0, reason='MANUAL_CLOSE')
    print('Local position marked closed')
"
```

## Emergency Procedures

### Circuit Breaker: Force Close All

If multiple positions stuck:

```python
# Emergency close all positions
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')

for ticker in list(engine.state.positions.keys()):
    try:
        engine.order_manager.submit_exit(
            ticker=ticker,
            shares=engine.state.positions[ticker].shares,
            reason='EMERGENCY_CLOSE'
        )
        print(f'🚨 Emergency exit submitted: {ticker}')
    except Exception as e:
        print(f'❌ Failed to exit {ticker}: {e}')
```

### Contact Escalation

| Timeframe | Action |
|-----------|--------|
| Immediate | Try all recovery options above |
| 10 min | Contact Alpaca support (chat) |
| 30 min | Email Alpaca with order IDs |
| 1 hour | Consider manual broker execution |

**Include in support ticket:**
- Order ID(s)
- Timestamp
- Position size
- Error messages
- Account ID

## Prevention

### 1. Pre-Trade Liquidity Check

```python
def check_liquidity(ticker):
    hist = get_historical_bars(ticker, days=5)
    avg_volume = hist['Volume'].mean()
    if avg_volume < 100000:  # 100K shares/day
        print(f"⚠️ Low liquidity - stuck position risk")
        return False
    return True
```

### 2. Avoid Pre-Market/Low Volume Periods

```python
# In _check_entries()
if self._is_pre_market():
    return  # Skip entries before 9:30 AM

volume = get_current_volume(ticker)
if volume < avg_volume * 0.1:  # <10% average
    print(f"⏸️ Low volume - skip entry")
    return
```

### 3. Position Size Limits for Illiquid Stocks

```python
# Reduce size for low-volume stocks
if avg_daily_volume < 500000:
    max_position_pct = 0.05  # 5% instead of 20%
```

## Related

- [Partial Fill Runbook](./partial_fill.md)
- [API Outage Runbook](./api_outage.md)
- Alpaca Support: https://alpaca.markets/support
- Emergency Close: Alpaca web interface
