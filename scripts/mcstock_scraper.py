#!/usr/bin/env python3
"""
MC STOCK CHARTS SCRAPER - Trade Ideas Scraper
============================================

Scrapes trade ideas from mcstockcharts.com/latest-report/ and outputs
a CSV compatible with watchlist_manager.py populate.

REQUIREMENTS:
-------------
    pip install requests beautifulsoup4

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

import requests
from bs4 import BeautifulSoup

# Configuration
BASE_URL = "https://www.mcstockcharts.com"
LOGIN_URL = f"{BASE_URL}/wp-login.php"
REPORT_URL = f"{BASE_URL}/latest-report/"
DATETIME_STR = datetime.now().strftime('%Y-%m-%d_%H%M%S')
DATE_STR = datetime.now().strftime('%Y-%m-%d')

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
        env_path = Path('/Users/mintmrlion/.openclaw/workspaces/trader/.env')
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


def extract_tickers(html: str) -> List[Dict]:
    """
    Extract trade ideas from report HTML.

    Returns list of dicts with ticker info.
    """
    logger = logging.getLogger(__name__)
    logger.debug("🔍 Parsing report HTML...")

    soup = BeautifulSoup(html, 'html.parser')
    ideas = []

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Get text content
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Patterns to match ticker mentions
    # Common patterns in MC reports: "$AAPL", "AAPL", "(AAPL)", etc.
    ticker_patterns = [
        r'\$([A-Z]{1,5})\b',  # $AAPL
        r'\b([A-Z]{2,5})\s+(?:\(|at\s+\$)',  # AAPL (context)
        r'(?:buy|add|position)\s+([A-Z]{2,5})\b',  # buy AAPL
        r'(?:watching|watch)\s+([A-Z]{2,5})\b',  # watching AAPL
    ]

    tickers_found = set()
    ticker_contexts = {}

    for line in lines:
        for pattern in ticker_patterns:
            matches = re.findall(pattern, line, re.IGNORECASE)
            for ticker in matches:
                ticker = ticker.upper()
                # Filter out common false positives
                if ticker in ['THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'USD', 'CEO', 'CFO']:
                    continue
                if len(ticker) < 2 or len(ticker) > 5:
                    continue

                tickers_found.add(ticker)
                if ticker not in ticker_contexts:
                    ticker_contexts[ticker] = []
                ticker_contexts[ticker].append(line[:150])  # Store context

    # Try to find tables with stock data
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                # First cell often contains ticker
                first_cell = cells[0].get_text(strip=True)
                if re.match(r'^[A-Z]{1,5}$', first_cell):
                    ticker = first_cell.upper()
                    tickers_found.add(ticker)
                    if ticker not in ticker_contexts:
                        ticker_contexts[ticker] = []
                    ticker_contexts[ticker].append(row.get_text(separator=' ', strip=True)[:150])

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


def validate_tickers(ideas: List[Dict]) -> List[Dict]:
    """
    Validate tickers against Yahoo Finance and enrich with data.

    Args:
        ideas: List of ticker dicts

    Returns:
        Validated and enriched ideas
    """
    logger = logging.getLogger(__name__)
    logger.info("🔍 Validating tickers with Yahoo Finance...")

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
            if price < 10:  # Skip stocks under $10
                logger.debug(f"Skipping {ticker}: Price ${price} < $10")
                continue

            market_cap = info.get('marketCap', 0)
            if market_cap < 1e9:  # Skip if market cap < $1B
                logger.debug(f"Skipping {ticker}: Market cap too small")
                continue

            # Get historical data for calculations
            hist = stock.history(period="1y")
            if len(hist) < 200:
                logger.debug(f"Skipping {ticker}: Insufficient history")
                continue

            current = hist['Close'].iloc[-1]
            avg_vol = hist['Volume'].tail(50).mean()
            dollar_vol = (current * avg_vol) / 1e6  # In millions

            if dollar_vol < 20:  # Skip if avg dollar volume < $20M
                logger.debug(f"Skipping {ticker}: Dollar volume ${dollar_vol:.1f}M < $20M")
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
                '$Vol_M': round(dollar_vol, 1)
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
        path = Path(f'/Users/mintmrlion/.openclaw/workspaces/trader/scans/mcstock_ideas_{DATE_STR}.csv')

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
    temp_path = Path(f'/Users/mintmrlion/.openclaw/workspaces/trader/scans/temp_mcstock_{DATETIME_STR}.csv')
    save_to_csv(ideas, str(temp_path))

    # Import and call watchlist_manager
    import subprocess
    result = subprocess.run(
        ['python3', '/Users/mintmrlion/.openclaw/workspaces/trader/scripts/watchlist_manager.py', 'populate', str(temp_path)],
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

        # Extract tickers
        ideas = extract_tickers(html)

        if not ideas:
            logger.warning("⚠️ No trade ideas found in report")
            sys.exit(EXIT_SUCCESS)

        logger.info(f"📝 Found {len(ideas)} potential ideas")

        # Validate tickers (unless skipped)
        if not args.skip_validation:
            import pandas as pd  # Required by validate_tickers
            ideas = validate_tickers(ideas)

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
