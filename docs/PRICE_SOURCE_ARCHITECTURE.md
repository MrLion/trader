# Price Source Architecture Analysis

## Current State

The `paper_portfolio.py status` command uses **yfinance EOD (End of Day) closing prices** instead of **Alpaca real-time prices**.

### Code Location
- File: `scripts/paper_portfolio.py`
- Lines: 110-122 (status command)
- Implementation:
  ```python
  import yfinance as yf
  stock = yf.Ticker(ticker)
  hist = stock.history(period="5d", interval="1d")
  eod_close = hist['Close'].iloc[-1]
  ```

## Why yfinance EOD Was Chosen

### 1. **Offline Capability**
- yfinance works without API credentials
- Portfolio can be checked when Alpaca is unreachable
- No rate limit concerns for simple status checks

### 2. **Consistency**
- EOD prices don't change after 4:00 PM ET
- Same value shown regardless of when you check after hours
- Comparable day-over-day performance metrics

### 3. **No API Rate Limits**
- Alpaca has strict rate limits (200 requests/minute for free tier)
- 11 positions × multiple checks = potential throttling
- yfinance is essentially free/unlimited

### 4. **Historical Context**
Looking at git history, EOD prices were introduced in commit `7a71eef`:
- Date: April 10, 2026
- Reason: Show consistent account valuation
- Previous behavior: Used entry prices (even more stale)

## Tradeoffs Analysis

### Option A: Keep yfinance EOD (Current)

**Pros:**
- ✅ Free, no rate limits
- ✅ Works offline
- ✅ Consistent values
- ✅ Standard accounting practice (mark to close)

**Cons:**
- ❌ 3.5-4% discrepancy during volatile after-hours (as seen with AMD, AVGO)
- ❌ Doesn't match Alpaca UI during extended hours
- ❌ Confusing to users expecting real-time values

### Option B: Use Alpaca Real-Time

**Pros:**
- ✅ Matches Alpaca UI exactly
- ✅ Real-time P&L during market hours
- ✅ Accurate after-hours valuation
- ✅ Single source of truth

**Cons:**
- ❌ Requires API credentials even for simple checks
- ❌ Rate limit risk (200 req/min)
- ❌ Values change continuously after hours
- ❌ Network dependency

### Option C: Hybrid Approach (Recommended)

Use Alpaca when available, fallback to yfinance:

```python
def get_position_price(ticker, fallback_to_yfinance=True):
    """Get best available price with fallback chain."""
    # Try Alpaca first (primary source)
    price = alpaca_client.get_latest_price(ticker)
    if price:
        return price, 'ALPACA'
    
    # Fallback to yfinance EOD
    if fallback_to_yfinance:
        return yfinance_eod_price(ticker), 'YF_EOD'
    
    return None, 'UNAVAILABLE'
```

**Pros:**
- ✅ Best of both worlds
- ✅ Matches Alpaca UI when possible
- ✅ Graceful degradation
- ✅ Can add `--offline` flag to skip Alpaca

**Cons:**
- ⚠️ More complex implementation
- ⚠️ Need to initialize AlpacaClient in paper_portfolio.py

## Recommendation

**Implement Option C (Hybrid)** with these specifics:

1. **Modify `cmd_status()` to accept `--realtime` flag**
2. **Default behavior**: Use Alpaca if available, fallback to yfinance
3. **Add `--offline` flag**: Skip Alpaca entirely
4. **Show price source** in output: `(Alpaca real-time)` or `(YF EOD)`

### Implementation Plan

```python
# In cmd_status()
use_realtime = args.realtime if hasattr(args, 'realtime') else True

if use_realtime:
    try:
        from traderlib.alpaca_client import AlpacaClient
        alpaca = AlpacaClient(mode='paper')
        price_source = 'ALPACA'
    except:
        alpaca = None
        price_source = 'YF_EOD'
else:
    alpaca = None
    price_source = 'YF_EOD'

# In position loop:
if alpaca:
    current_price = alpaca.get_latest_price(ticker) or yf_eod
else:
    current_price = yf_eod
```

### UI Changes

Update header to show price source:
```
============================================================
📊 PAPER TRADING ACCOUNT STATUS (Alpaca Real-Time)
============================================================
```

Or:
```
============================================================
📊 PAPER TRADING ACCOUNT STATUS (EOD Close - Apr 10)
============================================================
```

## Impact Assessment

### Current Pain Points
1. User confusion: "Why is my local account value different from Alpaca?"
2. After-hours discrepancies of 3-4% on volatile days
3. No way to see real-time P&L from command line

### Benefits of Hybrid Approach
1. Transparency: User knows which price source is being used
2. Flexibility: Can check offline if needed
3. Accuracy: Matches Alpaca when network available
4. Rate limit protection: Can force EOD mode if hitting limits

## Decision Matrix

| Scenario | Current | Hybrid |
|---------|---------|--------|
| Market open, online | ❌ EOD (stale) | ✅ Real-time |
| Market closed, online | ❌ EOD (different from Alpaca) | ✅ Real-time (matches Alpaca) |
| Offline | ✅ EOD | ✅ EOD (fallback) |
| Rate limited | ✅ EOD | ✅ EOD (fallback) |
| Consistency | ✅ Same value all day | ⚠️ Changes throughout day |

## Conclusion

The hybrid approach (Option C) addresses the core issue while maintaining the benefits of both systems. It provides:

1. **Transparency**: Users know which price source is active
2. **Accuracy**: Matches Alpaca UI when network available  
3. **Reliability**: Graceful fallback to yfinance EOD
4. **Flexibility**: CLI flags for different use cases

This is the recommended path forward.
