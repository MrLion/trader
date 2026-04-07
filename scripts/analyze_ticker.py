#!/usr/bin/env python3
"""Analyze a single ticker using manual pivot from watchlist."""

import yfinance as yf
import pandas as pd
import csv
from pathlib import Path

def get_manual_pivot(ticker):
    """Get manual pivot price from watchlist if it exists."""
    watchlist_path = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')
    if not watchlist_path.exists():
        return None
    
    with open(watchlist_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Ticker'].upper() == ticker.upper():
                try:
                    return float(row['Pivot_Price'])
                except:
                    return None
    return None

def analyze_ticker(ticker):
    """Full technical analysis of a ticker in standard format."""
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y")
        
        if len(hist) < 200:
            print(f"{ticker}: Insufficient data ({len(hist)} days)")
            return
            
        current = hist['Close'].iloc[-1]
        name = info.get('shortName', ticker)
        sector = info.get('sector', 'Unknown')
        industry = info.get('industry', 'Unknown')
        
        # Returns
        ret_1m = (current / hist['Close'].iloc[-20] - 1) * 100
        ret_3m = (current / hist['Close'].iloc[-65] - 1) * 100 if len(hist) >= 65 else 0
        ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0
        
        # Moving averages
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        ma50 = hist['Close'].rolling(50).mean().iloc[-1]
        ma150 = hist['Close'].rolling(150).mean().iloc[-1]
        ma200 = hist['Close'].rolling(200).mean().iloc[-1]
        
        # 52-week high/low
        high_52w = hist['Close'].max()
        from_high = ((high_52w - current) / high_52w) * 100
        
        # Stage 2 score
        score = 0
        if current > ma150: score += 1
        if current > ma200: score += 1
        if ma20 > ma50 > ma150 > ma200: score += 1
        if from_high < 15: score += 1
        
        # ATR calculation
        high_low = hist['High'] - hist['Low']
        high_close = abs(hist['High'] - hist['Close'].shift())
        low_close = abs(hist['Low'] - hist['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        
        # Entry/stop - use manual pivot if available
        manual_pivot = get_manual_pivot(ticker)
        if manual_pivot:
            pivot_price = manual_pivot
            recent_high = hist['High'].tail(5).max()
        else:
            recent_high = hist['High'].tail(5).max()
            pivot_price = recent_high + 0.01
        
        recent_low = hist['Low'].tail(10).min()
        stop = max(recent_low, current - 2 * atr)
        risk = (pivot_price - stop) / pivot_price * 100
        
        # Status emoji
        status = '🟢' if score >= 3 else '🟡' if score == 2 else '🔴'
        
        # Above MAs check
        above_20 = '✓' if current > ma20 else '✗'
        above_50 = '✓' if current > ma50 else '✗'
        above_150 = '✓' if current > ma150 else '✗'
        above_200 = '✓' if current > ma200 else '✗'
        
        print(f"\n{ticker.upper()} ({name}) — ${current:.2f}\n")
        print("| Metric | Value |")
        print("|:-------|:------|")
        print("| Company | {} |".format(name))
        print("| Sector | {} |".format(sector))
        print("| Industry | {} |".format(industry))
        print("| 1M Return | {:+.1f}% |".format(ret_1m))
        print("| 3M Return | {:+.1f}% |".format(ret_3m))
        print("| 6M Return | {:+.1f}% |".format(ret_6m))
        print("| Stage 2 Score | {}/4 {} |".format(score, status))
        print("| From 52W High | {:.1f}% |".format(from_high))
        print("| Above All MAs | {} {} {} {} 20/50/150/200 |".format(above_20, above_50, above_150, above_200))
        
        print("\n---\n\nENTRY SETUP\n")
        print("| Level | Price |")
        print("|:------|:------|")
        if manual_pivot:
            print("| Entry | ${:.2f} (your pivot) |".format(pivot_price))
        else:
            print("| Entry | ${:.2f} (break above ${:.2f}) |".format(pivot_price, recent_high))
        print("| Stop | ${:.2f} (2 ATR / below support) |".format(stop))
        print("| Risk | {:.1f}% |".format(risk))
        
        print("\nAssessment:")
        print("- **Momentum** — 6M: +{:.1f}%, 3M: +{:.1f}%, 1M: {:.1f}%".format(ret_6m, ret_3m, ret_1m))
        print("- **Stage 2** — {}/4 {}: Above 100/200 MA, MAs aligned".format(score, status))
        print("- **Distance from highs** — {:.1f}%".format(from_high))
        print("- **Risk level** — {:.1f}%".format(risk))
        
        # Verdict
        if score >= 3 and risk < 10:
            verdict = "A-TIER — Strong setup. Watch for volume-confirmed breakout."
        elif score >= 3:
            verdict = "TIER B — Developing Stage 2 setup. Promote to A on breakout."
        elif score >= 2:
            verdict = "TIER C — On radar, monitor for improvement."
        else:
            verdict = "PASS — Below Stage 2 criteria."
        
        print("\nVerdict: {}".format(verdict))
        
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_ticker.py <TICKER>")
        sys.exit(1)
    analyze_ticker(sys.argv[1].upper())
