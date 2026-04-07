#!/usr/bin/env python3
"""
STAGE 2 + RELATIVE STRENGTH SCREEN
================================

Reads tickers from a file and screens for Stage 2 candidates with 
strong relative strength vs SPY.

USAGE:
------
    python3 stage2_rs_screen.py <ticker_file.txt>
    python3 stage2_rs_screen.py data/weekly_watchlist.txt

INPUT FILE FORMAT:
------------------
    - One ticker per line
    - Comments start with #
    - Blank lines ignored

EXAMPLE INPUT FILE:
-------------------
    # Energy
    XOM
    CVX
    COP
    
    # Tech
    NVDA
    AAPL
    MSFT

OUTPUT:
-------
    - Stage 2 qualified stocks (above 150/200 MA, accumulation pattern)
    - Ranked by 6-month return (relative strength)
    - Top 20% by RS flagged for Tier B consideration

FILES:
------
    Output saved to: scans/stage2_screen_YYYY-MM-DD.csv

AUTHOR: Ace (Trading Agent)
DATE: 2026-04-06
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import csv

def load_tickers_from_file(filepath):
    """Load tickers from a text file, one per line."""
    tickers = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                # Extract ticker (first word before any spaces or comments)
                ticker = line.split()[0].upper()
                tickers.append(ticker)
    return tickers

def run_stage2_screen(tickers):
    """Run Stage 2 + RS screen on provided tickers."""
    
    print("🔍 STAGE 2 + RELATIVE STRENGTH SCREEN")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"Scanning {len(tickers)} tickers...")
    print()
    
    results = []
    errors = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y", interval="1d")
            info = stock.info
            
            if len(hist) < 150:
                continue
                
            # Current price
            close = hist['Close'].iloc[-1]
            
            # Universe filter: Price >= $10
            if close < 10:
                continue
                
            # Universe filter: Check volume (need ~2M+ shares for $20M daily dollar vol at $10)
            avg_volume = hist['Volume'].rolling(50).mean().iloc[-1]
            dollar_volume = close * avg_volume
            if dollar_volume < 20000000:  # $20M minimum
                continue
                
            # Moving averages
            ma150 = hist['Close'].rolling(150).mean().iloc[-1]
            ma200 = hist['Close'].rolling(200).mean().iloc[-1]
            
            # Stage 2 criteria
            above_150 = close > ma150
            above_200 = close > ma200
            ma150_above_200 = ma150 > ma200
            
            # 52-week high/low
            low_52w = hist['Close'].min()
            high_52w = hist['Close'].max()
            above_25_low = close >= low_52w * 1.25
            within_25_high = close >= high_52w * 0.75
            from_high = ((high_52w - close) / high_52w) * 100
            
            # 6-month return for RS ranking
            six_month_ago = hist['Close'].iloc[-130] if len(hist) >= 130 else hist['Close'].iloc[0]
            six_month_return = ((close / six_month_ago) - 1) * 100
            
            # Calculate RS vs SPY
            spy = yf.Ticker("SPY").history(period="1y")
            if len(spy) >= 130:
                spy_close = spy['Close'].iloc[-1]
                spy_six_month = spy['Close'].iloc[-130]
                spy_return = ((spy_close / spy_six_month) - 1) * 100
                rs_ratio = six_month_return - spy_return
            else:
                rs_ratio = 0
                
            # Volume pattern: accumulation days
            avg_vol_50 = hist['Volume'].rolling(50).mean().iloc[-1]
            recent = hist.tail(10)
            up_days = recent[recent['Close'] > recent['Open']]
            accumulation_days = len(up_days[up_days['Volume'] > avg_vol_50 * 1.5])
            
            # Check if Stage 2 qualified (relaxed: >= 1 accumulation day)
            stage2_qualified = all([
                above_150,
                above_200,
                ma150_above_200,
                above_25_low,
                within_25_high,
                accumulation_days >= 1
            ])
            
            results.append({
                'Ticker': ticker,
                'Price': close,
                '6M_Return': six_month_return,
                'RS_vs_SPY': rs_ratio,
                'Stage2': stage2_qualified,
                'Above_150MA': above_150,
                'Above_200MA': above_200,
                'MA150_Above_200': ma150_above_200,
                'Within_25_High': within_25_high,
                'From_52W_High': from_high,
                'Acc_Days': accumulation_days,
                'Dollar_Vol_M': dollar_volume / 1000000,
                'Sector': info.get('sector', 'Unknown'),
                'Industry': info.get('industry', 'Unknown')
            })
            
        except Exception as e:
            errors.append((ticker, str(e)))
            continue
    
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    if len(df) == 0:
        print("No stocks passed initial screening.")
        return None
    
    # Filter Stage 2 only
    stage2_df = df[df['Stage2'] == True].copy()
    
    # Rank by 6-month return (RS)
    if len(stage2_df) > 0:
        stage2_df = stage2_df.sort_values('6M_Return', ascending=False)
        
        # Top 20% by 6M return
        top_20_pct = int(len(stage2_df) * 0.2) + 1
        top_rs = stage2_df.head(top_20_pct)
        
        # Mark tiers
        stage2_df['Tier'] = 'C'
        stage2_df.loc[stage2_df.index.isin(top_rs.index), 'Tier'] = 'B'
    else:
        top_rs = pd.DataFrame()
    
    print("=" * 70)
    print(f"RESULTS: {len(stage2_df)} Stage 2 qualified | Top 20% RS: {len(top_rs)} names")
    print("=" * 70)
    print()
    
    if len(top_rs) > 0:
        print("🎯 TOP STAGE 2 + RS NAMES (Best candidates)")
        print("-" * 70)
        print(f"{'Ticker':<8} {'Price':>10} {'6M Return':>12} {'RS vs SPY':>12} {'From High':>12}")
        print("-" * 70)
        
        for _, row in top_rs.head(20).iterrows():
            print(f"{row['Ticker']:<8} ${row['Price']:>8.2f} {row['6M_Return']:>+10.1f}% {row['RS_vs_SPY']:>+10.1f}% {row['From_52W_High']:>10.1f}%")
    
    print()
    
    if len(stage2_df) > 0:
        print(f"📊 ALL STAGE 2 NAMES")
        print("-" * 70)
        print(f"{'Ticker':<8} {'Sector':<20} {'6M Return':>12} {'From High':>12}")
        print("-" * 70)
        
        for _, row in stage2_df.iterrows():
            print(f"{row['Ticker']:<8} {row['Sector']:<20} {row['6M_Return']:>+10.1f}% {row['From_52W_High']:>10.1f}%")
    
    print()
    print("📝 NEXT STEPS:")
    print("1. Review charts — look for VCP patterns, flat bases")
    print("2. Calculate RS line (stock vs SPY) — should be at/near highs")
    print("3. Check earnings dates — avoid within 5 days")
    print("4. Set pivot prices and run analyze_watchlist.py for entry scores")
    print()
    
    if len(errors) > 0:
        print(f"⚠️ {len(errors)} tickers had errors (skipped)")
    
    # Save results to CSV
    if len(stage2_df) > 0:
        output_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/stage2_screen_{datetime.now().strftime('%Y-%m-%d')}.csv")
        stage2_df.to_csv(output_file, index=False)
        print(f"\n📁 Saved to: {output_file}")
    
    return stage2_df

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 stage2_rs_screen.py <ticker_file.txt>")
        print("\nExample ticker file format:")
        print("  # Energy")
        print("  XOM")
        print("  CVX")
        print("  COP")
        print("  # Tech")
        print("  NVDA")
        print("  AAPL")
        sys.exit(1)
    
    ticker_file = sys.argv[1]
    
    if not Path(ticker_file).exists():
        print(f"Error: File not found: {ticker_file}")
        sys.exit(1)
    
    tickers = load_tickers_from_file(ticker_file)
    
    if len(tickers) == 0:
        print("Error: No valid tickers found in file")
        sys.exit(1)
    
    run_stage2_screen(tickers)
