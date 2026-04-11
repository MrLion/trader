#!/usr/bin/env python3
"""Force sync local state with live Alpaca API to remove test garbage."""
import json
from datetime import datetime
from pathlib import Path
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from traderlib.alpaca_client import AlpacaClient

DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'
DAILY_TRACKER_FILE = DATA_DIR / 'daily_tracker.json'


def _is_test_trade(trade: dict) -> bool:
    """Detect test trades using metadata patterns."""
    meta = trade.get('_meta', {})
    ticker = trade.get('ticker', '')
    price = trade.get('entry_price', 0)

    # Explicit test mode flag
    if meta.get('test_mode'):
        return True

    # Known test pattern: AAPL at exactly $150.00 (synthetic test price)
    if ticker == 'AAPL' and price == 150.0:
        return True

    # Known test patterns in validation failures
    if meta.get('validation_failed'):
        if ticker in ('MSFT', 'GOOGL', 'STOCK0', 'STOCK1', 'STOCK2'):
            return True
    return False


def count_production_trades():
    """Count production trades from log for accurate counters."""
    today = datetime.now().strftime('%Y-%m-%d')
    trade_count = 0
    entries_today = 0

    if not TRADES_FILE.exists():
        return {'trade_count': 0, 'entries_today': 0}

    try:
        with open(TRADES_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trade = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if _is_test_trade(trade):
                    continue

                trade_count += 1

                if trade.get('event') == 'ENTRY':
                    ts = trade.get('timestamp', '')
                    if ts.startswith(today):
                        entries_today += 1
    except Exception as e:
        print(f"⚠️  Warning: Could not read trade log: {e}")
        return {'trade_count': 0, 'entries_today': 0}

    return {'trade_count': trade_count, 'entries_today': entries_today}


def sync():
    print("🔄 Synchronizing local state with Alpaca API...")
    try:
        client = AlpacaClient(mode='paper')

        # Count production trades from log before syncing
        counts = count_production_trades()
        print(f"   Found {counts['trade_count']} production trades, "
              f"{counts['entries_today']} entries today")

        # 1. Sync Positions
        positions = client.list_positions()

        # 2. Sync Daily Tracker (preserve last_entry_reset, update if new day)
        today = datetime.now().strftime('%Y-%m-%d')
        daily_tracker = {
            "last_entry_reset": today,
            "timestamp": datetime.now().isoformat()
        }

        # Save to files
        data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')

        with open(data_dir / 'paper_positions.json', 'w') as f:
            json.dump(positions, f, indent=2)

        with open(data_dir / 'daily_tracker.json', 'w') as f:
            json.dump(daily_tracker, f, indent=2)

        print(f"✅ Successfully synced: {len(positions)} positions.")
        print(f"   Daily tracker: last_entry_reset = {today}")
        print(f"   Trade count: {counts['trade_count']}, Entries today: {counts['entries_today']}")
        print("🗑️  Test trades filtered from counters (identified by _meta.test_mode or validation patterns).")

    except Exception as e:
        print(f"❌ Sync failed: {e}")

if __name__ == "__main__":
    sync()
