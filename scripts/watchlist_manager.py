#!/usr/bin/env python3
"""
WATCHLIST MANAGER - Automated Watchlist Population & Management
================================================================

A command-line tool for managing the trading watchlist. Entry scoring
is handled automatically by analyze_watchlist.py based on Stage 2 score,
risk %, proximity to pivot, and momentum.

USAGE:
------
    python3 watchlist_manager.py <command> [args]

COMMANDS:
---------
    populate <scan_file.csv>
        Populate watchlist from a scan CSV file.

    add <ticker> [notes]
        Add a stock to watchlist.
        Example: python3 watchlist_manager.py add AAPL "Pullback to 21 EMA"

    remove <ticker>
        Remove a stock from the watchlist.
        Example: python3 watchlist_manager.py remove XEL

    list
        Display watchlist with current data.

WATCHLIST CRITERIA (from AGENTS.MD):
------------------------------------
    Hard Filters:
    - Price >= $10
    - Average daily dollar volume >= $20 million
    - Market cap >= $1 billion
    - Price above 100/200 SMA, within 25% of 52W high
    - 6-month return in top 20% of universe

    Removal Triggers:
    - Breaks below 200-day SMA
    - RS line makes new 3-month low
    - Base fails (undercuts base low on heavy volume)
    - No pattern development after 6 weeks on list

ENTRY SCORING:
--------------
    Entry scores are calculated by analyze_watchlist.py (max 100 pts):
    - Stage 2 Score: 30 pts max (≥4/4 = +30, ≥3/4 = +20, etc.)
    - Risk %: 30 pts max (<10% = +30, <15% = +20, etc.)
    - Proximity: 25 pts max (<3% = +25, <5% = +15, etc.)
    - Momentum: 15 pts max (6M return >50% = +15, >25% = +10)

    Tier 1: ≥60 pts | Tier 2: 40-59 pts | Tier 3: <40 pts

FILES:
------
    Watchlist data: /data/watchlist.csv
    Scan input:    /scans/*.csv (from midday_scan.py or other scanners)

EXAMPLE WORKFLOW:
-----------------
    1. Run midday scan: python3 midday_scan.py
       -> Saves to scans/leading_stocks_YYYY-MM-DD.csv

    2. Populate watchlist:
       python3 watchlist_manager.py populate scans/leading_stocks_2026-04-06.csv

    3. Analyze for entry scores:
       python3 scripts/analyze_watchlist.py

    4. Remove names that fall below criteria or rank in Tier 3 consistently

AUTHOR: Ace (Trading Agent)
DATE: 2026-04-06
"""

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

WATCHLIST_PATH = '/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv'
SCAN_DIR = '/Users/mintmrlion/.openclaw/workspaces/trader/scans'

def load_watchlist():
    """Load existing watchlist or create new."""
    if Path(WATCHLIST_PATH).exists():
        return pd.read_csv(WATCHLIST_PATH)
    else:
        columns = ['Ticker', 'Stage', 'RS_Rank', 'Base_Count', 'Pattern_Type',
                   'Pivot_Price', 'Stop_Level', 'Target_1', 'Target_2', 'R_Ratio',
                   'Avg_Volume_50d', 'Market_Cap', 'Sector', 'Industry', 'Notes',
                   'Added_Date', 'Alert_Set']
        return pd.DataFrame(columns=columns)

def get_stock_data(ticker, force=False):
    """Fetch fresh data for a ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        df = t.history(period="1y")

        min_days = 50 if force else 200
        if df.empty or len(df) < min_days:
            return None

        current = df['Close'].iloc[-1]
        avg_vol = df['Volume'].tail(50).mean()

        # Calculate ATR
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]

        # Stage 2 score using shared 10-point system
        stage = calculate_stage2_score(df)

        # 6-month return
        six_mo_return = (current / df['Close'].iloc[-126] - 1) * 100 if len(df) >= 126 else 0

        return {
            'Ticker': ticker.upper(),
            'Price': current,
            'Stage': stage,
            '6M_Return': six_mo_return,
            'ATR': atr,
            'Avg_Volume': avg_vol,
            'Sector': info.get('sector', 'Unknown'),
            'Industry': info.get('industry', 'Unknown'),
            'Market_Cap': info.get('marketCap', 0),
            'Name': info.get('shortName', ticker)
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def add_to_watchlist(ticker, notes='', force=False):
    """Add a single stock to watchlist."""
    df = load_watchlist()

    # Check if already exists
    if ticker.upper() in df['Ticker'].values:
        print(f"⚠️ {ticker} already in watchlist")
        return

    data = get_stock_data(ticker, force=force)
    if not data:
        print(f"❌ Could not fetch data for {ticker}")
        return

    new_row = {
        'Ticker': data['Ticker'],
        'Stage': data['Stage'],
        'RS_Rank': round(data['6M_Return'], 1),
        'Base_Count': '',
        'Pattern_Type': '',
        'Pivot_Price': '',
        'Stop_Level': round(data['Price'] - 2 * data['ATR'], 2) if data['ATR'] else '',
        'Target_1': '',
        'Target_2': '',
        'R_Ratio': '',
        'Avg_Volume_50d': int(data['Avg_Volume']),
        'Market_Cap': data['Market_Cap'],
        'Sector': data['Sector'],
        'Industry': data['Industry'],
        'Notes': notes,
        'Added_Date': datetime.now().strftime('%Y-%m-%d'),
        'Alert_Set': 'No'
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Added {ticker} to watchlist")

def populate_from_scan(scan_file):
    """Populate watchlist from a scan CSV file."""
    if not Path(scan_file).exists():
        print(f"❌ Scan file not found: {scan_file}")
        return

    scan_df = pd.read_csv(scan_file)
    df = load_watchlist()

    existing = set(df['Ticker'].values) if not df.empty else set()
    added = 0

    for _, row in scan_df.iterrows():
        ticker = row['Ticker']

        if ticker in existing:
            continue

        new_row = {
            'Ticker': ticker,
            'Stage': row['Stage2'],
            'RS_Rank': round(row['6M_%'], 1),
            'Base_Count': '',
            'Pattern_Type': '',
            'Pivot_Price': row['Entry_Breakout'] if 'Entry_Breakout' in row else '',
            'Stop_Level': row['Stop'] if 'Stop' in row else '',
            'Target_1': '',
            'Target_2': '',
            'R_Ratio': '',
            'Avg_Volume_50d': int(row['$Vol_M'] * 1000000) if '$Vol_M' in row else 0,
            'Market_Cap': 0,
            'Sector': row.get('Sector', 'Unknown'),
            'Industry': row.get('Industry', 'Unknown'),
            'Notes': f"6M: +{row['6M_%']:.1f}%, Risk: {row['Risk_%']:.1f}%",
            'Added_Date': datetime.now().strftime('%Y-%m-%d'),
            'Alert_Set': 'No'
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        existing.add(ticker)
        added += 1

    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Added {added} stocks from scan to watchlist")

def list_watchlist():
    """List current watchlist."""
    df = load_watchlist()

    if df.empty:
        # DESIGN FIX: Empty watchlist guidance - add how to populate help text
        print("📭 Watchlist is empty")
        print("\n💡 HOW TO POPULATE:")
        print("   1. From scan CSV: python3 scripts/watchlist_manager.py populate scans/leading_stocks_YYYY-MM-DD.csv")
        print("   2. Add single ticker: python3 scripts/watchlist_manager.py add AAPL")
        print("   3. Run midday scan: python3 scripts/midday_scan.py")
        print("   4. Sector scan: python3 scripts/sector_scan_comprehensive.py")
        print("\n   See docs/getting-started.md for full workflow")
        return

    # DESIGN FIX: Portfolio overlap - Add [IN PORTFOLIO] indicator
    # Load portfolio positions to check overlap
    import json
    from pathlib import Path
    portfolio_file = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/paper_positions.json')
    portfolio_tickers = set()
    if portfolio_file.exists():
        try:
            with open(portfolio_file) as f:
                positions = json.load(f)
                if isinstance(positions, dict):
                    portfolio_tickers = set(positions.keys())
                elif isinstance(positions, list):
                    portfolio_tickers = {p.get('ticker', '') for p in positions}
        except (json.JSONDecodeError, IOError):
            pass  # Portfolio file might be corrupted or empty

    # Add portfolio indicator column
    display_df = df[['Ticker', 'Stage', 'RS_Rank', 'Sector', 'Notes']].copy()
    if portfolio_tickers:
        display_df['Portfolio'] = display_df['Ticker'].apply(
            lambda t: '✓ IN PORTFOLIO' if t in portfolio_tickers else ''
        )

    print(f"\n📋 WATCHLIST ({len(df)} total)\n")
    print(display_df.to_string(index=False))
    print(f"\n💡 Run `python3 scripts/analyze_watchlist.py` to see entry scores (Tier 1/2/3)")
    print(f"   Stage 2 Score: 0-10 (8 = Price > 20/50/100/200 MA, proper stacking, 200MA rising, within 25% of high, above 1.25x low)")

def remove_ticker(ticker, dry_run=False):
    """Remove a ticker from watchlist.

    CLI-004: Added --dry-run flag for destructive commands.
    """
    df = load_watchlist()

    if ticker.upper() not in df['Ticker'].values:
        print(f"{EMOJI_CROSS} {ticker} not in watchlist")
        return

    if dry_run:
        print(f"{EMOJI_INFO} DRY RUN: Would remove {ticker} from watchlist")
        print(f"   (Use without --dry-run to actually remove)")
        return

    df = df[df['Ticker'] != ticker.upper()]
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"{EMOJI_CHECK} Removed {ticker} from watchlist")


def remove_all_tickers(force=False, dry_run=False):
    """Remove all tickers from watchlist with confirmation.

    CLI-004: Added --dry-run flag for destructive commands.
    """
    df = load_watchlist()

    if df.empty:
        print(f"{EMOJI_WARN} Watchlist is already empty")
        return

    count = len(df)

    # Backup before clearing (always created)
    from datetime import datetime
    backup_path = Path(WATCHLIST_PATH).parent / f"watchlist_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    if dry_run:
        print(f"{EMOJI_INFO} DRY RUN: Would remove all {count} tickers from watchlist")
        print(f"   Would create backup at: {backup_path}")
        print(f"   (Use without --dry-run to actually remove)")
        return

    # Create backup
    df.to_csv(backup_path, index=False)

    if not force:
        print(f"\n{EMOJI_WARN} WARNING: You are about to delete ALL {count} tickers from your watchlist.")
        print(f"\n{EMOJI_INFO} A backup will be created at: {backup_path}")
        print("   You can restore it manually if needed.")
        print("\nType 'DELETE ALL' to confirm, or anything else to cancel:")
        confirmation = input("> ")

        if confirmation.strip() != "DELETE ALL":
            print(f"{EMOJI_CROSS} Cancelled. No tickers were removed.")
            print(f"{EMOJI_INFO} Backup kept at: {backup_path}")
            return

    # Clear watchlist
    empty_df = pd.DataFrame(columns=df.columns)
    empty_df.to_csv(WATCHLIST_PATH, index=False)
    print(f"{EMOJI_CHECK} Removed all {count} tickers from watchlist")
    print(f"{EMOJI_INFO} Backup saved to: {backup_path}")

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python watchlist_manager.py populate <scan_file>")
        print("  python watchlist_manager.py add <ticker> [notes] [-force|--force]")
        print("  python watchlist_manager.py list")
        print("  python watchlist_manager.py remove <ticker> [--dry-run]")
        print("  python watchlist_manager.py remove-all [-force|--force] [--dry-run]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'populate' and len(sys.argv) >= 3:
        populate_from_scan(sys.argv[2])
    elif cmd == 'add' and len(sys.argv) >= 3:
        force = '--force' in sys.argv or '-force' in sys.argv
        # Extract notes (everything after ticker that's not --force or -force)
        args = sys.argv[2:]
        raw_ticker = args[0]
        # FINDING-011: Validate ticker format
        try:
            ticker = validate_ticker(raw_ticker)
        except ValueError as e:
            print(f"{EMOJI_CROSS} {e}")
            sys.exit(1)
        notes_args = [a for a in args[1:] if a not in ('--force', '-force')]
        notes = ' '.join(notes_args) if notes_args else ''
        add_to_watchlist(ticker, notes, force=force)
    elif cmd == 'list':
        list_watchlist()
    elif cmd == 'remove' and len(sys.argv) >= 3:
        dry_run = '--dry-run' in sys.argv
        # FINDING-011: Validate ticker format
        try:
            ticker = validate_ticker(sys.argv[2])
        except ValueError as e:
            print(f"{EMOJI_CROSS} {e}")
            sys.exit(1)
        remove_ticker(ticker, dry_run=dry_run)
    elif cmd == 'remove-all':
        force = '--force' in sys.argv or '-force' in sys.argv
        dry_run = '--dry-run' in sys.argv
        remove_all_tickers(force=force, dry_run=dry_run)
    else:
        print("Invalid command")
