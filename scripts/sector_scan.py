#!/usr/bin/env python3
"""
Sector Scan - Run daily before pre-market report
Saves sector performance + factor ETF data to scans/YYYY-MM-DD_sector_scan.csv
"""

import yfinance as yf
from datetime import datetime
from pathlib import Path

def run_sector_scan():
    """Scan all sectors and save results"""
    
    scan_date = datetime.now().strftime('%Y-%m-%d')
    print(f"🔍 Running sector scan for {scan_date}...")
    
    # Sector ETFs
    sectors = {
        "XLK": "Technology",
        "XLC": "Comm Services",
        "XLRE": "Real Estate",
        "XLF": "Financials",
        "XLB": "Materials",
        "XLI": "Industrials",
        "XLV": "Health Care",
        "XLY": "Consumer Disc",
        "XLU": "Utilities",
        "XLP": "Staples",
        "XLE": "Energy"
    }
    
    # Factor ETFs
    factors = {
        "MTUM": "Momentum",
        "IWF": "Growth",
        "QUAL": "Quality",
        "VLUE": "Value",
        "SPLV": "Low Vol",
        "IWD": "Value (large)",
        "IWM": "Small Cap"
    }
    
    results = {
        "scan_date": scan_date,
        "scan_time": datetime.now().isoformat(),
        "sectors": {},
        "factors": {},
        "spy_benchmark": {}
    }
    
    # Get SPY benchmark
    try:
        spy = yf.Ticker("SPY").history(period="5d")
        if len(spy) >= 2:
            spy_1w = ((spy['Close'].iloc[-1] / spy['Close'].iloc[0]) - 1) * 100
            results["spy_benchmark"] = {
                "1_week_return": round(spy_1w, 2),
                "current_price": round(spy['Close'].iloc[-1], 2)
            }
    except Exception as e:
        print(f"  SPY error: {e}")
    
    # Scan sectors
    print("  Scanning sectors...")
    for ticker, name in sectors.items():
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if len(data) >= 2:
                # Returns
                ret_1w = ((data['Close'].iloc[-1] / data['Close'].iloc[0]) - 1) * 100
                
                # Moving averages
                hist = yf.Ticker(ticker).history(period="6mo")
                close = hist['Close'].iloc[-1]
                ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                ma200 = hist['Close'].rolling(200).mean().iloc[-1]
                
                vs_spy = ret_1w - results["spy_benchmark"].get("1_week_return", 0)
                
                results["sectors"][ticker] = {
                    "name": name,
                    "price": round(close, 2),
                    "1_week_return": round(ret_1w, 2),
                    "vs_spy": round(vs_spy, 2),
                    "above_50ma": bool(close > ma50),
                    "above_200ma": bool(close > ma200)
                }
                print(f"    {ticker} ({name}): {ret_1w:+.2f}%")
        except Exception as e:
            print(f"    {ticker} error: {e}")
    
    # Scan factors
    print("  Scanning factors...")
    for ticker, name in factors.items():
        try:
            data = yf.Ticker(ticker).history(period="5d")
            spy = yf.Ticker("SPY").history(period="5d")
            if len(data) >= 2 and len(spy) >= 2:
                ret = ((data['Close'].iloc[-1] / data['Close'].iloc[0]) - 1) * 100
                spy_ret = ((spy['Close'].iloc[-1] / spy['Close'].iloc[0]) - 1) * 100
                vs_spy = ret - spy_ret
                
                status = "LEADING" if vs_spy > 0.5 else "LAGGING" if vs_spy < -0.5 else "NEUTRAL"
                
                results["factors"][ticker] = {
                    "name": name,
                    "1_week_return": round(ret, 2),
                    "vs_spy": round(vs_spy, 2),
                    "status": status
                }
                print(f"    {ticker} ({name}): {ret:+.2f}% [{status}]")
        except Exception as e:
            print(f"    {ticker} error: {e}")
    
    # Sort sectors by return
    sorted_sectors = sorted(
        results["sectors"].items(),
        key=lambda x: x[1]["1_week_return"],
        reverse=True
    )
    results["sector_ranking"] = [ticker for ticker, _ in sorted_sectors]
    results["leading_sectors"] = results["sector_ranking"][:3]
    results["lagging_sectors"] = results["sector_ranking"][-3:]
    
    # Save to CSV
    output_file = Path(f"/Users/mintmrlion/.openclaw/workspaces/trader/scans/{scan_date}_sector_scan.csv")
    
    # Write sectors to CSV
    with open(output_file, 'w') as f:
        f.write("ticker,name,price,1_week_return,vs_spy,above_50ma,above_200ma\n")
        for ticker, data in sorted_sectors:
            f.write(f"{ticker},{data['name']},{data['price']},{data['1_week_return']},{data['vs_spy']},{data['above_50ma']},{data['above_200ma']}\n")
        
        # Write factors
        f.write("\nfactor_ticker,factor_name,1_week_return,vs_spy,status\n")
        for ticker, data in results["factors"].items():
            f.write(f"{ticker},{data['name']},{data['1_week_return']},{data['vs_spy']},{data['status']}\n")
        
        # Write summary
        f.write(f"\nspy_benchmark,1_week_return,{results['spy_benchmark'].get('1_week_return', 0)}\n")
        f.write(f"leading_sectors,{'|'.join(results['leading_sectors'])}\n")
        f.write(f"lagging_sectors,{'|'.join(results['lagging_sectors'])}\n")
    
    print(f"\n✅ Scan complete. Saved to: {output_file}")
    print(f"   Leading: {', '.join(results['leading_sectors'])}")
    print(f"   Lagging: {', '.join(results['lagging_sectors'])}")
    
    return results

if __name__ == "__main__":
    run_sector_scan()
