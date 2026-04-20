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

import argparse
import csv
import html
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from traderlib import calculate_stage2_score, get_entry_score, get_stage2_details
from traderlib.stage2_utils import calculate_ma_support_stop

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

    # Determine regime from indices performance
    bullish_count = sum(1 for idx in report_data.get('indices', []) if idx.get('change', 0) > 0)
    regime = "BULL" if bullish_count >= 2 else "BEAR" if bullish_count == 0 else "NEUTRAL"
    regime_class = get_regime_class(regime)

    # Market close cards (for section header)
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

    # Major Indices table (like premarket)
    indices_table_html = ""
    for idx in report_data.get('indices', []):
        s20_class = "pass" if idx.get('above_20') else "fail"
        s50_class = "pass" if idx.get('above_50') else "fail"
        s200_class = "pass" if idx.get('above_200') else "fail"
        indices_table_html += f'''
        <tr>
            <td class="ticker">{esc(idx.get('ticker', ''))}</td>
            <td class="price">${idx.get('close', 0):,.2f}</td>
            <td class="signal {s20_class}">{'✓' if idx.get('above_20') else '✗'} 20MA</td>
            <td class="signal {s50_class}">{'✓' if idx.get('above_50') else '✗'} 50MA</td>
            <td class="signal {s200_class}">{'✓' if idx.get('above_200') else '✗'} 200MA</td>
        </tr>
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

    # Regime signals
    regime_signals_html = ""
    for sig_name, sig_status in report_data.get('regime_signals', []):
        status_class = "pass" if sig_status else "fail"
        status_icon = "✓" if sig_status else "✗"
        regime_signals_html += f'<div class="signal {status_class}"><span class="signal-icon">{status_icon}</span> {esc(sig_name)}</div>\n'

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
    ready_tickers = []
    for stock in report_data.get('watchlist_performance', []):
        change_class = "positive" if stock.get('change_pct', 0) > 0 else "negative" if stock.get('change_pct', 0) < 0 else ""
        vol_class = "high" if stock.get('volume_ratio', 1) > 1.5 else ""
        tier_class = "tier-1-priority" if stock.get('tier') == '1' else ""
        # Track ready stocks (Tier 1 within 3% of pivot)
        if stock.get('tier') == '1' and stock.get('dist_to_pivot') is not None and abs(stock.get('dist_to_pivot', 99)) < 3:
            ready_tickers.append(stock.get('ticker'))
        watchlist_rows += f'''
        <tr class="{tier_class}">
            <td class="ticker">{esc(stock.get('ticker', ''))}</td>
            <td class="{change_class}">{stock.get('change_pct', 0):+.2f}%</td>
            <td class="{vol_class}">{stock.get('volume_ratio', 1):.1f}x</td>
            <td>${stock.get('close', 0):.2f}</td>
            <td>${(stock.get('pivot') or 0):.2f}</td>
            <td>{(stock.get('dist_to_pivot') or 0):.1f}%</td>
            <td class="tier-{stock.get('tier', '3')}">T{stock.get('tier', '3')}</td>
        </tr>
        '''

    ready_html = f"<div class='ready-banner'>Tier 1 Ready: {', '.join(ready_tickers)}</div>" if ready_tickers else ""

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
        abbr {{
            border-bottom: 1px dotted var(--text-secondary);
            cursor: help;
            text-decoration: none;
        }}

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
        .vix.vix-low {{ border: 1px solid var(--accent-green); }}
        .vix.vix-elevated {{ border: 1px solid var(--accent-yellow); }}
        .vix.vix-high {{ border: 1px solid var(--accent-red); }}

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

        .signals-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }}
        .signal {{
            padding: 12px 15px;
            border-radius: 6px;
            font-size: 0.95rem;
        }}
        .signal.pass {{ background: rgba(74, 222, 128, 0.1); color: var(--accent-green); }}
        .signal.fail {{ background: rgba(248, 113, 113, 0.1); color: var(--accent-red); }}
        .signal-icon {{ font-weight: bold; margin-right: 8px; }}

        .progress-bar {{
            background: var(--bg-tertiary);
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-green) 0%, #22c55e 100%);
            box-shadow: 0 0 8px rgba(74, 222, 128, 0.3);
            border-radius: 4px;
            transition: width 0.3s ease;
        }}

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
        tbody tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
        .ticker {{ font-weight: bold; font-family: monospace; }}
        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}
        .high {{ color: var(--accent-green); font-weight: bold; }}
        .tier-1 {{ color: var(--accent-green); }}
        .tier-2 {{ color: var(--accent-yellow); }}
        .tier-3 {{ color: var(--accent-red); }}
        tr.tier-1-priority {{ border-left: 3px solid var(--accent-green); }}
        tr.tier-1-priority td:first-child {{ padding-left: 9px; }}
        tr.tier-1-priority:hover {{ background: rgba(74, 222, 128, 0.08); }}

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

        .ready-banner {{
            background: linear-gradient(135deg, rgba(74, 222, 128, 0.15) 0%, rgba(34, 197, 94, 0.1) 100%);
            border: 1px solid var(--accent-green);
            border-left: 4px solid var(--accent-green);
            color: var(--accent-green);
            padding: 14px 20px;
            border-radius: 8px;
            margin: 20px 0 10px 0;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .ready-banner::before {{
            content: "→";
            font-size: 1.2rem;
            font-weight: bold;
        }}

        .regime-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            margin-top: 15px;
        }}
        .regime-badge.bull {{ background: rgba(74, 222, 128, 0.2); color: var(--accent-green); }}
        .regime-badge.neutral {{ background: rgba(250, 204, 21, 0.2); color: var(--accent-yellow); }}
        .regime-badge.bear {{ background: rgba(248, 113, 113, 0.2); color: var(--accent-red); }}

        .timestamp {{
            text-align: center;
            padding: 20px;
            font-size: 0.85rem;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            margin-top: 20px;
        }}

        /* Print styles */
        @media print {{
            body {{
                background: white;
                color: black;
                padding: 10px;
            }}
            .section {{
                background: white;
                border: 1px solid #ccc;
                break-inside: avoid;
            }}
            .metric-card, .key-level {{
                background: #f5f5f5;
                border: 1px solid #ddd;
            }}
            .tier-1 {{ color: #15803d !important; }}
            .tier-2 {{ color: #a16207 !important; }}
            .tier-3 {{ color: #dc2626 !important; }}
            .positive {{ color: #15803d !important; }}
            .negative {{ color: #dc2626 !important; }}
            .ready-banner {{
                background: #f0fdf4 !important;
                border: 1px solid #22c55e !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            thead th {{
                background: #f5f5f5 !important;
            }}
            tr.tier-1-priority {{
                border-left: 3px solid #22c55e !important;
            }}
        }}

        @media (max-width: 768px) {{
            .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .signals-grid {{ grid-template-columns: 1fr; }}
            .crypto-row {{ flex-wrap: wrap; }}
            table {{ font-size: 0.8rem; }}
            th, td {{ padding: 8px; }}
            h1 {{ font-size: 1.5rem; }}
            .section {{ padding: 15px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Post-Market Report</h1>
            <div class="date">{esc(report_data.get('date', ''))}</div>
            <div class="regime-badge {regime_class}">{regime} CLOSE</div>
        </header>

        <div class="section section-close">
            <h2>📊 Market Close Summary</h2>
            <div class="metrics-grid">{indices_html}{vix_html}</div>
            {crypto_html}
        </div>

        <div class="section section-regime">
            <h2>Regime Assessment</h2>
            <div class="signals-grid">{regime_signals_html}</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {(report_data.get('bullish_count', 0) / 4 * 100):.0f}%"></div>
            </div>
            <div style="text-align: center; margin-top: 10px; color: var(--text-secondary);">
                Bullish Signals: {report_data.get('bullish_count', 0)}/4
            </div>
        </div>

        <div class="section section-indices">
            <h2>Major Indices</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead><tr><th><abbr title="Stock Ticker Symbol">Ticker</abbr></th><th><abbr title="Current Market Price">Price</abbr></th><th><abbr title="20-Day Simple Moving Average">20MA</abbr></th><th><abbr title="50-Day Simple Moving Average">50MA</abbr></th><th><abbr title="200-Day Simple Moving Average">200MA</abbr></th></tr></thead>
                    <tbody>{indices_table_html}</tbody>
                </table>
            </div>
        </div>

        <div class="section section-watchlist">
            <h2>📈 Watchlist Performance Today</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th><abbr title="Stock Ticker Symbol">Ticker</abbr></th>
                            <th><abbr title="Today's Percentage Change">Change</abbr></th>
                            <th><abbr title="Volume vs 50-Day Average">Volume</abbr></th>
                            <th><abbr title="Closing Price">Close</abbr></th>
                            <th><abbr title="Pivot/Breakout Price">Pivot</abbr></th>
                            <th><abbr title="Distance to Pivot Percentage">Dist%</abbr></th>
                            <th><abbr title="Entry Score Tier (1-3)">Tier</abbr></th>
                        </tr>
                    </thead>
                    <tbody>{watchlist_rows}</tbody>
                </table>
            </div>
            {ready_html}
        </div>

        <div class="section section-gaps">
            <h2>🚀 Gap Analysis (&gt;3%)</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th><abbr title="Stock Ticker Symbol">Ticker</abbr></th>
                            <th><abbr title="Gap Percentage">Gap</abbr></th>
                            <th><abbr title="Volume vs Average">Volume</abbr></th>
                            <th>Reason/Context</th>
                        </tr>
                    </thead>
                    <tbody>{gap_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="section section-action">
            <h2>🎯 Action Items for Tomorrow</h2>
            {action_html}
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
    """Analyze today's performance for all watchlist stocks with proper entry scoring."""
    if watchlist_df is None or watchlist_df.empty:
        return []

    results = []

    for _, row in watchlist_df.iterrows():
        ticker = row['Ticker']
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

            if len(hist) < 200:
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
            avg_volume = hist['Volume'].tail(50).mean() if len(hist) >= 50 else hist['Volume'].mean()
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1

            # Get pivot
            pivot = row.get('Pivot_Price', None)
            if pd.notna(pivot) and pivot:
                pivot = float(pivot)
                dist_to_pivot = ((pivot - close) / close) * 100
            else:
                pivot = None
                dist_to_pivot = None

            # Calculate comprehensive metrics for proper entry scoring
            ret_6m = (close / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0

            # Stage 2 score and MA flags
            s2_details = get_stage2_details(hist)
            stage2 = s2_details['score']
            below_50ma = not s2_details['criteria']['price_above_50ma']
            below_20ma = not s2_details['criteria']['price_above_20ma']

            # Calculate ATR for risk
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            atr_stop = close - (2 * atr)
            recent_low = hist['Low'].tail(10).min()
            stop = max(recent_low, atr_stop)

            # MA Support Stop calculation
            ma_result = calculate_ma_support_stop(
                close, s2_details, buffer_pct=0.01, cluster_spread_pct=0.05, min_cluster_size=2
            )
            if ma_result:
                stop = max(stop, ma_result['ma_support_stop'])

            risk = (pivot - stop) / pivot * 100 if pivot and pivot > stop else 0

            # Calculate entry score using same logic as premarket report
            entry_score = get_entry_score(
                stage2, risk, abs(dist_to_pivot) if dist_to_pivot else 99,
                ret_6m, rs_6m=0, below_50ma=below_50ma, below_20ma=below_20ma
            )

            # Tier based on entry score
            if entry_score >= 60:
                tier = '1'
            elif entry_score >= 40:
                tier = '2'
            else:
                tier = '3'

            results.append({
                'ticker': ticker,
                'change_pct': round(change_pct, 2),
                'close': round(close, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'volume_ratio': round(volume_ratio, 1),
                'pivot': round(pivot, 2) if pivot else None,
                'dist_to_pivot': round(dist_to_pivot, 1) if dist_to_pivot else None,
                'tier': tier,
                'entry_score': entry_score,
                'stage2': stage2,
                'ret_6m': round(ret_6m, 1)
            })

        except Exception as e:
            print(f"⚠️ Error analyzing {ticker}: {e}")
            continue

    # Sort by entry score (descending) to match premarket report
    results.sort(key=lambda x: (x['entry_score'], abs(x['change_pct'])), reverse=True)
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
        'crypto': {},
        'watchlist_performance': [],
        'gaps': [],
        'action_items': [],
        'regime_signals': [],
        'bullish_count': 0
    }

    # Load watchlist
    watchlist_df = load_watchlist()

    # 1. MARKET CLOSE SUMMARY (with MAs like Major Indices)
    indices_data = {}
    regime_checks = []
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="252d")  # 1 year for 200MA
            if len(data) >= 20:
                today = data.iloc[-1]
                close = today['Close']
                high = today['High']
                low = today['Low']

                # Calculate changes from prior day
                if len(data) >= 2:
                    prior = data.iloc[-2]
                    prev_close = prior['Close']
                    change = close - prev_close
                    pct = ((close / prev_close) - 1) * 100
                else:
                    change = 0
                    pct = 0

                # Calculate MAs
                ma20 = data['Close'].tail(20).mean() if len(data) >= 20 else close
                ma50 = data['Close'].tail(50).mean() if len(data) >= 50 else close
                ma200 = data['Close'].tail(200).mean() if len(data) >= 200 else close

                above_20 = close > ma20
                above_50 = close > ma50
                above_200 = close > ma200

                report_data['indices'].append({
                    'ticker': ticker,
                    'close': close,
                    'change': change,
                    'pct': pct,
                    'high': high,
                    'low': low,
                    'above_20': above_20,
                    'above_50': above_50,
                    'above_200': above_200,
                    'ma50': ma50
                })
                indices_data[ticker] = {'close': close, 'high': high, 'low': low}

                # Regime signal: Index above 50MA (bullish sign)
                regime_checks.append((ticker, above_50))
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

    # 3. REGIME ASSESSMENT (calculate signals)
    # Calculate regime signals
    bullish_signals = 0
    regime_signals = []

    # Signal 1: SPY above 50MA
    spy_above_50 = next((idx for idx in report_data['indices'] if idx['ticker'] == 'SPY'), None)
    spy_signal = spy_above_50 and spy_above_50['above_50'] if spy_above_50 else False
    if spy_signal:
        bullish_signals += 1
    regime_signals.append(("SPY > 50MA", spy_signal))

    # Signal 2: QQQ above 50MA
    qqq_above_50 = next((idx for idx in report_data['indices'] if idx['ticker'] == 'QQQ'), None)
    qqq_signal = qqq_above_50 and qqq_above_50['above_50'] if qqq_above_50 else False
    if qqq_signal:
        bullish_signals += 1
    regime_signals.append(("QQQ > 50MA", qqq_signal))

    # Signal 3: IWM above 50MA
    iwm_above_50 = next((idx for idx in report_data['indices'] if idx['ticker'] == 'IWM'), None)
    iwm_signal = iwm_above_50 and iwm_above_50['above_50'] if iwm_above_50 else False
    if iwm_signal:
        bullish_signals += 1
    regime_signals.append(("IWM > 50MA", iwm_signal))

    # Signal 4: VIX < 18 (low volatility = bullish)
    vix_bullish = report_data['vix'].get('price', 25) < 18
    if vix_bullish:
        bullish_signals += 1
    regime_signals.append(("VIX < 18", vix_bullish))

    report_data['regime_signals'] = regime_signals
    report_data['bullish_count'] = bullish_signals

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

    # 7. ACTION ITEMS - Dynamic based on market conditions
    regime_today = "BULL" if report_data['bullish_count'] >= 2 else "BEAR" if report_data['bullish_count'] == 0 else "MIXED"

    action_items = []

    # Gap analysis action
    if report_data['gaps']:
        gap_tickers = [g['ticker'] for g in report_data['gaps'][:3]]  # Top 3
        action_items.append({'text': f"📊 Review {len(report_data['gaps'])} gaps >3%: {', '.join(gap_tickers)}{'...' if len(report_data['gaps']) > 3 else ''}", 'checked': False})
    else:
        action_items.append({'text': '✓ No significant gaps to review today', 'checked': True})

    # Breakout/failure detection
    breakout_stocks = []
    failed_stocks = []
    for stock in report_data['watchlist_performance']:
        pivot = stock.get('pivot')
        if pivot and stock.get('change_pct', 0) > 3 and stock.get('close', 0) > pivot:
            breakout_stocks.append(stock['ticker'])
        elif pivot and stock.get('change_pct', 0) < -3 and stock.get('close', 0) < pivot * 0.97:
            failed_stocks.append(stock['ticker'])

    if breakout_stocks:
        action_items.append({'text': f"🚀 Update pivots for breakouts: {', '.join(breakout_stocks[:3])}", 'checked': False})
    if failed_stocks:
        action_items.append({'text': f"⚠️ Review failed setups: {', '.join(failed_stocks[:3])}", 'checked': False})
    if not breakout_stocks and not failed_stocks:
        action_items.append({'text': '✓ No breakouts or failures today', 'checked': True})

    # Regime-based sizing guidance
    if regime_today == "BULL":
        action_items.append({'text': '🟢 BULL regime: Full sizing on A+ setups', 'checked': False})
    elif regime_today == "BEAR":
        action_items.append({'text': '🔴 BEAR regime: Reduce size 50% or stay flat', 'checked': False})
    else:
        action_items.append({'text': '🟡 MIXED regime: A setups only, reduced size', 'checked': False})

    # VIX-based guidance
    vix_price = report_data['vix'].get('price', 20)
    if vix_price > 28:
        action_items.append({'text': f'⚡ High VIX ({vix_price:.1f}): Tighten stops, reduce exposure', 'checked': False})
    elif vix_price > 20:
        action_items.append({'text': f'⚡ Elevated VIX ({vix_price:.1f}): Watch for volatility expansion', 'checked': False})

    # Tier 1 ready stocks
    ready_for_tomorrow = [s['ticker'] for s in report_data['watchlist_performance']
                         if s.get('tier') == '1' and s.get('dist_to_pivot') is not None
                         and abs(s['dist_to_pivot']) < 5]
    if ready_for_tomorrow:
        action_items.append({'text': f"🎯 Tier 1 ready for tomorrow: {', '.join(ready_for_tomorrow[:5])}", 'checked': False})

    # Standard items
    action_items.append({'text': '🌙 Check overnight futures before bed', 'checked': False})
    action_items.append({'text': '📅 Review tomorrow\'s economic calendar', 'checked': False})

    report_data['action_items'] = action_items

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

        # Regime Assessment
        print("\n**REGIME ASSESSMENT**")
        for sig_name, sig_status in report_data['regime_signals']:
            icon = "✓" if sig_status else "✗"
            print(f"  {icon} {sig_name}")
        print(f"\nBullish Signals: {report_data['bullish_count']}/4")

        # Major Indices with MAs
        print("\n**MAJOR INDICES**")
        print(f"{'Ticker':<8} {'Price':<12} {'20MA':<10} {'50MA':<10} {'200MA':<10}")
        print("-" * 55)
        for idx in report_data['indices']:
            m20 = "✓" if idx.get('above_20') else "✗"
            m50 = "✓" if idx.get('above_50') else "✗"
            m200 = "✓" if idx.get('above_200') else "✗"
            print(f"{idx['ticker']:<8} ${idx['close']:<11.2f} {m20:<10} {m50:<10} {m200:<10}")

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
