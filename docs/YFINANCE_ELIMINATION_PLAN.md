# yfinance Elimination Migration Plan

## Executive Summary

**Objective:** Remove all yfinance dependencies and migrate to Alpaca API exclusively.

**Timeline:** 4-6 weeks
**Effort:** High
**Risk:** Medium (rate limit management, historical data constraints)
**Cost Impact:** +$99/month (Alpaca Unlimited subscription required)

---

## Current State Analysis

### yfinance Usage Matrix

| Script | Use Case | Data Needs | Alpaca Replacement Strategy |
|--------|----------|------------|----------------------------|
| `sector_scan.py` | Scan 18 ETFs daily | Historical (6mo, 5d) | Batch bars API calls |
| `analyze_ticker.py` | Deep analysis | Historical (1y) | Single bars API with caching |
| `analyze_watchlist.py` | Watchlist analysis | Historical (1y) | Single bars API with caching |
| `entry_signals.py` | SPY regime check | Historical (2d) | SPY bars API |
| `paper_engine.py` | Trading engine | Historical (6mo, 1y) | Refactor to use `paper_engine_alpaca.py` |
| `paper_exits.py` | Exit calculations | Historical (20d EMA) | Historical bars API |
| `paper_portfolio.py` | Portfolio status | Current prices | Position API + quotes API |
| `premarket_report.py` | Pre-market report | Historical (252d) | Batch bars with pagination |
| `postmarket_report.py` | Post-market report | Historical (252d) | Batch bars with pagination |
| `stage2_rs_screen.py` | RS screening | Historical (1y) | Batch bars with pagination |
| `watchlist_manager.py` | Price lookups | Current prices | Quotes API |
| `midday_scan.py` | Midday scanning | Current prices | Quotes API |
| `sector_scan_comprehensive.py` | Comprehensive scan | Historical (1y) | Batch bars with pagination |
| `mcstock_scraper.py` | Scraper validation | Current prices | Quotes API |
| `migrate_watchlist_stages.py` | One-time migration | Historical (1y) | Single bars API |
| `generate_fixtures.py` | Test fixtures | Historical (1y) | Cached historical data |
| `alpaca_client.py` | Client library | Fallback only | Remove fallback, raise exception |
| `paper_engine_alpaca.py` | Alpaca engine | Minimal (SPY) | Already uses Alpaca |

### Data Requirements Summary

| Data Type | Current (yfinance) | Required (Alpaca) | Volume |
|-----------|-------------------|-------------------|--------|
| Current prices | Unlimited, free | 200 req/min (free), Unlimited (paid) | ~50-100/day |
| Historical bars (1y) | Unlimited, free | 200 req/min, pagination required | ~18 ETFs + watchlist |
| 6-month history | Unlimited, free | 200 req/min | ~500 stocks scanned |
| SPY 1y history | Unlimited, free | 200 req/min | Frequent |

---

## Alpaca API Constraints

### Rate Limits (Free Tier)

| Endpoint | Limit | Impact on Migration |
|----------|-------|---------------------|
| Historical Bars | 200 req/min | **CRITICAL**: Reports need 500+ requests. Need batching + pagination. |
| Latest Quotes | 200 req/min | Manageable with caching |
| Latest Trades | 200 req/min | Manageable |
| Position Data | Included in REST | Use position API for portfolio prices |

### Alpaca Unlimited ($99/month)

| Feature | Limit | Impact |
|---------|-------|--------|
| Data Feed | SIP (real-time) | Required for accurate scanning |
| Historical | Same 200 req/min | Still need pagination strategy |
| WebSocket | Unlimited | Can subscribe to watchlist tickers |

---

## Migration Strategy

### Phase 1: Infrastructure (Week 1)

**1.1 Create AlpacaHistoricalData Manager**

```python
class AlpacaHistoricalDataManager:
    """Batch historical data fetching with rate limiting and caching."""
    
    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.cache = {}  # Persistent cache
        self.batch_size = 10  # Process 10 tickers at a time
    
    def fetch_bars_batch(self, tickers: List[str], days: int = 252) -> Dict[str, pd.DataFrame]:
        """Fetch historical bars for multiple tickers with rate limiting."""
        # Process in batches of 10
        # Store in cache
        # Return DataFrames
```

**1.2 Implement Caching Strategy**

- Daily cache for reports
- Hourly cache for scans
- In-memory cache for current prices
- Persistent cache (SQLite) for historical

**1.3 Upgrade Alpaca Subscription**

- Subscribe to Alpaca Unlimited ($99/month)
- Switch to SIP data feed
- Verify rate limits

### Phase 2: Portfolio & Trading (Week 2)

**2.1 Migrate `paper_portfolio.py`**

```python
# CURRENT (yfinance)
def cmd_status(args):
    for ticker in positions:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        price = hist['Close'].iloc[-1]

# TARGET (Alpaca)
def cmd_status(args):
    # Use position API current_price (already implemented)
    # For non-positions, use quotes API
    positions_data = alpaca.list_positions()
    for pos in positions_data:
        price = pos['current_price']  # Marked to market
```

**2.2 Migrate `paper_exits.py`**

```python
# CURRENT (yfinance)
def _get_cached_data(self, ticker: str, period: str = "20d") -> Optional[pd.DataFrame]:
    stock = yf.Ticker(ticker)
    return stock.history(period=period)

# TARGET (Alpaca)
def _get_cached_data(self, ticker: str, days: int = 20) -> Optional[pd.DataFrame]:
    return alpaca.get_historical_bars(ticker, days=days)
```

**2.3 Remove yfinance from `alpaca_client.py`**

```python
# Remove _yfinance_fallback_price()
# In get_latest_price(), use quotes API instead of trade API
# Use position API current_price when position exists
```

### Phase 3: Scanning & Analysis (Week 3-4)

**3.1 Migrate `sector_scan.py`**

```python
# CURRENT (yfinance) - 18 ETF calls
for ticker, name in sectors.items():
    data = yf.Ticker(ticker).history(period="6mo")

# TARGET (Alpaca) - Batch with rate limiting
def scan_sectors_batch():
    batch_size = 10  # Stay under 200 req/min
    for batch in chunks(sectors.keys(), batch_size):
        bars = alpaca.get_historical_bars_batch(batch, days=180)
        process_batch(bars)
        time.sleep(3)  # Rate limit protection
```

**3.2 Migrate `analyze_ticker.py`**

```python
# CURRENT (yfinance)
stock = yf.Ticker(ticker)
hist = stock.history(period="1y")

# TARGET (Alpaca)
hist = alpaca.get_historical_bars(ticker, days=365)
```

**3.3 Migrate Reports (`premarket_report.py`, `postmarket_report.py`)**

```python
# Batch fetch with caching
# Process 500 stocks in batches of 10
# Estimated time: 500/10 * 3s = 150 seconds (2.5 minutes) per report
```

**3.4 Migrate `stage2_rs_screen.py`**

```python
# Similar batching strategy
# Cache results for 1 hour
# Background job for scanning
```

### Phase 4: Utilities & Cleanup (Week 5)

**4.1 Migrate `watchlist_manager.py`**

```python
# CURRENT
stock = yf.Ticker(ticker)
current = stock.info['currentPrice']

# TARGET
quote = alpaca.get_latest_quote(ticker)
current = (quote.ask_price + quote.bid_price) / 2
```

**4.2 Migrate `midday_scan.py`**

```python
# Use quotes API for current prices
# Use cached historical for calculations
```

**4.3 Cleanup**

- Remove yfinance from `requirements.txt`
- Update TOOLS.md documentation
- Remove yfinance fallback in all places
- Update tests

### Phase 5: Testing & Validation (Week 6)

**5.1 Test Suite**

- Mock Alpaca responses in tests
- Verify rate limiting works
- Test offline behavior (should fail gracefully)

**5.2 Performance Validation**

- Compare execution time: yfinance vs Alpaca
- Verify report generation completes in <5 minutes
- Load test scanning with 500 stocks

---

## Implementation Details

### New Classes to Create

**1. `AlpacaDataManager`**

```python
class AlpacaDataManager:
    """Centralized data fetching with caching and rate limiting."""
    
    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.price_cache = {}
        self.bars_cache = {}
        self.cache_ttl = {
            'price': 60,      # 1 minute
            'bars_1d': 300,   # 5 minutes
            'bars_long': 3600 # 1 hour
        }
    
    def get_current_price(self, ticker: str) -> float:
        """Get current price from position API or quotes."""
        # Check position first
        # Then quotes API
        # Cache result
        pass
    
    def get_historical_bars(self, ticker: str, days: int) -> pd.DataFrame:
        """Get historical bars with caching."""
        # Check cache
        # Fetch from Alpaca
        # Paginate if needed (>7 days need pagination in some cases)
        pass
    
    def get_historical_bars_batch(self, tickers: List[str], days: int) -> Dict[str, pd.DataFrame]:
        """Batch fetch with rate limiting."""
        # Process in batches of 10
        # Rate limit: 200 req/min = ~3 seconds between batches
        pass
```

**2. `ScanningEngine`**

```python
class ScanningEngine:
    """Batch scanning with progress tracking."""
    
    def __init__(self, data_manager):
        self.data = data_manager
    
    def scan_sectors(self) -> Dict:
        """Scan all sector ETFs."""
        # Batch fetch 11 sector ETFs
        # Calculate returns, MAs
        # Return results
        pass
    
    def scan_watchlist(self, tickers: List[str]) -> Dict:
        """Scan watchlist tickers."""
        # Batch fetch
        # Calculate Stage 2 scores
        pass
```

### Modified Functions

**`get_latest_price()` in `alpaca_client.py`**

```python
def get_latest_price(self, ticker: str) -> Optional[float]:
    """Get current marked-to-market price."""
    # 1. Check position API (if held)
    if self.has_position(ticker):
        return float(self.get_position(ticker)['current_price'])
    
    # 2. Use quotes API (bid/ask midpoint)
    quote = self.get_latest_quote(ticker)
    return (quote.bid_price + quote.ask_price) / 2
```

---

## Risk Assessment

### High Risk

1. **Rate Limit Exceeded During Scans**
   - **Mitigation:** Implement strict batching (10 tickers/batch), 3s delays, circuit breaker
   - **Fallback:** Abort scan, use cached data

2. **Historical Data Gaps**
   - **Mitigation:** Validate data completeness, compare with yfinance during transition
   - **Fallback:** Raise error, notify user

### Medium Risk

1. **Increased Latency**
   - yfinance: Parallel, unlimited
   - Alpaca: Sequential, rate-limited
   - **Mitigation:** Aggressive caching, background pre-fetching

2. **Cost Increase**
   - $99/month for Unlimited
   - **Mitigation:** Evaluate after 1 month, can downgrade if scanning reduced

### Low Risk

1. **API Changes**
   - Alpaca could change endpoints
   - **Mitigation:** Pin SDK version, monitor deprecation notices

---

## Testing Strategy

### Unit Tests

- Mock Alpaca responses
- Test rate limiting logic
- Verify caching behavior

### Integration Tests

- Full scan with 500 stocks
- Report generation
- Portfolio status

### Load Tests

- Concurrent requests
- Rate limit boundary conditions
- Circuit breaker activation

---

## Cost Analysis

### Current (yfinance + Alpaca Free)

| Item | Cost | Notes |
|------|------|-------|
| yfinance | $0 | Unlimited, free |
| Alpaca Free | $0 | 200 req/min limit |
| **Total** | **$0** | |

### After Migration (Alpaca Unlimited)

| Item | Cost | Notes |
|------|------|-------|
| Alpaca Unlimited | $99/month | SIP data, still 200 req/min |
| **Total** | **$99/month** | **$1,188/year** |

### Cost-Benefit Analysis

**Benefits:**
- Single data source (simpler architecture)
- Real-time data (no 15-min delay)
- Consistent prices across all tools
- Professional data quality

**Costs:**
- $1,188/year subscription
- Development time (4-6 weeks)
- Slower scanning due to rate limits
- No offline capability

**Recommendation:** Worth it for production trading, but significant trade-off.

---

## Migration Checklist

### Pre-Migration

- [ ] Subscribe to Alpaca Unlimited
- [ ] Verify API keys and permissions
- [ ] Set up monitoring/alerting for rate limits
- [ ] Create `AlpacaDataManager` class
- [ ] Implement caching layer

### Migration Execution

- [ ] Phase 1: Infrastructure
- [ ] Phase 2: Portfolio & Trading
- [ ] Phase 3: Scanning & Analysis
- [ ] Phase 4: Utilities & Cleanup
- [ ] Phase 5: Testing & Validation

### Post-Migration

- [ ] Remove yfinance from requirements.txt
- [ ] Update documentation
- [ ] Archive old code
- [ ] Monitor for 1 week
- [ ] Document lessons learned

---

## Decision Matrix

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **Keep yfinance** | Free, unlimited, offline capable | Two data sources, occasional discrepancies | **Current - working** |
| **Hybrid (recommended)** | Best of both, cost controlled | More complex | **Minimal change needed** |
| **Full Alpaca** | Single source, real-time | $99/month, slower, offline broken | **If budget allows** |

**My recommendation:** Unless the $99/month is trivial and the 15-minute delay is causing real trading issues, the hybrid approach is better. The discrepancies you've seen are from using the wrong endpoint in `get_latest_price()`, not from yfinance itself.
