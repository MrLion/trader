#!/usr/bin/env python3
"""Mid-day Stage 2 scan with entry setup calculations.

Enhanced version with:
- CLI arguments for customization
- Dynamic sector loading from today's scan
- Watchlist integration
- Optional HTML output
"""

import argparse
import yfinance as yf
import pandas as pd
import html
from datetime import datetime
from pathlib import Path

# Base universe - liquid names by sector
BASE_UNIVERSE = {
    'Energy': ['XOM', 'CVX', 'COP', 'TTE', 'BP', 'SLB', 'HAL', 'OXY', 'DVN', 'FANG',
              'MPC', 'VLO', 'PSX', 'PBF', 'XLE', 'USO', 'XOP'],
    'Materials': ['FCX', 'ALB', 'VALE', 'SCCO', 'DOW', 'RIO', 'BHP', 'NEM', 'GOLD',
                   'MT', 'STLD', 'NUE', 'PAAS', 'WPM', 'RGLD', 'KGC', 'AEM'],
    'Biotech': ['MRK', 'BMY', 'GILD', 'REGN', 'AMGN', 'JNJ', 'GSK', 'AZN', 'NVS',
                'ARWR', 'APLS', 'RCUS', 'ACLX', 'GH', 'MDGL', 'NTRA'],
    'Industrials': ['CAT', 'FDX', 'MTZ', 'PWR', 'CW', 'LMT', 'RTX', 'NOC', 'HII', 'CSX',
                    'EME', 'FIX', 'UPS', 'UNP', 'CP', 'CNI', 'EXPD'],
    'Utilities': ['NEE', 'DUK', 'SO', 'AEP', 'SRE', 'ETR', 'ED', 'EXC', 'WEC', 'XEL',
                  'BWXT', 'SEDG']
}


def load_watchlist_tickers():
    """Load tickers from watchlist.csv"""
    watchlist_path = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')
    tickers = []
    if watchlist_path.exists():
        try:
            with open(watchlist_path, 'r') as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    tickers.append(row['Ticker'])
        except Exception:
            pass
    return tickers


def load_today_leading_sectors():
    """Load today's leading sectors from sector scan"""
    today = datetime.now().strftime('%Y-%m-%d')
    scan_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{today}_sector_scan.csv")

    leading_sectors = []
    if scan_file.exists():
        try:
            with open(scan_file, 'r') as f:
                import csv
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0] == 'leading_sectors' and len(row) > 1:
                        leading_sectors = [s.strip() for s in row[1].split('|') if s.strip()]
                        break
        except Exception:
            pass

    return leading_sectors


def get_sector_tickers(sectors, base_universe):
    """Get tickers for given sectors from base universe"""
    tickers = []
    sector_map = {
        'XLE': 'Energy', 'XLB': 'Materials', 'XBI': 'Biotech',
        'XLI': 'Industrials', 'XLU': 'Utilities', 'XLY': 'Consumer Disc',
        'XLK': 'Technology', 'XLF': 'Financials', 'XLV': 'Health Care',
        'XLP': 'Staples', 'XLC': 'Comm Services'
    }

    for sector in sectors:
        # Map ETF ticker to sector name
        sector_name = sector_map.get(sector, sector)
        if sector_name in base_universe:
            tickers.extend(base_universe[sector_name])

    return list(set(tickers))  # Remove duplicates


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
    if current >= high_52w * 0.85: score += 1

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


def calculate_setup(df):
    """Calculate entry setup with 2 ATR stop."""
    if df.empty:
        return None

    current = df['Close'].iloc[-1]
    atr = get_atr(df)

    if atr is None:
        return None

    recent_low = df['Low'].tail(10).min()
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


def generate_html_report(results, output_path, scan_time):
    """Generate HTML report similar to premarket comprehensive"""

    def esc(text):
        return html.escape(str(text)) if text else ""

    def get_tier_class(score):
        return "tier-a" if score == 4 else "tier-b"

    tier_a = [r for r in results if r['Stage2'] == 4]
    tier_b = [r for r in results if r['Stage2'] == 3]

    # Build rows for tier A
    tier_a_rows = ""
    for r in tier_a[:20]:
        status_icon = "🔥" if r['From_52W_High_%'] < 2 else "📈"
        tier_a_rows += f"""
        <tr class="{get_tier_class(r['Stage2'])}">
            <td class="ticker">{esc(r['Ticker'])}</td>
            <td>{esc(r['Name'][:25])}</td>
            <td class="price">${r['Price']:.2f}</td>
            <td class="{'positive' if r['6M_%'] > 0 else 'negative'}">{r['6M_%']:+.1f}%</td>
            <td>{r['From_52W_High_%']:.1f}%</td>
            <td>{status_icon}</td>
            <td>${r['Entry_Breakout']:.2f}</td>
            <td>${r['Stop']:.2f}</td>
            <td>{r['Risk_%']:.1f}%</td>
        </tr>
        """

    # Build rows for tier B
    tier_b_rows = ""
    for r in tier_b[:15]:
        tier_b_rows += f"""
        <tr class="{get_tier_class(r['Stage2'])}">
            <td class="ticker">{esc(r['Ticker'])}</td>
            <td>{esc(r['Name'][:25])}</td>
            <td class="price">${r['Price']:.2f}</td>
            <td class="{'positive' if r['6M_%'] > 0 else 'negative'}">{r['6M_%']:+.1f}%</td>
            <td>{r['From_52W_High_%']:.1f}%</td>
        </tr>
        """

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mid-Day Scan — {esc(scan_time)}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-green: #4ade80;
            --accent-red: #f87171;
            --accent-yellow: #facc15;
            --border-color: #475569;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ text-align: center; padding: 30px 0; border-bottom: 2px solid var(--border-color); margin-bottom: 30px; }}
        h1 {{ font-size: 2rem; margin-bottom: 10px; }}
        .date {{ color: var(--text-secondary); }}
        .summary {{ text-align: center; margin: 20px 0; color: var(--text-secondary); }}

        .section {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid var(--border-color);
        }}
        h2 {{ font-size: 1.3rem; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
        }}
        tr:hover {{ background: rgba(255,255,255,0.03); }}
        .ticker {{ font-weight: bold; font-family: monospace; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}

        .tier-a {{ border-left: 3px solid var(--accent-green); }}
        .tier-b {{ border-left: 3px solid var(--accent-yellow); }}

        @media (max-width: 768px) {{
            table {{ font-size: 0.8rem; }}
            th, td {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Mid-Day Scan</h1>
            <div class="date">{esc(scan_time)}</div>
        </header>

        <div class="summary">
            Found {len(results)} Stage 2+ candidates | Tier A: {len(tier_a)} | Tier B: {len(tier_b)}
        </div>

        <div class="section">
            <h2>🟢 Tier A — Stage 2 Score 4 ({len(tier_a)} candidates)</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Name</th>
                            <th>Price</th>
                            <th>6M</th>
                            <th>From High</th>
                            <th>Status</th>
                            <th>Entry</th>
                            <th>Stop</th>
                            <th>Risk</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tier_a_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>🟡 Tier B — Stage 2 Score 3 ({len(tier_b)} candidates)</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Name</th>
                            <th>Price</th>
                            <th>6M</th>
                            <th>From High</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tier_b_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Mid-day Stage 2 scan with entry setup calculations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic scan
  python3 midday_scan.py

  # Include watchlist tickers
  python3 midday_scan.py --include-watchlist

  # Focus on today's leading sectors only
  python3 midday_scan.py --leading-sectors-only

  # Generate HTML report
  python3 midday_scan.py --html

  # Custom dollar volume filter
  python3 midday_scan.py --min-dollar-vol 50000000
        '''
    )

    parser.add_argument('--min-dollar-vol', type=int, default=20_000_000,
                       help='Minimum dollar volume filter (default: 20M)')
    parser.add_argument('--stage2-min', type=int, default=3,
                       help='Minimum Stage 2 score (default: 3)')
    parser.add_argument('--include-watchlist', action='store_true',
                       help='Include watchlist.csv tickers in scan')
    parser.add_argument('--leading-sectors-only', action='store_true',
                       help='Scan only today\'s leading sectors')
    parser.add_argument('--output', type=str, default=None,
                       help='Custom output path for CSV (default: scans/leading_stocks_YYYY-MM-DD.csv)')
    parser.add_argument('--html', action='store_true',
                       help='Generate HTML report')
    parser.add_argument('--html-output', type=str, default=None,
                       help='Custom path for HTML report')

    args = parser.parse_args()

    scan_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"🎯 MID-DAY SCAN — {scan_time}\n")

    # Build ticker universe
    tickers = []

    if args.leading_sectors_only:
        # Load from today's sector scan
        leading_sectors = load_today_leading_sectors()
        if leading_sectors:
            tickers = get_sector_tickers(leading_sectors, BASE_UNIVERSE)
            print(f"📊 Scanning leading sectors: {', '.join(leading_sectors)}\n")
        else:
            print("⚠️ No leading sectors found in today's scan, using base universe\n")
            for sector_tickers in BASE_UNIVERSE.values():
                tickers.extend(sector_tickers)
    else:
        # Use full base universe
        for sector_tickers in BASE_UNIVERSE.values():
            tickers.extend(sector_tickers)

    # Add watchlist if requested
    if args.include_watchlist:
        watchlist_tickers = load_watchlist_tickers()
        tickers.extend(watchlist_tickers)
        print(f"📋 Added {len(watchlist_tickers)} tickers from watchlist\n")

    tickers = list(set(tickers))  # Remove duplicates
    print(f"🔍 Scanning {len(tickers)} tickers...\n")

    results = []

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="1y")
            info = t.info

            if df.empty or len(df) < 200:
                continue

            score = get_stage2_score(df)
            if score < args.stage2_min:
                continue

            setup = calculate_setup(df)
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

            if dollar_vol < args.min_dollar_vol:
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

    # Tier A
    tier_a = [r for r in results if r['Stage2'] == 4]
    print(f"\n🟢 TIER A — Stage 2 Score 4 ({len(tier_a)} candidates)")
    print("-"*80)
    for r in tier_a[:20]:
        status = "🔥 NEW HIGH" if r['From_52W_High_%'] < 2 else "📈 TRENDING"
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | "
              f"6M: {r['6M_%']:>+6.1f}% | From High: {r['From_52W_High_%']:>5.1f}% | {status}")
        print(f"       Entry: ${r['Entry_Breakout']:.2f} | Stop: ${r['Stop']:.2f} | Risk: {r['Risk_%']:.1f}%")
        print()

    # Tier B
    tier_b = [r for r in results if r['Stage2'] == 3]
    print(f"\n🟡 TIER B — Stage 2 Score 3 ({len(tier_b)} candidates)")
    print("-"*80)
    for r in tier_b[:15]:
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | "
              f"6M: {r['6M_%']:>+6.1f}% | From High: {r['From_52W_High_%']:>5.1f}%")

    # Save to CSV
    df_out = pd.DataFrame(results)
    date_str = datetime.now().strftime('%Y-%m-%d')

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(f'/Users/mintmrlion/.openclaw/workspaces/trader/scans/leading_stocks_{date_str}.csv')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False)
    print(f"\n📁 Saved CSV to: {output_path}")

    # Generate HTML if requested
    if args.html or args.html_output:
        if args.html_output:
            html_path = Path(args.html_output)
        else:
            html_path = Path(f'/Users/mintmrlion/.openclaw/workspaces/trader/reports/midday_scan_{date_str}.html')

        html_path.parent.mkdir(parents=True, exist_ok=True)
        generate_html_report(results, html_path, scan_time)
        print(f"📄 Saved HTML to: {html_path}")


if __name__ == '__main__':
    main()
