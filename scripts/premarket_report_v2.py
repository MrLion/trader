#!/usr/bin/env python3
"""
Pre-Market Report Generator
Reads from scans/ folder and combines with futures/indices data
"""

import yfinance as yf
import json
from datetime import datetime
from pathlib import Path

def load_sector_scan():
    """Load the latest sector scan from CSV"""
    import csv
    from datetime import datetime
    from pathlib import Path
    
    today = datetime.now().strftime('%Y-%m-%d')
    scan_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{today}_sector_scan.csv")
    
    if not scan_file.exists():
        print(f"⚠️ No sector scan found for {today}")
        print(f"   Run: python3 sector_scan.py")
        return None
    
    sectors = {}
    factors = {}
    leading = []
    lagging = []
    spy_benchmark = {}
    
    with open(scan_file, 'r') as f:
        reader = csv.reader(f)
        section = 'sectors'
        
        for row in reader:
            if len(row) == 0:
                continue
            
            # Skip headers
            if row[0] == 'ticker':
                continue
            if row[0] == 'factor_ticker':
                section = 'factors'
                continue
            if row[0] == 'spy_benchmark':
                section = 'summary'
                spy_benchmark['1_week_return'] = float(row[2]) if len(row) > 2 else 0
                continue
            if row[0] == 'leading_sectors':
                leading = row[1].split('|') if len(row) > 1 and row[1] else []
                continue
            if row[0] == 'lagging_sectors':
                lagging = row[1].split('|') if len(row) > 1 and row[1] else []
                continue
                
            if section == 'sectors' and len(row) >= 7 and row[0] != '':
                ticker = row[0]
                try:
                    sectors[ticker] = {
                        'name': row[1],
                        'price': float(row[2]),
                        '1_week_return': float(row[3]),
                        'vs_spy': float(row[4]),
                        'above_50ma': row[5] == 'True',
                        'above_200ma': row[6] == 'True'
                    }
                except ValueError:
                    continue
            elif section == 'factors' and len(row) >= 5:
                ticker = row[0]
                try:
                    factors[ticker] = {
                        'name': row[1],
                        '1_week_return': float(row[2]),
                        'vs_spy': float(row[3]),
                        'status': row[4]
                    }
                except ValueError:
                    continue
    
    return {
        'sectors': sectors,
        'factors': factors,
        'leading_sectors': leading,
        'lagging_sectors': lagging,
        'spy_benchmark': spy_benchmark
    }

def generate_report():
    """Generate pre-market report"""
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    print("🌅 PRE-MARKET REPORT — " + report_date)
    print()
    
    # 1. Load sector scan
    scan = load_sector_scan()
    
    # 2. Fetch futures
    print("**📊 OVERNIGHT FUTURES**")
    futures = {}
    for ticker, symbol in [("ES=F", "/ES"), ("NQ=F", "/NQ"), ("RTY=F", "/RTY"), 
                           ("YM=F", "/YM"), ("CL=F", "/CL"), ("GC=F", "/GC")]:
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if len(data) >= 2:
                curr = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                change = curr - prev
                pct = ((curr/prev)-1)*100
                arrow = "↑" if change > 0 else "↓"
                print(f"{symbol:5} ${curr:,.2f} {arrow} ({change:+.2f}, {pct:+.2f}%)")
                futures[symbol] = (curr, change, pct)
        except:
            pass
    
    # VIX
    try:
        vix = yf.Ticker("^VIX").history(period="5d")
        if len(vix) >= 2:
            vix_curr = vix['Close'].iloc[-1]
            vix_prev = vix['Close'].iloc[-2]
            vix_change = vix_curr - vix_prev
            vix_level = "Low <18" if vix_curr < 18 else "Elevated 18-28" if vix_curr < 28 else "High >28"
            print(f"VIX   {vix_curr:.2f} ({vix_change:+.2f}) — {vix_level}")
    except:
        pass
    
    # Crypto
    try:
        btc = yf.Ticker("BTC-USD").history(period="2d")
        eth = yf.Ticker("ETH-USD").history(period="2d")
        if len(btc) >= 2 and len(eth) >= 2:
            btc_curr = btc['Close'].iloc[-1]
            btc_prev = btc['Close'].iloc[-2]
            eth_curr = eth['Close'].iloc[-1]
            eth_prev = eth['Close'].iloc[-2]
            btc_pct = ((btc_curr/btc_prev)-1)*100
            eth_pct = ((eth_curr/eth_prev)-1)*100
            print(f"\nCrypto: BTC ${btc_curr:,.0f} ({btc_pct:+.2f}%) | ETH ${eth_curr:,.0f} ({eth_pct:+.2f}%)")
    except:
        pass
    
    # 3. Major Indices
    print("\n**📈 MAJOR INDICES vs KEY MAs**")
    indices = {}
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="6mo")
            close = data['Close'].iloc[-1]
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            ma50 = data['Close'].rolling(50).mean().iloc[-1]
            ma200 = data['Close'].rolling(200).mean().iloc[-1]
            
            s20 = "✓" if close > ma20 else "✗"
            s50 = "✓" if close > ma50 else "✗"
            s200 = "✓" if close > ma200 else "✗" if str(ma200) != "nan" else "—"
            
            print(f"{ticker:4} ${close:,.2f} | 20MA {s20} | 50MA {s50} | 200MA {s200}")
            indices[ticker] = (close, ma50)
        except:
            pass
    
    # 4. Regime Assessment
    print("\n**🔍 REGIME ASSESSMENT**")
    spy_close, spy_ma50 = indices.get("SPY", (0, 0))
    qqq_close, qqq_ma50 = indices.get("QQQ", (0, 0))
    iwm_close, iwm_ma50 = indices.get("IWM", (0, 0))
    
    # Get VIX for regime
    try:
        vix_curr = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
    except:
        vix_curr = 25
    
    signals = [
        ("SPY > 50 SMA", spy_close > spy_ma50),
        ("QQQ > 50 SMA", qqq_close > qqq_ma50),
        ("IWM > 50 SMA", iwm_close > iwm_ma50),
        ("VIX < 18", vix_curr < 18)
    ]
    
    bullish = sum(1 for _, v in signals if v)
    for sig, status in signals:
        print(f"{'✓' if status else '✗'} {sig}")
    print(f"\nBullish Signals: {bullish}/4")
    
    if bullish >= 4:
        regime = "🟢 BULL"
        advice = "Full exposure (80-100%)"
    elif bullish >= 2:
        regime = "🟡 NEUTRAL"
        advice = "40-60% exposure, A+ setups only"
    else:
        regime = "🔴 BEAR"
        advice = "0-20% exposure, capital preservation"
    
    print(f"\n{regime} — {advice}")
    
    # 5. SECTOR PERFORMANCE (from scan)
    if scan and "sectors" in scan:
        print("\n**🏭 SECTOR PERFORMANCE (1 Week)**")
        
        leading = scan.get("leading_sectors", [])
        lagging = scan.get("lagging_sectors", [])
        
        print("Leading:")
        for ticker in leading:
            if ticker in scan["sectors"]:
                s = scan["sectors"][ticker]
                print(f"  {ticker} {s['name']:11} {s['1_week_return']:+.2f}%")
        
        print("Lagging:")
        for ticker in lagging:
            if ticker in scan["sectors"]:
                s = scan["sectors"][ticker]
                print(f"  {ticker} {s['name']:11} {s['1_week_return']:+.2f}%")
    
    # 6. FACTOR ETFS (from scan)
    if scan and "factors" in scan:
        print("\n**🎯 FACTOR ETFS (vs SPY)**")
        
        for ticker, data in scan["factors"].items():
            print(f"{ticker:5} {data['name']:9} {data['1_week_return']:+.2f}% [{data['status']} {data['vs_spy']:+.2f}%]")
    
    # 7. Portfolio & Watchlist
    print("\n**💼 PORTFOLIO**")
    print("Positions: 0 | Invested: 0% | Heat: 0% | Cash: $50,000")
    
    print("\n**📋 WATCHLIST**")
    print("A-Tier: 0 | B-Tier: 0 | C-Tier: 0")
    print("⚠️ Run Stage 2 + RS screen to populate")
    
    # 8. Action Items
    print("\n**🎯 TODAY'S ACTION ITEMS**")
    print("1. ☐ Run Stage 2 + RS screen on leading sectors")
    print("2. ☐ Identify 3-5 A-tier setups")
    print("3. ☐ Check earnings calendar")
    print("4. ☐ Monitor gap scan >3% on 2x volume")
    print(f"5. ☐ NO NEW ENTRIES until reclaim" if bullish < 2 else "5. ☐ Execute A+ setups only")
    
    # 9. Key Levels
    print("\n**⚡ KEY LEVELS**")
    print(f"SPY: Reclaim ${spy_ma50:.0f} | QQQ: Reclaim ${qqq_ma50:.0f} | VIX: Watch 28")
    
    print("\n" + "—" * 50)
    print("Verdict: " + ("Bear regime. Stay flat." if bullish < 2 else "Cautious. Selective."))
    print("\n— Ace 🎯")

if __name__ == "__main__":
    generate_report()
