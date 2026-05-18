#!/usr/bin/env python3
"""
Comprehensive Sector Scan - 131 ETFs with full ranking system
Saves to scans/YYYY-MM-DD_sector_scan.csv
Updated with full ETF universe from master CSV
Shows TOP 15 results
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

import yaml
import yfinance as yf

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

def run_comprehensive_scan(top_n: int = 15):
    """Run comprehensive sector scan"""

    scan_date = datetime.now().strftime('%Y-%m-%d')
    print(f"🔍 Running comprehensive sector scan for {scan_date}...")
    print(f"   Scanning {len(ETFS)} ETFs...")
    
    results = []
    
    for ticker, name, category in ETFS:
        try:
            # Get full history
            hist = yf.Ticker(ticker).history(period="1y")
            
            if len(hist) < 130:
                continue
                
            close = hist['Close'].iloc[-1]
            high_52w = hist['Close'].max()
            from_high = ((high_52w - close) / high_52w) * 100
            
            # Calculate returns
            ret_1w = ((close / hist['Close'].iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0
            ret_1m = ((close / hist['Close'].iloc[-20]) - 1) * 100 if len(hist) >= 20 else 0
            ret_3m = ((close / hist['Close'].iloc[-65]) - 1) * 100 if len(hist) >= 65 else 0
            ret_6m = ((close / hist['Close'].iloc[-130]) - 1) * 100 if len(hist) >= 130 else 0
            
            # Moving averages
            above_20 = close > hist['Close'].rolling(20).mean().iloc[-1] if len(hist) >= 20 else False
            above_50 = close > hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else False
            above_200 = close > hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else False
            
            # Calculate full Stage 2 score using shared function
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
            
            print(f"  ✓ {ticker}")
            
        except Exception as e:
            print(f"  ✗ {ticker}: {str(e)[:30]}")
            continue
    
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
    
    print(f"\n✅ Scan complete!")
    print(f"   Saved: {output_file}")
    print(f"   ETFs scanned: {len(results)}")
    print(f"\n🏆 TOP {top_n} BY OVERALL RANK:")
    for row in sorted_by_score[:top_n]:
        print(f"   #{row['overall_rank']} {row['ticker']} ({row['name']}): {row['ret_6m']:+.1f}% (6M)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comprehensive sector scan")
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top-ranked ETFs to display (default: 15)",
    )
    args = parser.parse_args()
    run_comprehensive_scan(top_n=args.top)
