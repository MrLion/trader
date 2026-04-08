#!/usr/bin/env python3
"""Analyze entire watchlist for favorable entry points."""

import yfinance as yf
import pandas as pd
import csv
import argparse
from pathlib import Path
import os
import sys

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))
from stage2_utils import calculate_stage2_score, get_entry_score, get_stage2_tier

# Configurable paths - can be overridden via environment variables
WATCHLIST_PATH = Path(os.getenv('TRADER_WATCHLIST', '/Users/mintmrlion/.openclaw/workspaces/trader/data/watchlist.csv'))
OUTPUT_DIR = Path(os.getenv('TRADER_OUTPUT', '/Users/mintmrlion/.openclaw/workspaces/trader/reports'))

def calculate_rsi(prices, period=14):
    """Calculate RSI for a price series."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

def analyze_watchlist(output_csv=False, output_html=False):
    """Analyze all watchlist stocks and rank by entry attractiveness."""

    if not WATCHLIST_PATH.exists():
        print("❌ Watchlist not found")
        return

    # Load watchlist into pandas for easier manipulation
    df = pd.read_csv(WATCHLIST_PATH)

    # Fetch SPY for relative strength calculation
    print("📊 Fetching SPY benchmark...")
    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="1y")
        spy_current = spy_hist['Close'].iloc[-1]
        spy_1m = (spy_current / spy_hist['Close'].iloc[-20] - 1) * 100
        spy_3m = (spy_current / spy_hist['Close'].iloc[-65] - 1) * 100 if len(spy_hist) >= 65 else 0
        spy_6m = (spy_current / spy_hist['Close'].iloc[-130] - 1) * 100 if len(spy_hist) >= 130 else 0
    except Exception as e:
        print(f"⚠️ Error fetching SPY: {e}")
        spy_1m = spy_3m = spy_6m = 0

    # Track which tickers need pivot calculation
    calculated_pivots = {}
    failed_tickers = []

    results = []

    print(f"\n🔍 Analyzing {len(df)} watchlist stocks...")

    for idx, row in df.iterrows():
        ticker = row['Ticker']

        # Check if pivot is missing
        pivot_missing = pd.isna(row['Pivot_Price']) or row['Pivot_Price'] == ''
        pivot = None

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            info = stock.info

            if len(hist) < 200:
                failed_tickers.append((ticker, "Insufficient history (< 200 days)"))
                continue

            current = hist['Close'].iloc[-1]
            volume = hist['Volume'].iloc[-1]

            # Calculate pivot if missing
            if pivot_missing:
                recent_high = hist['High'].tail(5).max()
                pivot = round(recent_high + 0.01, 2)
                calculated_pivots[ticker] = pivot
                # Update the dataframe for persistence
                df.at[idx, 'Pivot_Price'] = pivot
            else:
                pivot = float(row['Pivot_Price'])

            # Returns
            ret_1m = (current / hist['Close'].iloc[-20] - 1) * 100
            ret_3m = (current / hist['Close'].iloc[-65] - 1) * 100 if len(hist) >= 65 else 0
            ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100 if len(hist) >= 130 else 0

            # Calculate RS vs SPY
            rs_1m = ret_1m - spy_1m
            rs_3m = ret_3m - spy_3m
            rs_6m = ret_6m - spy_6m

            # Volume ratio vs 50-day average
            avg_volume = hist['Volume'].tail(50).mean()
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

            # MAs
            ma20 = hist['Close'].rolling(20).mean().iloc[-1]
            ma50 = hist['Close'].rolling(50).mean().iloc[-1]
            ma150 = hist['Close'].rolling(150).mean().iloc[-1]
            ma200 = hist['Close'].rolling(200).mean().iloc[-1]

            # 52-week high
            high_52w = hist['Close'].max()
            from_high = ((high_52w - current) / high_52w) * 100

            # Calculate Stage 2 score using shared 7-point system
            score = calculate_stage2_score(hist)

            # ATR
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            # RSI
            rsi = calculate_rsi(hist['Close'])

            # Stop calculation
            recent_low = hist['Low'].tail(10).min()
            stop = max(recent_low, current - 2 * atr)

            # Risk calculation - flag invalid setups
            if pivot <= stop:
                risk = -1  # Invalid: stop would be above pivot
                risk_pct = 999  # Flag as invalid
            else:
                risk = (pivot - stop)
                risk_pct = (risk / pivot) * 100

            # Distance to pivot (positive = below pivot, negative = above/broke out)
            dist_to_pivot = ((pivot - current) / current) * 100

            # Entry attractiveness score using shared function
            entry_score = get_entry_score(score, risk_pct, dist_to_pivot, ret_6m, rs_6m)

            results.append({
                'Ticker': ticker,
                'Current': round(current, 2),
                'Pivot': pivot,
                'Dist_to_Pivot': round(dist_to_pivot, 1),
                'Stop': round(stop, 2),
                'Risk_%': round(risk_pct, 1),
                'Stage2': score,
                '1M': round(ret_1m, 1),
                '3M': round(ret_3m, 1),
                '6M': round(ret_6m, 1),
                'RS_6M': round(rs_6m, 1),
                'From_High': round(from_high, 1),
                'Volume_Ratio': round(volume_ratio, 1),
                'RSI': round(rsi, 1),
                'Entry_Score': entry_score,
                'Sector': info.get('sector', 'Unknown'),
                'Industry': info.get('industry', 'Unknown')
            })

        except Exception as e:
            failed_tickers.append((ticker, str(e)))
            print(f"⚠️ {ticker}: {e}")

    # Persist calculated pivots back to watchlist
    if calculated_pivots:
        df.to_csv(WATCHLIST_PATH, index=False)
        print(f"\n💾 Auto-calculated and saved pivots for {len(calculated_pivots)} tickers: {', '.join(calculated_pivots.keys())}")

    # Report failures
    if failed_tickers:
        print(f"\n⚠️ Failed to analyze {len(failed_tickers)} tickers:")
        for ticker, reason in failed_tickers[:10]:  # Show first 10
            print(f"  - {ticker}: {reason}")
        if len(failed_tickers) > 10:
            print(f"  ... and {len(failed_tickers) - 10} more")

    # Sort by entry score (descending)
    results.sort(key=lambda x: x['Entry_Score'], reverse=True)

    # Generate outputs
    if output_csv:
        generate_csv_output(results)

    if output_html:
        generate_html_output(results)

    # Display console output
    display_console_output(results)

    return results

def display_console_output(results):
    """Display formatted console output."""

    print("\n🎯 WATCHLIST ENTRY RANKINGS — Ranked by Entry Score\n")
    print("=" * 150)

    # Tier 1: Best setups (Score ≥60)
    print("\n**🟢 TIER 1 — BEST ENTRY SETUP (Entry Score ≥60)**\n")
    tier1 = [r for r in results if r['Entry_Score'] >= 60]
    if tier1:
        print(f"{'Ticker':<8} {'QScore':<7} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'S2':<5} {'RS 6M':<10} {'Vol':<8} {'RSI':<8} {'Sector'}")
        print("-" * 150)
        for r in tier1:
            risk_display = f"{r['Risk_%']:.1f}%" if r['Risk_%'] < 999 else "INVALID"
            print(f"{r['Ticker']:<8} {r['Entry_Score']:<6} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {risk_display:<7} {r['Stage2']:<3}/7 {r['RS_6M']:+>8.1f}% {r['Volume_Ratio']:<7.1f}x {r['RSI']:<7.1f} {r['Sector'][:20]}")
    else:
        print("No Tier 1 setups currently")

    # Tier 2: Good setups (Score 40-59)
    print("\n\n**🟡 TIER 2 — GOOD SETUP (Entry Score 40-59)**\n")
    tier2 = [r for r in results if 40 <= r['Entry_Score'] < 60]
    if tier2:
        print(f"{'Ticker':<8} {'QScore':<7} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'S2':<5} {'RS 6M':<10} {'Vol':<8} {'RSI':<8} {'Sector'}")
        print("-" * 150)
        for r in tier2:
            risk_display = f"{r['Risk_%']:.1f}%" if r['Risk_%'] < 999 else "INVALID"
            print(f"{r['Ticker']:<8} {r['Entry_Score']:<6} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {risk_display:<7} {r['Stage2']:<3}/7 {r['RS_6M']:+>8.1f}% {r['Volume_Ratio']:<7.1f}x {r['RSI']:<7.1f} {r['Sector'][:20]}")
    else:
        print("No Tier 2 setups currently")

    # Tier 3: Watch only (Score <40)
    print("\n\n**🔴 TIER 3 — WAIT / MONITOR (Entry Score <40)**\n")
    tier3 = [r for r in results if r['Entry_Score'] < 40]
    if tier3:
        print(f"{'Ticker':<8} {'QScore':<7} {'Price':<10} {'Pivot':<10} {'Dist%':<8} {'Risk%':<8} {'S2':<5} {'RS 6M':<10} {'Vol':<8} {'RSI':<8} {'Sector'}")
        print("-" * 150)
        for r in tier3:
            risk_display = f"{r['Risk_%']:.1f}%" if r['Risk_%'] < 999 else "INVALID"
            print(f"{r['Ticker']:<8} {r['Entry_Score']:<6} ${r['Current']:<9.2f} ${r['Pivot']:<9.2f} {r['Dist_to_Pivot']:<7.1f}% {risk_display:<7} {r['Stage2']:<3}/7 {r['RS_6M']:+>8.1f}% {r['Volume_Ratio']:<7.1f}x {r['RSI']:<7.1f} {r['Sector'][:20]}")
    else:
        print("No Tier 3 setups currently")

    # Summary
    print("\n" + "=" * 150)
    print(f"\n📊 SUMMARY: {len(tier1)} Tier 1 | {len(tier2)} Tier 2 | {len(tier3)} Tier 3 | Total: {len(results)}")

    # Top 3 recommendations
    if results:
        print("\n🎯 TOP 3 RECOMMENDATIONS:")
        for i, r in enumerate(results[:3], 1):
            risk_display = f"{r['Risk_%']:.1f}%" if r['Risk_%'] < 999 else "INVALID"
            tier_emoji = "🟢" if r['Entry_Score'] >= 60 else "🟡" if r['Entry_Score'] >= 40 else "🔴"
            print(f"  {i}. {r['Ticker']} — QScore: {r['Entry_Score']} {tier_emoji} | {r['Dist_to_Pivot']:.1f}% from pivot | {risk_display} risk | S2: {r['Stage2']}/7 | RS: {r['RS_6M']:+.1f}%")

def generate_csv_output(results):
    """Export results to CSV."""
    if not results:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
    csv_path = OUTPUT_DIR / f"watchlist_analysis_{timestamp}.csv"

    df = pd.DataFrame(results)
    # Rename Entry_Score to QScore for CSV output
    df = df.rename(columns={'Entry_Score': 'QScore'})
    df.to_csv(csv_path, index=False)
    print(f"\n💾 CSV exported: {csv_path}")

def generate_html_output(results):
    """Generate HTML report."""
    if not results:
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
    html_path = OUTPUT_DIR / f"watchlist_analysis_{timestamp}.html"

    # Simple HTML template
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Watchlist Analysis — {pd.Timestamp.now().strftime('%Y-%m-%d')}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f8fafc;
            --accent-green: #4ade80;
            --accent-yellow: #facc15;
            --accent-red: #f87171;
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg-primary); color: var(--text-primary); padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: var(--bg-secondary); }}
        .tier1 {{ color: var(--accent-green); }}
        .tier2 {{ color: var(--accent-yellow); }}
        .tier3 {{ color: var(--accent-red); }}
        .invalid {{ color: #ef4444; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🎯 Watchlist Analysis — {pd.Timestamp.now().strftime('%Y-%m-%d')}</h1>

    <h2 class="tier1">🟢 Tier 1 (Entry Score ≥60)</h2>
    <table>
        <tr><th>Ticker</th><th>QScore</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>RS 6M</th><th>Vol</th><th>RSI</th><th>Sector</th></tr>
        {''.join(f'<tr class="tier1"><td>{r["Ticker"]}</td><td>{r["Entry_Score"]}</td><td>${r["Current"]:.2f}</td><td>${r["Pivot"]:.2f}</td><td>{r["Dist_to_Pivot"]:.1f}%</td><td>{(f"{r["Risk_%"]:.1f}%" if r["Risk_%"] < 999 else "<span class=\\'invalid\\'>INVALID</span>")}</td><td>{r["Stage2"]}/7</td><td>{r["RS_6M"]:+.1f}%</td><td>{r["Volume_Ratio"]:.1f}x</td><td>{r["RSI"]:.1f}</td><td>{r["Sector"]}</td></tr>' for r in results if r['Entry_Score'] >= 60)}
    </table>

    <h2 class="tier2">🟡 Tier 2 (Entry Score 40-59)</h2>
    <table>
        <tr><th>Ticker</th><th>QScore</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>RS 6M</th><th>Vol</th><th>RSI</th><th>Sector</th></tr>
        {''.join(f'<tr class="tier2"><td>{r["Ticker"]}</td><td>{r["Entry_Score"]}</td><td>${r["Current"]:.2f}</td><td>${r["Pivot"]:.2f}</td><td>{r["Dist_to_Pivot"]:.1f}%</td><td>{(f"{r["Risk_%"]:.1f}%" if r["Risk_%"] < 999 else "<span class=\\'invalid\\'>INVALID</span>")}</td><td>{r["Stage2"]}/7</td><td>{r["RS_6M"]:+.1f}%</td><td>{r["Volume_Ratio"]:.1f}x</td><td>{r["RSI"]:.1f}</td><td>{r["Sector"]}</td></tr>' for r in results if 40 <= r['Entry_Score'] < 60)}
    </table>

    <h2 class="tier3">🔴 Tier 3 (Entry Score <40)</h2>
    <table>
        <tr><th>Ticker</th><th>QScore</th><th>Price</th><th>Pivot</th><th>Dist%</th><th>Risk%</th><th>S2</th><th>RS 6M</th><th>Vol</th><th>RSI</th><th>Sector</th></tr>
        {''.join(f'<tr class="tier3"><td>{r["Ticker"]}</td><td>{r["Entry_Score"]}</td><td>${r["Current"]:.2f}</td><td>${r["Pivot"]:.2f}</td><td>{r["Dist_to_Pivot"]:.1f}%</td><td>{(f"{r["Risk_%"]:.1f}%" if r["Risk_%"] < 999 else "<span class=\\'invalid\\'>INVALID</span>")}</td><td>{r["Stage2"]}/7</td><td>{r["RS_6M"]:+.1f}%</td><td>{r["Volume_Ratio"]:.1f}x</td><td>{r["RSI"]:.1f}</td><td>{r["Sector"]}</td></tr>' for r in results if r['Entry_Score'] < 40)}
    </table>
</body>
</html>"""

    with open(html_path, 'w') as f:
        f.write(html_content)
    print(f"💾 HTML exported: {html_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze watchlist for entry setups')
    parser.add_argument('--csv', action='store_true', help='Export results to CSV')
    parser.add_argument('--html', action='store_true', help='Export results to HTML')
    args = parser.parse_args()

    analyze_watchlist(output_csv=args.csv, output_html=args.html)
