#!/usr/bin/env python3
"""
MC STOCK CHARTS HISTORICAL SCRAPER
==================================

Scrapes historical weekly reports from mcstockcharts.com using direct URL generation
and outputs a time-series CSV for backtesting with weekly rotation.

USAGE:
------
    # Scrape all available history (back to 2023)
    python3 scripts/mcstock_historical_scraper.py

    # Scrape with date filter
    python3 scripts/mcstock_historical_scraper.py --start 2024-01-01 --end 2025-04-01

    # Scrape specific date range
    python3 scripts/mcstock_historical_scraper.py --start 2024-01-01 --end 2025-04-01

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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Configuration
BASE_URL = "https://www.mcstockcharts.com"
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


def generate_trading_dates(start_date: Optional[str], end_date: Optional[str]) -> List[date]:
    """
    Generate Mon-Fri trading dates within the range.
    Skips weekends. Market holidays will result in 404s which are handled gracefully.

    Args:
        start_date: Start date string (YYYY-MM-DD) or None for 2023-01-01
        end_date: End date string (YYYY-MM-DD) or None for today

    Returns:
        List of date objects (Mon-Fri only)
    """
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start = date(2023, 1, 1)  # Default to 2023

    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end = date.today()

    trading_dates = []
    current = start

    while current <= end:
        # Monday = 0, Friday = 4, Saturday = 5, Sunday = 6
        if current.weekday() < 5:  # Mon-Fri only
            trading_dates.append(current)
        current += timedelta(days=1)

    return trading_dates


def build_report_url(date_obj: date) -> str:
    """
    Build the pre-market report URL for a given date.

    Pattern: /members/pre-market-report-{weekday}-{month}-{day}-{year}-900a-m-est/
    """
    weekday_name = date_obj.strftime('%A').lower()
    month_name = date_obj.strftime('%B').lower()
    day = date_obj.day
    year = date_obj.year

    return f"{BASE_URL}/members/pre-market-report-{weekday_name}-{month_name}-{day}-{year}-900a-m-est/"


def fetch_report(session: requests.Session, url: str) -> Optional[str]:
    """
    Fetch a report page.

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


def extract_tickers_from_report(html: str) -> List[Tuple[str, str]]:
    """
    Extract tickers from report HTML.

    Returns list of (ticker, list_type) tuples.
    """
    logger = logging.getLogger(__name__)
    tickers = []

    soup = BeautifulSoup(html, 'html.parser')

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

    return tickers


def get_monday_date(date_obj: date) -> str:
    """
    Get the Monday of the week for a given date.
    MC Stock Charts weeks are Monday-based.
    """
    days_since_monday = date_obj.weekday()
    monday = date_obj - timedelta(days=days_since_monday)
    return monday.strftime('%Y-%m-%d')


def scrape_historical_data(
    session: requests.Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    delay: float = 2.0
) -> Dict[str, Dict[str, Tuple[str, str]]]:
    """
    Scrape historical data from MC Stock Charts using direct URL generation.

    Returns dict: {week_start: {ticker: (list_type, first_seen_date)}}
    """
    logger = logging.getLogger(__name__)
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]] = {}

    # Generate trading dates (Mon-Fri)
    trading_dates = generate_trading_dates(start_date, end_date)
    logger.info(f"📅 Generated {len(trading_dates)} trading dates (Mon-Fri)")

    skipped_dates = 0

    # Process dates from newest to oldest
    for date_obj in reversed(trading_dates):
        date_str = date_obj.strftime('%Y-%m-%d')
        week_start = get_monday_date(date_obj)

        # Initialize week if not exists
        if week_start not in weekly_tickers:
            weekly_tickers[week_start] = {}
            logger.info(f"📅 Processing week of {week_start}")

        # Build URL and fetch
        url = build_report_url(date_obj)
        logger.info(f"  📄 Scraping {date_str}")

        html = fetch_report(session, url)

        if html is None:
            logger.info(f"    ⏭️  No pre-market report for {date_str} (market holiday or missing)")
            skipped_dates += 1
            continue

        # Extract tickers
        day_tickers = extract_tickers_from_report(html)

        for ticker, list_type in day_tickers:
            if ticker not in weekly_tickers[week_start]:
                weekly_tickers[week_start][ticker] = (list_type, date_str)

        logger.info(f"    ✅ Found {len(day_tickers)} tickers for {date_str}")

        time.sleep(delay)

    logger.info(f"\n📊 Summary: {len(weekly_tickers)} weeks, {skipped_dates} dates skipped (no report)")

    return weekly_tickers


def save_to_csv(
    weekly_tickers: Dict[str, Dict[str, Tuple[str, str]]],
    output_path: str,
    scraped_date: str
) -> Path:
    """Save weekly tickers to CSV."""
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
        '--delay',
        type=float,
        default=2.0,
        help='Seconds between requests (default: 2.0)'
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
