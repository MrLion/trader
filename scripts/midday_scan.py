#!/usr/bin/env python3
"""Mid-day Stage 2 scan with entry setup calculations.

Loads tickers from watchlist or custom file - no hardcoded universe.
"""

import argparse
import csv
import html
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from traderlib import calculate_stage2_score, get_entry_score


def load_watchlist_tickers():
    """Load tickers from watchlist.csv"""
    watchlist_path = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')
    tickers = []
    if watchlist_path.exists():
        try:
            with open(watchlist_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tickers.append(row['Ticker'])
        except Exception:
            pass
    return tickers


def load_tickers_from_file(filepath):
    """Load tickers from a CSV or text file (one ticker per line)"""
    tickers = []
    path = Path(filepath)
    if not path.exists():
        return tickers

    try:
        # Try CSV first
        with open(path, 'r') as f:
            if filepath.endswith('.csv'):
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0] and not row[0].startswith('#'):
                        tickers.append(row[0].strip().upper())
            else:
                # Plain text file
                for line in f:
                    ticker = line.strip().upper()
                    if ticker and not ticker.startswith('#'):
                        tickers.append(ticker)
    except Exception:
        pass

    return tickers


def calculate_entry_score_midday(stage2_score, risk_pct, dist_to_entry, momentum_6m):
    """
    Calculate entry score (0-100) using shared function.
    For midday scan, we pass RS_6M as 0 since we don't calculate it here.
    """
    return get_entry_score(stage2_score, risk_pct, dist_to_entry, momentum_6m, rs_6m=0)


def get_tier(entry_score):
    """Return tier based on entry score."""
    if entry_score >= 60: return '1'
    elif entry_score >= 40: return '2'
    else: return '3'


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

    stop = max(recent_low, current - 2 * atr)
    risk = (current - stop) / current * 100

    return {
        'current': round(current, 2),
        'atr': round(atr, 2),
        'entry_breakout': round(recent_high + 0.01, 2),
        'stop': round(stop, 2),
        'risk_pct': round(risk, 2)
    }


def generate_html_report(results, output_path, scan_time):
    """Generate HTML report with Entry Score Tiers"""

    def esc(text):
        return html.escape(str(text)) if text else ""

    def get_tier_class(tier):
        return f"tier-{tier}"

    tier_1 = [r for r in results if r['Tier'] == '1']
    tier_2 = [r for r in results if r['Tier'] == '2']
    tier_3 = [r for r in results if r['Tier'] == '3']

    # Build rows for tier 1
    tier_1_rows = ""
    for r in tier_1[:20]:
        status_icon = "🔥" if r['Dist_to_Entry_%'] < 3 else "📈"
        tier_1_rows += f"""
        <tr class="{get_tier_class(r['Tier'])}">
            <td class="ticker">{esc(r['Ticker'])}</td>
            <td>{esc(r['Name'][:25])}</td>
            <td class="score">{r['Entry_Score']}</td>
            <td class="price">${r['Price']:.2f}</td>
            <td class="{'positive' if r['6M_%'] > 0 else 'negative'}">{r['6M_%']:+.1f}%</td>
            <td>{r['Risk_%']:.1f}%</td>
            <td>{r['Dist_to_Entry_%']:.1f}%</td>
            <td>{status_icon}</td>
            <td>${r['Entry_Breakout']:.2f}</td>
            <td>${r['Stop']:.2f}</td>
        </tr>
        """

    # Build rows for tier 2
    tier_2_rows = ""
    for r in tier_2[:15]:
        tier_2_rows += f"""
        <tr class="{get_tier_class(r['Tier'])}">
            <td class="ticker">{esc(r['Ticker'])}</td>
            <td>{esc(r['Name'][:25])}</td>
            <td class="score">{r['Entry_Score']}</td>
            <td class="price">${r['Price']:.2f}</td>
            <td class="{'positive' if r['6M_%'] > 0 else 'negative'}">{r['6M_%']:+.1f}%</td>
            <td>{r['Risk_%']:.1f}%</td>
            <td>{r['Dist_to_Entry_%']:.1f}%</td>
        </tr>
        """

    # Build rows for tier 3
    tier_3_rows = ""
    for r in tier_3[:10]:
        tier_3_rows += f"""
        <tr class="{get_tier_class(r['Tier'])}">
            <td class="ticker">{esc(r['Ticker'])}</td>
            <td>{esc(r['Name'][:25])}</td>
            <td class="score">{r['Entry_Score']}</td>
            <td class="price">${r['Price']:.2f}</td>
            <td class="{'positive' if r['6M_%'] > 0 else 'negative'}">{r['6M_%']:+.1f}%</td>
            <td>{r['Risk_%']:.1f}%</td>
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

        .tier-1 {{ border-left: 3px solid var(--accent-green); }}
        .tier-2 {{ border-left: 3px solid var(--accent-yellow); }}
        .tier-3 {{ border-left: 3px solid var(--accent-red); }}
        .score {{ font-weight: bold; }}

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
            Found {len(results)} Stage 2+ candidates | 🟢 Tier 1: {len(tier_1)} | 🟡 Tier 2: {len(tier_2)} | 🔴 Tier 3: {len(tier_3)}
        </div>

        <div class="section">
            <h2>🟢 Tier 1 — Entry Score ≥60 ({len(tier_1)} candidates) — Best Entry Setups</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Name</th>
                            <th>Score</th>
                            <th>Price</th>
                            <th>6M</th>
                            <th>Risk</th>
                            <th>Dist%</th>
                            <th>Status</th>
                            <th>Entry</th>
                            <th>Stop</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tier_1_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>🟡 Tier 2 — Entry Score 40-59 ({len(tier_2)} candidates) — Wait for Better Entry</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Name</th>
                            <th>Score</th>
                            <th>Price</th>
                            <th>6M</th>
                            <th>Risk</th>
                            <th>Dist%</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tier_2_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>🔴 Tier 3 — Entry Score &lt;40 ({len(tier_3)} candidates) — Monitor Only</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Name</th>
                            <th>Score</th>
                            <th>Price</th>
                            <th>6M</th>
                            <th>Risk</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tier_3_rows}
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
  # Scan your watchlist
  python3 midday_scan.py --include-watchlist

  # Scan custom tickers file (one ticker per line)
  python3 midday_scan.py --tickers-file my_tickers.txt

  # Generate HTML report from watchlist
  python3 midday_scan.py --include-watchlist --html

  # Custom dollar volume filter
  python3 midday_scan.py --include-watchlist --min-dollar-vol 50000000

Note: You must specify a ticker source (--include-watchlist or --tickers-file)
        '''
    )

    parser.add_argument('--min-dollar-vol', type=int, default=20_000_000,
                       help='Minimum dollar volume filter (default: 20M)')
    parser.add_argument('--entry-score-min', type=int, default=0,
                       help='Minimum entry score to include (default: 0)')
    parser.add_argument('--include-watchlist', action='store_true',
                       help='Include watchlist.csv tickers in scan')
    parser.add_argument('--tickers-file', type=str, default=None,
                       help='Path to file with tickers (one per line or CSV)')
    parser.add_argument('--output', type=str, default=None,
                       help='Custom output path for CSV (default: scans/leading_stocks_YYYY-MM-DD.csv)')
    parser.add_argument('--html', action='store_true',
                       help='Generate HTML report')
    parser.add_argument('--html-output', type=str, default=None,
                       help='Custom path for HTML report')

    args = parser.parse_args()

    scan_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"🎯 MID-DAY SCAN — {scan_time}\n")

    # Build ticker universe from specified sources
    tickers = []

    if args.tickers_file:
        file_tickers = load_tickers_from_file(args.tickers_file)
        tickers.extend(file_tickers)
        print(f"📄 Loaded {len(file_tickers)} tickers from {args.tickers_file}\n")

    if args.include_watchlist:
        watchlist_tickers = load_watchlist_tickers()
        tickers.extend(watchlist_tickers)
        print(f"📋 Loaded {len(watchlist_tickers)} tickers from watchlist\n")

    tickers = list(set(tickers))  # Remove duplicates

    if not tickers:
        print("❌ No tickers to scan. Use --include-watchlist or --tickers-file")
        print("   Examples:")
        print("   python3 midday_scan.py --include-watchlist")
        print("   python3 midday_scan.py --tickers-file my_tickers.txt")
        return

    print(f"🔍 Scanning {len(tickers)} tickers...\n")

    results = []

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="1y")
            info = t.info

            if df.empty or len(df) < 200:
                continue

            stage2_score = calculate_stage2_score(df)
            if stage2_score < 2:  # Minimum Stage 2 score of 2
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

            # Calculate distance to entry breakout
            dist_to_entry = abs((setup['entry_breakout'] - current) / current) * 100

            # Calculate entry score (0-100) using shared function
            entry_score = calculate_entry_score_midday(
                stage2_score,
                setup['risk_pct'],
                dist_to_entry,
                six_month_return
            )

            # Filter by minimum entry score
            if entry_score < args.entry_score_min:
                continue

            tier = get_tier(entry_score)

            results.append({
                'Ticker': ticker,
                'Name': info.get('shortName', ticker),
                'Sector': info.get('sector', 'Unknown'),
                'Industry': info.get('industry', 'Unknown'),
                'Price': current,
                'Stage2': stage2_score,
                'Entry_Score': entry_score,
                'Tier': tier,
                '6M_%': round(six_month_return, 1),
                '3M_%': round(three_month_return, 1),
                '1M_%': round(one_month_return, 1),
                'From_52W_High_%': round(from_high, 1),
                'Dist_to_Entry_%': round(dist_to_entry, 1),
                'ATR': setup['atr'],
                'Entry_Breakout': setup['entry_breakout'],
                'Stop': setup['stop'],
                'Risk_%': setup['risk_pct'],
                '$Vol_M': round(dollar_vol / 1_000_000, 1)
            })

        except Exception:
            continue

    # Sort by Entry Score (descending)
    results = sorted(results, key=lambda x: -x['Entry_Score'])

    # Output summary
    tier_counts = {'1': 0, '2': 0, '3': 0}
    for r in results:
        tier_counts[r['Tier']] = tier_counts.get(r['Tier'], 0) + 1

    print(f"Found {len(results)} Stage 2+ candidates")
    print(f"🟢 Tier 1: {tier_counts['1']} | 🟡 Tier 2: {tier_counts['2']} | 🔴 Tier 3: {tier_counts['3']}\n")
    print("="*80)

    # Tier 1 (Entry Score >= 60)
    tier_1 = [r for r in results if r['Tier'] == '1']
    print(f"\n🟢 TIER 1 — Entry Score ≥60 ({len(tier_1)} candidates) — Best entry setups")
    print("-"*80)
    for r in tier_1[:20]:
        status = "🔥 READY" if r['Dist_to_Entry_%'] < 3 else "📈 SETTING UP"
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | Score: {r['Entry_Score']:>2} | "
              f"Risk: {r['Risk_%']:>5.1f}% | {status}")
        print(f"       S2: {r['Stage2']}/7 | Entry: ${r['Entry_Breakout']:.2f} ({r['Dist_to_Entry_%']:.1f}% away) | Stop: ${r['Stop']:.2f}")
        print()

    # Tier 2 (Entry Score 40-59)
    tier_2 = [r for r in results if r['Tier'] == '2']
    print(f"\n🟡 TIER 2 — Entry Score 40-59 ({len(tier_2)} candidates) — Good setups, wait for better entry")
    print("-"*80)
    for r in tier_2[:15]:
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | Score: {r['Entry_Score']:>2} | "
              f"S2: {r['Stage2']}/7 | Risk: {r['Risk_%']:.1f}% | Entry: ${r['Entry_Breakout']:.2f}")

    # Tier 3 (Entry Score < 40)
    tier_3 = [r for r in results if r['Tier'] == '3']
    print(f"\n🔴 TIER 3 — Entry Score <40 ({len(tier_3)} candidates) — Monitor only")
    print("-"*80)
    for r in tier_3[:10]:
        print(f"{r['Ticker']:6} | {r['Name'][:25]:25} | ${r['Price']:>7.2f} | Score: {r['Entry_Score']:>2} | "
              f"S2: {r['Stage2']}/7 | Risk: {r['Risk_%']:.1f}%")

    # Save to CSV
    df_out = pd.DataFrame(results)
    date_str = datetime.now().strftime('%Y-%m-%d')
    datetime_str = datetime.now().strftime('%Y-%m-%d_%H%M%S')

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
            html_path = Path(f'/Users/mintmrlion/.openclaw/workspaces/trader/reports/midday_scan_{datetime_str}.html')

        html_path.parent.mkdir(parents=True, exist_ok=True)
        generate_html_report(results, html_path, scan_time)
        print(f"📄 Saved HTML to: {html_path}")


if __name__ == '__main__':
    main()
