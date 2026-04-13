#!/usr/bin/env python3
"""
MC STOCK CHARTS SCRAPER - Trade Ideas Scraper
============================================

Scrapes trade ideas from mcstockcharts.com/latest-report/ and outputs
a CSV compatible with watchlist_manager.py populate.

REQUIREMENTS:
-------------
    pip install requests beautifulsoup4 python-dotenv

AUTHENTICATION:
---------------
    Set environment variables:
        export MCSTOCK_USER="your_username"
        export MCSTOCK_PASS="your_password"

    Or create .env file in project root (see .env.example)

USAGE:
------
    # Basic scrape (today's report)
    python3 scripts/mcstock_scraper.py

    # Scrape specific date
    python3 scripts/mcstock_scraper.py --date 2026-04-06

    # Custom output path
    python3 scripts/mcstock_scraper.py --output data/mc_ideas.csv

    # Populate watchlist directly
    python3 scripts/mcstock_scraper.py --populate-watchlist

    # Dry run (preview without saving)
    python3 scripts/mcstock_scraper.py --dry-run

OUTPUT:
-------
    CSV with columns:
    - Ticker, Name, Sector, Industry
    - Stage2, 6M_%, 3M_%, 1M_%
    - Entry_Breakout, Stop, Risk_%
    - $Vol_M, Notes

EXAMPLE WORKFLOW:
-----------------
    1. Scrape ideas:
       python3 scripts/mcstock_scraper.py

    2. Populate watchlist:
       python3 scripts/watchlist_manager.py populate scans/mcstock_ideas_YYYY-MM-DD.csv

    3. Analyze:
       python3 scripts/analyze_watchlist.py

AUTHOR: Ace (Trading Agent)
DATE: 2026-04-07
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Configuration
BASE_URL = "https://www.mcstockcharts.com"
LOGIN_URL = f"{BASE_URL}/wp-login.php"
REPORT_URL = f"{BASE_URL}/latest-report/"
DATETIME_STR = datetime.now().strftime('%Y-%m-%d_%H%M%S')
DATE_STR = datetime.now().strftime('%Y-%m-%d')

# Project paths (script is in scripts/ directory)
SCRIPT_DIR = Path(__file__).parent

# Exit codes
EXIT_SUCCESS = 0
EXIT_AUTH_FAILED = 1
EXIT_REPORT_NOT_FOUND = 2
EXIT_NETWORK_ERROR = 3
EXIT_PARSE_ERROR = 4
EXIT_CONFIG_ERROR = 5


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
    """
    Authenticate with WordPress login.

    Returns True on success, False on failure.
    """
    logger = logging.getLogger(__name__)
    logger.info("🔐 Authenticating with MC Stock Charts...")

    try:
        # First, get the login page to capture any nonce/tokens
        response = session.get(LOGIN_URL, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for redirect_to field
        redirect_to = soup.find('input', {'name': 'redirect_to'})
        redirect_value = redirect_to['value'] if redirect_to else BASE_URL

        # Prepare login payload
        payload = {
            'log': username,
            'pwd': password,
            'rememberme': 'forever',
            'redirect_to': redirect_value,
            'testcookie': '1'
        }

        # Submit login
        response = session.post(LOGIN_URL, data=payload, timeout=30)
        response.raise_for_status()

        # Check if login succeeded
        if 'wp-login.php' in response.url or 'login_error' in response.text:
            # Check for specific error messages
            soup = BeautifulSoup(response.text, 'html.parser')
            error_div = soup.find('div', {'id': 'login_error'})
            if error_div:
                logger.error(f"Login failed: {error_div.get_text(strip=True)}")
            else:
                logger.error("Login failed: Invalid credentials or redirect issue")
            return False

        # Verify we have auth cookies
        if 'wordpress_logged_in' not in str(session.cookies):
            logger.warning("Auth cookie not found, but login may have succeeded")

        logger.info("✅ Authentication successful")
        return True

    except requests.exceptions.Timeout:
        logger.error("Login timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during login: {e}")
        return False


def fetch_report(session: requests.Session, date: Optional[str] = None) -> str:
    """
    Fetch the latest report page HTML.

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

        # Check if we got redirected to login
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


def extract_tickers(html: str, config: Optional[dict] = None) -> List[Dict]:
    """
    Extract trade ideas from report HTML.

    Looks for tickers under "THIS WEEKS READY LIST" and "WATCH LIST" sections.
    Returns list of dicts with ticker info.
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

    # Common false positives to filter out
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

    # Add extra false positives from config
    if config:
        for fp in config.get('extra_false_positives', []):
            false_positives.add(fp.upper())

    def is_valid_ticker(ticker: str) -> bool:
        """Check if a string looks like a valid ticker symbol."""
        if not ticker or len(ticker) < 2 or len(ticker) > 5:
            return False
        if not ticker.isalpha():
            return False
        if ticker.upper() in false_positives:
            return False
        return True

    def extract_from_section(section_header: str, end_headers: list, list_type: str = 'ready'):
        """Extract tickers from a specific section."""
        collecting = False

        for element in soup.find_all(['p', 'strong', 'b', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = element.get_text(strip=True).upper()

            # Start collecting when we see the start header
            if section_header in text:
                collecting = True
                logger.debug(f"Found start header: {text[:50]}")
                continue

            # Stop when we see an end header
            if collecting and any(end in text for end in end_headers):
                logger.debug(f"Found end header: {text[:50]}")
                break

            # Process p tags while collecting - pattern: TICKER    DOLLAR_PRICE
            if collecting and element.name == 'p':
                line = element.get_text(strip=True)
                # Pattern: TICKER followed by price like DOLLAR_XX.XX
                # Example: "ACLS        $96.78" or "AROC        $34.77"
                match = re.match(r'^([A-Z]{1,5})\s+\$([\d\.]+)', line)
                if match:
                    ticker = match.group(1)
                    price = match.group(2)
                    if is_valid_ticker(ticker):
                        tickers_found.add(ticker)
                        if ticker not in ticker_contexts:
                            ticker_contexts[ticker] = []
                        PRICE_PLACEHOLDER = "$" + "PRICE"
                        ticker_contexts[ticker].append(f"{list_type}: {ticker} @" + PRICE_PLACEHOLDER)
                        logger.debug("Found ticker: " + ticker + " @" + "$" + "PRICE")

    # Extract from "THIS WEEKS READY LIST" section (ends at "WATCH LIST")
    extract_from_section("THIS WEEKS READY LIST", ["WATCH LIST"], "ready")

    # Extract from "WATCH LIST" section (ends at common section markers)
    watch_endings = ["MORNING POST", "PARADE VIDEO", "TUESDAY", "WEDNESDAY",
                     "THURSDAY", "FRIDAY", "CHARTS", "DATA COURTESY"]
    extract_from_section("WATCH LIST", watch_endings, "watch")

    logger.info(f"🎯 Found {len(tickers_found)} potential tickers")

    # Build idea dicts
    for ticker in sorted(tickers_found):
        ideas.append({
            'Ticker': ticker,
            'Name': '',  # Will be filled by yfinance if needed
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


def load_scraper_config(config_path: Optional[str] = None) -> dict:
    """Load scraper validation config from YAML."""
    if config_path is None:
        config_path = PROJECT_ROOT / 'config' / 'scraper_config.yaml'

    defaults = {
        'validation': {
            'min_price': 10,
            'min_market_cap': 1_000_000_000,
            'min_history_days': 200,
            'min_dollar_volume': 20_000_000,
        },
        'extra_false_positives': [],
    }

    path = Path(config_path)
    if path.exists():
        try:
            import yaml
            with open(path) as f:
                user_config = yaml.safe_load(f) or {}
            for key in defaults:
                if key in user_config:
                    defaults[key] = {**defaults[key], **user_config[key]} if isinstance(defaults[key], dict) else user_config[key]
            return defaults
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to load scraper config: {e}, using defaults")

    return defaults


def validate_tickers(ideas: List[Dict], config: Optional[dict] = None) -> List[Dict]:
    """
    Validate tickers against Yahoo Finance and enrich with data.

    Args:
        ideas: List of ticker dicts
        config: Validation config from load_scraper_config()

    Returns:
        Validated and enriched ideas
    """
    logger = logging.getLogger(__name__)
    logger.info("🔍 Validating tickers with Yahoo Finance...")

    if config is None:
        config = load_scraper_config()

    validation = config.get('validation', {})
    min_price = validation.get('min_price', 10)
    min_market_cap = validation.get('min_market_cap', 1_000_000_000)
    min_history_days = validation.get('min_history_days', 200)
    min_dollar_volume = validation.get('min_dollar_volume', 20_000_000)

    import yfinance as yf

    validated = []

    for idea in ideas:
        ticker = idea['Ticker']
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Check if valid stock
            if not info or 'symbol' not in info:
                logger.debug(f"Skipping {ticker}: No data from YF")
                continue

            # Basic filters
            price = info.get('currentPrice', 0)
            if price < min_price:
                logger.debug(f"Skipping {ticker}: Price ${price} < ${min_price}")
                continue

            market_cap = info.get('marketCap', 0)
            if market_cap < min_market_cap:
                logger.debug(f"Skipping {ticker}: Market cap ${market_cap/1e9:.1f}B < ${min_market_cap/1e9:.1f}B")
                continue

            # Get historical data for calculations
            hist = stock.history(period="1y")
            if len(hist) < min_history_days:
                logger.debug(f"Skipping {ticker}: {len(hist)} days history < {min_history_days}")
                continue

            current = hist['Close'].iloc[-1]
            avg_vol = hist['Volume'].tail(50).mean()
            dollar_vol = current * avg_vol  # In dollars (not millions)

            if dollar_vol < min_dollar_volume:
                logger.debug(f"Skipping {ticker}: Dollar volume ${dollar_vol/1e6:.1f}M < ${min_dollar_volume/1e6:.0f}M")
                continue

            # Calculate returns
            ret_1m = (current / hist['Close'].iloc[-21] - 1) * 100 if len(hist) >= 21 else 0
            ret_3m = (current / hist['Close'].iloc[-63] - 1) * 100 if len(hist) >= 63 else 0
            ret_6m = (current / hist['Close'].iloc[-126] - 1) * 100 if len(hist) >= 126 else 0

            # Calculate Stage 2 score
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            sma100 = hist['Close'].rolling(100).mean().iloc[-1]
            sma200 = hist['Close'].rolling(200).mean().iloc[-1]
            high_52w = hist['Close'].rolling(252).max().iloc[-1]

            stage = 0
            if current > sma100: stage += 1
            if current > sma200: stage += 1
            if sma20 > sma50 > sma100 > sma200: stage += 1
            if current >= high_52w * 0.85: stage += 1

            # Calculate ATR and entry levels
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            entry = current + (atr * 0.5)  # Slight breakout
            stop = current - (2 * atr)
            risk_pct = ((entry - stop) / entry) * 100 if entry > 0 else 0

            idea.update({
                'Name': info.get('shortName', ticker),
                'Sector': info.get('sector', 'Unknown'),
                'Industry': info.get('industry', 'Unknown'),
                'Stage2': stage,
                '6M_%': round(ret_6m, 1),
                '3M_%': round(ret_3m, 1),
                '1M_%': round(ret_1m, 1),
                'Entry_Breakout': round(entry, 2),
                'Stop': round(stop, 2),
                'Risk_%': round(risk_pct, 1),
                '$Vol_M': round(dollar_vol / 1e6, 1)
            })

            validated.append(idea)
            logger.debug(f"✅ Validated {ticker}")

        except Exception as e:
            logger.debug(f"Error validating {ticker}: {e}")
            continue

    logger.info(f"✅ {len(validated)}/{len(ideas)} tickers validated")
    return validated


def save_to_csv(ideas: List[Dict], output_path: Optional[str] = None) -> Path:
    """Save ideas to CSV file."""
    if not ideas:
        raise ValueError("No ideas to save")

    if output_path:
        path = Path(output_path)
    else:
        path = PROJECT_ROOT / f'scans/mcstock_ideas_{DATE_STR}.csv'

    path.parent.mkdir(parents=True, exist_ok=True)

    # Determine fieldnames from first idea
    fieldnames = list(ideas[0].keys())

    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ideas)

    return path


def populate_watchlist(ideas: List[Dict]) -> None:
    """Populate watchlist directly from ideas."""
    logger = logging.getLogger(__name__)

    # Save to temp CSV first
    temp_path = PROJECT_ROOT / f'scans/temp_mcstock_{DATETIME_STR}.csv'
    save_to_csv(ideas, str(temp_path))

    # Import and call watchlist_manager
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

    # Clean up temp file
    temp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description='Scrape trade ideas from MC Stock Charts'
    )
    parser.add_argument(
        '--date',
        help='Specific date to scrape (YYYY-MM-DD format)'
    )
    parser.add_argument(
        '--output',
        help='Custom output path for CSV'
    )
    parser.add_argument(
        '--populate-watchlist',
        action='store_true',
        help='Automatically populate watchlist after scraping'
    )
    parser.add_argument(
        '--config',
        help='Path to scraper config YAML file'
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip Yahoo Finance validation (faster)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview results without saving'
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

        # Preview in dry-run mode
        if args.dry_run:
            logger.info("\n📋 DRY RUN - Found ideas:")
            for idea in ideas[:10]:  # Show first 10
                logger.info(f"  {idea['Ticker']}: {idea.get('Name', 'N/A')} "
                          f"(Stage {idea.get('Stage2', '?')}, Risk {idea.get('Risk_%', '?')}%)")
            if len(ideas) > 10:
                logger.info(f"  ... and {len(ideas) - 10} more")
            sys.exit(EXIT_SUCCESS)

        # Save to CSV
        output_path = save_to_csv(ideas, args.output)
        logger.info(f"✅ Saved {len(ideas)} ideas to: {output_path}")

        # Populate watchlist if requested
        if args.populate_watchlist:
            logger.info("📝 Populating watchlist...")
            populate_watchlist(ideas)

        logger.info("🎉 Done!")
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
