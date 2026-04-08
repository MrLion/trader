# Alpaca API Migration Plan

**Status:** Phase 1 Complete ✅ — Infrastructure built  
**Created:** 2026-04-08  
**Priority:** High  
**Estimated Duration:** 2-3 days  

---

## Phase 1: Infrastructure ✅ COMPLETE

### Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `scripts/alpaca_client.py` | REST + WebSocket client | ~300 |
| `scripts/paper_engine_alpaca.py` | Main engine with WebSocket | ~400 |
| `scripts/setup_alpaca.py` | Configuration helper | ~150 |
| `data/config/example.alpaca_config.json` | Config template | 20 |

### Usage

```bash
# 1. Configure API credentials
python3 scripts/setup_alpaca.py

# 2. Test connection
python3 scripts/setup_alpaca.py --test

# 3. Start Alpaca-powered engine
python3 scripts/paper_engine_alpaca.py

# Or set env vars directly:
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
python3 scripts/paper_engine_alpaca.py
```

---

## Overview

Migrate paper trading engine from yfinance (15min delayed, polling-only) to Alpaca API for real-time data and trade execution.

**Current State:**
- Data: yfinance (free, 15min delay)
- Execution: Simulated locally
- Polling: Every 30 seconds

**Target State:**
- Data: Alpaca real-time (no delay) via WebSocket + REST
- Execution: Alpaca paper trading API (for now)
- Polling: WebSocket streaming (no polling for prices)

---

## Phase 1: Infrastructure Setup

### 1.1 Dependencies

```bash
pip install alpaca-trade-api alpaca-py websockets
```

### 1.2 Configuration

Create `data/config/alpaca_config.json` (gitignore this):

```json
{
  "paper": {
    "api_key": "YOUR_PAPER_KEY",
    "secret_key": "YOUR_PAPER_SECRET",
    "base_url": "https://paper-api.alpaca.markets"
  },
  "live": {
    "api_key": "YOUR_LIVE_KEY",
    "secret_key": "YOUR_LIVE_SECRET",
    "base_url": "https://api.alpaca.markets"
  },
  "data_feed": "sip",  // sip for paid, iex for free
  "mode": "paper"
}
```

### 1.3 Environment Variables

```bash
export ALPACA_API_KEY="..."
export ALPACA_SECRET_KEY="..."
export ALPACA_MODE="paper"  # or "live"
```

---

## Phase 2: Data Layer Migration ✅ COMPLETE

### Files Created/Modified

| File | Changes | Purpose |
|------|---------|---------|
| `scripts/alpaca_client.py` | Enhanced | Rate limiting, fallback to yfinance |
| `scripts/rate_limiter.py` | New | Rate limiting, circuit breakers, health monitoring |

### Rate Limiting

**Implementation:**
- 200 requests/minute tracking (Alpaca limit)
- Automatic wait time calculation
- Exponential backoff on errors (up to 60s)
- Circuit breaker after 5 errors in 1 minute

### Data Fallback

**Primary → Fallback Chain:**
1. Alpaca WebSocket cache (real-time)
2. Alpaca REST API (rate limited)
3. yfinance (unlimited, free)

**Health Monitoring:**
- Tracks Alpaca and yfinance health separately
- Automatic failover on failures
- Recovery detection after 3 successes

### Usage

```python
from alpaca_client import AlpacaClient, health_monitor

client = AlpacaClient(mode='paper')

# Get price with automatic fallback
price = client.get_latest_price('AAPL')  # Tries Alpaca → yfinance

# Get historical bars with fallback
bars = client.get_historical_bars('AAPL', days=252)  # Tries Alpaca → yfinance

# Check health
print(client.get_health_summary())
# Output: WebSocket: ✅ (50 prices cached) | Rate Limit: 15/200 | Circuit: 🟢 CLOSED
```

---

## Phase 3: Execution Layer Migration

### 3.1 Order Submission

Replace local state simulation with actual API calls:

```python
# Current (simulated)
def enter_position(self, ticker, entry_price, shares, ...):
    position = Position(...)
    self.positions[ticker] = position
    self.cash -= entry_price * shares

# New (Alpaca API)
def enter_position(self, ticker, entry_price, shares, ...):
    order = self.alpaca.submit_order(
        symbol=ticker,
        qty=shares,
        side='buy',
        type='market',  # or 'limit' at pivot price
        time_in_force='day',
        stop_loss={'stop_price': stop_price}
    )
    return order
```

### 3.2 Position Sync

**Two-way sync between local state and Alpaca:**

```python
def sync_positions(self):
    """Pull positions from Alpaca, update local state."""
    alpaca_positions = self.alpaca.list_positions()

    for pos in alpaca_positions:
        if pos.symbol not in self.positions:
            # Position exists in Alpaca but not locally - sync it
            self._sync_from_alpaca(pos)

    # Check for positions closed externally
    for ticker in list(self.positions.keys()):
        if ticker not in [p.symbol for p in alpaca_positions]:
            self._handle_externally_closed(ticker)
```

### 3.3 Order Lifecycle Management

Handle Alpaca order states:
- `new` → `filled` (entry complete)
- `filled` → `held` (position open)
- `held` → `closed` (exit complete)

```python
def check_order_status(self, order_id):
    order = self.alpaca.get_order(order_id)

    if order.status == 'filled':
        self._on_entry_filled(order)
    elif order.status in ['canceled', 'expired']:
        self._on_entry_failed(order)
```

---

## Phase 4: WebSocket Integration

### 4.1 Architecture Decision

**Hybrid Model (Recommended):**
- **WebSocket** for: Price updates, trade fills, order status changes
- **REST** for: Historical bars, entry logic, position sizing
- **Polling** for: Keep-alive checks, WebSocket health (every 60s)

**Why hybrid:**
- WebSocket for real-time → lower latency
- REST for heavy data → no rate limit issues
- Fallback to REST if WebSocket disconnects

### 4.2 Event Loop Integration

```python
# In paper_engine.py main loop
async def run(self):
    # Start WebSocket in background
    asyncio.create_task(self.price_stream.run())

    while self.running:
        # Check exits using cached WebSocket prices
        self._check_exits()

        # Check entries using REST (every 30s)
        if self._should_check_entries():
            self._check_entries()

        await asyncio.sleep(1)  # Main loop ticks every second
```

### 4.3 WebSocket Message Handlers

```python
async def handle_trade_update(self, trade):
    """Called on every trade tick via WebSocket."""
    ticker = trade.symbol
    price = trade.price

    # Update price cache
    self.price_cache[ticker] = {
        'price': price,
        'timestamp': datetime.now()
    }

    # Check if position needs exit
    if ticker in self.positions:
        self._evaluate_exit(ticker, price)

async def handle_order_update(self, order):
    """Called when order status changes."""
    if order.event == 'fill':
        if order.side == 'buy':
            self._on_entry_filled(order)
        else:
            self._on_exit_filled(order)
```

---

## Phase 5: Risk & Error Handling

### 5.1 Rate Limits

**Alpaca Limits:**
- REST API: 200 requests/minute per account
- WebSocket: Unlimited (preferred for high frequency)

**Mitigation:**
- Use WebSocket for price data (unlimited)
- Batch REST requests where possible
- Implement exponential backoff on 429 errors
- Cache historical data (don't re-fetch every loop)

### 5.2 Error Scenarios

| Scenario | Response |
|----------|----------|
| WebSocket disconnect | Fallback to REST polling, retry WebSocket in 5s |
| API rate limit | Exponential backoff, log warning |
| Order rejected | Log reason (insufficient funds, halted, etc), skip ticker |
| Partial fill | Handle in order update, adjust position size |
| Position mismatch | Sync from Alpaca, log discrepancy |

### 5.3 Circuit Breakers

```python
def check_health(self):
    """Run before each iteration."""
    # Check WebSocket connection
    if not self.price_stream.connected:
        self._reconnect_websocket()

    # Check API health
    if self.api_error_count > 5:
        self._pause_trading("Too many API errors")

    # Check account status
    account = self.alpaca.get_account()
    if account.status != 'ACTIVE':
        self._pause_trading(f"Account status: {account.status}")
```

---

## Phase 6: Testing & Validation

### 6.1 Unit Tests

Create `tests/test_alpaca_client.py`:
- Mock Alpaca API responses
- Test order submission flow
- Test position sync logic
- Test WebSocket message handling

### 6.2 Paper Trading Validation

Run parallel for 1 week:
- **Old engine:** yfinance + simulated trades (continue running)
- **New engine:** Alpaca paper trading (test mode)

Compare:
- Entry signals (should match)
- Exit timing (Alpaca should be faster)
- P&L calculations (should match closely)

### 6.3 Checklist Before Live

- [ ] All paper trades execute correctly
- [ ] Position sync works both ways
- [ ] WebSocket reconnects automatically
- [ ] Rate limits never hit
- [ ] Error handling tested for all scenarios
- [ ] Fallback to REST works
- [ ] Shutdown is graceful (no orphaned orders)

---

## Phase 7: Files to Create/Modify

### New Files

| File | Purpose | Lines |
|------|---------|-------|
| `scripts/alpaca_client.py` | Unified REST + WebSocket client | ~400 |
| `scripts/price_stream.py` | WebSocket price streaming | ~200 |
| `scripts/order_manager.py` | Order lifecycle management | ~250 |
| `tests/test_alpaca_integration.py` | Integration tests | ~150 |

### Modified Files

| File | Changes | Lines |
|------|---------|-------|
| `scripts/paper_engine.py` | Integrate WebSocket, use Alpaca client | +200 |
| `scripts/paper_state.py` | Add position sync from Alpaca | +100 |
| `scripts/paper_exits.py` | Use real-time prices from cache | +50 |
| `.gitignore` | Add Alpaca config | +3 |

### New Config

| File | Purpose |
|------|---------|
| `data/config/.alpaca_config.json` | API keys (gitignored) |
| `data/config/example.alpaca_config.json` | Template |

---

## Implementation Timeline

| Day | Phase | Tasks |
|-----|-------|-------|
| Day 1 | 1-2 | Setup Alpaca account, install deps, build REST client, migrate historical data |
| Day 2 | 3-4 | Build WebSocket stream, integrate with engine, test price updates |
| Day 3 | 5-7 | Add error handling, circuit breakers, testing, validation run |

**Total: ~1,100 lines across 7 new/modified files**

---

## Open Questions

1. **Free vs Paid Data:** Alpaca free tier uses IEX feed (~1.5M trades/day). Paid SIP has all trades. Do you have paid market data?

2. **Market Data Delay:** Even with Alpaca, non-paid accounts get SIP data with 15min delay during market hours. Do you want to upgrade?

3. **Order Types:** Market orders execute immediately but may have slippage. Limit orders at pivot price may not fill. Which to use?

4. **Position Sync Frequency:** Sync with Alpaca every loop (1s) or only on events?

---

## Dependencies

```
alpaca-trade-api>=3.0.0
alpaca-py>=0.8.0
websockets>=11.0
```

---

## Next Action

1. Sign up for Alpaca account (paper trading is free)
2. Generate API keys
3. Choose integration approach (REST-only, WebSocket, or hybrid)
4. Start Phase 1 implementation
