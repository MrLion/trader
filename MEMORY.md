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

**Stage 2 Score Criteria (7-Point System):**
1. Price > 50-day SMA (1 pt)
2. Price > 100-day SMA (1 pt)
3. Price > 200-day SMA (1 pt)
4. MA Alignment: 50 > 100 > 200 (1 pt)
5. 200-day SMA rising for 20+ days (1 pt)
6. Within 25% of 52-week high (1 pt)
7. Price ≥ 1.25× 52-week low (1 pt)

**Compliance Thresholds:**
- 6-7 pts: Excellent Stage 2 (Tier 1 quality) 🟢
- 4-5 pts: Good Stage 2 (Tier 2 quality) 🟡
- <4 pts: Developing (Tier 3) 🔴

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
- **Stage 2 Score (7-point system: 50/100/200 MA, Alignment, 200MA Slope, 52w High/Low)**
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

---

## Output Format Selection Guide

**Console Output (Default)**
- Uses ASCII tables, ANSI color codes, monospace formatting
- Best for: Terminal viewing, local console output
- Script: `entry_signals.py` default mode

**Plain Text Output**
- Clean text without tables or special formatting
- Best for: Telegram, email, SMS, copy-paste to notes
- Template: `docs/templates/stock_analysis.md`
- Use when: Output might be viewed in messaging apps or non-monospace contexts

**When to use each:**
- Telegram posts → Plain text template
- Terminal review → Console output
- Email reports → Plain text template
- Quick scanning → Console output with colors
- Archiving/sharing → Plain text template

---

## Versioning Convention (2026-04-29)

**Format:** `WW.XX.YY.ZZ`

| Digit | Bump When | Examples |
|-------|-----------|----------|
| **ZZ** | Fixes, improvements, chores | bug fix, refactors, cleanups, docs patches |
| **YY** | Features | new capability that changes what the system can DO |
| **XX** | Minor releases | milestone completion, multi-feature bundle, significant architectural change |
| **WW** | Major releases | breaking changes, new engine, strategy overhaul |

**Workflow:**
1. Do the work
2. Update `CHANGELOG.md`
3. Bump `VERSION`
4. `git commit`
5. `git tag -a v$VERSION -m "$message"`


**Clarification:**
- **ZZ (improvement)** — Bug fixes, refactors, cleanups, docs patches, better UX, new columns on existing tables, new UI elements on existing screens, new panels on existing dashboards, new scripts that are thin wrappers or organizers, keyboard shortcuts, color coding, layout tweaks, performance gains
- **YY (feature)** — Entirely new capability the system did not have before: new strategy type, new data integration, backtesting engine, automated trading, Telegram delivery, earnings gating, new screening algorithm

**Rule of thumb:** If it adds a file but doesn't change what the system can *do* for the trader, it's ZZ. If it unlocks a new capability the trader didn't have before, it's YY.
---

## Roadmap Management (2026-04-30)

The roadmap lives in `plans/roadmap-2026.md`. It tracks **version-level milestones only** — not individual fixes, patches, or sub-features.

- **What goes on the roadmap:** net-new versions with a distinct theme (UX, Safety, Insight, Capability, Accessibility). Each row is one discrete phase of work.
- **What stays off:** patches, bug fixes, incremental improvements, or sub-items of an existing version. Those live in version-specific plans under `docs/superpowers/plans/` and get marked there.
- **Every version row must link to its plan and spec/design doc** (if they exist). No bare entries. The plan is the source of truth for sub-items and completion status; the roadmap is just the index.
- **Statuses:** `TBD` → `Partially Shipped` (core done, some sub-items remain) → `Shipped` (all plan sub-items complete). Never mark `Shipped` until the linked plan has every item checked off.
- **On ship:** update `Latest Shipped` in the header, mark status. If partially shipped, note what remains.
- **Version narratives follow who-why-what-how:** who it's for (the trader), why it matters (the pain point), what's being built, and how (the approach). Keep each section to 2-3 sentences. The table is the index; the sections carry the context.
- **When adding a new version:** write the plan first (in `docs/superpowers/plans/`), then add the row to the roadmap with links. Aspirational rows (no plan yet) are allowed as north-star direction — mark Design and Plan as `—` and keep them at the bottom of the table.
