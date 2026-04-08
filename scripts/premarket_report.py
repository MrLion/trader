#!/usr/bin/env python3
"""
Pre-Market Report Generator

Generate pre-market briefings with futures, indices, regime assessment,
economic calendar, sector leaders, and watchlist rankings.
Supports both console and HTML output.
"""

import yfinance as yf
import csv
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import re
import pandas as pd
import html
import sys

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from stage2_utils import calculate_stage2_score, get_entry_score

def generate_html_report(report_data, output_path):
    """Generate standalone HTML report with embedded CSS"""

    # HTML escape helper
    def esc(text):
        return html.escape(str(text)) if text else ""

    # Color helpers
    def get_change_color(change):
        return "#4ade80" if change > 0 else "#f87171" if change < 0 else "#9ca3af"

    def get_regime_class(regime):
        return "bull" if "BULL" in regime else "bear" if "BEAR" in regime else "neutral"

    def get_tier_class(tier):
        return f"tier-{tier}"

    futures_html = ""
    for f in report_data.get('futures', []):
        color = get_change_color(f.get('change', 0))
        futures_html += f'''
        <div class="metric-card">
            <div class="metric-symbol">{esc(f.get('symbol', ''))}</div>
            <div class="metric-value">${f.get('price', 0):,.2f}</div>
            <div class="metric-change" style="color: {color}">
                {f.get('arrow', '')} {f.get('change', 0):+.2f} ({f.get('pct', 0):+.2f}%)
            </div>
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

    # Crypto section
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

    # Regime signals
    regime_signals_html = ""
    for sig_name, sig_status in report_data.get('regime_signals', []):
        status_class = "pass" if sig_status else "fail"
        status_icon = "✓" if sig_status else "✗"
        regime_signals_html += f'<div class="signal {status_class}"><span class="signal-icon">{status_icon}</span> {esc(sig_name)}</div>\n'

    # Economic events
    econ = report_data.get('economic', {})
    events_html = ""
    if econ.get('events'):
        risk_class = "high" if econ.get('risk_level') == '🔴' else "medium" if econ.get('risk_level') == '🟡' else "low"
        for event in econ.get('events', []):
            impact_class = "high" if event.get('impact') == '🔴' else "medium" if event.get('impact') == '🟡' else "low"
            events_html += f'''
            <div class="event-item">
                <span class="event-time">{esc(event.get('time', ''))}</span>
                <span class="event-impact impact-{impact_class}">{esc(event.get('impact', ''))}</span>
                <span class="event-name">{esc(event.get('event', ''))}</span>
            </div>
            '''
        econ_html = f'''
        <div class="section">
            <h2>Economic Calendar</h2>
            <div class="risk-badge risk-{risk_class}">{econ.get('risk_level', '🟢')} {esc(econ.get('advice', ''))}</div>
            <div class="events-list">{events_html}</div>
        </div>
        '''
    else:
        econ_html = '''
        <div class="section">
            <h2>Economic Calendar</h2>
            <div class="risk-badge risk-low">🟢 Clear day, trade normally</div>
        </div>
        '''

    # Indices
    indices_html = ""
    for idx in report_data.get('indices', []):
        s20_class = "pass" if idx.get('above_20') else "fail"
        s50_class = "pass" if idx.get('above_50') else "fail"
        s200_class = "pass" if idx.get('above_200') else "fail"
        indices_html += f'''
        <tr>
            <td class="ticker">{esc(idx.get('ticker', ''))}</td>
            <td class="price">${idx.get('close', 0):,.2f}</td>
            <td class="signal {s20_class}">{'✓' if idx.get('above_20') else '✗'} 20MA</td>
            <td class="signal {s50_class}">{'✓' if idx.get('above_50') else '✗'} 50MA</td>
            <td class="signal {s200_class}">{'✓' if idx.get('above_200') else '✗'} 200MA</td>
        </tr>
        '''

    # Sector leaders
    sector_rows = ""
    for row in report_data.get('sector_leaders', [])[:20]:
        sector_rows += f'''
        <tr>
            <td>{row.get('overall_rank', 0)}</td>
            <td class="ticker">{esc(row.get('ticker', ''))}</td>
            <td>{esc(row.get('name', '')[:22])}</td>
            <td class="{'positive' if row.get('ret_1w', 0) > 0 else 'negative'}">{row.get('ret_1w', 0):+.1f}%</td>
            <td class="{'positive' if row.get('ret_1m', 0) > 0 else 'negative'}">{row.get('ret_1m', 0):+.1f}%</td>
            <td class="{'positive' if row.get('ret_3m', 0) > 0 else 'negative'}">{row.get('ret_3m', 0):+.1f}%</td>
            <td class="{'positive' if row.get('ret_6m', 0) > 0 else 'negative'}">{row.get('ret_6m', 0):+.1f}%</td>
            <td class="stage2-score">{row.get('stage2_score', 0)}</td>
        </tr>
        '''

    # Watchlist
    watchlist_rows = ""
    for stock in report_data.get('watchlist', []):
        dist_class = "ready" if abs(stock.get('dist_to_pivot', 99)) < 3 else "close" if abs(stock.get('dist_to_pivot', 99)) < 5 else ""
        dist_sign = '+' if stock.get('dist_to_pivot', 0) > 0 else ''
        tier_priority_class = "tier-1-priority" if stock.get('tier') == '1' else ""
        watchlist_rows += f'''
        <tr class="{tier_priority_class}">
            <td class="ticker">{esc(stock.get('ticker', ''))}</td>
            <td class="tier {get_tier_class(stock.get('tier', '3'))}">T{esc(stock.get('tier', ''))}</td>
            <td class="score">{stock.get('entry_score', 0)}</td>
            <td class="price">${stock.get('current', 0):.2f}</td>
            <td class="pivot">${stock.get('pivot', 0):.2f}</td>
            <td class="dist {dist_class}">{dist_sign}{stock.get('dist_to_pivot', 0):.1f}%</td>
            <td class="risk">{stock.get('risk_pct', 0):.1f}%</td>
            <td class="stage2">{stock.get('stage2', 0)}/4</td>
            <td class="momentum">{stock.get('ret_6m', 0):.1f}%</td>
            <td class="sector">{esc(stock.get('sector', ''))}</td>
        </tr>
        '''

    ready_tickers = report_data.get('ready_tickers', [])
    ready_html = f"<div class='ready-banner'>Tier 1 Ready: {', '.join(ready_tickers)}</div>" if ready_tickers else ""

    # Action items
    action_items = report_data.get('action_items', [])
    action_html = ""
    for item in action_items:
        checked = "checked" if item.get('checked') else ""
        action_html += f'<div class="action-item"><input type="checkbox" {checked} disabled> {esc(item.get('text', ''))}</div>\n'

    # Key levels
    levels = report_data.get('key_levels', {})

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pre-Market Report — {esc(report_data.get('date', ''))}</title>
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
        .vix-level {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 5px; }}

        .crypto-row {{
            background: var(--bg-tertiary);
            padding: 12px 20px;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            gap: 10px;
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
            background: var(--accent-green);
            border-radius: 4px;
            transition: width 0.3s ease;
        }}

        .risk-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.9rem;
            margin-bottom: 15px;
        }}
        .risk-high {{ background: rgba(248, 113, 113, 0.2); color: var(--accent-red); }}
        .risk-medium {{ background: rgba(250, 204, 21, 0.2); color: var(--accent-yellow); }}
        .risk-low {{ background: rgba(74, 222, 128, 0.2); color: var(--accent-green); }}

        .events-list {{ display: flex; flex-direction: column; gap: 10px; }}
        .event-item {{
            background: var(--bg-tertiary);
            padding: 12px 15px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .event-time {{ color: var(--text-secondary); font-family: monospace; min-width: 80px; }}
        .event-impact {{ font-size: 1.2rem; }}

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

        .tier-1 {{ color: var(--accent-green); }}
        .tier-2 {{ color: var(--accent-yellow); }}
        .tier-3 {{ color: var(--accent-red); }}
        .dist.ready {{ color: var(--accent-green); font-weight: bold; }}
        .dist.close {{ color: var(--accent-yellow); }}

        .ready-banner {{
            background: rgba(74, 222, 128, 0.15);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
            padding: 12px 20px;
            border-radius: 8px;
            margin: 15px 0;
            font-weight: 500;
        }}

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

        .verdict {{
            text-align: center;
            padding: 30px;
            font-size: 1.2rem;
            color: var(--text-secondary);
            border-top: 2px solid var(--border-color);
            margin-top: 30px;
        }}
        .verdict strong {{ color: var(--text-primary); }}

        /* Sticky table headers */
        thead tr {{
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        thead th {{
            background: var(--bg-secondary);
            border-bottom: 2px solid var(--border-color);
        }}

        /* Zebra striping */
        tbody tr:nth-child(even) {{
            background: rgba(255,255,255,0.02);
        }}

        /* Visual priority for Tier 1 */
        tr.tier-1-priority {{
            border-left: 3px solid var(--accent-green);
        }}
        tr.tier-1-priority td:first-child {{
            padding-left: 9px;
        }}
        tr.tier-1-priority:hover {{
            background: rgba(74, 222, 128, 0.08);
        }}

        /* Section headings with icons */
        h2::before {{
            display: inline-block;
            margin-right: 10px;
            font-weight: normal;
        }}
        .section-futures h2::before {{ content: ""; }}
        .section-regime h2::before {{ content: ""; }}
        .section-indices h2::before {{ content: ""; }}
        .section-sectors h2::before {{ content: ""; }}
        .section-watchlist h2::before {{ content: ""; }}
        .section-action h2::before {{ content: ""; }}
        .section-levels h2::before {{ content: ""; }}

        /* Enhanced progress bar with gradient */
        .progress-fill {{
            background: linear-gradient(90deg, var(--accent-green) 0%, #22c55e 100%);
            box-shadow: 0 0 8px rgba(74, 222, 128, 0.3);
        }}

        /* Improved ready banner with icon */
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

        /* Tooltips for abbreviations */
        abbr {{
            border-bottom: 1px dotted var(--text-secondary);
            cursor: help;
            text-decoration: none;
        }}

        /* Timestamp footer */
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
            .metric-card, .key-level, .event-item {{
                background: #f5f5f5;
                border: 1px solid #ddd;
            }}
            .progress-fill {{
                background: #22c55e !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
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
            table {{ font-size: 0.8rem; }}
            th, td {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Pre-Market Report</h1>
            <div class="date">{esc(report_data.get('date', ''))}</div>
            <div class="regime-badge {get_regime_class(report_data.get('regime', ''))}">
                {esc(report_data.get('regime', ''))}
            </div>
        </header>

        <div class="section section-futures">
            <h2>Overnight Futures</h2>
            <div class="metrics-grid">{futures_html}{vix_html}</div>
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

        {econ_html}

        <div class="section section-indices">
            <h2>Major Indices</h2>
            <table>
                <thead><tr><th><abbr title="Stock Ticker Symbol">Ticker</abbr></th><th><abbr title="Current Market Price">Price</abbr></th><th><abbr title="20-Day Simple Moving Average">20MA</abbr></th><th><abbr title="50-Day Simple Moving Average">50MA</abbr></th><th><abbr title="200-Day Simple Moving Average">200MA</abbr></th></tr></thead>
                <tbody>{indices_html}</tbody>
            </table>
        </div>

        <div class="section section-sectors">
            <h2>Sector Leaders</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead><tr><th><abbr title="Overall Performance Rank">Rank</abbr></th><th><abbr title="Stock Ticker Symbol">Ticker</abbr></th><th>Company Name</th><th><abbr title="1 Week Return">1W</abbr></th><th><abbr title="1 Month Return">1M</abbr></th><th><abbr title="3 Month Return">3M</abbr></th><th><abbr title="6 Month Return">6M</abbr></th><th><abbr title="Stage 2 Score (0-4)">S2</abbr></th></tr></thead>
                    <tbody>{sector_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="section section-watchlist">
            <h2>Watchlist Analysis</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead><tr><th><abbr title="Stock Ticker Symbol">Ticker</abbr></th><th><abbr title="Entry Score Tier (1-3)">Tier</abbr></th><th><abbr title="Entry Score (0-100)">Score</abbr></th><th><abbr title="Current Price">Current</abbr></th><th><abbr title="Pivot/Breakout Price">Pivot</abbr></th><th><abbr title="Distance to Pivot Percentage">Dist%</abbr></th><th><abbr title="Risk Percentage from Entry to Stop">Risk%</abbr></th><th><abbr title="Stage 2 Score (0-4)">S2</abbr></th><th><abbr title="6 Month Return">6M</abbr></th><th>Sector</th></tr></thead>
                    <tbody>{watchlist_rows}</tbody>
                </table>
            </div>
            {ready_html}
        </div>

        <div class="section section-action">
            <h2>Action Items</h2>
            {action_html}
        </div>

        <div class="section section-levels">
            <h2>Key Levels</h2>
            <div class="key-levels">
                <div class="key-level">
                    <div class="label">SPY 50MA</div>
                    <div class="value">${levels.get('spy_ma50', 0):.0f}</div>
                </div>
                <div class="key-level">
                    <div class="label">QQQ 50MA</div>
                    <div class="value">${levels.get('qqq_ma50', 0):.0f}</div>
                </div>
                <div class="key-level">
                    <div class="label">VIX Watch</div>
                    <div class="value">28</div>
                </div>
            </div>
        </div>

        <div class="verdict">
            <strong>Verdict:</strong> {esc(report_data.get('regime', '').split()[1] if report_data.get('regime') else 'NEUTRAL')} regime.
            {report_data.get('verdict_action', 'Be selective.')}
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
                    
                    # Calculate Stage 2 score using shared 7-point system
                    stage2 = calculate_stage2_score(hist)

                    # Calculate additional data for display
                    ma20 = hist['Close'].rolling(20).mean().iloc[-1]
                    ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                    high_52w = hist['Close'].max()
                    from_high = ((high_52w - current) / high_52w) * 100
                    
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
                    
                    # ENTRY SCORE CALCULATION using shared function (7-point system thresholds)
                    # Note: RS_6M not calculated in premarket, pass 0
                    entry_score = get_entry_score(stage2, risk, abs(dist_to_pivot), ret_6m, rs_6m=0)
                    
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

def generate_comprehensive_report(output_format='console', output_path=None):
    """Generate comprehensive pre-market report"""

    report_date = datetime.now().strftime('%Y-%m-%d')

    # Data collection structure
    report_data = {
        'date': report_date,
        'futures': [],
        'vix': {},
        'crypto': {},
        'regime_signals': [],
        'bullish_count': 0,
        'regime': '',
        'economic': {'events': [], 'risk_level': '🟢', 'advice': 'Clear day, trade normally'},
        'indices': [],
        'sector_leaders': [],
        'watchlist': [],
        'ready_tickers': [],
        'action_items': [],
        'key_levels': {},
        'verdict_action': ''
    }

    # Load data
    scan = load_comprehensive_scan()
    watchlist = load_watchlist()

    # 1. OVERNIGHT FUTURES
    futures_symbols = [("ES=F", "/ES"), ("NQ=F", "/NQ"), ("RTY=F", "/RTY"),
                       ("YM=F", "/YM"), ("CL=F", "/CL"), ("GC=F", "/GC")]
    for ticker, symbol in futures_symbols:
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if len(data) >= 2:
                curr = data['Close'].iloc[-1]
                prev = data['Close'].iloc[-2]
                change = curr - prev
                pct = ((curr/prev)-1)*100
                arrow = "↑" if change > 0 else "↓"
                report_data['futures'].append({
                    'symbol': symbol,
                    'price': curr,
                    'change': change,
                    'pct': pct,
                    'arrow': arrow
                })
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
            report_data['vix'] = {
                'price': vix_curr,
                'change': vix_change,
                'level': vix_level
            }
    except:
        report_data['vix'] = {'price': 25, 'change': 0, 'level': 'Elevated 18-28'}

    # Crypto
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
                'btc_pct': ((btc_curr/btc_prev)-1)*100,
                'eth_price': eth_curr,
                'eth_change': eth_curr - eth_prev,
                'eth_pct': ((eth_curr/eth_prev)-1)*100
            }
    except:
        pass

    # ECONOMIC CALENDAR
    econ = fetch_economic_calendar()
    if econ['today']:
        has_high_impact = any(e['impact'] == '🔴' for e in econ['today'])
        if has_high_impact:
            report_data['economic']['risk_level'] = '🔴'
            report_data['economic']['advice'] = "Reduce size 50% or wait for post-event clarity"
        else:
            report_data['economic']['risk_level'] = '🟡'
            report_data['economic']['advice'] = "Normal size, watch for volatility at event time"
        report_data['economic']['events'] = econ['today']

    # MAJOR INDICES
    indices = {}
    for ticker in ["SPY", "QQQ", "IWM"]:
        try:
            data = yf.Ticker(ticker).history(period="1y")
            close = data['Close'].iloc[-1]
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            ma50 = data['Close'].rolling(50).mean().iloc[-1]
            ma200 = data['Close'].rolling(200).mean().iloc[-1]
            indices[ticker] = (close, ma50, ma200)
            report_data['indices'].append({
                'ticker': ticker,
                'close': close,
                'above_20': close > ma20,
                'above_50': close > ma50,
                'above_200': close > ma200,
                'ma20': ma20,
                'ma50': ma50,
                'ma200': ma200
            })
        except:
            pass

    # REGIME ASSESSMENT
    spy_close, spy_ma50, spy_ma200 = indices.get("SPY", (0, 0, 0))
    qqq_close, qqq_ma50, qqq_ma200 = indices.get("QQQ", (0, 0, 0))
    iwm_close, iwm_ma50, iwm_ma200 = indices.get("IWM", (0, 0, 0))

    vix_curr = report_data['vix'].get('price', 25)

    signals = [
        ("SPY > 50 SMA", spy_close > spy_ma50),
        ("QQQ > 50 SMA", qqq_close > qqq_ma50),
        ("IWM > 50 SMA", iwm_close > iwm_ma50),
        ("VIX < 18", vix_curr < 18)
    ]

    bullish = sum(1 for _, v in signals if v)
    report_data['regime_signals'] = signals
    report_data['bullish_count'] = bullish

    regime = "🟢 BULL" if bullish >= 4 else "🟡 NEUTRAL" if bullish >= 2 else "🔴 BEAR"
    report_data['regime'] = regime

    # SECTOR LEADERS
    if scan:
        report_data['sector_leaders'] = scan[:20]

    # WATCHLIST
    if watchlist:
        report_data['watchlist'] = watchlist
        # Ready tickers
        ready = [s['ticker'] for s in watchlist if s['tier'] == '1' and abs(s['dist_to_pivot']) < 3]
        report_data['ready_tickers'] = ready

    # ACTION ITEMS - Dynamic based on market conditions
    action_items = []

    # Sector leaders action (scan is a list of top performers)
    if scan and len(scan) > 0:
        top_sectors = [s['ticker'] for s in scan[:3]]
        action_items.append({'text': f"🏭 Review top sectors: {', '.join(top_sectors)}", 'checked': False})
    else:
        action_items.append({'text': '⚠️ Run sector scan to identify leading sectors', 'checked': False})

    # Ready tickers action
    if report_data.get('ready_tickers'):
        ready = report_data['ready_tickers'][:5]
        action_items.append({'text': f"🎯 Tier 1 ready ({len(report_data['ready_tickers'])}): {', '.join(ready)}{'...' if len(report_data['ready_tickers']) > 5 else ''}", 'checked': False})
    else:
        action_items.append({'text': '⏸️ No Tier 1 setups ready - scan for new candidates', 'checked': False})

    # Watchlist tier breakdown
    if watchlist:
        t1 = sum(1 for s in watchlist if s['tier'] == '1')
        t2 = sum(1 for s in watchlist if s['tier'] == '2')
        t3 = sum(1 for s in watchlist if s['tier'] == '3')
        action_items.append({'text': f"📋 Watchlist: {t1} Tier 1 | {t2} Tier 2 | {t3} Tier 3", 'checked': True})

    # Regime-based action
    if bullish >= 4:
        action_items.append({'text': '🟢 BULL regime (4/4): Full exposure, execute best setups', 'checked': False})
    elif bullish >= 2:
        action_items.append({'text': '🟡 Mixed regime: Selective entries on A+ setups', 'checked': False})
    else:
        action_items.append({'text': '🔴 BEAR regime: No new entries until reclaim', 'checked': False})

    # VIX warning
    vix_price = report_data['vix'].get('price', 20)
    if vix_price >= 28:
        action_items.append({'text': f'⚡ High VIX ({vix_price:.1f}): Reduce size, wider stops', 'checked': False})
    elif vix_price >= 18:
        action_items.append({'text': f'⚡ Elevated VIX ({vix_price:.1f}): Normal size, stay alert', 'checked': False})

    # Economic calendar check
    econ = report_data.get('economic', {})
    if econ.get('events'):
        high_impact = sum(1 for e in econ['events'] if e.get('impact') == '🔴')
        if high_impact > 0:
            action_items.append({'text': f'🔴 {high_impact} HIGH impact event(s) today - trade around them', 'checked': False})
        else:
            action_items.append({'text': '🟡 Medium impact events today - watch for volatility', 'checked': False})
    else:
        action_items.append({'text': '✓ Clear economic calendar - normal trading', 'checked': True})

    # Standard items
    action_items.append({'text': '📊 Review top 20 for actionable setups', 'checked': False})
    action_items.append({'text': '📅 Check earnings calendar', 'checked': False})
    action_items.append({'text': '🌅 Monitor pre-market gaps >3%', 'checked': False})

    report_data['action_items'] = action_items

    # KEY LEVELS
    report_data['key_levels'] = {
        'spy_ma50': spy_ma50,
        'qqq_ma50': qqq_ma50,
        'vix_watch': 28
    }

    # VERDICT
    report_data['verdict_action'] = 'Stay flat.' if bullish < 2 else 'Be selective.'

    # OUTPUT
    if output_format == 'html':
        if not output_path:
            datetime_str = datetime.now().strftime('%Y-%m-%d_%H%M%S')
            output_path = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/reports/premarket_report_{datetime_str}.html")
        else:
            output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = generate_html_report(report_data, output_path)
        print(f"✅ HTML report saved to: {result}")
        return result
    else:
        # Console output
        print("🌅 COMPREHENSIVE PRE-MARKET REPORT — " + report_date)
        print()

        print("**📊 OVERNIGHT FUTURES**")
        for f in report_data['futures']:
            print(f"{f['symbol']:5} ${f['price']:,.2f} {f['arrow']} ({f['change']:+.2f}, {f['pct']:+.2f}%)")

        v = report_data['vix']
        print(f"VIX   {v['price']:.2f} ({v['change']:+.2f}) — {v['level']}")

        c = report_data['crypto']
        if c:
            print(f"\nCrypto: BTC ${c['btc_price']:,.0f} ({c['btc_pct']:+.2f}%) | ETH ${c['eth_price']:,.0f} ({c['eth_pct']:+.2f}%)")

        print("\n**📅 ECONOMIC CALENDAR (US)**")
        if report_data['economic']['events']:
            print(f"{report_data['economic']['risk_level']} Today's Events:")
            for e in report_data['economic']['events']:
                print(f"   {e['time']} {e['impact']} {e['event']}")
            print(f"   → {report_data['economic']['advice']}")
        else:
            print("🟢 No major US economic events today")
            print("   → Clear day, trade normally")

        print("\n**📈 MAJOR INDICES vs KEY MAs**")
        for idx in report_data['indices']:
            s20 = "✓" if idx['above_20'] else "✗"
            s50 = "✓" if idx['above_50'] else "✗"
            s200 = "✓" if idx['above_200'] else "✗"
            print(f"{idx['ticker']:4} ${idx['close']:,.2f} | 20MA {s20} | 50MA {s50} | 200MA {s200}")

        print("\n**🔍 REGIME ASSESSMENT**")
        for sig, status in report_data['regime_signals']:
            print(f"{'✓' if status else '✗'} {sig}")
        print(f"\nBullish Signals: {bullish}/4")
        print(f"\n{regime}")

        if report_data['sector_leaders']:
            print("\n**🏆 TOP 20 LEADING ETFs (by Overall Rank)**")
            print(f"{'Rank':<5} {'Ticker':<6} {'Name':<22} {'1W':>8} {'1M':>8} {'3M':>8} {'6M':>8} {'S2':>3}")
            print("-" * 90)
            for row in report_data['sector_leaders']:
                print(f"{row['overall_rank']:<5} {row['ticker']:<6} {row['name']:<22} "
                      f"{row['ret_1w']:>+7.1f}% {row['ret_1m']:>+7.1f}% "
                      f"{row['ret_3m']:>+7.1f}% {row['ret_6m']:>+7.1f}% "
                      f"{row['stage2_score']:>3}")

        print("\n**📋 WATCHLIST ANALYSIS — Entry Score Rankings**")
        if report_data['watchlist']:
            tier_counts = {'1': 0, '2': 0, '3': 0}
            for stock in report_data['watchlist']:
                tier_counts[stock['tier']] = tier_counts.get(stock['tier'], 0) + 1
            print(f"Total: {len(report_data['watchlist'])} | 🟢 Tier 1: {tier_counts['1']} | 🟡 Tier 2: {tier_counts['2']} | 🔴 Tier 3: {tier_counts['3']}")

            print(f"\n{'Ticker':<8} {'Tier':<8} {'Score':<7} {'Current':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'S2':<4} {'6M':<10} {'Sector'}")
            print("-" * 95)
            for stock in report_data['watchlist']:
                tier_icon = '🟢' if stock['tier'] == '1' else '🟡' if stock['tier'] == '2' else '🔴'
                dist_sign = '+' if stock['dist_to_pivot'] > 0 else ''
                print(f"{stock['ticker']:<8} {tier_icon} T{stock['tier']:<4} {stock['entry_score']:<6} ${stock['current']:<9.2f} ${stock['pivot']:<9.2f} "
                      f"{dist_sign}{stock['dist_to_pivot']:<6.1f}% {stock['risk_pct']:<7.1f}% "
                      f"{stock['stage2']}/4  {stock['ret_6m']:>9.1f}% {stock['sector']}")

            if report_data['ready_tickers']:
                print(f"\n✅ Tier 1 Ready (Score ≥60, within 3%): {', '.join(report_data['ready_tickers'])}")
        else:
            print("⚠️ Watchlist is empty")
            print("   Run: python3 watchlist_manager.py add TICKER")

        print("\n**🎯 TODAY'S ACTION ITEMS**")
        for i, item in enumerate(report_data['action_items'], 1):
            print(f"{i}. ☐ {item['text']}")

        print(f"\n**⚡ KEY LEVELS**")
        print(f"SPY: Reclaim ${report_data['key_levels']['spy_ma50']:.0f} | QQQ: Reclaim ${report_data['key_levels']['qqq_ma50']:.0f} | VIX: Watch 28")

        print("\n" + "—" * 60)
        print(f"Verdict: {regime.split()[1] if regime else 'NEUTRAL'} regime. {report_data['verdict_action']}")
        print("\n— Ace 🎯")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate comprehensive pre-market report')
    parser.add_argument('--html', action='store_true', help='Generate HTML report instead of console output')
    parser.add_argument('--output', type=str, default=None, help='Output path for HTML report (default: reports/premarket_report_YYYY-MM-DD.html)')
    args = parser.parse_args()

    output_format = 'html' if args.html else 'console'
    generate_comprehensive_report(output_format=output_format, output_path=args.output)
