#!/usr/bin/env python3
"""Analyze entire watchlist for favorable entry points."""

import yfinance as yf
import pandas as pd
import csv
from pathlib import Path

WATCHLIST_PATH = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')

def analyze_watchlist():
    """Analyze all watchlist stocks and rank by entry attractiveness."""
    
    if not WATCHLIST_PATH.exists():
        print("❌ Watchlist not found")
        return
    
    with open(WATCHLIST_PATH, 'r') as f:
        reader = csv.DictReader(f)
        watchlist = list(reader)
    
    results = []
    
    for row in watchlist:
        ticker = row['Ticker']
        pivot = float(row['Pivot_Price']) if row['Pivot_Price'] else None
        
        if not pivot:
            continue
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            info = stock.info
            
            if len(hist) < 200:
                continue
            
            current = hist['Close'].iloc[-1]
            
            # Returns
            ret_1m = (current / hist['Close'].iloc[-20] - 1) * 100
            ret_3m = (current / hist['Close'].iloc[-65] - 1) * 100 if len(hist) >= 65 else 0
            ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0
            
            # MAs
            ma20 = hist['Close'].rolling(20).mean().iloc[-1]
            ma50 = hist['Close'].rolling(50).mean().iloc[-1]
            ma150 = hist['Close'].rolling(150).mean().iloc[-1]
            ma200 = hist['Close'].rolling(200).mean().iloc[-1]
            
            # 52-week high
            high_52w = hist['Close'].max()
            from_high = ((high_52w - current) / high_52w) * 100
            
            # Stage 2 score
            score = 0
            if current > ma150: score += 1
            if current > ma200: score += 1
            if ma20 > ma50 > ma150 > ma200: score += 1
            if from_high < 15: score += 1
            
            # ATR
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]
            
            # Stop
            recent_low = hist['Low'].tail(10).min()
            stop = max(recent_low, current - 2 * atr)
            risk = (pivot - stop) / pivot * 100 if pivot > stop else 0
            
            # Distance to pivot
            dist_to_pivot = ((pivot - current) / current) * 100 if current > 0 else 0
            
            # Entry attractiveness score (higher = better)
            # Factors: Stage 2 score, risk %, proximity to pivot, momentum
            entry_score = 0
            if score >= 4: entry_score += 30
            elif score >= 3: entry_score += 20
            elif score >= 2: entry_score += 10
            
            if risk < 10: entry_score += 30
            elif risk < 15: entry_score += 20
            elif risk < 20: entry_score += 10
            
            if dist_to_pivot < 3: entry_score += 25  # Very close to breakout
            elif dist_to_pivot < 5: entry_score += 15
            elif dist_to_pivot < 10: entry_score += 5
            
            if ret_6m > 50: entry_score += 15
            elif ret_6m > 25: entry_score += 10
            
            results.append({
                'Ticker': ticker,
                'Current': round(current, 2),
                'Pivot': pivot,
                'Dist_to_Pivot': round(dist_to_pivot, 1),
                'Stop': round(stop, 2),
                'Risk_%': round(risk, 1),
                'Stage2': score,
                '1M': round(ret_1m, 1),
                '3M': round(ret_3m, 1),
                '6M': round(ret_6m, 1),
                'From_High': round(from_high, 1),
                'Entry_Score': entry_score,
                'Sector': info.get('sector', 'Unknown')
            })
            
        except Exception as e:
            print(f"⚠️ {ticker}: {e}")
    
    # Sort by entry score (descending)
    results.sort(key=lambda x: x['Entry_Score'], reverse=True)
    
    # Display
    print("\n🎯 WATCHLIST ENTRY RANKINGS — Ranked by Favorability\n")
    print("=" * 120)
    
    # Tier 1: Best setups (Score ≥60)
    print("\n**🟢 TIER 1 — BEST ENTRY SETUP (Score ≥60)**\n")
    tier1 = [r for r in results if r['Entry_Score'] >= 60]
    if tier1:
        print(f"{'Ticker':<8} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'Stage2':<8} {'6M':<10} {'Sector'}")
        print("-" * 120)
        for r in tier1:
            print(f"{r['Ticker']:<8} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {r['Risk_%']:<7.1f}% {r['Stage2']:<6}/4 🟢 {r['6M']:+>8.1f}% {r['Sector']}")
    else:
        print("No Tier 1 setups currently")
    
    # Tier 2: Good setups (Score 40-59)
    print("\n\n**🟡 TIER 2 — GOOD SETUP (Score 40-59)**\n")
    tier2 = [r for r in results if 40 <= r['Entry_Score'] < 60]
    if tier2:
        print(f"{'Ticker':<8} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'Stage2':<8} {'6M':<10} {'Sector'}")
        print("-" * 120)
        for r in tier2:
            print(f"{r['Ticker']:<8} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {r['Risk_%']:<7.1f}% {r['Stage2']:<6}/4 🟡 {r['6M']:+>8.1f}% {r['Sector']}")
    else:
        print("No Tier 2 setups currently")
    
    # Tier 3: Watch only (Score <40)
    print("\n\n**🔴 TIER 3 — WAIT / MONITOR (Score <40)**\n")
    tier3 = [r for r in results if r['Entry_Score'] < 40]
    if tier3:
        print(f"{'Ticker':<8} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'Stage2':<8} {'6M':<10} {'Sector'}")
        print("-" * 120)
        for r in tier3:
            print(f"{r['Ticker']:<8} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {r['Risk_%']:<7.1f}% {r['Stage2']:<6}/4 🔴 {r['6M']:+>8.1f}% {r['Sector']}")
    else:
        print("No Tier 3 setups currently")
    
    # Summary
    print("\n" + "=" * 120)
    print(f"\n📊 SUMMARY: {len(tier1)} Tier 1 | {len(tier2)} Tier 2 | {len(tier3)} Tier 3 | Total: {len(results)}")
    
    # Top 3 recommendations
    if results:
        print("\n🎯 TOP 3 RECOMMENDATIONS:")
        for i, r in enumerate(results[:3], 1):
            print(f"  {i}. {r['Ticker']} — {r['Dist_to_Pivot']:.1f}% from pivot, {r['Risk_%']:.1f}% risk, Stage 2 {r['Stage2']}/4")

if __name__ == "__main__":
    analyze_watchlist()
