#!/usr/bin/env python3
"""Migrate watchlist Stage values from 4-point to 7-point system."""

import sys
from pathlib import Path
import pandas as pd
import yfinance as yf

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from stage2_utils import calculate_stage2_score

WATCHLIST_PATH = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')

def migrate_watchlist():
    """Recalculate Stage values for all watchlist entries."""
    if not WATCHLIST_PATH.exists():
        print("❌ Watchlist not found")
        return

    df = pd.read_csv(WATCHLIST_PATH)
    print(f"📋 Found {len(df)} watchlist entries")
    print("🔄 Recalculating Stage 2 scores using 7-point system...")

    updated_count = 0
    failed_count = 0

    for idx, row in df.iterrows():
        ticker = row['Ticker']
        old_stage = row['Stage']

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

            if len(hist) < 200:
                print(f"  ⚠️ {ticker}: Insufficient data, keeping old score {old_stage}")
                failed_count += 1
                continue

            new_stage = calculate_stage2_score(hist)
            df.at[idx, 'Stage'] = new_stage

            if new_stage != old_stage:
                print(f"  ✅ {ticker}: {old_stage} → {new_stage}")
            else:
                print(f"  ℹ️  {ticker}: {old_stage} (unchanged)")

            updated_count += 1

        except Exception as e:
            print(f"  ❌ {ticker}: Error - {e}, keeping old score {old_stage}")
            failed_count += 1

    # Save updated watchlist
    df.to_csv(WATCHLIST_PATH, index=False)

    print(f"\n📊 Migration complete:")
    print(f"   Updated: {updated_count}")
    print(f"   Failed: {failed_count}")
    print(f"\n💾 Saved to: {WATCHLIST_PATH}")

    # Summary statistics
    print(f"\n📈 New Stage distribution:")
    stage_counts = df['Stage'].value_counts().sort_index(ascending=False)
    for stage, count in stage_counts.items():
        tier = "Tier 1" if stage >= 6 else "Tier 2" if stage >= 4 else "Tier 3"
        print(f"   Stage {stage}: {count} stocks ({tier})")

if __name__ == "__main__":
    migrate_watchlist()
