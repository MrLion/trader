#!/usr/bin/env python3
"""
CLEAN TEST TRADES - Trade Log Cleanup Utility
==============================================

Removes test/development entries from production paper_trades.jsonl.
Consolidates functionality from clean_trade_log.py and clean_test_trades.py.

Test entries are identified by:
- Explicit test_mode flag in metadata
- Known test patterns (AAPL at $150, validation_failed with test tickers)
- Unrealistic entry prices (> $5000 - extreme test data errors)
- Unusually high share counts (> 500 shares)
- Missing required fields
- Duplicate entries from repeated test runs
- Old dates (2024, 2025 in 2026)
- Known test tickers (DELISTED, STOCK0-2)

USAGE:
    python3 scripts/clean_test_trades.py [options]

OPTIONS:
    --dry-run    Show what would be removed without making changes
    --auto       Non-interactive mode (auto-backup + no confirmation)
    --strict     Use stricter filtering (removes more potentially suspect entries)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from traderlib.paths import data_dir

# Default data paths - resolved via traderlib.paths
DATA_DIR = data_dir()
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'


def is_test_entry(trade: Dict, strict: bool = False, seen_signatures: set = None) -> Tuple[bool, str]:
    """
    Determine if a trade entry is test data.
    Combines detection from both clean_test_trades.py and clean_trade_log.py

    Returns: (is_test, reason)
    """
    meta = trade.get('_meta', {})
    entry_price = trade.get('entry_price', 0)
    shares = trade.get('shares', 0)
    ticker = trade.get('ticker', '')
    timestamp = trade.get('timestamp', '')

    # === From clean_trade_log.py - Explicit test markers ===
    if meta.get('test_mode'):
        return True, "test_mode_flag"

    if ticker == 'AAPL' and entry_price == 150.0:
        return True, "test_pattern_aapl_150"

    if meta.get('validation_failed') and ticker in ('MSFT', 'GOOGL', 'STOCK0', 'STOCK1', 'STOCK2'):
        return True, "validation_failed_test"

    # === Original clean_test_trades.py checks ===
    # Check for required fields
    required = ['event', 'ticker', 'timestamp', 'entry_price', 'shares']
    for field in required:
        if field not in trade:
            return True, f"missing_{field}"

    # Known test patterns - AAPL/MSFT/GOOGL at exact prices from test data
    if ticker in ('AAPL', 'MSFT', 'GOOGL', 'DELISTED'):
        if entry_price in (150.0, 151.0, 152.0, 200.0, 250.0, 300.0, 500.0):
            return True, f"known_test_ticker_{ticker}_{entry_price}"

    # Stock0, Stock1, Stock2 patterns from integration tests
    if ticker.startswith('STOCK') and ticker[5:].isdigit():
        return True, f"test_stock_pattern_{ticker}"

    # Old dates (2024 or earlier in 2026) are likely test data
    if isinstance(timestamp, str):
        if timestamp.startswith('2024-'):
            return True, "old_date_2024"
        if timestamp.startswith('2025-'):
            return True, "old_date_2025"

    # Known test patterns
    if entry_price == 500.0 and shares == 1000:
        return True, "known_test_pattern_500_1000"

    if entry_price == 200.0 and shares == 100 and ticker == 'AAPL':
        return True, "known_test_pattern_200_100"

    # Realistic price check (flag extreme prices that are likely test data errors)
    if entry_price > 5000:
        return True, f"unrealistic_price_{entry_price}"

    # Realistic position size check
    if shares > 500:
        return True, f"unrealistic_shares_{shares}"

    # Position value check (most positions under $50k)
    position_value = entry_price * shares
    if position_value > 50000:
        return True, f"unrealistic_value_{position_value}"

    # Strict mode additional checks
    if strict:
        # Check for repeated timestamps (possible test duplicates)
        if isinstance(timestamp, str) and timestamp.endswith('.000000'):
            return True, "synthetic_timestamp"

        # Check for suspicious P&L on exits
        if trade.get('event') == 'EXIT':
            pnl = trade.get('realized_pnl', 0)
            if abs(pnl) > 10000:
                return True, f"unrealistic_pnl_{pnl}"

    return False, ""


def analyze_trades(trades: List[Dict], strict: bool = False) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Analyze trades and separate production from test data.

    Returns: (production_trades, test_trades, stats)
    """
    production = []
    test = []
    reasons = {}

    # Track duplicates
    seen_signatures = set()

    for trade in trades:
        # Create signature for duplicate detection
        sig = (
            trade.get('event', ''),
            trade.get('ticker', ''),
            trade.get('entry_price', 0),
            trade.get('shares', 0),
            trade.get('timestamp', '')[:19]  # Precision to seconds
        )

        # Check for duplicates
        if sig in seen_signatures:
            test.append(trade)
            reasons['duplicate'] = reasons.get('duplicate', 0) + 1
            continue

        seen_signatures.add(sig)

        # Check if test entry
        is_test, reason = is_test_entry(trade, strict)
        if is_test:
            test.append(trade)
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            production.append(trade)

    stats = {
        'total': len(trades),
        'production': len(production),
        'test': len(test),
        'reasons': reasons
    }

    return production, test, stats


def load_trades(filepath: Path) -> List[Dict]:
    """Load trades from JSONL file."""
    trades = []
    if not filepath.exists():
        print(f"❌ Trades file not found: {filepath}")
        return trades

    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                trade = json.loads(line)
                trades.append(trade)
            except json.JSONDecodeError as e:
                print(f"⚠️  Warning: Could not parse line {line_num}: {e}")

    return trades


def save_trades(trades: List[Dict], filepath: Path):
    """Save trades to JSONL file."""
    with open(filepath, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')


def create_backup(filepath: Path) -> Path:
    """Create backup of trades file with .jsonl.backup extension."""
    backup_path = filepath.with_suffix('.jsonl.backup')

    if filepath.exists():
        with open(filepath, 'r') as src:
            with open(backup_path, 'w') as dst:
                dst.write(src.read())
        print(f"💾 Original log backed up to: {backup_path}")

    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description='Clean test data from paper_trades.jsonl',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/clean_test_trades.py --dry-run     # Preview changes
  python3 scripts/clean_test_trades.py --auto         # Non-interactive mode
  python3 scripts/clean_test_trades.py --strict     # Aggressive filtering
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying file')
    parser.add_argument('--auto', action='store_true',
                       help='Non-interactive mode (auto-backup + no confirmation)')
    parser.add_argument('--strict', action='store_true',
                       help='Use stricter filtering criteria')
    parser.add_argument('--file', type=Path, default=TRADES_FILE,
                       help=f'Path to trades file (default: {TRADES_FILE})')

    args = parser.parse_args()

    print("=" * 60)
    print("📊 TRADE DATA CLEANUP UTILITY")
    print("=" * 60)
    print()

    # Load trades
    print(f"📂 Loading trades from: {args.file}")
    trades = load_trades(args.file)
    print(f"   Loaded {len(trades)} total entries")
    print()

    if not trades:
        print("❌ No trades to process")
        return 1

    # Analyze
    print("🔍 Analyzing entries...")
    production, test, stats = analyze_trades(trades, strict=args.strict)

    # Report
    print()
    print("=" * 60)
    print("📈 ANALYSIS RESULTS")
    print("=" * 60)
    print(f"   Total entries:     {stats['total']}")
    print(f"   Production:        {stats['production']}")
    print(f"   Test entries:      {stats['test']}")
    print(f"   Reduction:         {stats['test']/stats['total']*100:.1f}%")
    print()

    if stats['reasons']:
        print("📝 Removal reasons:")
        for reason, count in sorted(stats['reasons'].items(), key=lambda x: -x[1]):
            print(f"   - {reason}: {count}")
        print()

    # Sample of entries to remove
    if test:
        print("🔍 Sample entries to be removed:")
        for i, entry in enumerate(test[:3], 1):
            print(f"   {i}. {entry.get('ticker')} @ ${entry.get('entry_price')} "
                  f"x {entry.get('shares')} shares ({entry.get('event')})")
        if len(test) > 3:
            print(f"   ... and {len(test) - 3} more")
        print()

    # Dry run or execute
    if args.dry_run:
        print("🏃 DRY RUN MODE - No changes made")
        print("   Run without --dry-run to apply changes")
        return 0

    if not test:
        print("✅ No test entries found - file is clean!")
        return 0

    # Auto mode: non-interactive with automatic backup
    if args.auto:
        create_backup(args.file)
        save_trades(production, args.file)
        print(f"\n✅ Cleaned {stats['test']} test trades")
        print(f"✅ {len(production)} production trades remaining")
        return 0

    # Interactive mode: Create backup and confirm before proceeding
    create_backup(args.file)

    print("⚠️  WARNING: This will permanently remove test entries")
    print(f"   {stats['test']} entries will be deleted")
    print()

    if input("Proceed? Type 'clean' to confirm: ") != 'clean':
        print("❌ Cancelled")
        return 0

    # Execute cleanup
    save_trades(production, args.file)
    print()
    print("✅ Cleanup complete!")
    print(f"   Removed {stats['test']} test entries")
    print(f"   Kept {len(production)} production entries")
    print(f"   File: {args.file}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
