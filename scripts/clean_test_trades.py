#!/usr/bin/env python3
"""
CLEAN TEST TRADES - Phase 1: Data Cleanup Utility
===================================================

Removes test/development entries from production paper_trades.jsonl.

Test entries are identified by:
- Unrealistic entry prices (> $400 for most stocks)
- Unusually high share counts (> 500 shares)
- Missing required fields
- Duplicate entries from repeated test runs
- Known test patterns (e.g., AAPL at $500)

USAGE:
    python3 scripts/clean_test_trades.py [--dry-run] [--backup]

OPTIONS:
    --dry-run    Show what would be removed without making changes
    --backup     Create timestamped backup before cleaning
    --strict     Use stricter filtering (removes more potentially suspect entries)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Default data paths
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(__file__).parent.parent / 'data'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'


def is_test_entry(trade: Dict, strict: bool = False) -> Tuple[bool, str]:
    """
    Determine if a trade entry is test data.

    Returns: (is_test, reason)
    """
    # Check for required fields
    required = ['event', 'ticker', 'timestamp', 'entry_price', 'shares']
    for field in required:
        if field not in trade:
            return True, f"missing_{field}"

    entry_price = trade.get('entry_price', 0)
    shares = trade.get('shares', 0)
    ticker = trade.get('ticker', '')

    # Known test patterns
    if entry_price == 500.0 and shares == 1000:
        return True, "known_test_pattern_500_1000"

    if entry_price == 200.0 and shares == 100 and ticker == 'AAPL':
        # This specific pattern appears multiple times in test data
        return True, "known_test_pattern_200_100"

    # Realistic price check (most stocks are under $500)
    if entry_price > 400:
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
        if 'timestamp' in trade:
            ts = trade['timestamp']
            if isinstance(ts, str) and ts.endswith('.000000'):
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
    """Create timestamped backup of trades file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = filepath.parent / f"paper_trades_backup_{timestamp}.jsonl"

    if filepath.exists():
        with open(filepath, 'r') as src:
            with open(backup_path, 'w') as dst:
                dst.write(src.read())
        print(f"📁 Backup created: {backup_path}")

    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description='Clean test data from paper_trades.jsonl',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/clean_test_trades.py --dry-run     # Preview changes
  python3 scripts/clean_test_trades.py --backup     # Clean with backup
  python3 scripts/clean_test_trades.py --strict     # Aggressive filtering
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying file')
    parser.add_argument('--backup', action='store_true',
                       help='Create backup before cleaning')
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

    # Create backup if requested
    if args.backup:
        create_backup(args.file)

    # Confirm before proceeding
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
