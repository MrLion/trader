# Data Source Architecture Analysis: yfinance vs Alpaca

## Executive Summary

The project uses a **dual-source architecture** with yfinance and Alpaca serving different, complementary roles. Alpaca is the **trading execution engine** while yfinance provides **analysis, scanning, and offline capabilities**.

**Key Insight:** This is an intentional, well-designed architecture - not a technical debt issue.

---

## Current Usage Breakdown

### yfinance Usage (18 production scripts)

| Script Category | Scripts | Purpose |
|----------------|---------|---------|
| **Market Analysis** | `analyze_ticker.py`, `analyze_watchlist.py` | Deep-dive technical analysis, offline research |
| **Sector/Scanning** | `sector_scan.py`, `sector_scan_comprehensive.py`, `stage2_rs_screen.py` | Screen hundreds of stocks without rate limits |
| **Reports** | `premarket_report.py`, `postmarket_report.py` | Generate HTML reports with historical data |
| **Market Data** | `entry_signals.py`, `midday_scan.py` | SPY regime checks, broad market metrics |
| **Portfolio** | `paper_portfolio.py` | EOD valuation (offline capable) |
| **Data Utilities** | `watchlist_manager.py`, `migrate_watchlist_stages.py` | Price lookups for watchlist population |
| **Trading Engine** | `paper_engine.py`, `paper_exits.py` | Historical data for stop calculations |

### Alpaca Client Usage (7 production scripts)

| Script Category | Scripts | Purpose |
|----------------|---------|---------|
| **Trading Engine** | `paper_engine_alpaca.py`, `order_manager.py` | Real-time execution, WebSocket streaming |
| **Account/State** | `sync_state.py`, `setup_alpaca.py`, `validate_alpaca.py` | Position sync, account management |
| **Entry Signals** | `entry_signals.py` | Live price validation before entry |

---

## Architectural Rationale

### Why yfinance Dominates Analysis Tools

**1. Rate Limit Protection**
- Alpaca: 200 requests/minute (free tier)
- yfinance: Effectively unlimited
- Scanning 500 stocks would hit Alpaca limits in ~2.5 seconds

**2. Cost Structure**
- Alpaca: Requires API credentials, paid tiers for better data
- yfinance: Completely free, no authentication
- Analysis tools should be runnable by anyone without setup

**3. Offline Capability**
- Alpaca: Requires network, API authentication
- yfinance: Works anywhere, anytime
- Critical for development, testing, disaster recovery

**4. Historical Data**
- Alpaca: Limited history (free tier), requires pagination
- yfinance: 20+ years of daily data in one call
- Essential for 200-day MA, 1-year RS calculations

### Why Alpaca Dominates Execution

**1. Real-Time Requirements**
- Execution requires millisecond-level prices
- WebSocket streaming vs polling
- 15-minute delay unacceptable for fills

**2. Trading Integration**
- Order submission, position tracking
- Account synchronization
- Fill confirmations

**3. Market Hours**
- Alpaca works during market hours
- yfinance has delays even for current prices

---

## Detailed Use Case Analysis

### Use Case 1: Pre-Market Gap Scan (`sector_scan.py`)

```python
# Scans ~500 stocks for gaps >3%
for ticker in all_stocks:
    data = yf.Ticker(ticker).history(period="5d")
    # Calculate gap from previous close
```

**Why yfinance?**
- 500 API calls would exhaust Alpaca quota instantly
- Scan runs at 6:30 AM, no urgency for real-time
- Results feed watchlist, not immediate trading

**If using Alpaca:**
- Would need rate limiting, pagination
- 500 calls at 200/min = 2.5 minutes minimum
- Risk of throttling, failed scans

### Use Case 2: Portfolio Status (`paper_portfolio.py`)

```python
# Show account value with EOD prices
for ticker in positions:
    hist = yf.Ticker(ticker).history(period="5d")
    eod_close = hist['Close'].iloc[-1]
```

**Why yfinance?**
- Simple status check shouldn't require API credentials
- User may want to check offline
- EOD prices sufficient for daily reconciliation

**Trade-off:**
- -3.5% variance during volatile after-hours (acceptable for status)
- +100% uptime (no API dependency)

### Use Case 3: Entry Signal Validation (`entry_signals.py`)

```python
# Uses BOTH sources
spy_data = yf.Ticker("SPY").history(period="2d")  # Market regime
# ... later ...
current_price = alpaca_client.get_latest_price(ticker)  # Entry validation
```

**Hybrid approach:**
- SPY regime: yfinance (sufficient for broad trend)
- Entry price: Alpaca (must be accurate for execution)

### Use Case 4: Live Trading (`paper_engine_alpaca.py`)

```python
# WebSocket streaming for real-time execution
price = alpaca_client.get_latest_price(ticker)  # Millisecond accuracy
order = alpaca_client.submit_market_order(...)  # Direct execution
```

**Why Alpaca mandatory:**
- 15-minute delay = unacceptable slippage
- Order submission requires broker integration
- Position tracking must be real-time

---

## Rate Limit Analysis

### Alpaca Limits (Free Tier)

| Endpoint | Limit | Implications |
|----------|-------|--------------|
| REST API | 200 req/min | 11 positions = 18 checks/min max |
| WebSocket | Unlimited | Only for subscribed tickers |
| Historical | 200 req/min | 1 year of daily = 1 call |

### yfinance Limits

| Usage | Limit | Implications |
|-------|-------|--------------|
| Unauthenticated | ~1000/hour | Sufficient for analysis |
| Bulk download | No limit | Download 500 stocks at once |

### Scenario: Market Open Analysis

**Task:** Analyze 100 stocks for entries

**Alpaca approach:**
- 100 API calls = 30 seconds at rate limit
- Risk of hitting limit during active trading
- Need complex queuing, retry logic

**yfinance approach:**
- 100 API calls = parallel, ~5 seconds
- No rate limit concerns
- Can run anytime without credentials

---

## Cost Analysis

### Alpaca Pricing

| Tier | Cost | Data |
|------|------|------|
| Free | $0 | IEX feed, 15-min delayed |
| Unlimited | $99/month | SIP feed, real-time |

### yfinance Pricing

| Tier | Cost | Data |
|------|------|------|
| Free | $0 | Real-time (Yahoo), 20+ years history |

### Cost Decision Matrix

| Script | Monthly Cost (Alpaca) | yfinance Alternative |
|--------|------------------------|------------------------|
| `sector_scan.py` | $99 (unlimited needed) | $0 |
| `analyze_watchlist.py` | $99 | $0 |
| `paper_portfolio.py` | $99 | $0 |
| `paper_engine_alpaca.py` | $0 (free tier sufficient) | N/A (requires execution) |

**Annual savings from dual-source:** ~$1,188 (avoiding Unlimited tier)

---

## Failure Mode Analysis

### Alpaca Failure Scenarios

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| API down | Trading halts | yfinance fallback for analysis |
| Rate limit hit | Status checks fail | yfinance completely offline-capable |
| Auth expired | All Alpaca calls fail | yfinance works without credentials |
| Network partition | Real-time data lost | yfinance may be cached locally |

### yfinance Failure Scenarios

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| Yahoo API change | Analysis scripts break | Alpaca as fallback for critical data |
| Rate limit | Temporary 403 errors | Retry logic, Alpaca fallback |
| Data delay | Historical data stale | Alpaca real-time for execution |

---

## Strategic Recommendations

### Keep Current Architecture

**Rationale:**
1. **Cost efficiency:** Save $1,188/year vs Alpaca Unlimited
2. **Reliability:** Dual-source = redundancy
3. **Accessibility:** Analysis tools work without setup
4. **Performance:** No rate limiting on scans

### Selective Improvements

**High Priority:**
1. **Add `--realtime` flag to `paper_portfolio.py`**
   - Use Alpaca when available
   - Fallback to yfinance EOD
   - Show price source in output

2. **Document price source in UI**
   - "(EOD Close)" vs "(Real-time)"
   - Explain 3-5% after-hours variance is expected

**Low Priority:**
1. **Migrate SPY regime checks to Alpaca**
   - Only if 15-min delay causes issues
   - Currently acceptable for broad trend

2. **Add price source indicators in reports**
   - Clarify data freshness in HTML reports

---

## Conclusion

The dual-source architecture is **correct and intentional**:

- **yfinance** = Analysis, scanning, offline tools
- **Alpaca** = Real-time execution, order management

This is not technical debt - it's **strategic architecture** that:
1. Reduces costs by $1,188/year
2. Improves reliability through redundancy
3. Makes tools accessible without API setup
4. Protects rate limits for critical trading functions

**Recommended action:** Add `--realtime` option to `paper_portfolio.py` for users who want Alpaca prices, but keep yfinance as default for the reasons above.
