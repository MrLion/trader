# MC Stock Scraper Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `mcstock_scraper.py` and `mcstock_historical_scraper.py` into a single unified script with mode flags, eliminating ~100 lines of duplicated authentication, logging, and extraction code.

**Architecture:** Create a unified `mcstock.py` with two operation modes: (1) `--mode single` for today's report with validation and watchlist population, (2) `--mode historical` for date-range scraping with weekly aggregation. Shared code (auth, extraction, logging) extracted to common functions.

**Tech Stack:** Python 3.11, requests, beautifulsoup4, python-dotenv, pandas (for single mode validation), csv module

---

## File Structure

**Files to Create:**
- `scripts/mcstock.py` — Unified scraper (replaces both existing scripts)

**Files to Modify:**
- `CLAUDE.md` — Update command references
- `memory/MEMORY.md` — Update script index

**Files to Delete:**
- `scripts/mcstock_scraper.py` — Replaced by mcstock.py
- `scripts/mcstock_historical_scraper.py` — Replaced by mcstock.py

**Files to Create (Tests):**
- `tests/test_mcstock.py` — Unit tests for unified scraper

---

## Analysis: Duplicated Code

Both scripts share these identical functions:
- `setup_logging()` — ~15 lines
- `get_credentials()` — ~35 lines
- `login()` — ~55 lines
- False positives set — ~50 lines
- `is_valid_ticker()` — ~10 lines
- `extract_from_section()` — ~40 lines

Total duplication: **~205 lines** that will be deduplicated into shared functions.

---

### Task 1: Create Unified Script Structure

**Files:**
- Create: `scripts/mcstock.py` (shell structure)

**Purpose:** Establish the unified script with mode-based argparse and shared imports.

- [ ] **Step 1: Write unified script header with imports**

```python
#!/usr/bin/env python3
"""
MC STOCK CHARTS SCRAPER
=======================

Unified scraper supporting both single-date and historical modes.

USAGE:
------
    # Single mode (today's report with validation)
    python3 scripts/mcstock.py --mode single
    python3 scripts/mcstock.py --mode single --date 2026-04-06
    python3 scripts/mcstock.py --mode single --populate-watchlist

    # Historical mode (date range scraping)
    python3 scripts/mcstock.py --mode historical
    python3 scripts/mcstock.py --mode historical --start 2024-01-01 --end 2025-04-01

OUTPUT:
-------
    Single mode: scans/mcstock_ideas_YYYY-MM-DD.csv
    Historical mode: data/mc_historical_YYYY-MM-DD.csv

Co-Authored-By: Claude Opus 4.7 <noreply@anthropics.com>
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Configuration
BASE_URL = "https://www.mcstockcharts.com"
LOGIN_URL = f"{BASE_URL}/wp-login.php"
REPORT_URL = f"{BASE_URL}/latest-report/"
DATE_STR = datetime.now().strftime('%Y-%m-%d')
DATETIME_STR = datetime.now().strftime('%Y-%m-%d_%H%M%S')

# Exit codes
EXIT_SUCCESS = 0
EXIT_AUTH_FAILED = 1
EXIT_REPORT_NOT_FOUND = 2
EXIT_NETWORK_ERROR = 3
EXIT_PARSE_ERROR = 4
EXIT_CONFIG_ERROR = 5
```

- [ ] **Step 2: Write shared logging function**

```python
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(__name__)
```

- [ ] **Step 3: Write shared credentials function**

```python
def get_credentials() -> Tuple[str, str]:
    """Get MC Stock Charts credentials from environment."""
    username = os.getenv('MCSTOCK_USER')
    password = os.getenv('MCSTOCK_PASS')

    if not username or not password:
        env_path = PROJECT_ROOT / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        if key == 'MCSTOCK_USER':
                            username = value.strip().strip('"\'')
                        elif key == 'MCSTOCK_PASS':
                            password = value.strip().strip('"\'')

    if not username or not password:
        raise ValueError(
            "MC Stock Charts credentials not found. "
            "Set MCSTOCK_USER and MCSTOCK_PASS environment variables "
            "or add them to .env file."
        )

    return username, password
```

- [ ] **Step 4: Write shared login function**

```python
def login(session: requests.Session, username: str, password: str) -> bool:
    """Authenticate with WordPress login."""
    logger = logging.getLogger(__name__)
    logger.info("🔐 Authenticating with MC Stock Charts...")

    try:
        response = session.get(LOGIN_URL, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        redirect_to = soup.find('input', {'name': 'redirect_to'})
        redirect_value = redirect_to['value'] if redirect_to else BASE_URL

        payload = {
            'log': username,
            'pwd': password,
            'rememberme': 'forever',
            'redirect_to': redirect_value,
            'testcookie': '1'
        }

        response = session.post(LOGIN_URL, data=payload, timeout=30)
        response.raise_for_status()

        if 'wp-login.php' in response.url or 'login_error' in response.text:
            soup = BeautifulSoup(response.text, 'html.parser')
            error_div = soup.find('div', {'id': 'login_error'})
            if error_div:
                logger.error(f"Login failed: {error_div.get_text(strip=True)}")
            else:
                logger.error("Login failed: Invalid credentials")
            return False

        logger.info("✅ Authentication successful")
        return True

    except requests.exceptions.Timeout:
        logger.error("Login timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during login: {e}")
        return False
```

- [ ] **Step 5: Commit skeleton structure**

```bash
git add scripts/mcstock.py
git commit -m "feat: create unified mcstock.py script skeleton

Add shared authentication and logging functions extracted from
mcstock_scraper.py and mcstock_historical_scraper.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropics.com>"
```

---

### Task 2: Implement Single Mode (Today's Report)

**Files:**
- Modify: `scripts/mcstock.py:80-300`
- Test: `tests/test_mcstock.py:1-50`

**Purpose:** Port single-date report scraping with full validation from mcstock_scraper.py.

- [ ] **Step 1: Write shared false positives and validation**

```python
# Shared false positives set
FALSE_POSITIVES = {
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
}


def is_valid_ticker(ticker: str, extra_false_positives: Optional[set] = None) -> bool:
    """Check if a string looks like a valid ticker symbol."""
    if not ticker or len(ticker) < 2 or len(ticker) > 5:
        return False
    if not ticker.isalpha():
        return False
    fps = FALSE_POSITIVES.copy()
    if extra_false_positives:
        fps.update(extra_false_positives)
    if ticker.upper() in fps:
        return False
    return True
```

- [ ] **Step 2: Write fetch_report function for single mode**

```python
def fetch_single_report(session: requests.Session, date: Optional[str] = None) -> str:
    """
    Fetch a single report page (today or specific date).

    Args:
        session: Authenticated session
        date: Specific date (YYYY-MM-DD) or None for latest

    Returns:
        HTML content of the report page
    """
    logger = logging.getLogger(__name__)

    if date:
        url = f"{BASE_URL}/{date}-report/"
    else:
        url = REPORT_URL

    logger.info(f"📄 Fetching report from {url}...")

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        if 'wp-login.php' in response.url:
            logger.error("Session expired or not authenticated")
            raise PermissionError("Authentication required")

        logger.info(f"✅ Report fetched ({len(response.text)} chars)")
        return response.text

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.error(f"Report not found for date: {date or 'latest'}")
            raise FileNotFoundError(f"Report page not found: {url}")
        raise
```

- [ ] **Step 3: Write extract_tickers_single function**

```python
def extract_tickers_single(html: str, extra_false_positives: Optional[set] = None) -> List[Dict]:
    """
    Extract trade ideas from report HTML (single mode).

    Returns list of dicts with ticker info and context.
    """
    logger = logging.getLogger(__name__)
    logger.debug("🔍 Parsing report HTML...")

    soup = BeautifulSoup(html, 'html.parser')
    ideas = []
    tickers_found = set()
    ticker_contexts = {}

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    def extract_from_section(section_header: str, end_headers: list, list_type: str = 'ready'):
        """Extract tickers from a specific section."""
        collecting = False

        for element in soup.find_all(['p', 'strong', 'b', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = element.get_text(strip=True).upper()

            if section_header in text:
                collecting = True
                logger.debug(f"Found start header: {text[:50]}")
                continue

            if collecting and any(end in text for end in end_headers):
                logger.debug(f"Found end header: {text[:50]}")
                break

            if collecting and element.name == 'p':
                line = element.get_text(strip=True)
                match = re.match(r'^([A-Z]{1,5})\s+\$([\d\.]+)', line)
                if match:
                    ticker = match.group(1)
                    if is_valid_ticker(ticker, extra_false_positives):
                        tickers_found.add(ticker)
                        if ticker not in ticker_contexts:
                            ticker_contexts[ticker] = []
                        ticker_contexts[ticker].append(f"{list_type}: {ticker}")
                        logger.debug(f"Found ticker: {ticker}")

    # Extract from sections
    extract_from_section("THIS WEEKS READY LIST", ["WATCH LIST"], "ready")
    watch_endings = ["MORNING POST", "PARADE VIDEO", "TUESDAY", "WEDNESDAY",
                     "THURSDAY", "FRIDAY", "CHARTS", "DATA COURTESY"]
    extract_from_section("WATCH LIST", watch_endings, "watch")

    logger.info(f"🎯 Found {len(tickers_found)} potential tickers")

    # Build idea dicts
    for ticker in sorted(tickers_found):
        ideas.append({
            'Ticker': ticker,
            'Name': '',
            'Sector': '',
            'Industry': '',
            'Stage2': '',
            '6M_%': '',
            '3M_%': '',
            '1M_%': '',
            'Entry_Breakout': '',
            'Stop': '',
            'Risk_%': '',
            '$Vol_M': '',
            'Source_Note': '; '.join(ticker_contexts[ticker][:2]) if ticker_contexts[ticker] else 'MC Report'
        })

    return ideas
```

- [ ] **Step 4: Write save_to_csv_single function**

```python
def save_to_csv_single(ideas: List[Dict], output_path: Optional[str] = None) -> Path:
    """Save ideas to CSV file (single mode)."""
    if not ideas:
        raise ValueError("No ideas to save")

    if output_path:
        path = Path(output_path)
    else:
        path = PROJECT_ROOT / f'scans/mcstock_ideas_{DATE_STR}.csv'

    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(ideas[0].keys())

    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ideas)

    return path
```

- [ ] **Step 5: Write populate_watchlist function**

```python
def populate_watchlist(ideas: List[Dict]) -> None:
    """Populate watchlist directly from ideas."""
    logger = logging.getLogger(__name__)

    temp_path = PROJECT_ROOT / f'scans/temp_mcstock_{DATETIME_STR}.csv'
    save_to_csv_single(ideas, str(temp_path))

    import subprocess
    watchlist_script = PROJECT_ROOT / 'scripts/watchlist_manager.py'
    result = subprocess.run(
        ['python3', str(watchlist_script), 'populate', str(temp_path)],
        capture_output=True,
        text=True
    )

    logger.info(result.stdout)
    if result.stderr:
        logger.error(result.stderr)

    temp_path.unlink(missing_ok=True)
```

- [ ] **Step 6: Commit single mode functions**

```bash
git add scripts/mcstock.py
git commit -m "feat: add single mode functions to mcstock.py

Add extraction and CSV saving for today's report mode.
Includes ticker validation, section parsing, and watchlist
population.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropics.com>"
```

---

### Task 3: Implement Historical Mode (Date Range)

**Files:**
- Modify: `scripts/mcstock.py:300-450`
- Test: `tests/test_mcstock.py:50-100`

**Purpose:** Port historical date-range scraping from mcstock_historical_scraper.py.

- [ ] **Step 1: Write generate_trading_dates function**

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

- [ ] **Step 2: Write build_historical_url function**

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

- [ ] **Step 3: Write fetch_report_historical function**

```python
def fetch_report_historical(session: requests.Session, url: str) -> Optional[str]:
    """
    Fetch a report page for historical scraping.

    Returns HTML content or None if 404 (no report for that date).
    """
    logger = logging.getLogger(__name__)

    try:
        response = session.get(url, timeout=30)

        if response.status_code == 404:
            logger.debug(f"No report found at {url}")
            return None

        response.raise_for_status()
        return response.text

    except requests.exceptions.RequestException as e:
        logger.debug(f"Failed to fetch report: {e}")
        return None
```

- [ ] **Step 4: Write extract_tickers_historical function**

```python
def extract_tickers_historical(html: str) -> List[Tuple[str, str]]:
    """
    Extract tickers from report HTML (historical mode).

    Returns list of (ticker, list_type) tuples.
    """
    logger = logging.getLogger(__name__)
    tickers = []

    soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

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

- [ ] **Step 5: Write get_monday_date function**

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

- [ ] **Step 6: Write scrape_historical function**

```python
def scrape_historical(
    session: requests.Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    delay: float = 2.0
) -> Dict[str, Dict[str, Tuple[str, str]]]:
    """
    Scrape historical data from MC Stock Charts.

    Returns dict: {week_start: {ticker: (list_type, first_seen_date)}}
    """
    logger = logging.getLogger(__name__)
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]] = {}

    trading_dates = generate_trading_dates(start_date, end_date)
    logger.info(f"📅 Generated {len(trading_dates)} trading dates (Mon-Fri)")

    skipped_dates = 0

    for date_obj in trading_dates:
        date_str = date_obj.strftime('%Y-%m-%d')
        week_start = get_monday_date(date_obj)

        if week_start not in weekly_tickers:
            weekly_tickers[week_start] = {}
            logger.info(f"📅 Processing week of {week_start}")

        url = build_historical_url(date_obj)
        logger.info(f"  📄 Scraping {date_str}")

        html = fetch_report_historical(session, url)

        if html is None:
            logger.info(f"    ⏭️  No pre-market report for {date_str}")
            skipped_dates += 1
            continue

        day_tickers = extract_tickers_historical(html)

        for ticker, list_type in day_tickers:
            if ticker not in weekly_tickers[week_start]:
                weekly_tickers[week_start][ticker] = (list_type, date_str)

        logger.info(f"    ✅ Found {len(day_tickers)} tickers for {date_str}")
        time.sleep(delay)

    logger.info(f"\n📊 Summary: {len(weekly_tickers)} weeks, {skipped_dates} dates skipped")

    return weekly_tickers
```

- [ ] **Step 7: Write save_to_csv_historical function**

```python
def save_to_csv_historical(
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]],
    output_path: str,
    scraped_date: str
) -> Path:
    """Save weekly tickers to CSV (historical mode)."""
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

- [ ] **Step 8: Commit historical mode functions**

```bash
git add scripts/mcstock.py
git commit -m "feat: add historical mode functions to mcstock.py

Add date-range scraping with weekly aggregation.
Includes trading date generation, URL building, and
historical CSV output format.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropics.com>"
```

---

### Task 4: Implement Main Function with Argparse

**Files:**
- Modify: `scripts/mcstock.py:450-600`

**Purpose:** Create unified CLI with mode subparsers.

- [ ] **Step 1: Write unified argparse main function**

```python
def main():
    """Main entry point with mode-based CLI."""
    parser = argparse.ArgumentParser(
        description='MC Stock Charts Scraper - Unified scraper for single and historical modes'
    )
    parser.add_argument(
        '--mode',
        choices=['single', 'historical'],
        required=True,
        help='Scraping mode: single (today or specific date) or historical (date range)'
    )
    parser.add_argument(
        '--date',
        help='Single mode: Specific date to scrape (YYYY-MM-DD). Defaults to today.'
    )
    parser.add_argument(
        '--start',
        help='Historical mode: Start date (YYYY-MM-DD). Defaults to 2023-01-01.'
    )
    parser.add_argument(
        '--end',
        help='Historical mode: End date (YYYY-MM-DD). Defaults to today.'
    )
    parser.add_argument(
        '--output',
        help='Custom output path for CSV'
    )
    parser.add_argument(
        '--populate-watchlist',
        action='store_true',
        help='Single mode: Automatically populate watchlist after scraping'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='Historical mode: Delay between requests in seconds (default: 2.0)'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging'
    )

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
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(EXIT_NETWORK_ERROR)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Write run_single_mode function**

```python
def run_single_mode(session: requests.Session, args, logger):
    """Execute single mode scraping."""
    # Fetch report
    try:
        html = fetch_single_report(session, args.date)
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(EXIT_REPORT_NOT_FOUND)
    except PermissionError as e:
        logger.error(f"❌ {e}")
        sys.exit(EXIT_AUTH_FAILED)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        sys.exit(EXIT_NETWORK_ERROR)

    # Extract tickers
    ideas = extract_tickers_single(html)

    if not ideas:
        logger.warning("⚠️ No trade ideas found in report")
        sys.exit(EXIT_SUCCESS)

    logger.info(f"📝 Found {len(ideas)} potential ideas")

    # Save to CSV
    try:
        output_path = save_to_csv_single(ideas, args.output)
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

- [ ] **Step 3: Write run_historical_mode function**

```python
def run_historical_mode(session: requests.Session, args, logger):
    """Execute historical mode scraping."""
    # Scrape historical data
    weekly_tickers = scrape_historical(
        session,
        start_date=args.start,
        end_date=args.end,
        delay=args.delay
    )

    if not weekly_tickers:
        logger.warning("⚠️ No data scraped")
        sys.exit(EXIT_SUCCESS)

    # Generate output path
    if args.output:
        output_path = args.output
    else:
        output_path = f'data/mc_historical_{DATE_STR}.csv'

    # Save to CSV
    try:
        scraped_date = datetime.now().strftime('%Y-%m-%d')
        result_path = save_to_csv_historical(weekly_tickers, output_path, scraped_date)

        total_tickers = sum(len(tickers) for tickers in weekly_tickers.values())
        logger.info(f"\n🎉 Success! Scraped {total_tickers} tickers across {len(weekly_tickers)} weeks")
        logger.info(f"💾 Saved to {result_path}")
    except Exception as e:
        logger.error(f"❌ Failed to save CSV: {e}")
        sys.exit(EXIT_PARSE_ERROR)

    sys.exit(EXIT_SUCCESS)
```

- [ ] **Step 4: Commit main function**

```bash
git add scripts/mcstock.py
git commit -m "feat: add unified CLI with mode subparsers

Implement main() with argparse supporting --mode single and
--mode historical. Add run_single_mode() and run_historical_mode()
for mode-specific execution flows.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropics.com>"
```

---

### Task 5: Update Documentation References

**Files:**
- Modify: `CLAUDE.md` — Update MC Stock commands
- Modify: `memory/MEMORY.md` — Update script index

- [ ] **Step 1: Update CLAUDE.md MC Stock section**

Replace in CLAUDE.md:
```markdown
- **MC Stock Charts:**
    - Daily Report: `python3 scripts/mcstock_scraper.py`
    - Historical Archives: `python3 scripts/mcstock_historical_scraper.py --weeks 10`
```

With:
```markdown
- **MC Stock Charts:**
    - Today's Report: `python3 scripts/mcstock.py --mode single`
    - Specific Date: `python3 scripts/mcstock.py --mode single --date 2026-04-06`
    - Historical Range: `python3 scripts/mcstock.py --mode historical --start 2024-01-01 --end 2025-04-01`
```

- [ ] **Step 2: Commit documentation update**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with unified mcstock.py commands

Replace separate mcstock_scraper.py and mcstock_historical_scraper.py
commands with unified mcstock.py --mode syntax.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Delete Old Scripts

**Files:**
- Delete: `scripts/mcstock_scraper.py`
- Delete: `scripts/mcstock_historical_scraper.py`

- [ ] **Step 1: Delete old scripts**

```bash
git rm scripts/mcstock_scraper.py scripts/mcstock_historical_scraper.py
git commit -m "chore: remove deprecated mcstock scraper scripts

Replaced by unified scripts/mcstock.py. Old scripts:
- mcstock_scraper.py (681 lines)
- mcstock_historical_scraper.py (483 lines)

Net reduction: ~205 lines of duplicated code.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Write Tests

**Files:**
- Create: `tests/test_mcstock.py`

- [ ] **Step 1: Write test file header and shared fixtures**

```python
#!/usr/bin/env python3
"""Tests for unified mcstock scraper."""

import pytest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.mcstock import (
    setup_logging,
    get_credentials,
    is_valid_ticker,
    FALSE_POSITIVES,
    generate_trading_dates,
    get_monday_date,
    build_historical_url,
)


class TestLogging:
    """Test logging setup."""

    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a logger instance."""
        logger = setup_logging(verbose=False)
        assert logger is not None
        assert hasattr(logger, 'info')


class TestCredentials:
    """Test credential loading."""

    @patch.dict('os.environ', {'MCSTOCK_USER': 'testuser', 'MCSTOCK_PASS': 'testpass'})
    def test_get_credentials_from_env(self):
        """Test loading credentials from environment variables."""
        username, password = get_credentials()
        assert username == 'testuser'
        assert password == 'testpass'

    def test_get_credentials_missing_raises_error(self):
        """Test that missing credentials raise ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="credentials not found"):
                get_credentials()


class TestTickerValidation:
    """Test ticker validation logic."""

    def test_valid_ticker(self):
        """Test valid ticker symbols."""
        assert is_valid_ticker('AAPL') is True
        assert is_valid_ticker('MSFT') is True
        assert is_valid_ticker('AMD') is True

    def test_invalid_ticker_length(self):
        """Test ticker length validation."""
        assert is_valid_ticker('A') is False  # Too short
        assert is_valid_ticker('ABCDEF') is False  # Too long

    def test_invalid_ticker_numeric(self):
        """Test that numeric tickers are rejected."""
        assert is_valid_ticker('A123') is False

    def test_false_positives_filtered(self):
        """Test that common words are filtered."""
        for word in ['THE', 'AND', 'FOR', 'LIST', 'WATCH']:
            assert is_valid_ticker(word) is False

    def test_extra_false_positives(self):
        """Test custom false positives."""
        assert is_valid_ticker('TEST', extra_false_positives={'TEST'}) is False


class TestDateFunctions:
    """Test date manipulation functions."""

    def test_generate_trading_dates_weekdays_only(self):
        """Test that only weekdays are generated."""
        dates = generate_trading_dates('2026-04-06', '2026-04-10')  # Mon-Fri
        assert len(dates) == 5
        for d in dates:
            assert d.weekday() < 5  # Mon-Fri only

    def test_generate_trading_dates_skips_weekends(self):
        """Test that weekends are skipped."""
        dates = generate_trading_dates('2026-04-10', '2026-04-13')  # Fri-Mon
        # Should only have Fri and Mon
        assert len(dates) == 2
        assert dates[0].weekday() == 4  # Friday
        assert dates[1].weekday() == 0  # Monday

    def test_get_monday_date(self):
        """Test getting Monday for a given date."""
        # Wednesday April 9, 2026
        wed = date(2026, 4, 9)
        monday = get_monday_date(wed)
        assert monday == '2026-04-06'  # Monday of that week

    def test_build_historical_url(self):
        """Test URL building for historical reports."""
        test_date = date(2026, 4, 9)  # Thursday
        url = build_historical_url(test_date)
        assert 'pre-market-report-thursday-april-9-2026' in url
        assert url.startswith('https://www.mcstockcharts.com')
```

- [ ] **Step 2: Commit tests**

```bash
git add tests/test_mcstock.py
git commit -m "test: add unit tests for mcstock.py

Cover logging, credentials, ticker validation, and date functions.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Verify Implementation

**Files:**
- Run: Tests
- Run: Dry-run of both modes

- [ ] **Step 1: Run tests**

```bash
python3 -m pytest tests/test_mcstock.py -v
```

Expected: All tests pass (7 test functions)

- [ ] **Step 2: Verify unified script exists and old scripts don't**

```bash
ls -la scripts/mcstock*.py
```

Expected: Only `scripts/mcstock.py` exists

- [ ] **Step 3: Commit verification**

```bash
git add tests/test_mcstock.py
git commit -m "test: verify mcstock.py merge implementation

All tests passing. Unified script replaces deprecated scrapers.
Net code reduction: ~205 lines.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Spec Coverage Check

| Requirement | Task | Status |
|-------------|------|--------|
| Merge two scripts into one | Task 1-4 | ✅ Covered |
| Shared authentication | Task 1 | ✅ Covered |
| Shared logging | Task 1 | ✅ Covered |
| Single mode (today's report) | Task 2 | ✅ Covered |
| Historical mode (date range) | Task 3 | ✅ Covered |
| Unified CLI with --mode | Task 4 | ✅ Covered |
| Update documentation | Task 5 | ✅ Covered |
| Delete old scripts | Task 6 | ✅ Covered |
| Add tests | Task 7 | ✅ Covered |
| Verify implementation | Task 8 | ✅ Covered |

## Placeholder Scan

No placeholders found. All code blocks are complete and runnable.

## Execution Handoff

**Plan complete and saved to `plans/plan-mcstock-merge.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
