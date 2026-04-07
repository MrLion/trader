#!/usr/bin/env python3
"""
Post-Market Report Generator
Run after market close (4:00-5:00 PM ET)
"""

import yfinance as yf
from datetime import datetime
from pathlib import Path
import csv

def generate_postmarket_report():
    """Generate post-market EOD report"""
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    print("🌙 POST-MARKET REPORT — " + report_date)
    print()
    
    # 1. MARKET CLOSE SUMMARY
    print("**📊 MARKET CLOSE SUMMARY**")
    indices = {}
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                close = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                change = ((close / prev) - 1) * 100
                high = data['High'].iloc[-1]
                low = data['Low'].iloc[-1]
                print(f"{ticker}: ${close:.2f} ({change:+.2f}%) | H: ${high:.2f} L: ${low:.2f}")
                indices[ticker] = (close, change)
        except:
            pass
    
    # 2. VIX CLOSE
    try:
        vix = yf.Ticker("^VIX").history(period="2d")
        if len(vix) >= 2:
            vix_close = vix['Close'].iloc[-1]
            vix_prev = vix['Close'].iloc[-2]
            vix_change = ((vix_close / vix_prev) - 1) * 100
            print(f"\nVIX: {vix_close:.2f} ({vix_change:+.2f}%)")
    except:
        pass
    
    # 3. TOP PERFORMING SECTORS (check today's scan)
    scan_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{report_date}_sector_scan.csv")
    if scan_file.exists():
        print("\n**🏆 SECTOR LEADERS (Today's Scan)**")
        with open(scan_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)[:10]
            for row in rows:
                print(f"  {row['Ticker']}: {row['1W']}% (1W) | Stage 2: {row.get('Stage2_Score', 'N/A')}")
    
    # 4. ACTION ITEMS FOR TOMORROW
    print("\n**🎯 ACTION ITEMS FOR TOMORROW**")
    print("1. ☐ Review today's gaps >3%")
    print("2. ☐ Update watchlist tiers")
    print("3. ☐ Run overnight futures check")
    print("4. ☐ Check earnings calendar for next 5 days")
    print("5. ☐ Log any trades taken today")
    
    # 5. KEY LEVELS FOR TOMORROW
    if 'SPY' in indices:
        spy_close, _ = indices['SPY']
        print(f"\n**⚡ KEY LEVELS FOR TOMORROW**")
        print(f"SPY: Support ~${spy_close * 0.98:.0f} | Resistance ~${spy_close * 1.02:.0f}")
    
    print("\n" + "—" * 50)
    print("End of day. Log your trades. Prepare for tomorrow.")
    print("\n— Ace 🎯")

if __name__ == "__main__":
    generate_postmarket_report()
