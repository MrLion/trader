# MEMORY.md — Long-Term Memory

## Scan Naming Conventions

**Date Format:** `YYYY-MM-DD`

**Sector/Industry Rankings:**
- `leading_sectors_YYYY-MM-DD.csv` — Main sector rankings
- `leading_sectors_ranks_YYYY-MM-DD.csv` — With rank scores
- `leading_sectors_summary_YYYY-MM-DD.csv` — Summary view

**Stock Scans:**
- `leading_stocks_YYYY-MM-DD.csv` — Main Stage 2 candidates
- `leading_stocks_sectors_YYYY-MM-DD.csv` — By sector group
- `leading_stocks_telecom_YYYY-MM-DD.csv` — Telecom focus
- `leading_stocks_initial_YYYY-MM-DD.csv` — Initial broad scan

**Location:** `/scans/` folder

**Process:**
1. Run sector rankings first
2. Identify leading sectors (top 3-5)
3. Run Stage 2 scan on stocks within those sectors
4. Save with date stamp
5. **Generate HTML report** to `reports/EOD_Report_YYYY-MM-DD.html`
6. **Post to channel** with HTML file attached (summary text + document attachment)
7. Use `--force-document` flag for HTML files

**Last Updated:** 2026-04-06

---

## Stock Analysis Format (Template)

**Script:** `scripts/analyze_ticker.py`

**Command:** `python3 scripts/analyze_ticker.py TICKER`

**Example Output:**
```
TICKER (Company Name) — $PRICE

| Metric | Value |
|:-------|:------|
| Company | [Full Name] |
| Sector | [GICS Sector] |
| Industry | [Sub-industry] |
| 1M Return | [+%] |
| 3M Return | [+%] |
| 6M Return | [+%] |
| Stage 2 Score | [X/4] [🟢/🟡/🔴] |
| From 52W High | [X%] |
| Above All MAs | [✓/✗] 20/50/150/200 |

---

ENTRY SETUP

| Level | Price |
|:------|:------|
| Entry | $X.XX (break above / your pivot) |
| Stop | $X.XX (2 ATR / below support) |
| Risk | X% |

Assessment:
- **Momentum** — 1M/3M/6M trend analysis
- **Stage 2** — Technical condition
- **Distance from highs** — Risk evaluation  
- **Risk level** — Acceptable or too wide

Verdict: [A-TIER / TIER B / TIER C / PASS]
```

**Stage 2 Score Criteria (4 points):**
1. Price above 150-day SMA
2. Price above 200-day SMA
3. MA alignment (20 > 50 > 150 > 200)
4. Within 15% of 52-week high

**Command Format:** `Analyze $TICKER` (e.g., Analyze $AAPL)

**Standard Output Structure:**

```
TICKER (Company Name) — $PRICE

| Metric | Value |
|:-------|:------|
| Company | [Full Name] |
| Sector | [GICS Sector] |
| Industry | [Sub-industry] |
| 1M Return | [+%] |
| 3M Return | [+%] |
| 6M Return | [+%] |
| Stage 2 Score | [X/4] [🟢/🟡/🔴] |
| From 52W High | [X%] |
| Above All MAs | [✓/✗] 20/50/100/200 |

---

ENTRY SETUP

| Level | Price |
|:------|:------|
| Entry | $X.XX (break above / pullback to) |
| Stop | $X.XX (2 ATR / below support) |
| Risk | X% |

Assessment:
- **Momentum** — 1M/3M/6M trend analysis
- **Stage 2** — Technical condition
- **Distance from highs** — Risk evaluation
- **Risk level** — Acceptable or too wide

Verdict: [A-TIER / PASS / WAIT]
```

**Key Elements to Include:**
- Company name and sector/industry classification
- Returns (1M, 3M, 6M) for momentum context
- **Stage 2 Score (4 criteria: above 100SMA, above 200SMA, MA bullish, near 52W high)**
- Distance from 52W highs (%)
- Entry/stop/risk calculation (2 ATR standard)
- Visual status (🟢 = strong, 🟡 = developing, 🔴 = weak)
- Clear verdict with rationale

---

## Report Posting Workflow

**For EOD and Pre-Market Reports:**

1. Generate HTML report → `reports/EOD_Report_YYYY-MM-DD.html`
2. Post summary + attach HTML file:

```bash
openclaw message send --channel telegram --account trader --target 47258942 \
  --message "📊 EOD Report — April 6, 2026\n\nRegime: [status]\nA-Tier: [tickers]\n\nFull report attached." \
  --media /Users/mintmrlion/.openclaw/workspaces/trader/reports/EOD_Report_YYYY-MM-DD.html \
  --force-document
```

**Key:** Use `--force-document` so Telegram treats HTML as file, not image preview.

**Reports Location:** `/Users/mintmrlion/.openclaw/workspaces/trader/reports/`

**Last Updated:** 2026-04-06

---

## Watchlist Analysis Format

**Script:** `scripts/analyze_watchlist.py`

**Command:** `python3 scripts/analyze_watchlist.py`

**Purpose:** Analyze entire watchlist and rank stocks by entry favorability

**Scoring System:**
- Stage 2 Score ≥4: +30 pts | ≥3: +20 pts | ≥2: +10 pts
- Risk <10%: +30 pts | <15%: +20 pts | <20%: +10 pts
- Distance to Pivot <3%: +25 pts | <5%: +15 pts | <10%: +5 pts
- 6M Return >50%: +15 pts | >25%: +10 pts

**Tier Thresholds:**
- **Tier 1 (Score ≥60):** Best entry setups — ready now
- **Tier 2 (Score 40-59):** Good setups — wait for better entry
- **Tier 3 (Score <40):** Monitor only — too far or too wide

**Output Format:**
```
🎯 WATCHLIST ENTRY RANKINGS — Ranked by Favorability

**🟢 TIER 1 — BEST ENTRY SETUP (Score ≥60)**
Ticker   Price   Pivot   Dist%   Risk%   Stage2   6M      Sector
ANAB     $62.43  $60.10  -3.7%   9.8%    4/4 🟢   +168.3% Healthcare

**🟡 TIER 2 — GOOD SETUP (Score 40-59)**
STRL     $393.71 $420.00 +6.7%   10.7%   4/4 🟡   +15.4%  Industrials

**🔴 TIER 3 — WAIT / MONITOR (Score <40)**
(none)

SUMMARY: X Tier 1 | Y Tier 2 | Z Tier 3 | Total: N

🎯 TOP 3 RECOMMENDATIONS:
  1. TICKER — X% from pivot, Y% risk, Stage 2 Z/4
```

**When to Run:**
- Weekly: After populating new watchlist
- Daily: Pre-market to identify ready setups
- After adding new stocks to watchlist

**Action Rules:**
- Tier 1 + within 2% + risk <10% = Ready for immediate entry
- Tier 1 + 2-5% from pivot = Set price alert at pivot
- Tier 2 = Wait for pullback or base formation
- Tier 3 = Remove or monitor only
