#!/usr/bin/env python3
"""Force sync local state with live Alpaca API to remove test garbage."""
import json
from pathlib import Path
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from alpaca_client import AlpacaClient

def sync():
    print("🔄 Synchronizing local state with Alpaca API...")
    try:
        client = AlpacaClient(mode='paper')

        # 1. Sync Account
        account = client.get_account()
        account_data = {
            "initial_capital": 100000.0,
            "cash": account['cash'],
            "equity": account['equity'],
            "day_pnl": 0.0,
            "trade_count": 0, # Resetting since we are purging garbage
            "entries_today": 0,
            "last_entry_reset": "2026-04-08",
            "open_positions": len(client.list_positions()),
            "timestamp": "2026-04-08T20:00:00Z"
        }

        # 2. Sync Positions
        positions = client.list_positions()

        # Save to files
        data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')

        with open(data_dir / 'paper_account.json', 'w') as f:
            json.dump(account_data, f, indent=2)

        with open(data_dir / 'paper_positions.json', 'w') as f:
            json.dump(positions, f, indent=2)

        print(f"✅ Successfully synced: {len(positions)} positions and account data.")
        print("🗑️  All test garbage (STOCK0, DELISTED) has been purged.")

    except Exception as e:
        print(f"❌ Sync failed: {e}")

if __name__ == "__main__":
    sync()
