# MC Stock Scraper Merge Implementation Plan (Revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--mode historical` flag to existing `mcstock_scraper.py` to support date-range scraping, then delete `mcstock_historical_scraper.py`. Keep `mcstock_scraper.py` as the filename.

**Architecture:** Extend existing `mcstock_scraper.py` with a new `--mode` argument supporting `single` (default, today's report) and `historical` (date range). Extract shared code from `mcstock_historical_scraper.py` into `mcstock_scraper.py`, then delete the historical scraper.

**Tech Stack:** Python 3.11, requests, beautifulsoup4, python-dotenv, pandas

---

## File Structure

**Files to Modify:**
- `scripts/mcstock_scraper.py` — Add `--mode historical` support

**Files to Delete:**
- `scripts/mcstock_historical_scraper.py` — Replaced by new functionality

**Files to Create:**
- `tests/test_mcstock_scraper.py` — Tests for unified scraper

---

## Analysis: Code to Port from mcstock_historical_scraper.py

The historical scraper has these functions to integrate:
- `generate_trading_dates()` — Generate Mon-Fri dates (lines 155-186)
- `build_report_url()` — Build historical URL (lines 189-200)
- `extract_tickers_from_report()` — Extract tickers (lines 226-300)
- `scrape_historical()` — Main historical loop (lines 313-367)
- `save_to_csv()` — Save historical format (lines 370-388)

---

### Task 1: Add Mode Argument and Single Mode Support

**Files:**
- Modify: `scripts/mcstock_scraper.py`

**Purpose:** Add `--mode` argument and single mode execution flow.

- [ ] **Step 1: Add --mode argument to argparse**

In the existing `main()` function in `mcstock_scraper.py`, modify the argument parser:

```python
def main():
    parser = argparse.ArgumentParser(
        description='Scrape trade ideas from MC Stock Charts'
    )
    parser.add_argument(
        '--mode',
        choices=['single', 'historical'],
        default='single',
        help='Scraping mode: single (today or specific date) or historical (date range)'
    )
    # ... keep existing arguments ...
```

- [ ] **Step 2: Add mode dispatch in main**

Replace the existing main logic with mode dispatch:

```python
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    try:
        # Get credentials
        try:
            username, password = get_credentials()
        except ValueError as e:
            logger.error(f"❌ {e}")
            sys.exit(EXIT_CONFIG_ERROR)

        # Create session
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        # Login
        if not login(session, username, password):
            logger.error("❌ Authentication failed")
            sys.exit(EXIT_AUTH_FAILED)

        # Execute based on mode
        if args.mode == 'single':
            run_single_mode(session, args, logger)
        elif args.mode == 'historical':
            run_historical_mode(session, args, logger)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Interrupted by user")
        sys.exit(EXIT_SUCCESS)
```

- [ ] **Step 3: Create run_single_mode function**

Extract the existing main logic into `run_single_mode()`:

```python
def run_single_mode(session: requests.Session, args, logger):
    """Execute single mode scraping (today or specific date)."""
    # Fetch report
    try:
        html = fetch_report(session, args.date)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(EXIT_REPORT_NOT_FOUND)
    except PermissionError as e:
        logger.error(f"❌ {e}")
        sys.exit(EXIT_AUTH_FAILED)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        sys.exit(EXIT_NETWORK_ERROR)

    # Load config
    config = load_scraper_config(args.config)

    # Extract tickers
    ideas = extract_tickers(html, config=config)

    if not ideas:
        logger.warning("⚠️ No trade ideas found in report")
        sys.exit(EXIT_SUCCESS)

    logger.info(f"📝 Found {len(ideas)} potential ideas")

    # Validate tickers (unless skipped)
    if not args.skip_validation:
        ideas = validate_tickers(ideas, config=config)

    if not ideas:
        logger.warning("⚠️ No ideas passed validation")
        sys.exit(EXIT_SUCCESS)

    # Dry run or save
    if args.dry_run:
        logger.info("\n📋 DRY RUN - Found ideas:")
        for idea in ideas[:10]:
            logger.info(f"  {idea['Ticker']}")
        if len(ideas) > 10:
            logger.info(f"  ... and {len(ideas) - 10} more")
        sys.exit(EXIT_SUCCESS)

    # Save to CSV
    try:
        output_path = save_to_csv(ideas, args.output)
        logger.info(f"💾 Saved to {output_path}")
    except Exception as e:
        logger.error(f"❌ Failed to save CSV: {e}")
        sys.exit(EXIT_PARSE_ERROR)

    # Populate watchlist if requested
    if args.populate_watchlist:
        logger.info("📋 Populating watchlist...")
        populate_watchlist(ideas)
        logger.info("✅ Watchlist populated")

    logger.info(f"\n🎉 Success! Scraped {len(ideas)} ideas")
    sys.exit(EXIT_SUCCESS)
```

- [ ] **Step 4: Commit changes**

```bash
git add scripts/mcstock_scraper.py
git commit -m "feat: add --mode argument and single mode to mcstock_scraper.py

Add --mode argument with 'single' (default) and 'historical' choices.
Extract existing logic into run_single_mode() function.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Add Historical Mode Functions

**Files:**
- Modify: `scripts/mcstock_scraper.py`

**Purpose:** Port historical scraping functions from mcstock_historical_scraper.py.

- [ ] **Step 1: Add generate_trading_dates function**

Add after existing functions:

```python
def generate_trading_dates(start_date: Optional[str], end_date: Optional[str]) -> List[date]:
    """
    Generate Mon-Fri trading dates within the range.

    Args:
        start_date: Start date string (YYYY-MM-DD) or None for 2023-01-01
        end_date: End date string (YYYY-MM-DD) or None for today

    Returns:
        List of date objects (Mon-Fri only)
    """
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start = date(2023, 1, 1)

    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end = date.today()

    trading_dates = []
    current = start

    while current <= end:
        if current.weekday() < 5:  # Mon-Fri only
            trading_dates.append(current)
        current += timedelta(days=1)

    return trading_dates
```

- [ ] **Step 2: Add build_historical_url function**

```python
def build_historical_url(date_obj: date) -> str:
    """
    Build the pre-market report URL for historical scraping.

    Pattern: /members/pre-market-report-{weekday}-{month}-{day}-{year}-900a-m-est/
    """
    weekday_name = date_obj.strftime('%A').lower()
    month_name = date_obj.strftime('%B').lower()
    day = date_obj.day
    year = date_obj.year

    return f"{BASE_URL}/members/pre-market-report-{weekday_name}-{month_name}-{day}-{year}-900a-m-est/"
```

- [ ] **Step 3: Add extract_tickers_historical function**

```python
def extract_tickers_historical(html: str, false_positives: set) -> List[Tuple[str, str]]:
    """
    Extract tickers from report HTML for historical mode.

    Returns list of (ticker, list_type) tuples.
    """
    logger = logging.getLogger(__name__)
    tickers = []

    soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    def is_valid_ticker(ticker: str) -> bool:
        if not ticker or len(ticker) < 2 or len(ticker) > 5:
            return False
        if not ticker.isalpha():
            return False
        if ticker.upper() in false_positives:
            return False
        return True

    def extract_from_section(section_header: str, end_headers: list, list_type: str = 'ready'):
        collecting = False

        for element in soup.find_all(['p', 'strong', 'b', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = element.get_text(strip=True).upper()

            if section_header in text:
                collecting = True
                continue

            if collecting and any(end in text for end in end_headers):
                break

            if collecting and element.name == 'p':
                line = element.get_text(strip=True)
                match = re.match(r'^([A-Z]{1,5})\s+\$([\d\.]+)', line)
                if match:
                    ticker = match.group(1)
                    if is_valid_ticker(ticker):
                        tickers.append((ticker, list_type))

    extract_from_section("THIS WEEKS READY LIST", ["WATCH LIST"], "ready")
    watch_endings = ["MORNING POST", "PARADE VIDEO", "TUESDAY", "WEDNESDAY",
                     "THURSDAY", "FRIDAY", "CHARTS", "DATA COURTESY"]
    extract_from_section("WATCH LIST", watch_endings, "watch")

    return tickers
```

- [ ] **Step 4: Add get_monday_date function**

```python
def get_monday_date(date_obj: date) -> str:
    """
    Get the Monday of the week for a given date.
    MC Stock Charts weeks are Monday-based.
    """
    days_since_monday = date_obj.weekday()
    monday = date_obj - timedelta(days=days_since_monday)
    return monday.strftime('%Y-%m-%d')
```

- [ ] **Step 5: Add save_historical_csv function**

```python
def save_historical_csv(
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]],
    output_path: str,
    scraped_date: str
) -> Path:
    """Save weekly tickers to CSV for historical mode."""
    path = PROJECT_ROOT / output_path
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['week_start', 'ticker', 'list_type', 'first_seen_date', 'scraped_date'])

        for week_start in sorted(weekly_tickers.keys()):
            for ticker in sorted(weekly_tickers[week_start].keys()):
                list_type, first_seen_date = weekly_tickers[week_start][ticker]
                writer.writerow([week_start, ticker, list_type, first_seen_date, scraped_date])

    return path
```

- [ ] **Step 6: Add run_historical_mode function**

```python
def run_historical_mode(session: requests.Session, args, logger):
    """Execute historical mode scraping."""
    # Generate trading dates
    trading_dates = generate_trading_dates(args.start, args.end)
    logger.info(f"📅 Generated {len(trading_dates)} trading dates (Mon-Fri)")

    # Load false positives from config
    config = load_scraper_config(args.config)
    false_positives = config.get('extra_false_positives', set())
    false_positives.update({
        'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'USD', 'CEO', 'CFO',
        'BOOK', 'POINT', 'TODAY', 'UNITS', 'LIST', 'WATCH', 'THIS',
        'WEEKS', 'READY', 'WEEK', 'DAYS', 'DAY', 'STOCK', 'STOCKS',
        'BUY', 'SELL', 'HOLD', 'ADD', 'NEW', 'OLD', 'LAST', 'FIRST',
        'FROM', 'WITH', 'HAVE', 'HAS', 'HAD', 'WAS', 'WERE', 'BEEN',
        'WILL', 'WOULD', 'COULD', 'SHOULD', 'MAY', 'MIGHT', 'MUST',
        'CAN', 'CANT', 'DONT', 'WONT', 'SHOULDNT', 'ISNT', 'ARENT',
        'VERY', 'JUST', 'NOW', 'THEN', 'THAN', 'ONLY', 'EVEN', 'ALSO',
        'BACK', 'AFTER', 'BEFORE', 'OVER', 'UNDER', 'INTO', 'THROUGH',
        'DURING', 'ABOUT', 'SINCE', 'UNTIL', 'WHILE', 'WHERE', 'WHEN',
        'THAT', 'THIS', 'THESE', 'THOSE', 'THEY', 'THEM', 'THEIR',
        'SHE', 'HER', 'HERS', 'HE', 'HIM', 'HIS', 'IT', 'ITS',
        'WE', 'US', 'OUR', 'OURS', 'YOU', 'YOUR', 'YOURS',
        'ALL', 'ANY', 'BOTH', 'EACH', 'FEW', 'MORE', 'MOST', 'OTHER',
        'SOME', 'SUCH', 'NO', 'NOR', 'NOT', 'SO', 'TOO', 'VERY',
        'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN'
    })

    # Scrape historical data
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]] = {}
    skipped_dates = 0

    for date_obj in trading_dates:
        date_str = date_obj.strftime('%Y-%m-%d')
        week_start = get_monday_date(date_obj)

        if week_start not in weekly_tickers:
            weekly_tickers[week_start] = {}
            logger.info(f"📅 Processing week of {week_start}")

        url = build_historical_url(date_obj)
        logger.info(f"  📄 Scraping {date_str}")

        # Fetch report
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 404:
                logger.info(f"    ⏭️  No pre-market report for {date_str}")
                skipped_dates += 1
                continue
            response.raise_for_status()
            html = response.text
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to fetch report: {e}")
            skipped_dates += 1
            continue

        # Extract tickers
        day_tickers = extract_tickers_historical(html, false_positives)

        for ticker, list_type in day_tickers:
            if ticker not in weekly_tickers[week_start]:
                weekly_tickers[week_start][ticker] = (list_type, date_str)

        logger.info(f"    ✅ Found {len(day_tickers)} tickers for {date_str}")
        time.sleep(args.delay if hasattr(args, 'delay') else 2.0)

    if not weekly_tickers:
        logger.warning("⚠️ No data scraped")
        sys.exit(EXIT_SUCCESS)

    # Generate output path
    if args.output:
        output_path = args.output
    else:
        output_path = f'data/mc_historical_{datetime.now().strftime("%Y-%m-%d")}.csv'

    # Save to CSV
    try:
        scraped_date = datetime.now().strftime('%Y-%m-%d')
        result_path = save_historical_csv(weekly_tickers, output_path, scraped_date)

        total_tickers = sum(len(tickers) for tickers in weekly_tickers.values())
        logger.info(f"\n🎉 Success! Scraped {total_tickers} tickers across {len(weekly_tickers)} weeks")
        logger.info(f"💾 Saved to {result_path}")
    except Exception as e:
        logger.error(f"❌ Failed to save CSV: {e}")
        sys.exit(EXIT_PARSE_ERROR)

    sys.exit(EXIT_SUCCESS)
```

- [ ] **Step 7: Commit historical mode**

```bash
git add scripts/mcstock_scraper.py
git commit -m "feat: add historical mode to mcstock_scraper.py

Add --mode historical with date range scraping support.
Port functions from mcstock_historical_scraper.py:
- generate_trading_dates()
- build_historical_url()
- extract_tickers_historical()
- save_historical_csv()
- run_historical_mode()

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: Delete mcstock_historical_scraper.py

**Files:**
- Delete: `scripts/mcstock_historical_scraper.py`

- [ ] **Step 1: Delete historical scraper**

```bash
git rm scripts/mcstock_historical_scraper.py
git commit -m "chore: remove deprecated mcstock_historical_scraper.py

Functionality merged into mcstock_scraper.py with --mode historical.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Update Documentation

**Files:**
- Modify: `CLAUDE.md` — Update MC Stock command references
- Modify: `memory/MEMORY.md` — Update script index if needed

- [ ] **Step 1: Update CLAUDE.md**

Replace existing MC Stock section:
```markdown
- **MC Stock Charts:**
    - Today's Report: `python3 scripts/mcstock_scraper.py --mode single`
    - Specific Date: `python3 scripts/mcstock_scraper.py --mode single --date 2026-04-06`
    - Historical Range: `python3 scripts/mcstock_scraper.py --mode historical --start 2024-01-01 --end 2025-04-01`
```

- [ ] **Step 2: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with unified mcstock_scraper.py commands

Replace separate historical scraper command with --mode syntax.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Write Tests

**Files:**
- Create: `tests/test_mcstock_scraper.py`

- [ ] **Step 1: Write tests for new functions**

```python
#!/usr/bin/env python3
"""Tests for unified mcstock_scraper."""

import pytest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from mcstock_scraper import (
    generate_trading_dates,
    build_historical_url,
    get_monday_date,
)


class TestGenerateTradingDates:
    """Test trading date generation."""

    def test_weekdays_only(self):
        """Test that only weekdays are generated."""
        dates = generate_trading_dates('2026-04-06', '2026-04-10')  # Mon-Fri
        assert len(dates) == 5
        for d in dates:
            assert d.weekday() < 5

    def test_skips_weekends(self):
        """Test that weekends are skipped."""
        dates = generate_trading_dates('2026-04-10', '2026-04-13')  # Fri-Mon
        assert len(dates) == 2
        assert dates[0].weekday() == 4  # Friday
        assert dates[1].weekday() == 0  # Monday


class TestBuildHistoricalUrl:
    """Test URL building for historical reports."""

    def test_url_format(self):
        """Test URL contains expected components."""
        test_date = date(2026, 4, 9)
        url = build_historical_url(test_date)
        assert 'mcstockcharts.com' in url
        assert 'pre-market-report' in url
        assert 'thursday' in url.lower()


class TestGetMondayDate:
    """Test Monday date calculation."""

    def test_wednesday_returns_monday(self):
        """Test that Wednesday returns Monday of same week."""
        wed = date(2026, 4, 9)
        monday = get_monday_date(wed)
        assert monday == '2026-04-06'
```

- [ ] **Step 2: Commit tests**

```bash
git add tests/test_mcstock_scraper.py
git commit -m "test: add tests for mcstock_scraper.py historical mode

Cover generate_trading_dates, build_historical_url, get_monday_date.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Verify Implementation

**Files:**
- Run: Tests
- Verify: Both modes work

- [ ] **Step 1: Run tests**

```bash
python3 -m pytest tests/test_mcstock_scraper.py -v
```

Expected: All tests pass

- [ ] **Step 2: Verify file structure**

```bash
ls -la scripts/mcstock*.py
```

Expected: Only `scripts/mcstock_scraper.py` exists

- [ ] **Step 3: Commit verification**

```bash
git add tests/test_mcstock_scraper.py
git commit -m "test: verify mcstock_scraper.py historical mode implementation

All tests passing. Historical functionality merged into unified scraper.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Fix `traderlib` module path for `--populate-watchlist`

**Problem:** When `mcstock_scraper.py` runs `--populate-watchlist`, it spawns `watchlist_manager.py` via `subprocess.run()`. `watchlist_manager.py` imports `traderlib` but has no `sys.path.insert(0, str(Path(__file__).parent.parent))`, so the import fails with `ModuleNotFoundError`.

**Files:**
- Modify: `scripts/watchlist_manager.py`

- [ ] **Step 1: Add `sys.path` insertion at the top of the imports**

  After the existing `import` block and before the `from traderlib` imports, add:

  ```python
  import json
  import sys
  from datetime import datetime
  from pathlib import Path

  # Allow imports from project root when script is run directly
  sys.path.insert(0, str(Path(__file__).parent.parent))

  import pandas as pd
  import yfinance as yf

  from traderlib import calculate_stage2_score
  from traderlib.validation import validate_ticker, EMOJI_CHECK, EMOJI_CROSS, EMOJI_WARN, EMOJI_INFO
  ```

- [ ] **Step 2: Verify the fix**

  Run:
  ```bash
  cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 scripts/watchlist_manager.py list
  ```
  Expected: Watchlist lists without `ModuleNotFoundError`.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/watchlist_manager.py
  git commit -m "fix: add sys.path for traderlib import in watchlist_manager.py

  Fixes ModuleNotFoundError when watchlist_manager.py is run standalone
  (e.g., from mcstock_scraper.py --populate-watchlist subprocess).

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
  ```

---

## Spec Coverage Check

| Requirement | Task | Status |
|-------------|------|--------|
| Keep mcstock_scraper.py filename | All tasks | ✅ Revised |
| Add --mode argument | Task 1 | ✅ Covered |
| Single mode (default) | Task 1 | ✅ Covered |
| Historical mode | Task 2 | ✅ Covered |
| Delete mcstock_historical_scraper.py | Task 3 | ✅ Covered |
| Update documentation | Task 4 | ✅ Covered |
| Add tests | Task 5 | ✅ Covered |
| Verify implementation | Task 6 | ✅ Covered |
| Fix watchlist_manager.py sys.path | Task 7 | ✅ Covered |

## Execution Handoff

**Plan complete and saved to `plans/plan-mcstock-merge-revised.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
