#!/usr/bin/env python3
"""Clean test trades from paper_trades.jsonl - remove them permanently."""
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'

def is_test_trade(trade: dict) -> bool:
    """Detect test trades."""
    meta = trade.get('_meta', {})
    ticker = trade.get('ticker', '')
    price = trade.get('entry_price', 0)

    if meta.get('test_mode'):
        return True
    if ticker == 'AAPL' and price == 150.0:
        return True
    if meta.get('validation_failed'):
        if ticker in ('MSFT', 'GOOGL', 'STOCK0', 'STOCK1', 'STOCK2'):
            return True
    return False


def clean_log():
    if not TRADES_FILE.exists():
        print("No trade log found.")
        return

    # Read all trades
    with open(TRADES_FILE, 'r') as f:
        lines = f.readlines()

    # Filter out test trades
    production_trades = []
    removed = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            trade = json.loads(line)
            if is_test_trade(trade):
                removed += 1
                print(f"🗑️  Removing test trade: {trade.get('ticker')} @ ${trade.get('entry_price')} ({trade.get('event')})")
            else:
                production_trades.append(line)
        except json.JSONDecodeError:
            continue

    # Backup original
    backup_path = TRADES_FILE.with_suffix('.jsonl.backup')
    TRADES_FILE.rename(backup_path)
    print(f"💾 Original log backed up to: {backup_path}")

    # Write clean log
    with open(TRADES_FILE, 'w') as f:
        for line in production_trades:
            f.write(line + '\n')

    print(f"\n✅ Cleaned {removed} test trades")
    print(f"✅ {len(production_trades)} production trades remaining")


if __name__ == '__main__':
    clean_log()
