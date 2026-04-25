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

import yfinance as yf

from traderlib import calculate_stage2_score

# Full ETF universe from comprehensive CSV
ETFS = [
    ("USO", "Oil (commodity)"),
    ("DBE", "Energy"),
    ("OIH", "Oil Services"),
    ("XOP", "E&P (Exploration)"),
    ("EWY", "South Korea"),
    ("PDBC", "Opt Yield Commodities"),
    ("FCG", "Natural Gas"),
    ("DBC", "Broad Commodities"),
    ("XLE", "Energy"),
    ("XTL", "Telecom"),
    ("CRAK", "Refiners"),
    ("SLV", "Silver"),
    ("EWZ", "Brazil"),
    ("BDRY", "Dry Bulk Shipping"),
    ("FAN", "Wind Energy"),
    ("REMX", "Rare Earths"),
    ("LIT", "Lithium/Battery"),
    ("SIL", "Silver Miners"),
    ("XBI", "Biotech"),
    ("COPX", "Copper Miners"),
    ("SOXX", "PHLX Semiconductor"),
    ("DBP", "Precious Metals"),
    ("GDX", "Gold Miners"),
    ("AMLP", "MLPs/Midstream"),
    ("TAN", "Solar Energy"),
    ("GDXJ", "Junior Gold Miners"),
    ("RNRG", "Renewables"),
    ("EWT", "Taiwan"),
    ("GLD", "Gold"),
    ("SMH", "Semiconductors"),
    ("ICLN", "Clean Energy"),
    ("PPLT", "Platinum"),
    ("XLB", "Materials"),
    ("VLUE", "Value Factor"),
    ("DBB", "Base Metals"),
    ("XME", "Metals & Mining"),
    ("PBJ", "Food & Beverage"),
    ("IFRA", "Infrastructure"),
    ("CARZ", "Auto"),
    ("XTN", "Transportation"),
    ("EWU", "UK"),
    ("GRID", "Smart Grid"),
    ("IBB", "Nasdaq Biotech"),
    ("PPH", "Pharma"),
    ("EWJ", "Japan"),
    ("XLU", "Utilities"),
    ("PALL", "Palladium"),
    ("IWN", "Small Cap Value"),
    ("DBA", "Agriculture"),
    ("XPH", "Pharma (alt)"),
    ("PAVE", "Infrastructure"),
    ("XAR", "Aerospace/Defense"),
    ("QCLN", "Clean Energy/Transport"),
    ("XLP", "Consumer Staples"),
    ("XLI", "Industrials"),
    ("EEM", "Emerging Markets"),
    ("IWD", "Value (Russell)"),
    ("URA", "Uranium"),
    ("KRE", "Regional Banks"),
    ("EFA", "Developed Markets"),
    ("SCHH", "REITs"),
    ("PSR", "Active REITs"),
    ("ITA", "Aerospace/Defense"),
    ("SPLV", "Low Volatility"),
    ("IYT", "Transportation"),
    ("VGK", "Europe"),
    ("IWM", "Russell 2000"),
    ("FXR", "Transportation/Logistics"),
    ("KBE", "Banks"),
    ("RGI", "Industrials Equal Weight"),
    ("MUB", "Municipal Bonds"),
    ("SHY", "1-3 Year Treasuries"),
    ("REZ", "Residential REITs"),
    ("JNK", "Junk Bonds"),
    ("XLRE", "Real Estate"),
    ("HYG", "High Yield"),
    ("TIP", "TIPS"),
    ("VNQ", "REITs Broad"),
    ("AGG", "Total Bond Market"),
    ("RSP", "S&P 500 Equal Weight"),
    ("BND", "Total Bond Market"),
    ("IYR", "US Real Estate"),
    ("IEF", "7-10 Year Treasuries"),
    ("EMB", "Emerging Market Bonds"),
    ("LQD", "IG Corporate"),
    ("REM", "mREITs"),
    ("MORT", "Mortgage REITs"),
    ("TLT", "20+ Year Treasuries"),
    ("XLV", "Health Care"),
    ("USMV", "Min Volatility"),
    ("DIA", "Dow Jones"),
    ("QUAL", "Quality Factor"),
    ("IWO", "Small Cap Growth"),
    ("VTI", "Total Stock Market"),
    ("SPY", "S&P 500"),
    ("MTUM", "Momentum Factor"),
    ("PEJ", "Leisure/Entertainment"),
    ("QQQ", "NASDAQ 100"),
    ("JETS", "Airlines"),
    ("XLC", "Communication Services"),
    ("XLK", "Technology"),
    ("IAI", "Broker-Dealers"),
    ("EWG", "Germany"),
    ("XHE", "Health Care Equipment"),
    ("KIE", "Insurance"),
    ("AIQ", "Artificial Intelligence"),
    ("XRT", "Retail"),
    ("RYF", "Financial Services"),
    ("XLF", "Financials"),
    ("HACK", "Cybersecurity"),
    ("ARKG", "Genomics"),
    ("BIZD", "BDCs"),
    ("IWF", "Growth Factor"),
    ("HOMZ", "Housing"),
    ("BOTZ", "Robotics/Automation"),
    ("XLY", "Consumer Discretionary"),
    ("FXI", "China"),
    ("XHB", "Homebuilders"),
    ("INDA", "India"),
    ("FDN", "Internet"),
    ("CIBR", "Cybersecurity (alt)"),
    ("IHI", "Medical Devices"),
    ("IHF", "Healthcare Providers"),
    ("UNG", "Natural Gas (commodity)"),
    ("ITB", "Home Construction"),
    ("SKYY", "Cloud Computing"),
    ("BETZ", "Betting/Gaming"),
    ("IBUY", "Online Retail"),
    ("WCLD", "Cloud Computing (alt)"),
    ("SOCL", "Social Media"),
    ("IGV", "Software"),
]

def calculate_stage2_score_from_hist(hist):
    """Calculate Stage 2 score using shared 10-point system."""
    return calculate_stage2_score(hist)

def run_comprehensive_scan(top_n: int = 15):
    """Run comprehensive sector scan"""

    scan_date = datetime.now().strftime('%Y-%m-%d')
    print(f"🔍 Running comprehensive sector scan for {scan_date}...")
    print(f"   Scanning {len(ETFS)} ETFs...")
    
    results = []
    
    for ticker, name in ETFS:
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
            'Ticker', 'Name', '1W', '1M', '3M', '6M',
            'Above_20', 'Above_50', 'Above_200', 'From_High',
            'Stage2_Score', 'Rank_Score', 'Rank_6M', 'Rank_3M', 'Rank_1M', 'Overall_Rank'
        ])
        
        for row in sorted_by_score:
            writer.writerow([
                row['ticker'],
                row['name'],
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
