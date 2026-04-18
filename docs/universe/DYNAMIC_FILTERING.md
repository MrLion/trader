# Dynamic Universe Filtering

**Module:** `traderlib/universe_builder.py`

Dynamic universe building fetches active US equities from Alpaca and applies a prefilter pipeline to create tradable stock universes.

---

## Overview

The universe builder replaces static ticker lists with dynamic filtering:

1. Fetches ~13,500 active US equities from Alpaca
2. Applies filters in order (cheap first, expensive last)
3. Caches results for 4 hours
4. Excludes ETFs via name-pattern detection

**Benefits:**
- No manual ticker list maintenance
- Catches new IPOs automatically
- Removes delisted names automatically
- ETF exclusion without hardcoded lists

---

## The Filtering Funnel

```
Total Assets (13,552)
       ↓
[Tradable Filter] — Remove non-tradable, OTC, AMEX, ETFs (~2,000)
       ↓
After Tradable (7,297)
       ↓
[Price Filter] — Remove stocks below minimum price
       ↓
After Price (4,637)
       ↓
[Dollar Volume Filter] — Remove illiquid names
       ↓
Final Universe (1,147)
```

### Step 1: Tradable Filter (FREE)

```python
filtered = [
    a for a in all_assets
    if getattr(a, 'tradable', False)
    and getattr(a, 'exchange', '') not in exclude_exchanges
    and not is_etf(a)
]
```

**Filters applied:**
- `tradable=True` — Must be tradable on Alpaca
- `exchange not in ['OTC', 'AMEX']` — Exclude OTC/AMEX stocks
- `not is_etf(a)` — Exclude ETFs via name-pattern detection

**ETF Detection:**
```python
def is_etf(asset) -> bool:
    name = asset.name.upper()
    
    # Direct ETF indicators
    if 'ETF' in name or 'EXCHANGE-TRADED FUND' in name:
        return True
    
    # Trusts from known ETF providers
    if 'TRUST' in name:
        etf_providers = ['SPDR', 'QQQ', 'ISHARES', 'VANGUARD', 'INVESCO', 'PROSHARES']
        if any(x in name for x in etf_providers):
            return True
    
    # Fund names that are typically ETFs
    if 'FUND' in name:
        etf_fund_providers = ['WISDOMTREE', 'PIMCO', 'RBB FUND', 'ALPHA ARCHITECT', 'STATE STREET']
        if any(x in name for x in etf_fund_providers):
            return True
    
    return False
```

**Why name-pattern?** Alpaca API doesn't distinguish stocks from ETFs (per official FAQ). Name-pattern detection catches ~2,000 ETFs automatically.

### Step 2: Price Filter (FREE)

```python
# Get current prices for filtered assets
current_prices = self._get_current_prices(tickers_to_check)

# Filter by minimum price
filtered_with_price = [
    a for a in filtered
    if current_prices.get(getattr(a, 'symbol', ''), 0) >= min_price
]
```

**Profile thresholds:**
| Profile | Min Price |
|---------|-----------|
| large-cap | $10 |
| high-octane | $2 |

### Step 3: Dollar Volume Filter (EXPENSIVE)

```python
# Compute average daily dollar volume for survivors
dollar_volumes = self._compute_dollar_volumes(tickers_for_dvol, lookback_days=60)

# Filter by minimum dollar volume
validated = [
    t for t, dvol in dollar_volumes.items()
    if dvol and dvol >= min_dvol
]
```

**Profile thresholds:**
| Profile | Min Dollar Volume | Min Shares |
|---------|-------------------|------------|
| large-cap | $80M+ | 1M+ |
| high-octane | $20M+ | 400K+ |

**Lookback:** 60 days of daily bars

---

## Universe Profiles

### Large-Cap Profile

```yaml
universes:
  large_cap:
    min_price: 10
    min_dollar_volume: 80000000  # $80M
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
```

**Characteristics:**
- ~1,000-1,500 stocks
- Institutional-quality names
- Lower volatility
- Better for position trading

### High-Octane Profile

```yaml
universes:
  high_octane:
    min_price: 2
    min_dollar_volume: 20000000  # $20M
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
```

**Characteristics:**
- ~2,000-3,000 stocks
- Includes growth/momentum names
- Higher volatility
- Better for swing trading

---

## Cache Behavior

Universes are cached with same-day invalidation:

```python
CACHE_TTL_HOURS = 4  # Refresh every 4 hours during market hours

def _get_cache_path(self, profile: str) -> Path:
    today = date.today().strftime('%Y-%m-%d')
    return self.UNIVERSES_DIR / f'{profile}_{today}.csv'
```

### Cache File Format

```csv
Ticker,Profile,GeneratedDate,TotalAssets,AfterTradable,AfterPrice,AfterDVol
AAPL,large_cap,2026-04-17 09:30:00,13552,7297,4637,1147
MSFT,large_cap,2026-04-17 09:30:00,13552,7297,4637,1147
...
```

### Cache Hit Response

```
Cache hit: large_cap_2026-04-17.csv (age: 1.2h)
Funnel: 13,552 → 7,297 → 4,637 → 1,147
Loaded 1,147 tickers in 0.02s
```

### Cache Miss Response

```
Building universe: large_cap
  Fetching assets from Alpaca...
  Fetched 13,552 assets
  Filtered to 7,297 (tradable, exclude OTC, AMEX, ~2,000 ETFs)
  Fetching current prices for 7,297 tickers...
  Received prices for 7,297 tickers
  Filtered to 4,637 (price ≥ $10)
  Computing liquidity metrics for 4,637 stocks (60-day lookback)...
  Filtered to 1,147 (dollar vol ≥ $80M)
  Saved to data/universes/large_cap_2026-04-17.csv
Built universe in 45.3s
```

---

## Usage

### Trend Screener Integration

```bash
# Uses universe_builder internally
python3 scripts/trend_screener.py --profile large-cap

# Force refresh (bypass cache)
python3 scripts/trend_screener.py --profile large-cap --force-refresh
```

### Programmatic Usage

```python
from traderlib.universe_builder import UniverseBuilder

builder = UniverseBuilder()

# Load universe (checks cache first)
result = builder.load_universe('large_cap')

print(f"Tickers: {len(result.tickers)}")
print(f"Funnel: {result.total_assets} → {result.after_tradable_filter} → {result.after_price_filter} → {result.after_dvol_filter}")

# Force rebuild
result = builder.load_universe('large_cap', force_refresh=True)
```

### Export to CSV

```python
# Universe saved automatically to data/universes/
# Load directly:
import pandas as pd
df = pd.read_csv('data/universes/large_cap_2026-04-17.csv')
tickers = df['Ticker'].tolist()
```

---

## Rate Limiting

Universe building makes bulk API calls:

| Step | API Calls | Rate Limit Impact |
|------|-----------|-------------------|
| Fetch assets | 1 call | Negligible |
| Get prices | ~73 batches (100/batch) | ~73 calls |
| Dollar volume | 1 batch call | 1 call |

**Total:** ~75 API calls for full rebuild

**Paid tier:** 10,000 calls/min — no impact
**Free tier:** 200 calls/min — may need delays

---

## Troubleshooting

### "No tickers in universe"

**Possible causes:**
- Cache expired and API failed
- Filters too restrictive
- Market closed (delayed data)

**Solutions:**
```bash
# Force refresh
python3 scripts/trend_screener.py --profile large-cap --force-refresh

# Check API connection
python3 scripts/validate_alpaca.py

# Try high-octane (less restrictive)
python3 scripts/trend_screener.py --profile high-octane
```

### "ETFs still appearing"

**Possible causes:**
- Name-pattern detection missed new ETF provider
- Cache contains old data

**Solutions:**
```bash
# Clear cache
rm data/universes/*.csv

# Rebuild
python3 scripts/trend_screener.py --profile large-cap --force-refresh

# If still appearing, add to extra_false_positives in config
# Edit config/screener_config.yaml
```

### Cache showing zeros

**Fixed in v0.6.1.2** — If still seeing zeros:

```bash
# Clear cache and rebuild
rm data/universes/*.csv
python3 scripts/trend_screener.py --profile large-cap
```

---

## Configuration

Universe settings in `config/screener_config.yaml`:

```yaml
universes:
  default: large_cap
  
  large_cap:
    min_price: 10
    min_dollar_volume: 80000000
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
    
  high_octane:
    min_price: 2
    min_dollar_volume: 20000000
    lookback_days: 60
    exclude_exchanges: ['OTC', 'AMEX']
```

---

## Performance

| Operation | Time |
|-----------|------|
| Cache hit | < 0.1s |
| Full rebuild | 30-60s |
| Price filter | ~10s |
| Dollar volume | ~20-40s |

**Optimization:** Batch processing (100 tickers/batch) reduces API overhead.

---

## Related Documentation

- [../trend_screener/USER_GUIDE.md](../trend_screener/USER_GUIDE.md) — Trend Screener usage
- [../strategies/OVERVIEW.md](../strategies/OVERVIEW.md) — Strategy plugins
- [traderlib/universe_builder.py](../../traderlib/universe_builder.py) — Source code
- [CHANGELOG.md](../../CHANGELOG.md) — ETF exclusion fix (v0.6.1.2)
