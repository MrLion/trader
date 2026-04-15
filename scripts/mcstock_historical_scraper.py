#!/usr/bin/env python3
"""
MC STOCK CHARTS HISTORICAL SCRAPER
==================================

Scrapes historical weekly reports from mcstockcharts.com/report-archives/
and outputs a time-series CSV for backtesting with weekly rotation.

USAGE:
------
    # Scrape all available history
    python3 scripts/mcstock_historical_scraper.py

    # Scrape with date filter
    python3 scripts/mcstock_historical_scraper.py --start 2024-01-01 --end 2025-04-01

    # Scrape last N weeks only
    python3 scripts/mcstock_historical_scraper.py --weeks 10

    # Limit pages for testing
    python3 scripts/mcstock_historical_scraper.py --max-pages 2

OUTPUT:
-------
    CSV with columns:
    - week_start: Monday date for the week (YYYY-MM-DD)
    - ticker: Stock symbol
    - list_type: 'ready' or 'watch'
    - first_seen_date: Date ticker first appeared that week
    - scraped_date: When this record was scraped

EXAMPLE WORKFLOW:
-----------------
    1. Scrape historical data:
       python3 scripts/mcstock_historical_scraper.py --output data/mc_historical.csv

    2. Use in backtest (future feature):
       python3 scripts/backtest.py --weekly-watchlist data/mc_historical.csv

AUTHOR: Ace (Trading Agent)
DATE: 2026-04-15
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Configuration
BASE_URL = "https://www.mcstockcharts.com"
ARCHIVES_URL = f"{BASE_URL}/report-archives/"
LOGIN_URL = f"{BASE_URL}/wp-login.php"

# Exit codes
EXIT_SUCCESS = 0
EXIT_AUTH_FAILED = 1
EXIT_NETWORK_ERROR = 2
EXIT_CONFIG_ERROR = 3


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(__name__)


def get_credentials() -> Tuple[str, str]:
    """Get MC Stock Charts credentials from environment."""
    username = os.getenv('MCSTOCK_USER')
    password = os.getenv('MCSTOCK_PASS')

    if not username or not password:
        # Try loading from .env file
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


def login(session: requests.Session, username: str, password: str) -> bool:
    """Authenticate with WordPress login."""
    logger = logging.getLogger(__name__)
    logger.info("🔐 Authenticating with MC Stock Charts...")

    try:
        # First, get the login page
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


def fetch_archive_page(session: requests.Session, page_num: int = 1) -> Optional[str]:
    """Fetch an archive page HTML."""
    logger = logging.getLogger(__name__)

    url = ARCHIVES_URL if page_num == 1 else f"{ARCHIVES_URL}?_page={page_num}"
    logger.debug(f"Fetching archive page {page_num}: {url}")

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch archive page {page_num}: {e}")
        return None


def parse_report_urls(html: str) -> List[Tuple[str, str]]:
    """
    Extract report URLs and dates from archive page.

    Returns list of (url, date_str) tuples.
    Date format: YYYY-MM-DD
    """
    logger = logging.getLogger(__name__)
    reports = []

    soup = BeautifulSoup(html, 'html.parser')

    # Find all report links - try multiple strategies
    report_links = set()  # Use set to avoid duplicates

    # Strategy 1: Look in article/div containers (desktop layout)
    for article in soup.find_all(['article', 'div'], class_=re.compile(r'post|entry|report')):
        link = article.find('a', href=re.compile(r'/members/pre-market-report-'))
        if link:
            report_links.add(link.get('href', ''))

    # Strategy 2: Find all links directly (catches all layouts)
    for link in soup.find_all('a', href=re.compile(r'/members/pre-market-report-')):
        report_links.add(link.get('href', ''))

    # Strategy 3: Look for archive list items (common WordPress pattern)
    for li in soup.find_all('li', class_=re.compile(r'post|entry|report')):
        link = li.find('a', href=re.compile(r'/members/pre-market-report-'))
        if link:
            report_links.add(link.get('href', ''))

    # Strategy 4: Look in any element with common archive classes
    for elem in soup.find_all(class_=re.compile(r'archive|post|entry|report')):
        link = elem.find('a', href=re.compile(r'/members/pre-market-report-'))
        if link:
            report_links.add(link.get('href', ''))

    logger.debug(f"Raw report links found (before URL filtering): {len(report_links)}")

    # Process unique report URLs
    for url in report_links:
        if not url:
            continue
        if url.startswith('/'):
            url = BASE_URL + url

        # Parse date from URL
        # Format: /members/pre-market-report-{weekday}-{month}-{day}-{year}-{time}/
        date_match = re.search(r'/pre-market-report-[a-z]+-([a-z]+)-(\d+)-(\d{4})-\d+a-m-est', url)
        if date_match:
            month_name, day, year = date_match.groups()
            try:
                # Convert month name to number
                month_num = datetime.strptime(month_name.lower(), '%B').month
                date_str = f"{year}-{month_num:02d}-{int(day):02d}"
                reports.append((url, date_str))
            except ValueError:
                logger.warning(f"Could not parse date from URL: {url}")

    logger.debug(f"Found {len(reports)} reports on page")
    return reports


def get_monday_date(date_str: str) -> str:
    """
    Get the Monday of the week for a given date.
    MC Stock Charts weeks are Monday-based.
    """
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    # weekday(): Monday=0, Sunday=6
    days_since_monday = date_obj.weekday()
    monday = date_obj - timedelta(days=days_since_monday)
    return monday.strftime('%Y-%m-%d')


def extract_tickers_from_report(session: requests.Session, url: str) -> List[Tuple[str, str]]:
    """
    Extract tickers from a single report.

    Returns list of (ticker, list_type) tuples.
    """
    logger = logging.getLogger(__name__)
    tickers = []

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # False positives to filter
        false_positives = {
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
                    # Pattern: TICKER followed by price like $XX.XX
                    match = re.match(r'^([A-Z]{1,5})\s+\$([\d\.]+)', line)
                    if match:
                        ticker = match.group(1)
                        if is_valid_ticker(ticker):
                            tickers.append((ticker, list_type))

        # Extract from "THIS WEEKS READY LIST" section
        extract_from_section("THIS WEEKS READY LIST", ["WATCH LIST"], "ready")

        # Extract from "WATCH LIST" section
        watch_endings = ["MORNING POST", "PARADE VIDEO", "TUESDAY", "WEDNESDAY",
                         "THURSDAY", "FRIDAY", "CHARTS", "DATA COURTESY"]
        extract_from_section("WATCH LIST", watch_endings, "watch")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch report {url}: {e}")

    return tickers


def scrape_historical_data(
    session: requests.Session,
    max_pages: Optional[int] = None,
    weeks_limit: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    delay: float = 2.0
) -> Dict[str, Dict[str, Tuple[str, str]]]:
    """
    Scrape historical data from MC Stock Charts archives.

    Returns dict: {week_start: {ticker: (list_type, first_seen_date)}}
    """
    logger = logging.getLogger(__name__)
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]] = {}

    page = 1
    weeks_collected = 0

    while True:
        if max_pages and page > max_pages:
            logger.info(f"Reached max pages limit ({max_pages})")
            break

        logger.info(f"📄 Fetching archive page {page}...")
        html = fetch_archive_page(session, page)

        if not html:
            logger.error(f"Failed to fetch page {page}, stopping")
            break

        reports = parse_report_urls(html)

        if not reports:
            logger.info("No more reports found")
            break

        # Log dates found on this page
        if reports:
            all_dates = sorted(set([date_str for _, date_str in reports]))
            logger.debug(f"Page {page} reports found: {len(reports)}, dates: {all_dates}")

        # Check if we've gone past the date range (archives are newest → oldest)
        # If all reports on this page are before start_date, we can stop
        if start_date and reports:
            newest_date = max([date_str for _, date_str in reports])
            oldest_date = min([date_str for _, date_str in reports])
            logger.debug(f"Page {page} date range: {oldest_date} to {newest_date}, start_date filter: {start_date}")
            if newest_date < start_date:
                logger.info(f"All reports on page {page} are before start_date ({start_date}), stopping")
                break

        # Group reports by week
        week_reports: Dict[str, List[Tuple[str, str]]] = {}
        for url, date_str in reports:
            week_start = get_monday_date(date_str)

            # Date filtering
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue

            if week_start not in week_reports:
                week_reports[week_start] = []
            week_reports[week_start].append((url, date_str))

        # Scrape each week's reports
        weeks_processed_this_page = 0
        for week_start in sorted(week_reports.keys(), reverse=True):
            if weeks_limit and weeks_collected >= weeks_limit:
                logger.info(f"Reached weeks limit ({weeks_limit})")
                break

            logger.info(f"📅 Processing week of {week_start}")

            if week_start not in weekly_tickers:
                weekly_tickers[week_start] = {}

            # Scrape each day's report for this week
            for url, date_str in week_reports[week_start]:
                logger.info(f"  📄 Scraping {date_str}")

                day_tickers = extract_tickers_from_report(session, url)

                for ticker, list_type in day_tickers:
                    if ticker not in weekly_tickers[week_start]:
                        weekly_tickers[week_start][ticker] = (list_type, date_str)

                time.sleep(delay)

            weeks_collected += 1
            weeks_processed_this_page += 1
            logger.info(f"  ✅ Found {len(weekly_tickers[week_start])} tickers for week of {week_start}")

        if weeks_limit and weeks_collected >= weeks_limit:
            break

        # Early termination: only stop if we've gone PAST the date range
        # (all reports are older than start_date)
        # Don't stop if we haven't reached the range yet (newer than end_date)
        if weeks_processed_this_page == 0 and reports:
            all_dates = [date_str for _, date_str in reports]
            newest_date = max(all_dates)
            oldest_date = min(all_dates)
            # Only stop if the newest report on this page is before start_date
            # (we've gone too far back in time)
            if newest_date < start_date:
                logger.info(f"All reports on page {page} are before start_date ({start_date}), stopping")
                break
            else:
                logger.debug(f"Page {page} has reports after end_date, continuing to older pages")

        page += 1
        time.sleep(delay)

    return weekly_tickers


def save_to_csv(
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]],
    output_path: str,
    scraped_date: str
) -> Path:
    """Save weekly tickers to CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['week_start', 'ticker', 'list_type', 'first_seen_date', 'scraped_date'])

        for week_start in sorted(weekly_tickers.keys()):
            for ticker in sorted(weekly_tickers[week_start].keys()):
                list_type, first_seen_date = weekly_tickers[week_start][ticker]
                writer.writerow([week_start, ticker, list_type, first_seen_date, scraped_date])

    return path


def main():
    parser = argparse.ArgumentParser(
        description='Scrape historical MC Stock Charts data for backtesting'
    )
    parser.add_argument(
        '--start',
        help='Filter: Start date (YYYY-MM-DD) - optional'
    )
    parser.add_argument(
        '--end',
        help='Filter: End date (YYYY-MM-DD) - optional'
    )
    parser.add_argument(
        '--output',
        default='data/mc_historical_watchlists.csv',
        help='Output CSV path (default: data/mc_historical_watchlists.csv)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        help='Max archive pages to scrape (default: all)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='Seconds between requests (default: 2.0)'
    )
    parser.add_argument(
        '--weeks',
        type=int,
        help='Limit to N most recent weeks'
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

        # Scrape historical data
        logger.info("🚀 Starting historical scrape...")
        weekly_tickers = scrape_historical_data(
            session,
            max_pages=args.max_pages,
            weeks_limit=args.weeks,
            start_date=args.start,
            end_date=args.end,
            delay=args.delay
        )

        if not weekly_tickers:
            logger.warning("⚠️ No data scraped")
            sys.exit(EXIT_SUCCESS)

        # Calculate summary stats
        total_weeks = len(weekly_tickers)
        total_tickers = sum(len(tickers) for tickers in weekly_tickers.values())

        # Save to CSV
        scraped_date = datetime.now().strftime('%Y-%m-%d')
        output_path = save_to_csv(weekly_tickers, args.output, scraped_date)

        logger.info(f"\n🎉 Done!")
        logger.info(f"   Weeks scraped: {total_weeks}")
        logger.info(f"   Total ticker entries: {total_tickers}")
        logger.info(f"   Output: {output_path}")

        sys.exit(EXIT_SUCCESS)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Interrupted by user")
        sys.exit(EXIT_SUCCESS)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(EXIT_NETWORK_ERROR)


if __name__ == '__main__':
    main()
