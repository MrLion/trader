# Entry Signals: Tier Scoring System

**Script:** `scripts/entry_signals.py`

This document explains the tier classification logic, scoring components, and output categories used by the Entry Signals Scanner.

---

## Overview

The Entry Signals Scanner ranks watchlist stocks by **Entry Score** (0-100) and classifies them into tiers based on setup quality. The system uses a **dual-requirement** logic: both Entry Score AND Stage 2 Score must meet thresholds.

---

## Tier Classification Logic

### Dual-Requirement Formula

```python
if entry_score >= 60 and stage2 >= 6:
    tier = "Tier 1"
elif entry_score >= 40 and stage2 >= 5:
    tier = "Tier 2"
else:
    tier = "Tier 3"
```

| Tier | Entry Score | Stage 2 Score | Meaning |
|------|-------------|---------------|---------|
| **Tier 1** | ≥ 60 | ≥ 6/8 | Best entry setups — ready now |
| **Tier 2** | ≥ 40 | ≥ 5/8 | Good setups — wait for better entry |
| **Tier 3** | < 40 | any | Monitor only — too far or too wide |

**Key:** A high entry score alone is NOT enough. Tier 1 requires Stage 2 ≥ 6. Tier 2 requires Stage 2 ≥ 5.

---

## Entry Score Components (Max 100 Points)

Entry score is calculated by `traderlib.stage2_utils.get_entry_score()`:

| Component | Criteria | Points |
|-----------|----------|--------|
| **Stage 2 Score** | 7-8/8 | +30 |
| | 6/8 | +25 |
| | 5/8 | +20 |
| | 4/8 | +15 |
| | 3/8 | +10 |
| | 2/8 | +5 |
| **Risk %** | < 10% | +30 |
| | < 15% | +20 |
| | < 20% | +10 |
| | < 25% | +5 |
| **Distance to Pivot** | < 3% | +25 |
| | < 5% | +15 |
| | < 10% | +5 |
| **6M Momentum** | > 50% | +15 |
| | > 25% | +10 |
| **RS vs SPY** | > 20% | +10 |
| | > 10% | +5 |
| **MA Penalties** | Below 50 MA | -20 |
| | Below 20 MA | -10 |

---

## Output Categories (Console Display)

The scanner categorizes results into 5 buckets based on score and proximity to pivot:

| Category | Entry Score | Distance to Pivot | Meaning |
|----------|-------------|-------------------|---------|
| **Ready Now** | ≥ 60 | Within ±1% | Immediate entry candidates |
| **Close to Pivot** | ≥ 60 | 1-3% | Watch for breakout confirmation |
| **Extended** | ≥ 60 | > 3% | High quality but extended from pivot |
| **Tier 2 Watch** | 40-59 | any | Developing setups |
| **Tier 3 / Below** | < 40 | any | Not ready |

**Note:** The `--min-tier` flag filters which categories are displayed:
- `--min-tier 1`: Tier 1 only (Ready Now, Close to Pivot, Extended)
- `--min-tier 2`: Tier 1 + Tier 2
- `--min-tier 3`: All tiers (default)

---

## Console Output Columns

### Ready Now / Close to Pivot / Extended

```
Ticker   Score  Tier   Stage2   Dist         Risk%   ATR%    MA%     Stop   Price      → Pivot     Age
--------------------------------------------------------------------------------------------------------
NVDA     78     Tier 1   7/8    +1.2% 📈    8.5     9.2     7.8     MA     $125.40    $123.90     2m ago
```

| Column | Description |
|--------|-------------|
| **Ticker** | Stock symbol |
| **Score** | Entry Score (0-100) |
| **Tier** | Tier classification (Tier 1/2/3) |
| **Stage2** | Stage 2 score out of 8 |
| **Dist** | Distance to pivot with direction icon (📈 = extended, 📉 = below pivot) |
| **Risk%** | Final risk percentage (tighter of ATR/MA) |
| **ATR%** | ATR-based stop risk % |
| **MA%** | MA Support Stop risk % (— if not applicable) |
| **Stop** | Stop type used (ATR or MA) |
| **Price** | Current price |
| **→ Pivot** | Pivot/breakout price |
| **Age** | Time since signal generated (s/m/h ago) |

### Tier 2 Watch

```
Ticker   Score  Tier   Stage2   Dist         Risk%   Current    → Pivot
------------------------------------------------------------------------
AAPL     52     Tier 2   5/8    -2.1% 📉    12.3    $178.50    $182.30
```

### Tier 3 / Below Threshold

```
Ticker   Score  Tier   Stage2   Dist         Risk%   Current    → Pivot
------------------------------------------------------------------------
TSLA     28     Tier 3   3/8    +8.5% 📈    18.2    $245.00    $225.80
```

---

## Signal Age Tracking

Each signal includes a timestamp when generated. The **Age** column shows how fresh the signal is:

- `< 60s`: Displayed as `Xs ago`
- `< 1h`: Displayed as `Xm ago`
- `> 1h`: Displayed as `Xh ago`

**Why it matters:** Stale signals (> 1h old) may indicate outdated pivots or price action that has moved on.

---

## Dual Risk Parameters

The scanner calculates two stop types and uses the tighter (higher) stop:

1. **ATR Stop:** `current_price - (2 × ATR(14))`
2. **MA Support Stop:** Based on clustered moving averages below price

**Final Stop Selection:**
```python
if ma_support_stop and ma_support_stop > atr_stop:
    stop = ma_support_stop  # MA stop is tighter
    stop_type = 'MA'
else:
    stop = atr_stop  # ATR stop is tighter or MA not available
    stop_type = 'ATR'
```

This gives you two risk percentages in the output:
- **ATR%:** Risk if using ATR stop
- **MA%:** Risk if using MA Support Stop (— if not applicable or wider)

---

## Market Condition Filter

The scanner checks SPY market conditions before displaying signals:

```
📊 Market Condition: SPY +0.42%
```

If SPY declines more than the configured threshold (default: -0.5% from prior close):

```
⚠️  Market filter blocking entries
   Reason: SPY declined more than 0.5% from prior close
   Resets when: SPY closes above prior day high or filter threshold adjusted
   Note: Use --i-know-what-im-doing flag to override (not recommended during downtrends)
```

**Note:** Signals are still calculated and displayed, but the market warning indicates elevated risk.

---

## Configuration

Tier thresholds and entry criteria are configured in `config/risk_config.yaml`:

```yaml
entry:
  min_entry_score: 60          # Minimum score for Tier 1
  max_dist_to_pivot_pct: 2.0   # Maximum distance for "Ready Now"
  min_volume_ratio: 1.5        # Minimum volume confirmation
```

Override via environment variables:
```bash
RISK_ENTRY_MIN_ENTRY_SCORE=50 python3 scripts/entry_signals.py
RISK_ENTRY_MAX_DIST_TO_PIVOT_PCT=3.0 python3 scripts/entry_signals.py
```

---

## Export Formats

Signals can be exported in multiple formats:

```bash
# CSV export
python3 scripts/entry_signals.py --export-csv

# HTML report
python3 scripts/entry_signals.py --export-html

# JSON export
python3 scripts/entry_signals.py --export json
```

**HTML Report Sections:**
- Tier 1 (Ready Now) table with all columns
- Tier 2 (Score 40-59) table
- Tier 3 signals excluded from HTML (too many, low priority)

---

## Related Documentation

- **[TOOLS.md](../../TOOLS.md)** — yfinance usage, script commands
- **[docs/RISK_GUIDE.md](../RISK_GUIDE.md)** — Position sizing, stop loss methodology
- **[AGENTS.MD](../../AGENTS.MD)** — Entry protocol, trading rhythm
- **[traderlib/stage2_utils.py](../../traderlib/stage2_utils.py)** — Source code for scoring functions

---

## Quick Reference

```bash
# Scan watchlist for Tier 1 signals
python3 scripts/entry_signals.py

# Include Tier 2 signals
python3 scripts/entry_signals.py --min-tier 2

# Deep dive single ticker
python3 scripts/entry_signals.py --ticker AAPL

# Export HTML report
python3 scripts/entry_signals.py --export-html
```

**Entry Criteria Summary:**
- Tier 1: Score ≥ 60, Stage 2 ≥ 6, within ±1% of pivot
- Tier 2: Score ≥ 40, Stage 2 ≥ 5
- Market filter: SPY must not decline > 0.5% from prior close
