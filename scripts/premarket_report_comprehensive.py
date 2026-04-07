#!/usr/bin/env python3
"""
Comprehensive Pre-Market Report Generator
Reads from scans/YYYY-MM-DD_sector_scan.csv (comprehensive format)
"""

import yfinance as yf
import csv
from datetime import datetime, timedelta
from pathlib import Path
import re
import pandas as pd

def load_watchlist():
    """Load watchlist from CSV with current prices and calculate entry score"""
    watchlist_path = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')
    
    if not watchlist_path.exists():
        return None
    
    results = []
    with open(watchlist_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row['Ticker']
            try:
                pivot = float(row['Pivot_Price']) if row['Pivot_Price'] else None
                if not pivot:
                    continue
                
                # Get current price and calculate metrics
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period='1y')
                    if len(hist) < 200:
                        continue
                    
                    current = hist['Close'].iloc[-1]
                    
                    # Calculate returns
                    ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0
                    
                    # Calculate MAs for Stage 2
                    ma20 = hist['Close'].rolling(20).mean().iloc[-1]
                    ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                    ma150 = hist['Close'].rolling(150).mean().iloc[-1] if len(hist) >= 150 else 0
                    ma200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else 0
                    
                    # Stage 2 score
                    stage2 = 0
                    if current > ma150: stage2 += 1
                    if current > ma200: stage2 += 1
                    if ma20 > ma50 > ma150 > ma200: stage2 += 1
                    high_52w = hist['Close'].max()
                    from_high = ((high_52w - current) / high_52w) * 100
                    if from_high < 15: stage2 += 1
                    
                    # ATR for stop
                    high_low = hist['High'] - hist['Low']
                    high_close = abs(hist['High'] - hist['Close'].shift())
                    low_close = abs(hist['Low'] - hist['Close'].shift())
                    ranges = pd.concat([high_low, high_close, low_close], axis=1)
                    true_range = ranges.max(axis=1)
                    atr = true_range.rolling(14).mean().iloc[-1]
                    
                    # Stop and risk
                    recent_low = hist['Low'].tail(10).min()
                    stop = max(recent_low, current - 2 * atr)
                    risk = (pivot - stop) / pivot * 100 if pivot > stop else 0
                    
                    # Distance to pivot
                    dist_to_pivot = ((pivot - current) / current) * 100
                    
                    # ENTRY SCORE CALCULATION
                    entry_score = 0
                    
                    # Stage 2 points (max 30)
                    if stage2 >= 4: entry_score += 30
                    elif stage2 >= 3: entry_score += 20
                    elif stage2 >= 2: entry_score += 10
                    
                    # Risk points (max 30)
                    if risk < 10: entry_score += 30
                    elif risk < 15: entry_score += 20
                    elif risk < 20: entry_score += 10
                    
                    # Proximity points (max 25)
                    if abs(dist_to_pivot) < 3: entry_score += 25
                    elif abs(dist_to_pivot) < 5: entry_score += 15
                    elif abs(dist_to_pivot) < 10: entry_score += 5
                    
                    # Momentum points (max 15)
                    if ret_6m > 50: entry_score += 15
                    elif ret_6m > 25: entry_score += 10
                    
                    # Tier based on score
                    if entry_score >= 60: tier = '1'
                    elif entry_score >= 40: tier = '2'
                    else: tier = '3'
                    
                    results.append({
                        'ticker': ticker,
                        'tier': tier,
                        'entry_score': entry_score,
                        'pivot': pivot,
                        'current': round(current, 2),
                        'dist_to_pivot': round(dist_to_pivot, 1),
                        'stop': round(stop, 2),
                        'risk_pct': round(risk, 1),
                        'stage2': stage2,
                        'ret_6m': round(ret_6m, 1),
                        'sector': row.get('Sector', 'Unknown')
                    })
                except Exception as e:
                    continue
            except (ValueError, KeyError):
                continue
    
    # Sort by entry score (descending)
    results.sort(key=lambda x: x['entry_score'], reverse=True)
    
    return results

def load_comprehensive_scan():
    """Load comprehensive sector scan from CSV"""
    today = datetime.now().strftime('%Y-%m-%d')
    scan_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{today}_sector_scan.csv")
    
    if not scan_file.exists():
        print(f"⚠️ No scan found for {today}")
        print(f"   Run: python3 sector_scan_comprehensive.py")
        return None
    
    results = []
    with open(scan_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                'ticker': row['Ticker'],
                'name': row['Name'],
                'ret_1w': float(row['1W']),
                'ret_1m': float(row['1M']),
                'ret_3m': float(row['3M']),
                'ret_6m': float(row['6M']),
                'above_20': row['Above_20'] == 'True',
                'above_50': row['Above_50'] == 'True',
                'above_200': row['Above_200'] == 'True',
                'from_high': float(row['From_High']),
                'stage2_score': int(row['Stage2_Score']),
                'rank_score': float(row['Rank_Score']),
                'overall_rank': int(row['Overall_Rank'])
            })
    
    return results

def fetch_economic_calendar():
    """Fetch US economic events for today and tomorrow"""
    try:
        from urllib.request import urlopen
        
        today = datetime.now()
        
        # Fetch from tradingcharts.com
        url = f"https://forex.tradingcharts.com/economic_calendar/{today.strftime('%Y-%m-%d')}.html?code=USD"
        
        try:
            response = urlopen(url, timeout=5)
            html = response.read().decode('utf-8')
        except:
            return {'today': [], 'tomorrow': []}
        
        events = []
        
        # Parse events (simplified)
        lines = html.split('\n')
        for i, line in enumerate(lines):
            if 'USD' in line and ('08:30 AM' in line or '02:00 PM' in line or '10:00 AM' in line):
                # Extract event name
                for j in range(i, min(i+3, len(lines))):
                    if any(x in lines[j] for x in ['FOMC', 'CPI', 'PCE', 'Core', 'Jobless', 'CREDIT']):
                        time_match = re.search(r'(\d{2}:\d{2} [AP]M)', line)
                        time_str = time_match.group(1) if time_match else 'TBD'
                        
                        # Determine impact
                        impact = '🟡'
                        if any(x in lines[j] for x in ['FOMC', 'CPI', 'PCE', 'Core']):
                            impact = '🔴'
                        elif 'Jobless' in lines[j]:
                            impact = '🟡'
                        
                        events.append({
                            'time': time_str,
                            'event': lines[j].strip(),
                            'impact': impact
                        })
                        break
        
        return {'today': events[:5], 'tomorrow': []}  # Limit to 5 events
        
    except Exception as e:
        return {'today': [], 'tomorrow': []}

def generate_comprehensive_report():
    """Generate comprehensive pre-market report"""
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    print("🌅 COMPREHENSIVE PRE-MARKET REPORT — " + report_date)
    print()
    
    # Load data
    scan = load_comprehensive_scan()
    watchlist = load_watchlist()
    
    # 1. OVERNIGHT FUTURES
    print("**📊 OVERNIGHT FUTURES**")
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
    
    # 4. ECONOMIC CALENDAR
    print("\n**📅 ECONOMIC CALENDAR (US)**")
    econ = fetch_economic_calendar()
    
    if econ['today']:
        risk_level = '🟢'
        has_high_impact = any(e['impact'] == '🔴' for e in econ['today'])
        if has_high_impact:
            risk_level = '🔴'
            advice = "Reduce size 50% or wait for post-event clarity"
        elif econ['today']:
            risk_level = '🟡'
            advice = "Normal size, watch for volatility at event time"
        else:
            advice = "Clear day, trade normally"
        
        print(f"{risk_level} Today's Events:")
        for event in econ['today']:
            print(f"   {event['time']} {event['impact']} {event['event']}")
        print(f"   → {advice}")
    else:
        print("🟢 No major US economic events today")
        print("   → Clear day, trade normally")
    
    # 5. MAJOR INDICES
    print("\n**📈 MAJOR INDICES vs KEY MAs**")
    indices = {}
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="1y")
            close = data['Close'].iloc[-1]
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            ma50 = data['Close'].rolling(50).mean().iloc[-1]
            ma200 = data['Close'].rolling(200).mean().iloc[-1]
            
            s20 = "✓" if close > ma20 else "✗"
            s50 = "✓" if close > ma50 else "✗"
            s200 = "✓" if close > ma200 else "✗"
            
            print(f"{ticker:4} ${close:,.2f} | 20MA {s20} | 50MA {s50} | 200MA {s200}")
            indices[ticker] = (close, ma50, ma200)
        except:
            pass
    
    # 3. REGIME
    print("\n**🔍 REGIME ASSESSMENT**")
    spy_close, spy_ma50, spy_ma200 = indices.get("SPY", (0, 0, 0))
    qqq_close, qqq_ma50, qqq_ma200 = indices.get("QQQ", (0, 0, 0))
    iwm_close, iwm_ma50, iwm_ma200 = indices.get("IWM", (0, 0, 0))
    
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
    
    regime = "🟢 BULL" if bullish >= 4 else "🟡 NEUTRAL" if bullish >= 2 else "🔴 BEAR"
    print(f"\n{regime}")
    
    # 4. SECTOR LEADERS (from comprehensive scan)
    if scan:
        print("\n**🏆 TOP 20 LEADING ETFs (by Overall Rank)**")
        print(f"{'Rank':<5} {'Ticker':<6} {'Name':<22} {'1W':>8} {'1M':>8} {'3M':>8} {'6M':>8} {'S2':>3}")
        print("-" * 90)
        
        for row in scan[:20]:
            print(f"{row['overall_rank']:<5} {row['ticker']:<6} {row['name']:<22} "
                  f"{row['ret_1w']:>+7.1f}% {row['ret_1m']:>+7.1f}% "
                  f"{row['ret_3m']:>+7.1f}% {row['ret_6m']:>+7.1f}% "
                  f"{row['stage2_score']:>3}")
    
    # 6. WATCHLIST
    print("\n**📋 WATCHLIST ANALYSIS — Entry Score Rankings**")
    if watchlist:
        # Count by tier
        tier_counts = {'1': 0, '2': 0, '3': 0}
        for stock in watchlist:
            tier_counts[stock['tier']] = tier_counts.get(stock['tier'], 0) + 1
        
        print(f"Total: {len(watchlist)} | 🟢 Tier 1: {tier_counts['1']} | 🟡 Tier 2: {tier_counts['2']} | 🔴 Tier 3: {tier_counts['3']}")
        
        # Show ALL stocks sorted by entry score
        print(f"\n{'Ticker':<8} {'Tier':<8} {'Score':<7} {'Current':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'S2':<4} {'6M':<10} {'Sector'}")
        print("-" * 95)
        
        for stock in watchlist:
            tier_icon = '🟢' if stock['tier'] == '1' else '🟡' if stock['tier'] == '2' else '🔴'
            dist_sign = '+' if stock['dist_to_pivot'] > 0 else ''
            print(f"{stock['ticker']:<8} {tier_icon} T{stock['tier']:<4} {stock['entry_score']:<6} ${stock['current']:<9.2f} ${stock['pivot']:<9.2f} "
                  f"{dist_sign}{stock['dist_to_pivot']:<6.1f}% {stock['risk_pct']:<7.1f}% "
                  f"{stock['stage2']}/4  {stock['ret_6m']:>9.1f}% {stock['sector']}")
        
        # Highlight ready setups
        ready = [s for s in watchlist if s['tier'] == '1' and abs(s['dist_to_pivot']) < 3]
        if ready:
            print(f"\n✅ Tier 1 Ready (Score ≥60, within 3%): {', '.join(s['ticker'] for s in ready)}")
    else:
        print("⚠️ Watchlist is empty")
        print("   Run: python3 watchlist_manager.py add TICKER")
    
    # 7. ACTION ITEMS
    print("\n**🎯 TODAY'S ACTION ITEMS**")
    print("1. ☐ Review top 20 for actionable setups")
    print("2. ☐ Check individual stock charts in leading sectors")
    print("3. ☐ Check earnings calendar")
    print("4. ☐ Monitor pre-market gaps")
    print(f"5. ☐ {'NO NEW ENTRIES until reclaim' if bullish < 2 else 'EXECUTE A+ SETUPS ONLY'}")
    
    # 8. KEY LEVELS
    print(f"\n**⚡ KEY LEVELS**")
    print(f"SPY: Reclaim ${spy_ma50:.0f} | QQQ: Reclaim ${qqq_ma50:.0f} | VIX: Watch 28")
    
    print("\n" + "—" * 60)
    print(f"Verdict: {regime.split()[1]} regime. {'Stay flat.' if bullish < 2 else 'Be selective.'}")
    print("\n— Ace 🎯")

if __name__ == "__main__":
    generate_comprehensive_report()
