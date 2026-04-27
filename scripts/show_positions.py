#!/usr/bin/env python3
import yfinance as yf
import json
from datetime import datetime

# Open positions
tickers = ['AMD','AROC','ASX','ATI','AVGO','CAT','JAZZ','KEYS','MU','NPO','NEE','APH','NFG','FER']

print('Fetching current prices...\n')

try:
    data = yf.download(tickers, period='1d', progress=False)
    
    if len(tickers) == 1:
        current_prices = {tickers[0]: float(data['Close'].iloc[-1])}
    else:
        current_prices = {k: float(v) for k, v in data['Close'].iloc[-1].to_dict().items()}
except Exception as e:
    print(f"Error fetching prices: {e}")
    current_prices = {}

# Read positions
with open('/Users/mintmrlion/.openclaw/workspaces/trader/data/paper_positions.json', 'r') as f:
    positions = json.load(f)

print('=' * 70)
print(f'OPEN POSITIONS — {len(positions)} Active | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
print('=' * 70)
print()

total_unrealized = 0.0
total_invested = 0.0

for ticker, pos in positions.items():
    entry = float(pos['entry_price'])
    shares = int(pos['shares'])
    stop = float(pos['stop_price'])
    target = float(pos.get('target_price', entry * 1.1))
    initial_risk = float(pos.get('initial_risk', 0))
    
    current = current_prices.get(ticker, entry)
    if ticker not in current_prices:
        # Try to fetch individually
        try:
            ticker_data = yf.Ticker(ticker).history(period='1d')
            current = float(ticker_data['Close'].iloc[-1])
            current_prices[ticker] = current
        except:
            current = entry
    
    invested = entry * shares
    market_value = current * shares
    unrealized = (current - entry) * shares
    pct_change = ((current - entry) / entry) * 100 if entry else 0
    r_multiple = unrealized / initial_risk if initial_risk else 0
    
    total_unrealized += unrealized
    total_invested += invested
    
    stop_type = pos.get('current_stop_type', 'HARD')
    
    emoji = '🟢' if unrealized > 0 else '🔴' if unrealized < 0 else '⚪'
    
    print(f"{emoji} {ticker:5} | Entry: ${entry:,.2f} → Current: ${current:,.2f} | Shares: {shares}")
    print(f"   P&L: ${unrealized:+,.2f} ({pct_change:+.1f}%) | R: {r_multiple:+.1f}R | Stop: ${stop:,.2f} [{stop_type}]")
    print()

# Calculate today's realized P&L from closed trades
today_realized = 0.0
today = datetime.now().strftime('%Y-%m-%d')
try:
    with open('/Users/mintmrlion/.openclaw/workspaces/trader/data/paper_trades.jsonl', 'r') as f:
        for line in f:
            try:
                trade = json.loads(line.strip())
                if trade.get('timestamp', '')[:10] == today and trade.get('event') == 'EXIT':
                    pnl = trade.get('realized_pnl', 0)
                    if pnl:
                        today_realized += pnl
            except:
                pass
except:
    pass

print('=' * 70)
print(f"TOTAL INVESTED:   ${total_invested:,.2f}")
print(f"UNREALIZED P&L:   ${total_unrealized:+,.2f}  (Open positions vs entry)")
print(f"PORTFOLIO VALUE:  ${total_invested + total_unrealized:,.2f}")
print('-' * 70)
print(f"REALIZED P&L:     ${today_realized:+,.2f}  (Closed trades today)")
print('=' * 70)
print()
print("Note: 'Daily P&L' in broker dashboards = Realized + Unrealized")
