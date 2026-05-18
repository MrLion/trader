#!/usr/bin/env python3
"""
Comprehensive Sector Scan — 148 ETFs across 8 categories with full ranking.
Saves to scans/YYYY-MM-DD_sector_scan.csv
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

import yaml
import yfinance as yf
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from traderlib import calculate_stage2_score

# Load ETF universe from categorized config file
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "sector_etfs.yaml"
with open(_CONFIG_PATH) as _f:
    _ETF_CONFIG = yaml.safe_load(_f)

ETFS = []
for _cat_key, _cat_data in _ETF_CONFIG["categories"].items():
    _label = _cat_data["label"]
    for _etf in _cat_data["etfs"]:
        ETFS.append((_etf["ticker"], _etf["name"], _label))

def calculate_stage2_score_from_hist(hist):
    """Calculate Stage 2 score using shared 10-point system."""
    return calculate_stage2_score(hist)

def run_comprehensive_scan(top_n: int = 10):
    """Run comprehensive sector scan"""

    scan_date = datetime.now().strftime('%Y-%m-%d')
    print(f"Scanning {len(ETFS)} ETFs across 8 categories...")

    results = []
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Starting...", total=len(ETFS))

        for ticker, name, category in ETFS:
            progress.update(task, description=f"Fetching {ticker}...")
            try:
                hist = yf.Ticker(ticker).history(period="1y")

                if len(hist) < 130:
                    progress.advance(task)
                    continue

                close = hist['Close'].iloc[-1]
                high_52w = hist['Close'].max()
                from_high = ((high_52w - close) / high_52w) * 100

                ret_1w = ((close / hist['Close'].iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0
                ret_1m = ((close / hist['Close'].iloc[-20]) - 1) * 100 if len(hist) >= 20 else 0
                ret_3m = ((close / hist['Close'].iloc[-65]) - 1) * 100 if len(hist) >= 65 else 0
                ret_6m = ((close / hist['Close'].iloc[-130]) - 1) * 100 if len(hist) >= 130 else 0

                above_20 = close > hist['Close'].rolling(20).mean().iloc[-1] if len(hist) >= 20 else False
                above_50 = close > hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else False
                above_200 = close > hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else False

                stage2_score = calculate_stage2_score(hist)

                results.append({
                    'ticker': ticker,
                    'name': name,
                    'category': category,
                    'ret_1w': ret_1w,
                    'ret_1m': ret_1m,
                    'ret_3m': ret_3m,
                    'ret_6m': ret_6m,
                    'above_20': above_20,
                    'above_50': above_50,
                    'above_200': above_200,
                    'from_high': from_high,
                    'stage2_score': stage2_score
                })
            except Exception:
                failed += 1

            progress.advance(task)
    
    if len(results) == 0:
        print("No results found!")
        return
    
    # Calculate rankings
    for timeframe in ['6m', '3m', '1m', '1w']:
        sorted_by = sorted(results, key=lambda x: x[f'ret_{timeframe}'], reverse=True)
        ranks = {row['ticker']: i+1 for i, row in enumerate(sorted_by)}
        for row in results:
            row[f'rank_{timeframe}'] = ranks[row['ticker']]
    
    # Calculate rank score (weighted average)
    for row in results:
        row['rank_score'] = (
            row['rank_6m'] * 0.4 +
            row['rank_3m'] * 0.3 +
            row['rank_1m'] * 0.2 +
            row['rank_1w'] * 0.1
        )
    
    # Calculate overall rank
    sorted_by_score = sorted(results, key=lambda x: x['rank_score'])
    for i, row in enumerate(sorted_by_score):
        row['overall_rank'] = i + 1
    
    # Save to CSV
    output_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{scan_date}_sector_scan.csv")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Ticker', 'Name', 'Category', '1W', '1M', '3M', '6M',
            'Above_20', 'Above_50', 'Above_200', 'From_High',
            'Stage2_Score', 'Rank_Score', 'Rank_6M', 'Rank_3M', 'Rank_1M', 'Overall_Rank'
        ])
        
        for row in sorted_by_score:
            writer.writerow([
                row['ticker'],
                row['name'],
                row['category'],
                f"{row['ret_1w']:.2f}",
                f"{row['ret_1m']:.2f}",
                f"{row['ret_3m']:.2f}",
                f"{row['ret_6m']:.2f}",
                row['above_20'],
                row['above_50'],
                row['above_200'],
                f"{row['from_high']:.2f}",
                row['stage2_score'],
                f"{row['rank_score']:.2f}",
                row['rank_6m'],
                row['rank_3m'],
                row['rank_1m'],
                row['overall_rank']
            ])
    
    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n✅ Scanned {len(results)}/{len(ETFS)} ETFs{f' ({failed} failed)' if failed else ''}")
    print(f"   Output: {output_file}")

    def _row_str(r):
        return (
            f"{r['overall_rank']:<3} "
            f"{r['ticker']:<6} "
            f"{r['category']:<16} "
            f"{r['ret_1w']:>+7.1f}% "
            f"{r['ret_1m']:>+7.1f}% "
            f"{r['ret_3m']:>+7.1f}% "
            f"{r['ret_6m']:>+7.1f}% "
            f"{r['rank_score']:>6.1f} "
            f"{r['stage2_score']:>3}"
        )

    hdr = (
        f"{'#':<3} "
        f"{'Ticker':<6} "
        f"{'Category':<16} "
        f"{'1W':>7} "
        f"{'1M':>7} "
        f"{'3M':>7} "
        f"{'6M':>7} "
        f"{'Score':>6} "
        f"{'S2':>3}"
    )

    # Overall TOP N
    print(f"\n🏆 TOP {top_n} BY OVERALL RANK:")
    print(hdr)
    print("─" * len(hdr))
    for row in sorted_by_score[:top_n]:
        print(_row_str(row))

    # TOP 3 per category
    print(f"\n🏅 TOP 3 BY CATEGORY:")
    seen_categories = []
    for row in sorted_by_score:
        if row['category'] not in seen_categories:
            seen_categories.append(row['category'])
    for category in seen_categories:
        cat_rows = [r for r in sorted_by_score if r['category'] == category]
        count = len(cat_rows)
        print(f"\n  {category} ({count}):")
        for r in cat_rows[:3]:
            print(f"  {_row_str(r)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comprehensive sector scan")
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top-ranked ETFs to display (default: 10)",
    )
    args = parser.parse_args()
    run_comprehensive_scan(top_n=args.top)
