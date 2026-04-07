#!/usr/bin/env python3
"""
WATCHLIST MANAGER - Automated Watchlist Population & Management
================================================================

A command-line tool for managing the trading watchlist with automatic
tier assignment based on Stage 2 score and relative strength.

USAGE:
------
    python3 watchlist_manager.py <command> [args]

COMMANDS:
---------
    populate <scan_file.csv>
        Populate watchlist from a scan CSV file. Auto-assigns tiers based on:
        - Stage 4 + 6M return >50%  -> Tier B
        - Stage 3 or lower RS       -> Tier C
        
    add <ticker> [tier] [notes]
        Manually add a stock to watchlist.
        Example: python3 watchlist_manager.py add AAPL B "Pullback to 21 EMA"
        
    promote <ticker> <new_tier>
        Promote or demote a stock to a different tier.
        Example: python3 watchlist_manager.py promote HAL A
        
    remove <ticker>
        Remove a stock from the watchlist.
        Example: python3 watchlist_manager.py remove XEL
        
    list [tier]
        Display watchlist. Optionally filter by tier (A, B, or C).
        Example: python3 watchlist_manager.py list A

TIER SYSTEM:
------------
    A - Actionable: Mature setup, pivot defined, entry within 1-3 days
       Max: 5 stocks | Pre-calc entry/stop/size, alerts set
       
    B - Developing: Constructive base forming, not at buy point yet
       Max: 10 stocks | Monitor daily, promote to A when pattern ready
       
    C - On Radar: Strong RS, interesting story, early stage
       Max: 15 stocks | Weekly review, promote to B when base starts

AUTO-TIER LOGIC:
----------------
    When populating from scans, tier is assigned automatically:
    - Stage 4 (perfect Stage 2) + 6M return >50%  -> Tier B
    - Stage 3 or lower momentum                    -> Tier C
    - Manual adds default to Tier C unless specified

WATCHLIST CRITERIA (from AGENTS.md):
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
       -> Auto-adds Stage 2+ candidates to Tier C/B
       
    3. Review and promote promising setups:
       python3 watchlist_manager.py list C
       python3 watchlist_manager.py promote HAL B
       
    4. When pattern matures, promote to A:
       python3 watchlist_manager.py promote HAL A
       
    5. Set alerts for Tier A entries in your broker platform

AUTHOR: Ace (Trading Agent)
DATE: 2026-04-06
"""

import pandas as pd
import yfinance as yf
import json
from datetime import datetime
from pathlib import Path

WATCHLIST_PATH = '/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv'
SCAN_DIR = '/Users/mintmrlion/.openclaw/workspaces/trader/scans'

def load_watchlist():
    """Load existing watchlist or create new."""
    if Path(WATCHLIST_PATH).exists():
        return pd.read_csv(WATCHLIST_PATH)
    else:
        columns = ['Ticker', 'Tier', 'Stage', 'RS_Rank', 'Base_Count', 'Pattern_Type', 
                   'Pivot_Price', 'Stop_Level', 'Target_1', 'Target_2', 'R_Ratio',
                   'Avg_Volume_50d', 'Market_Cap', 'Sector', 'Industry', 'Notes', 
                   'Added_Date', 'Promoted_Date', 'Alert_Set']
        return pd.DataFrame(columns=columns)

def get_stock_data(ticker):
    """Fetch fresh data for a ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        df = t.history(period="1y")
        
        if df.empty or len(df) < 200:
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
        
        # Stage 2 score
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma100 = df['Close'].rolling(100).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1]
        high_52w = df['Close'].rolling(252).max().iloc[-1]
        
        stage = 0
        if current > sma100: stage += 1
        if current > sma200: stage += 1
        if sma20 > sma50 > sma100 > sma200: stage += 1
        if current >= high_52w * 0.85: stage += 1
        
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

def add_to_watchlist(ticker, tier='C', notes='', manual=False):
    """Add a single stock to watchlist."""
    df = load_watchlist()
    
    # Check if already exists
    if ticker.upper() in df['Ticker'].values:
        print(f"⚠️ {ticker} already in watchlist")
        return
    
    data = get_stock_data(ticker)
    if not data:
        print(f"❌ Could not fetch data for {ticker}")
        return
    
    # Auto-determine tier if not manual
    if not manual:
        # If Stage 4 and near highs with tight pattern -> Tier B
        if data['Stage'] == 4 and data['6M_Return'] > 30:
            tier = 'B'
        else:
            tier = 'C'
    
    new_row = {
        'Ticker': data['Ticker'],
        'Tier': tier,
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
        'Promoted_Date': '',
        'Alert_Set': 'No'
    }
    
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Added {ticker} to Tier {tier}")

def populate_from_scan(scan_file, auto_tier=True):
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
        
        # Auto-tier logic
        if auto_tier:
            if row['Stage2'] == 4 and row['6M_%'] > 50:
                tier = 'B'
            else:
                tier = 'C'
        else:
            tier = 'C'
        
        new_row = {
            'Ticker': ticker,
            'Tier': tier,
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
            'Promoted_Date': '',
            'Alert_Set': 'No'
        }
        
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        existing.add(ticker)
        added += 1
    
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Added {added} stocks from scan to watchlist")

def list_watchlist(tier=None):
    """List current watchlist, optionally filtered by tier."""
    df = load_watchlist()
    
    if df.empty:
        print("Watchlist is empty")
        return
    
    if tier:
        df = df[df['Tier'] == tier]
    
    print(f"\n📋 WATCHLIST ({len(df)} total)\n")
    print(df[['Ticker', 'Tier', 'Stage', 'RS_Rank', 'Sector', 'Notes']].to_string(index=False))

def promote_ticker(ticker, new_tier):
    """Promote/demote a ticker to a different tier."""
    df = load_watchlist()
    
    if ticker.upper() not in df['Ticker'].values:
        print(f"❌ {ticker} not in watchlist")
        return
    
    # Convert Promoted_Date to string type to avoid dtype issues
    df['Promoted_Date'] = df['Promoted_Date'].astype(str)
    
    df.loc[df['Ticker'] == ticker.upper(), 'Tier'] = new_tier
    df.loc[df['Ticker'] == ticker.upper(), 'Promoted_Date'] = datetime.now().strftime('%Y-%m-%d')
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Promoted {ticker} to Tier {new_tier}")

def remove_ticker(ticker):
    """Remove a ticker from watchlist."""
    df = load_watchlist()
    
    if ticker.upper() not in df['Ticker'].values:
        print(f"❌ {ticker} not in watchlist")
        return
    
    df = df[df['Ticker'] != ticker.upper()]
    df.to_csv(WATCHLIST_PATH, index=False)
    print(f"✅ Removed {ticker} from watchlist")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python watchlist_manager.py populate <scan_file>")
        print("  python watchlist_manager.py add <ticker> [tier] [notes]")
        print("  python watchlist_manager.py list [tier]")
        print("  python watchlist_manager.py promote <ticker> <tier>")
        print("  python watchlist_manager.py remove <ticker>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'populate' and len(sys.argv) >= 3:
        populate_from_scan(sys.argv[2])
    elif cmd == 'add' and len(sys.argv) >= 3:
        tier = sys.argv[3] if len(sys.argv) > 3 else 'C'
        notes = sys.argv[4] if len(sys.argv) > 4 else ''
        add_to_watchlist(sys.argv[2], tier, notes, manual=True)
    elif cmd == 'list':
        tier = sys.argv[2] if len(sys.argv) > 2 else None
        list_watchlist(tier)
    elif cmd == 'promote' and len(sys.argv) >= 4:
        promote_ticker(sys.argv[2], sys.argv[3])
    elif cmd == 'remove' and len(sys.argv) >= 3:
        remove_ticker(sys.argv[2])
    else:
        print("Invalid command")
