import yfinance as yf
import datetime

# Futures and key tickers
futures = ['ES=F', 'NQ=F', 'RTY=F', 'CL=F', 'GC=F', 'BTC-USD', 'ETH-USD', '^VIX']

print("=== OVERNIGHT FUTURES & INDICES ===")
for t in futures:
    try:
        ticker = yf.Ticker(t)
        hist = ticker.history(period='5d')
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            curr_close = hist['Close'].iloc[-1]
            change = curr_close - prev_close
            pct = (change / prev_close) * 100
            print(f"{t}: {curr_close:.2f} ({change:+.2f}, {pct:+.2f}%)")
        else:
            print(f"{t}: {hist['Close'].iloc[-1]:.2f} (limited data)")
    except Exception as e:
        print(f"{t}: Error - {e}")

print()
print("=== SPY/QQQ TECHNICAL ===")
for etf in ['SPY', 'QQQ']:
    try:
        hist = yf.Ticker(etf).history(period='3mo')
        if len(hist) > 0:
            close = hist['Close'].iloc[-1]
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            above_20 = "Yes" if close > sma20 else "No"
            above_50 = "Yes" if close > sma50 else "No"
            print(f"{etf}: ${close:.2f} | 20SMA: ${sma20:.2f} | 50SMA: ${sma50:.2f} | Above 20SMA: {above_20} | Above 50SMA: {above_50}")
    except Exception as e:
        print(f"{etf}: Error - {e}")

print()
print("=== A-TIER WATCHLIST CHECK ===")
watchlist = ['LITE', 'CIEN', 'FTI', 'DOW', 'SQM']
for t in watchlist:
    try:
        ticker = yf.Ticker(t)
        hist = ticker.history(period='3mo')
        info = ticker.info
        if len(hist) > 0:
            close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((close - prev_close) / prev_close) * 100
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma50 = hist['Close'].rolling(50).mean().iloc[-1]
            volume = hist['Volume'].iloc[-1]
            avg_vol = hist['Volume'].rolling(50).mean().iloc[-1]
            vol_ratio = volume / avg_vol if avg_vol > 0 else 0

            print(f"{t}: ${close:.2f} ({change_pct:+.2f}%) | 20SMA: ${sma20:.2f} | 50SMA: ${sma50:.2f} | Vol: {vol_ratio:.1f}x avg")
    except Exception as e:
        print(f"{t}: Error - {e}")
