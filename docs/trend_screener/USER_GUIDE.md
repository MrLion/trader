# Trend Screener User Guide

**Script:** `scripts/trend_screener.py`

A discovery tool that combines MarketSurge-style trend filters with MA (Moving Average) convergence detection to find stocks with optimal support zones and VCP (Volatility Contraction Pattern) patterns.

---

## Quick Start

```bash
# Discovery mode - find stocks with MA convergence across the market
python3 scripts/trend_screener.py --profile large-cap --rank-by convergence

# Entry timing - rank your watchlist by setup readiness
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

# Single ticker deep dive with MA data
python3 scripts/trend_screener.py --tickers AAPL --show-ma-data

# Detect VCP patterns in candidates
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp
```

---

## Two Modes of Operation

### 1. Discovery Mode (Market-Wide Scan)

Scans the entire market to find stocks meeting your criteria.

```bash
# Scan large-cap universe ($80M+ daily dollar volume)
python3 scripts/trend_screener.py --profile large-cap

# Scan high-octane stocks ($20M+ daily dollar volume, more volatile)
python3 scripts/trend_screener.py --profile high-octane

# Filter by minimum convergence score
python3 scripts/trend_screener.py --profile large-cap --min-convergence-score 60

# Export results to CSV
python3 scripts/trend_screener.py --profile large-cap --export-csv scans/trend_screen.csv
```

**How Discovery Works:**
1. Fetches ~13,500 active US equities from Alpaca
2. Filters out ETFs, OTC/AMEX stocks, illiquid names
3. Applies MarketSurge-style trend filters (MA stacking, price above MAs)
4. Calculates MA convergence scores for survivors
5. Ranks by convergence score or RS

**Universe Profiles:**

| Profile | Min Dollar Volume | Min Shares/day | Use Case |
|---------|-------------------|----------------|----------|
| `large-cap` | $80M+ | 1M+ | Stable, institutional names |
| `high-octane` | $20M+ | 400K+ | More volatile, momentum names |

### 2. Entry Timing Mode (Watchlist Analysis)

Analyzes your existing watchlist to find the best setups.

```bash
# Rank watchlist by setup readiness (proximity to pivot)
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup

# Rank by RS strength (best performers first)
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by rs

# Entry mode: find stocks near pivot points
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --entry-mode pivot

# Entry mode: find VCP breakout candidates
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --entry-mode vcp
```

**Entry Modes:**

| Mode | Description | Best For |
|------|-------------|----------|
| `pivot` | Stocks within 5% of pivot price | Traditional breakouts |
| `vcp` | VCP pattern near pivot | Contraction breakouts |
| `pullback` | Pullback to MA support | MA support plays |

---

## CLI Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--profile` | Universe profile: `large-cap`, `high-octane` | `large-cap` |
| `--ticker-file` | Path to ticker file (one per line) | None (uses universe) |
| `--tickers` | Specific tickers to analyze (comma-separated) | None |
| `--rank-by` | Ranking: `convergence`, `setup`, `rs` | `convergence` |
| `--entry-mode` | Entry mode: `pivot`, `vcp`, `pullback` | None |
| `--min-convergence-score` | Minimum convergence score (0-100) | 0 |
| `--detect-vcp` | Detect and display VCP patterns | False |
| `--show-ma-data` | Show detailed MA data in output | False |
| `--export-csv` | Export results to CSV | False |
| `--top` | Show only top N results | 20 |
| `--force-refresh` | Bypass cache, rebuild universe | False |

---

## Understanding Output

### Console Output Format

```
Trend Screener Results — 2026-04-17
Profile: large-cap | Ranked by: convergence

Grade A (Score 70-100) — Optimal MA convergence
┌─────────────────────────────────────────────────────────────────────────┐
│ Ticker   Price    Conv   Grade   Cluster        Pivot     Dist%   RS%   │
│ NVDA     $125.40   85    A      [20,50,100]   $123.90   +1.2%   +45%   │
│ MSFT     $412.30   78    A      [20,50,100]   $410.00   +0.6%   +22%   │
└─────────────────────────────────────────────────────────────────────────┘

Grade B (Score 50-69) — Good convergence
┌─────────────────────────────────────────────────────────────────────────┐
│ AAPL     $178.50   62    B      [20,50]       $182.30   -2.1%   +18%   │
└─────────────────────────────────────────────────────────────────────────┘

Progress: Batches ━━━━━━━━━━━━ 12/12 • ETA: 0s
Scan completed in 70.3s
Found 23 candidates
```

### Columns Explained

| Column | Description |
|--------|-------------|
| **Ticker** | Stock symbol |
| **Price** | Current price |
| **Conv** | Convergence score (0-100) |
| **Grade** | A (70-100), B (50-69), C (30-49) |
| **Cluster** | MAs in cluster (e.g., [20,50,100]) |
| **Pivot** | Pivot/breakout price |
| **Dist%** | Distance from pivot (+ = extended, - = below) |
| **RS%** | Relative strength vs SPY (6-month) |

### Convergence Grades

| Grade | Score Range | Meaning | Action |
|-------|-------------|---------|--------|
| **A** | 70-100 | Optimal MA convergence, tight cluster | Prime candidate |
| **B** | 50-69 | Good convergence, some separation | Watch list |
| **C** | 30-49 | Weak convergence, wide spread | Monitor only |

---

## VCP Pattern Detection

Use `--detect-vcp` to identify Volatility Contraction Patterns:

```bash
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp
```

**VCP Output:**
```
NVDA: VCP Detected — VALID
  Contractions: 3
  Depths: 22% → 11% → 5% (progression valid ✓)
  Volume: Drying up ✓
  Pivot: $126.50
  Stop: $118.20
```

**Valid VCP Criteria:**
- Minimum 2 contractions
- Each contraction < 70% depth of prior (progression)
- Volume declining through pattern
- Price near pivot (within 1-5%)

See [docs/patterns/VCP.md](../patterns/VCP.md) for detailed VCP methodology.

---

## MA Convergence Scoring

Convergence scores (0-100) quantify the quality of MA clustering below price.

### Scoring Components (100 points total)

| Component | Max Points | How It's Calculated |
|-----------|------------|---------------------|
| **Tightness** | 30 | Inverse of cluster spread (tighter = better) |
| **Cluster Size** | 25 | Number of MAs in cluster (more = better) |
| **Price Distance** | 15 | How close price is to cluster (closer = better) |
| **Risk Improvement** | 30 | Stop improvement vs ATR-only stop |

### Cluster Detection

A valid cluster requires:
1. Minimum 2 MAs below price (from ma10, ma20, ma50, ma100, ma200)
2. Cluster spread ≤ 5%: `(highest_ma - lowest_ma) / highest_ma ≤ 0.05`
3. MA support stop at `lowest_ma × (1 - buffer)` where buffer = 1%

See [docs/trend_screener/MA_CONVERGENCE.md](MA_CONVERGENCE.md) for algorithm details.

---

## Example Workflows

### Workflow 1: Daily Discovery

```bash
# 1. Run discovery scan (large-cap universe)
python3 scripts/trend_screener.py --profile large-cap --export-csv scans/trend_$(date +%Y-%m-%d).csv

# 2. Review top candidates
python3 scripts/trend_screener.py --profile large-cap --top 30

# 3. Deep dive on promising names with VCP check
python3 scripts/trend_screener.py --tickers NVDA,MSFT,AAPL --detect-vcp --show-ma-data

# 4. Add promising names to watchlist
python3 scripts/watchlist_manager.py add NVDA "VCP breakout setup, MA cluster support"
```

### Workflow 2: Watchlist Timing

```bash
# 1. Rank watchlist by setup readiness
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --top 20

# 2. Focus on names near pivots
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --entry-mode pivot --min-convergence-score 50

# 3. Export actionable setups
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup --export-csv scans/watchlist_setups.csv
```

### Workflow 3: Sector Rotation Scan

```bash
# 1. Scan for leaders in specific sector (tech)
python3 scripts/trend_screener.py --tickers NVDA,MSFT,AAPL,GOOGL,META,AVGO --rank-by rs

# 2. Check convergence on sector leaders
python3 scripts/trend_screener.py --tickers NVDA,MSFT,AAPL --show-ma-data

# 3. Detect VCP on extended names (wait for contraction)
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp
```

---

## Progress Bar & Timing

The screener uses a Rich progress bar with per-batch ETA:

```
Batches ━━━━━━━━━━━━ 12/12 • ETA: 45s
```

- Processes tickers in batches of 100
- ETA calculated per-batch (more stable than per-ticker)
- Single-line display (no 100+ lines of spam)
- Timing displayed: "Built universe in 12.4s", "Scan completed in 70.3s"

---

## Cache Behavior

Universes are cached for 4 hours with same-day invalidation:

```
Cache hit: large_cap_2026-04-17.csv (age: 1.2h)
Funnel: 13,552 → 7,297 → 4,637 → 1,147
```

**Cache Invalidation:**
- Same-day cache with 4-hour TTL
- Auto-refreshes after market open
- Use `--force-refresh` to bypass cache

**Funnel Metrics on Cache Hit:**
- Shows actual counts from when cache was built
- Example: 13,552 total assets → 1,147 after all filters

---

## Troubleshooting

### "No candidates found"
- Check if market is open (cache may be stale)
- Try `--force-refresh` to rebuild
- Lower `--min-convergence-score` threshold
- Try `high-octane` profile for more candidates

### "API rate limit exceeded"
- Paid tier: 10,000 req/min handles rapid requests
- Free tier: Consider upgrading or running during off-peak

### "VCP detection failed"
- Requires 200 days of history for proper swing detection
- Check if ticker has sufficient trading history

### Cache showing zeros
- Bug fixed in v0.6.1.2
- If still seeing zeros, delete cache and re-run:
  ```bash
  rm data/universes/*.csv
  python3 scripts/trend_screener.py --profile large-cap
  ```

---

## Related Documentation

- [MA_CONVERGENCE.md](MA_CONVERGENCE.md) — Scoring algorithm deep dive
- [../patterns/VCP.md](../patterns/VCP.md) — VCP pattern detection guide
- [../strategies/VCP_BREAKOUT.md](../strategies/VCP_BREAKOUT.md) — VCP breakout strategy
- [../METHODOLOGY.md](../METHODOLOGY.md) — Stage 2 methodology
- [TOOLS.md](../../TOOLS.md) — yfinance usage, script commands

---

## Quick Reference

```bash
# Discovery
python3 scripts/trend_screener.py --profile large-cap --rank-by convergence
python3 scripts/trend_screener.py --profile high-octane --top 30

# Watchlist timing
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --rank-by setup
python3 scripts/trend_screener.py --ticker-file data/watchlist.csv --entry-mode pivot

# Single ticker analysis
python3 scripts/trend_screener.py --tickers AAPL --show-ma-data
python3 scripts/trend_screener.py --tickers NVDA --detect-vcp

# Export
python3 scripts/trend_screener.py --profile large-cap --export-csv scans/trend.csv
```
