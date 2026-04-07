#!/usr/bin/env python3
"""
Post-Market Report Generator - Comprehensive Edition
Run after market close (4:00-5:00 PM ET)

Features:
- Market close summary with intraday ranges
- Overnight futures tracking
- VIX analysis with level classification
- Crypto (BTC/ETH) performance
- Watchlist performance analysis
- Gap detection (>3% moves)
- HTML and console output
"""

import yfinance as yf
import pandas as pd
import csv
import argparse
import html
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/reports')
WATCHLIST_PATH = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv')

def load_watchlist():
    """Load watchlist from CSV."""
    if not WATCHLIST_PATH.exists():
        return None

    df = pd.read_csv(WATCHLIST_PATH)
    return df

def generate_html_report(report_data, output_path):
    """Generate standalone HTML report with embedded CSS."""

    def esc(text):
        return html.escape(str(text)) if text else ""

    def get_change_color(change):
        return "#4ade80" if change > 0 else "#f87171" if change < 0 else "#9ca3af"

    def get_regime_class(regime):
        return "bull" if "BULL" in regime else "bear" if "BEAR" in regime else "neutral"

    # Market close cards
    indices_html = ""
    for idx in report_data.get('indices', []):
        color = get_change_color(idx.get('change', 0))
        indices_html += f'''
        <div class="metric-card">
            <div class="metric-symbol">{esc(idx.get('ticker', ''))}</div>
            <div class="metric-value">${idx.get('close', 0):,.2f}</div>
            <div class="metric-change" style="color: {color}">
                {idx.get('change', 0):+.2f} ({idx.get('pct', 0):+.2f}%)
            </div>
            <div class="metric-range">H: ${idx.get('high', 0):.2f} L: ${idx.get('low', 0):.2f}</div>
        </div>
        '''

    # VIX card
    vix = report_data.get('vix', {})
    vix_level_class = "low" if vix.get('level', '').startswith('Low') else "elevated" if vix.get('level', '').startswith('Elevated') else "high"
    vix_html = f'''
    <div class="metric-card vix vix-{vix_level_class}">
        <div class="metric-symbol">VIX</div>
        <div class="metric-value">{vix.get('price', 0):.2f}</div>
        <div class="metric-change" style="color: {get_change_color(vix.get('change', 0))}">
            {vix.get('change', 0):+.2f}
        </div>
        <div class="vix-level">{esc(vix.get('level', ''))}</div>
    </div>
    '''

    # Futures
    futures_html = ""
    for f in report_data.get('futures', []):
        color = get_change_color(f.get('change', 0))
        futures_html += f'''
        <div class="metric-card">
            <div class="metric-symbol">{esc(f.get('symbol', ''))}</div>
            <div class="metric-value">${f.get('price', 0):,.2f}</div>
            <div class="metric-change" style="color: {color}">
                {f.get('change', 0):+.2f} ({f.get('pct', 0):+.2f}%)
            </div>
        </div>
        '''

    # Crypto
    crypto = report_data.get('crypto', {})
    crypto_html = ""
    if crypto.get('btc_price'):
        btc_color = get_change_color(crypto.get('btc_change', 0))
        eth_color = get_change_color(crypto.get('eth_change', 0))
        crypto_html = f'''
        <div class="crypto-row">
            <span class="crypto-label">BTC</span>
            <span class="crypto-price">${crypto.get('btc_price', 0):,.0f}</span>
            <span class="crypto-change" style="color: {btc_color}">{crypto.get('btc_pct', 0):+.2f}%</span>
            <span class="crypto-divider">|</span>
            <span class="crypto-label">ETH</span>
            <span class="crypto-price">${crypto.get('eth_price', 0):,.0f}</span>
            <span class="crypto-change" style="color: {eth_color}">{crypto.get('eth_pct', 0):+.2f}%</span>
        </div>
        '''

    # Watchlist performance
    watchlist_rows = ""
    for stock in report_data.get('watchlist_performance', []):
        change_class = "positive" if stock.get('change_pct', 0) > 0 else "negative" if stock.get('change_pct', 0) < 0 else ""
        vol_class = "high" if stock.get('volume_ratio', 1) > 1.5 else ""
        watchlist_rows += f'''
        <tr>
            <td class="ticker">{esc(stock.get('ticker', ''))}</td>
            <td class="{change_class}">{stock.get('change_pct', 0):+.2f}%</td>
            <td class="{vol_class}">{stock.get('volume_ratio', 1):.1f}x</td>
            <td>${stock.get('close', 0):.2f}</td>
            <td>${stock.get('pivot', 0):.2f}</td>
            <td>{stock.get('dist_to_pivot', 0):.1f}%</td>
            <td class="tier-{stock.get('tier', '3')}">T{stock.get('tier', '3')}</td>
        </tr>
        '''

    # Gap analysis
    gap_rows = ""
    for gap in report_data.get('gaps', []):
        gap_class = "positive" if gap.get('gap_pct', 0) > 0 else "negative"
        reason = esc(gap.get('reason', ''))
        gap_rows += f'''
        <tr class="{gap_class}">
            <td class="ticker">{esc(gap.get('ticker', ''))}</td>
            <td class="{gap_class}">{gap.get('gap_pct', 0):+.2f}%</td>
            <td>{gap.get('volume_ratio', 1):.1f}x avg</td>
            <td>{reason}</td>
        </tr>
        '''

    if not gap_rows:
        gap_rows = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No significant gaps today</td></tr>'

    # Action items
    action_items = report_data.get('action_items', [])
    action_html = ""
    for item in action_items:
        checked = "checked" if item.get('checked') else ""
        action_html += f'<div class="action-item"><input type="checkbox" {checked} disabled> {esc(item.get("text", ""))}</div>\n'

    # Key levels
    levels = report_data.get('key_levels', {})
    levels_html = ""
    for ticker, data in levels.items():
        levels_html += f'''
        <div class="key-level">
            <div class="label">{ticker}</div>
            <div class="value">Support: ${data.get('support', 0):.0f}</div>
            <div class="value">Resistance: ${data.get('resistance', 0):.0f}</div>
        </div>
        '''

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Post-Market Report — {esc(report_data.get('date', ''))}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #334155;
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
        .container {{ max-width: 1400px; margin: 0 auto; }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid var(--border-color);
            margin-bottom: 30px;
        }}
        h1 {{ font-size: 2rem; margin-bottom: 10px; }}
        .date {{ color: var(--text-secondary); font-size: 1.1rem; }}

        .section {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid var(--border-color);
        }}
        h2 {{
            font-size: 1.3rem;
            margin-bottom: 20px;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .metric-symbol {{ font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 5px; }}
        .metric-value {{ font-size: 1.4rem; font-weight: bold; margin-bottom: 5px; }}
        .metric-change {{ font-size: 0.95rem; font-weight: 500; }}
        .metric-range {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 5px; }}
        .vix-level {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 5px; }}

        .crypto-row {{
            background: var(--bg-tertiary);
            padding: 12px 20px;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            gap: 10px;
            margin-top: 15px;
        }}
        .crypto-label {{ color: var(--text-secondary); font-size: 0.9rem; }}
        .crypto-price {{ font-weight: bold; }}
        .crypto-divider {{ color: var(--border-color); margin: 0 5px; }}

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
            letter-spacing: 0.5px;
        }}
        tr:hover {{ background: rgba(255,255,255,0.03); }}
        .ticker {{ font-weight: bold; font-family: monospace; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}
        .high {{ color: var(--accent-green); font-weight: bold; }}
        .tier-1 {{ color: var(--accent-green); }}
        .tier-2 {{ color: var(--accent-yellow); }}
        .tier-3 {{ color: var(--accent-red); }}

        .action-item {{
            padding: 10px 0;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .action-item:last-child {{ border-bottom: none; }}
        input[type="checkbox"] {{
            width: 18px;
            height: 18px;
            accent-color: var(--accent-green);
        }}

        .key-levels {{
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        .key-level {{
            background: var(--bg-tertiary);
            padding: 15px 20px;
            border-radius: 8px;
        }}
        .key-level .label {{ color: var(--text-secondary); font-size: 0.85rem; }}
        .key-level .value {{ font-size: 1.2rem; font-weight: bold; margin-top: 5px; }}

        .timestamp {{
            text-align: center;
            padding: 20px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            margin-top: 20px;
        }}

        @media (max-width: 768px) {{
            .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
            table {{ font-size: 0.8rem; }}
            th, td {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌙 Post-Market Report</h1>
            <div class="date">{esc(report_data.get('date', ''))}</div>
        </header>

        <div class="section">
            <h2>📊 Market Close Summary</h2>
            <div class="metrics-grid">{indices_html}{vix_html}</div>
            {crypto_html}
        </div>

        <div class="section">
            <h2>🌙 Overnight Futures</h2>
            <div class="metrics-grid">{futures_html}</div>
        </div>

        <div class="section">
            <h2>📈 Watchlist Performance Today</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Change</th>
                        <th>Volume</th>
                        <th>Close</th>
                        <th>Pivot</th>
                        <th>Dist%</th>
                        <th>Tier</th>
                    </tr>
                </thead>
                <tbody>{watchlist_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>🚀 Gap Analysis (&gt;3%)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Gap</th>
                        <th>Volume</th>
                        <th>Reason/Context</th>
                    </tr>
                </thead>
                <tbody>{gap_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>🎯 Action Items for Tomorrow</h2>
            {action_html}
        </div>

        <div class="section">
            <h2>⚡ Key Levels for Tomorrow</h2>
            <div class="key-levels">{levels_html}</div>
        </div>

        <div class="timestamp">
            Report generated on {esc(report_data.get('date', ''))} at {esc(datetime.now().strftime('%H:%M %Z'))} | Data via Yahoo Finance
        </div>
    </div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return output_path

def analyze_watchlist_performance(watchlist_df):
    """Analyze today's performance for all watchlist stocks."""
    if watchlist_df is None or watchlist_df.empty:
        return []

    results = []

    for _, row in watchlist_df.iterrows():
        ticker = row['Ticker']
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")

            if len(hist) < 2:
                continue

            # Today's data
            today = hist.iloc[-1]
            prior = hist.iloc[-2]

            close = today['Close']
            change_pct = ((close / prior['Close']) - 1) * 100
            high = today['High']
            low = today['Low']
            volume = today['Volume']

            # Volume vs 50-day average
            avg_volume = hist['Volume'].tail(50).mean() if len(hist) >= 50 else volume
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1

            # Get pivot
            pivot = row.get('Pivot_Price', None)
            if pd.notna(pivot) and pivot:
                pivot = float(pivot)
                dist_to_pivot = ((pivot - close) / close) * 100
            else:
                pivot = None
                dist_to_pivot = None

            # Determine tier from watchlist
            stage = row.get('Stage', 0)
            tier = '1' if stage >= 3 else '2' if stage >= 2 else '3'

            results.append({
                'ticker': ticker,
                'change_pct': round(change_pct, 2),
                'close': round(close, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'volume_ratio': round(volume_ratio, 1),
                'pivot': round(pivot, 2) if pivot else None,
                'dist_to_pivot': round(dist_to_pivot, 1) if dist_to_pivot else None,
                'tier': tier
            })

        except Exception as e:
            print(f"⚠️ Error analyzing {ticker}: {e}")
            continue

    # Sort by absolute change (most active first)
    results.sort(key=lambda x: abs(x['change_pct']), reverse=True)
    return results

def detect_gaps(watchlist_performance):
    """Detect stocks with gaps >3%."""
    gaps = []

    for stock in watchlist_performance:
        if abs(stock['change_pct']) >= 3.0:
            gaps.append({
                'ticker': stock['ticker'],
                'gap_pct': stock['change_pct'],
                'volume_ratio': stock['volume_ratio'],
                'reason': 'Earnings/Move' if stock['volume_ratio'] > 2 else 'News/Driven'
            })

    return gaps

def generate_postmarket_report(output_format='console', output_path=None):
    """Generate comprehensive post-market report."""

    report_date = datetime.now().strftime('%Y-%m-%d')
    datetime_str = datetime.now().strftime('%Y-%m-%d_%H%M%S')

    # Initialize report data
    report_data = {
        'date': report_date,
        'indices': [],
        'vix': {},
        'futures': [],
        'crypto': {},
        'watchlist_performance': [],
        'gaps': [],
        'action_items': [],
        'key_levels': {}
    }

    # Load watchlist
    watchlist_df = load_watchlist()

    # 1. MARKET CLOSE SUMMARY
    indices_data = {}
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                today = data.iloc[-1]
                prior = data.iloc[-2]
                close = today['Close']
                prev_close = prior['Close']
                change = close - prev_close
                pct = ((close / prev_close) - 1) * 100
                high = today['High']
                low = today['Low']

                report_data['indices'].append({
                    'ticker': ticker,
                    'close': close,
                    'change': change,
                    'pct': pct,
                    'high': high,
                    'low': low
                })
                indices_data[ticker] = {'close': close, 'high': high, 'low': low}
        except Exception as e:
            print(f"⚠️ Error fetching {ticker}: {e}")

    # 2. VIX CLOSE
    try:
        vix = yf.Ticker("^VIX").history(period="2d")
        if len(vix) >= 2:
            vix_close = vix['Close'].iloc[-1]
            vix_prev = vix['Close'].iloc[-2]
            vix_change = vix_close - vix_prev
            vix_level = "Low <18" if vix_close < 18 else "Elevated 18-28" if vix_close < 28 else "High >28"

            report_data['vix'] = {
                'price': vix_close,
                'change': vix_change,
                'level': vix_level
            }
    except Exception as e:
        print(f"⚠️ Error fetching VIX: {e}")

    # 3. OVERNIGHT FUTURES
    futures_symbols = [("ES=F", "/ES"), ("NQ=F", "/NQ"), ("RTY=F", "/RTY")]
    for ticker, symbol in futures_symbols:
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                curr = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                change = curr - prev
                pct = ((curr / prev) - 1) * 100

                report_data['futures'].append({
                    'symbol': symbol,
                    'price': curr,
                    'change': change,
                    'pct': pct
                })
        except:
            pass

    # 4. CRYPTO
    try:
        btc = yf.Ticker("BTC-USD").history(period="2d")
        eth = yf.Ticker("ETH-USD").history(period="2d")
        if len(btc) >= 2 and len(eth) >= 2:
            btc_curr = btc['Close'].iloc[-1]
            btc_prev = btc['Close'].iloc[-2]
            eth_curr = eth['Close'].iloc[-1]
            eth_prev = eth['Close'].iloc[-2]

            report_data['crypto'] = {
                'btc_price': btc_curr,
                'btc_change': btc_curr - btc_prev,
                'btc_pct': ((btc_curr / btc_prev) - 1) * 100,
                'eth_price': eth_curr,
                'eth_change': eth_curr - eth_prev,
                'eth_pct': ((eth_curr / eth_prev) - 1) * 100
            }
    except:
        pass

    # 5. WATCHLIST PERFORMANCE
    if watchlist_df is not None:
        report_data['watchlist_performance'] = analyze_watchlist_performance(watchlist_df)

    # 6. GAP ANALYSIS
    if report_data['watchlist_performance']:
        report_data['gaps'] = detect_gaps(report_data['watchlist_performance'])

    # 7. ACTION ITEMS
    bullish_count = sum(1 for idx in report_data['indices'] if idx['change'] > 0)
    regime_today = "BULL" if bullish_count >= 2 else "BEAR" if bullish_count == 0 else "MIXED"

    report_data['action_items'] = [
        {'text': f'Review today\'s {len(report_data["gaps"])} gaps >3%', 'checked': False},
        {'text': 'Update watchlist pivots for any breakouts', 'checked': False},
        {'text': f'Note: {regime_today} day - adjust sizing accordingly', 'checked': False},
        {'text': 'Check overnight futures before bed', 'checked': False},
        {'text': 'Review tomorrow\'s economic calendar', 'checked': False}
    ]

    # 8. KEY LEVELS
    for idx in report_data['indices']:
        ticker = idx['ticker']
        close = idx['close']
        high = idx['high']
        low = idx['low']

        report_data['key_levels'][ticker] = {
            'support': low,
            'resistance': high
        }

    # OUTPUT
    if output_format == 'html':
        if not output_path:
            output_path = REPORTS_DIR / f"postmarket_report_{datetime_str}.html"
        else:
            output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = generate_html_report(report_data, output_path)
        print(f"✅ HTML report saved to: {result}")
        return result

    else:
        # CONSOLE OUTPUT
        print("🌙 POST-MARKET REPORT — " + report_date)
        print()

        print("**📊 MARKET CLOSE SUMMARY**")
        for idx in report_data['indices']:
            print(f"{idx['ticker']:4} ${idx['close']:>7.2f} ({idx['change']:>+.2f}, {idx['pct']:>+.2f}%) | H: ${idx['high']:.2f} L: ${idx['low']:.2f}")

        v = report_data['vix']
        if v:
            print(f"\nVIX:  {v['price']:.2f} ({v['change']:+.2f}) — {v['level']}")

        if report_data['futures']:
            print("\n**🌙 OVERNIGHT FUTURES**")
            for f in report_data['futures']:
                arrow = "↑" if f['change'] > 0 else "↓"
                print(f"{f['symbol']:5} ${f['price']:>8,.2f} {arrow} ({f['change']:>+.2f}, {f['pct']:>+.2f}%)")

        c = report_data['crypto']
        if c:
            print(f"\n**💰 CRYPTO**")
            print(f"BTC: ${c['btc_price']:>10,.0f} ({c['btc_pct']:>+.2f}%) | ETH: ${c['eth_price']:>9,.0f} ({c['eth_pct']:>+.2f}%)")

        # Watchlist performance
        if report_data['watchlist_performance']:
            print("\n**📈 WATCHLIST PERFORMANCE TODAY**")
            gained = sum(1 for s in report_data['watchlist_performance'] if s['change_pct'] > 0)
            declined = sum(1 for s in report_data['watchlist_performance'] if s['change_pct'] < 0)
            print(f"Total: {len(report_data['watchlist_performance'])} | Gained: {gained} | Declined: {declined}")
            print()
            print(f"{'Ticker':<8} {'Change':<10} {'Vol':<8} {'Close':<10} {'Pivot':<10} {'Dist%':<8} {'Tier'}")
            print("-" * 75)
            for stock in report_data['watchlist_performance'][:15]:  # Show top 15
                change_str = f"{stock['change_pct']:+.2f}%"
                tier_icon = '🟢' if stock['tier'] == '1' else '🟡' if stock['tier'] == '2' else '🔴'
                vol_str = f"{stock['volume_ratio']:.1f}x"
                pivot_str = f"${stock['pivot']:.2f}" if stock['pivot'] else "N/A"
                dist_str = f"{stock['dist_to_pivot']:.1f}%" if stock['dist_to_pivot'] is not None else "N/A"
                print(f"{stock['ticker']:<8} {change_str:<10} {vol_str:<8} ${stock['close']:<9.2f} {pivot_str:<10} {dist_str:<8} {tier_icon} T{stock['tier']}")

            if len(report_data['watchlist_performance']) > 15:
                print(f"\n... and {len(report_data['watchlist_performance']) - 15} more")

        # Gaps
        if report_data['gaps']:
            print("\n**🚀 GAPS >3%**")
            for gap in report_data['gaps']:
                arrow = "📈" if gap['gap_pct'] > 0 else "📉"
                print(f"{arrow} {gap['ticker']}: {gap['gap_pct']:+.2f}% (Vol: {gap['volume_ratio']:.1f}x) — {gap['reason']}")
        else:
            print("\n**🚀 GAPS >3%**")
            print("No significant gaps today")

        # Action items
        print("\n**🎯 ACTION ITEMS FOR TOMORROW**")
        for i, item in enumerate(report_data['action_items'], 1):
            print(f"{i}. ☐ {item['text']}")

        # Key levels
        print("\n**⚡ KEY LEVELS FOR TOMORROW**")
        for ticker, levels in report_data['key_levels'].items():
            print(f"{ticker}: Support ~${levels['support']:.0f} | Resistance ~${levels['resistance']:.0f}")

        print("\n" + "—" * 60)
        print(f"Market status: {regime_today} day")
        print("\n— Ace 🎯")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate comprehensive post-market report')
    parser.add_argument('--html', action='store_true', help='Generate HTML report instead of console output')
    parser.add_argument('--output', type=str, default=None, help='Output path for HTML report')
    args = parser.parse_args()

    output_format = 'html' if args.html else 'console'
    generate_postmarket_report(output_format=output_format, output_path=args.output)
