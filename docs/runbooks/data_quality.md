# Runbook: Data Quality Issues

**Last Updated:** 2026-04-08  
**Severity:** Medium - Trading signals affected  
**Estimated Recovery Time:** 3-10 minutes

---

## Symptoms

- Entry scores seem "off" (too high or too low)
- Stage 2 scores calculated as 0 for obvious uptrends
- `⚠️ Insufficient historical data (15 bars)` warnings
- Relative Strength (RS) calculations showing impossible values (>100%)
- Pivot distances calculated incorrectly
- ATR showing 0 or negative values

## Diagnosis

### Step 1: Verify Data Source

```bash
# Check which data provider is active
python3 -c "
from alpaca_client import AlpacaClient
client = AlpacaClient()
print(f'Primary: {client.health.primary}')
print(f'Current: {client.health.get_provider()}')
"

# If "yfinance": Using fallback (may be stale)
```

### Step 2: Check Historical Data Freshness

```bash
# Verify data recency
python3 -c "
from alpaca_client import AlpacaClient
import pandas as pd

client = AlpacaClient()
hist = client.get_historical_bars('AAPL', days=5)

if hist is not None:
    last_date = hist.index[-1]
    age = pd.Timestamp.now() - last_date
    print(f'Last data point: {last_date}')
    print(f'Data age: {age}')
    
    if age.days > 1:
        print('⚠️ Stale data detected')
"
```

### Step 3: Check SPY Cache

```bash
# SPY cache affects RS calculations
python3 -c "
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')
print(f'SPY cache date: {engine.spy_cache.get(\"date\")}')
print(f'SPY 6M return: {engine.spy_cache.get(\"return_6m\")}')
"

# Expected: Today's date, return between -20% and +50%
```

### Step 4: Verify Watchlist Data

```bash
# Check if pivot prices are valid
python3 -c "
import pandas as pd
from pathlib import Path

watchlist = pd.read_csv(Path('data/watchlist.csv'))
print(f'Rows: {len(watchlist)}')
print(f'Null pivots: {watchlist[\"Pivot_Price\"].isna().sum()}')
print(f'Zero pivots: {(watchlist[\"Pivot_Price\"] == 0).sum()}')
"
```

## Recovery

### Fix A: Refresh SPY Cache

```bash
# Force SPY cache refresh
python3 -c "
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')
engine.spy_cache['date'] = None  # Force refresh
engine._refresh_spy_cache()
print('✅ SPY cache refreshed')
"
```

### Fix B: Clear Price Cache

```bash
# Clear WebSocket price cache
python3 -c "
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')
engine.price_cache.clear()
print('✅ Price cache cleared')
"
```

### Fix C: Regenerate Historical Data

```bash
# Delete and re-fetch historical data
rm -rf data/cache/*.csv  # If using cache files

# Restart engine to fetch fresh data
python3 scripts/paper_engine_alpaca.py
```

### Fix D: Fix Watchlist Issues

```python
# Correct invalid pivot prices
import pandas as pd
from pathlib import Path

watchlist = pd.read_csv(Path('data/watchlist.csv'))

# Fix zero/negative pivots
watchlist.loc[watchlist['Pivot_Price'] <= 0, 'Pivot_Price'] = \
    watchlist.loc[watchlist['Pivot_Price'] <= 0, 'Current_Price'] * 1.02

watchlist.to_csv(Path('data/watchlist.csv'), index=False)
print('✅ Watchlist corrected')
```

### Fix E: Reset Data Directory (Nuclear Option)

**Warning:** This clears all cached data and positions

```bash
# Backup first
cp -r data data.backup.$(date +%Y%m%d_%H%M)

# Clear cache
rm -rf data/paper_positions.json
rm -rf data/paper_account.json
rm -rf data/cache/*

# Re-initialize
python3 scripts/setup_alpaca.py --reset
```

## Common Data Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Stage 2 = 0 | Insufficient history (<30 days) | Wait for more data or skip ticker |
| RS > 100% | SPY cache stale | Refresh SPY cache |
| ATR = 0 | Flat stock or 1-day data | Use minimum ATR of 0.5% |
| Pivot distance NaN | Missing pivot price | Update watchlist.csv |
| Score > 100 | Risk override not applied | Check risk_pct calculation |

## Prevention

### 1. Daily Data Validation

Add to `paper_engine_alpaca.py`:

```python
def _validate_data_quality(self, hist, ticker):
    """Check data quality before using."""
    if hist is None or len(hist) < 30:
        return False, "Insufficient history"
    
    if hist['Close'].std() == 0:
        return False, "Flat price data"
    
    last_date = hist.index[-1]
    if (datetime.now() - last_date).days > 2:
        return False, "Stale data"
    
    return True, "OK"
```

### 2. Automated Cache Warnings

```python
# Log warning if cache is old
if self.spy_cache['date'] != today:
    print(f"⚠️ SPY cache from {self.spy_cache['date']}, recalculating...")
```

### 3. Data Quality Dashboard

```bash
# Add to daily report
python3 -c "
from paper_engine_alpaca import AlpacaPaperEngine
engine = AlpacaPaperEngine(mode='paper')

print('=== Data Quality Check ===')
print(f'SPY cache: {engine.spy_cache[\"date\"]}')
print(f'Price cache entries: {len(engine.price_cache)}')
print(f'Price cache age: check timestamps')
"
```

## Validation Checklist

Before trading each day:

- [ ] SPY cache date = today
- [ ] Watchlist has no null pivot prices
- [ ] Historical data < 24 hours old
- [ ] Sample 3 tickers: Stage 2 scores look reasonable (0-7)
- [ ] Sample 3 tickers: Entry scores look reasonable (0-100)

## Related

- [API Outage Runbook](./api_outage.md) - Data source failures
- Entry Score Documentation: README.md
- yfinance fallback: Automatic when Alpaca fails
