#!/usr/bin/env python3
"""Mid-day Stage 2 scan with entry setup calculations."""

import yfinance as yf
import pandas as pd
from datetime import datetime

# Leading sectors from today's scan
FOCUS_SECTORS = {
    'Energy': ['XLE', 'USO', 'XOP', 'OIH', 'FCG'],
    'Materials': ['XLB', 'FCX', 'ALB', 'VALE', 'SCCO', 'DOW'],
    'Telecom': ['XTL'],
    'Biotech': ['XBI'],
    'Commodities': ['DBC']
}

# Key tickers from leading sectors (from prior scans + liquid names)
TICKERS = [
    # Energy
    'XOM', 'CVX', 'COP', 'TTE', 'BP', 'SLB', 'HAL', 'OXY', 'DVN', 'FANG',
    'MPC', 'VLO', 'PSX', 'PBF', 'XLE', 'USO', 'XOP',
    # Materials
    'FCX', 'ALB', 'VALE', 'SCCO', 'DOW', 'RIO', 'BHP', 'NEM', 'GOLD',
    'MT', 'STLD', 'NUE', 'PAAS', 'WPM', 'RGLD', 'KGC', 'AEM',
    # Health Care (Biotech leaders)
    'MRK', 'BMY', 'GILD', 'REGN', 'AMGN', 'JNJ', 'GSK', 'AZN', 'NVS',
    'ARWR', 'APLS', 'RCUS', 'ACLX', 'GH', 'MDGL', 'NTRA',
    # Industrials
    'CAT', 'FDX', 'MTZ', 'PWR', 'CW', 'LMT', 'RTX', 'NOC', 'HII', 'CSX',
    'EME', 'FIX', 'UPS', 'UNP', 'CP', 'CNI', 'EXPD',
    # Utilities (select strong names)
    'NEE', 'DUK', 'SO', 'AEP', 'SRE', 'ETR', 'ED', 'EXC', 'WEC', 'XEL',
    'BWXT', 'SEDG'
]

def get_stage2_score(df):
    """Calculate Stage 2 score (0-4)."""
    if df.empty or len(df) < 200:
        return 0
    
    current = df['Close'].iloc[-1]
    sma20 = df['Close'].rolling(20).mean().iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    sma100 = df['Close'].rolling(100).mean().iloc[-1]
    sma200 = df['Close'].rolling(200).mean().iloc[-1]
    high_52w = df['Close'].rolling(252).max().iloc[-1]
    
    score = 0
    if current > sma100: score += 1
    if current > sma200: score += 1
    if sma20 > sma50 > sma100 > sma200: score += 1
    if current >= high_52w * 0.85: score += 1  # Within 15% of 52w high
    
    return score

def get_atr(df, period=14):
    """Calculate ATR for stop placement."""
    if len(df) < period + 1:
        return None
    
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift())
    low_close = abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean().iloc[-1]
    return atr

def calculate_setup(df, info):
    """Calculate entry setup with 2 ATR stop."""
    if df.empty:
        return None
    
    current = df['Close'].iloc[-1]
    atr = get_atr(df)
    
    if atr is None:
        return None
    
    # Stop at 2 ATR below recent support (use 10-day low as proxy)
    recent_low = df['Low'].tail(10).min()
    
    # Entry logic: breakout above 5-day high or pullback to 20 SMA
    recent_high = df['High'].tail(5).max()
    sma20 = df['Close'].rolling(20).mean().iloc[-1]
    
    stop = max(recent_low, current - 2 * atr)
    risk = (current - stop) / current * 100
    
    return {
        'current': round(current, 2),
        'atr': round(atr, 2),
        'entry_breakout': round(recent_high + 0.01, 2),
        'stop': round(stop, 2),
        'risk_pct': round(risk, 2),
        'sma20': round(sma20, 2)
    }

def main():
    print(f"🎯 MID-DAY SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    results = []
    
    for ticker in TICKERS:
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="1y")
            info = t.info
            
            if df.empty or len(df) < 200:
                continue
            
            score = get_stage2_score(df)
            if score < 3:  # Focus on Stage 2 stocks only
                continue
            
            setup = calculate_setup(df, info)
            if not setup:
                continue
            
            current = setup['current']
            six_month_return = (current / df['Close'].iloc[-126] - 1) * 100 if len(df) >= 126 else 0
            three_month_return = (current / df['Close'].iloc[-63] - 1) * 100 if len(df) >= 63 else 0
            one_month_return = (current / df['Close'].iloc[-21] - 1) * 100 if len(df) >= 21 else 0
            
            high_52w = df['Close'].rolling(252).max().iloc[-1]
            from_high = (high_52w - current) / high_52w * 100
            
            avg_vol = df['Volume'].tail(50).mean()
            dollar_vol = avg_vol * current
            
            if dollar_vol < 20_000_000:  # Skip illiquid names
                continue
            
            results.append({
                'Ticker': ticker,
                'Name': info.get('shortName', ticker),
                'Sector': info.get('sector', 'Unknown'),
                'Industry': info.get('industry', 'Unknown'),
                'Price': current,
                'Stage2': score,
                '6M_%': round(six_month_return, 1),
                '3M_%': round(three_month_return, 1),
                '1M_%': round(one_month_return, 1),
                'From_52W_High_%': round(from_high, 1),
                'ATR': setup['atr'],
                'Entry_Breakout': setup['entry_breakout'],
                'Stop': setup['stop'],
                'Risk_%': setup['risk_pct'],
                '$Vol_M': round(dollar_vol / 1_000_000, 1)
            })
            
        except Exception as e:
            continue
    
    # Sort by Stage 2 score, then by 6M return
    results = sorted(results, key=lambda x: (-x['Stage2'], -x['6M_%']))
    
    # Output summary
    print(f"Found {len(results)} Stage 2+ candidates\n")
    print("="*80)
    
    # Tier A: Stage 2 Score 4
    tier_a = [r for r in results if r['Stage2'] == 4]
    print(f"\n🟢 TIER A — Stage 2 Score 4 ({len(tier_a)} candidates)")
    print("-"*80)
    for r in tier_a[:20]:
        status = "🔥 NEW HIGH" if r['From_52W_High_%'] < 2 else "📈 TRENDING"
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | "
              f"6M: {r['6M_%']:>+6.1f}% | From High: {r['From_52W_High_%']:>5.1f}% | {status}")
        print(f"       Entry: ${r['Entry_Breakout']:.2f} | Stop: ${r['Stop']:.2f} | Risk: {r['Risk_%']:.1f}%")
        print()
    
    # Tier B: Stage 2 Score 3
    tier_b = [r for r in results if r['Stage2'] == 3]
    print(f"\n🟡 TIER B — Stage 2 Score 3 ({len(tier_b)} candidates)")
    print("-"*80)
    for r in tier_b[:15]:
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | "
              f"6M: {r['6M_%']:>+6.1f}% | From High: {r['From_52W_High_%']:>5.1f}%")
    
    # Save to CSV
    df_out = pd.DataFrame(results)
    date_str = datetime.now().strftime('%Y-%m-%d')
    output_path = f'/Users/mintmrlion/.openclaw/workspaces/trader/scans/leading_stocks_{date_str}.csv'
    df_out.to_csv(output_path, index=False)
    print(f"\n📁 Saved to: {output_path}")

if __name__ == '__main__':
    main()
