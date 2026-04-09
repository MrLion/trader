import pandas as pd
import yfinance as yf
from pathlib import Path
import os

def download_fixture(ticker, days=252, filename=None):
    if filename is None:
        filename = f"{ticker.lower()}_{days}days.csv"

    print(f"Downloading {ticker} for {days} days...")
    stock = yf.Ticker(ticker)
    hist = stock.history(period=f"{days}d")

    if hist.empty:
        print(f"❌ Failed to download {ticker}")
        return False

    path = Path("tests/fixtures") / filename
    hist.to_csv(path)
    print(f"✅ Saved to {path}")
    return True

def create_synthetic_fixture(filename, rows=100, pattern="flat"):
    print(f"Creating synthetic fixture: {filename} ({pattern})")
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=rows, freq='D')

    if pattern == "flat":
        close = np.full(rows, 100.0)
    elif pattern == "volatile":
        close = 100.0 + np.cumsum(np.random.randn(rows) * 5)
    elif pattern == "insufficient":
        rows = 20 # Force < 30
        dates = pd.date_range(end=pd.Timestamp.now(), periods=rows, freq='D')
        close = np.linspace(100, 110, rows)
    else:
        close = np.linspace(100, 150, rows)

    df = pd.DataFrame({
        'Open': close, 'High': close * 1.01, 'Low': close * 0.99, 'Close': close, 'Volume': 1000000
    }, index=dates)

    path = Path("tests/fixtures") / filename
    df.to_csv(path)
    print(f"✅ Saved to {path}")

if __name__ == "__main__":
    # Real data
    download_fixture("AAPL", 365, "aapl_6months.csv")
    download_fixture("SPY", 365, "spy_6months.csv")

    # Synthetic edge cases
    create_synthetic_fixture("flat_stock.csv", pattern="flat")
    create_synthetic_fixture("volatile_stock.csv", pattern="volatile")
    create_synthetic_fixture("insufficient_data.csv", pattern="insufficient")
