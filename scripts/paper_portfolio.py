#!/usr/bin/env python3
"""CLI tool for paper trading portfolio management and monitoring."""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / 'lib'))

# Data paths
DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
POSITIONS_FILE = DATA_DIR / 'paper_positions.json'
ACCOUNT_FILE = DATA_DIR / 'paper_account.json'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'


def load_json_file(filepath: Path) -> Optional[Dict]:
    """Load JSON file if it exists."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def load_trades(limit: int = 100) -> List[Dict]:
    """Load recent trades from JSONL file."""
    if not TRADES_FILE.exists():
        return []

    trades = []
    try:
        with open(TRADES_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    except Exception:
        pass

    return trades[-limit:] if trades else []


def format_currency(value: float) -> str:
    """Format currency with sign."""
    return f"${value:,.2f}"


def format_pct(value: float) -> str:
    """Format percentage with sign."""
    color = "🟢" if value >= 0 else "🔴"
    return f"{color} {value:+.2f}%"


def cmd_status(args):
    """Show current account and market status."""
    account = load_json_file(ACCOUNT_FILE)
    positions = load_json_file(POSITIONS_FILE)

    if not account:
        print("❌ No account data found. Engine may not be running.")
        return

    print("\n" + "=" * 60)
    print("📊 PAPER TRADING ACCOUNT STATUS")
    print("=" * 60)

    print(f"\n💰 CAPITAL")
    print(f"   Initial: {format_currency(account.get('initial_capital', 0))}")
    print(f"   Cash:    {format_currency(account.get('cash', 0))}")
    print(f"   Equity:  {format_currency(account.get('equity', 0))}")

    pnl = account.get('equity', 0) - account.get('initial_capital', 0)
    pnl_pct = (pnl / account.get('initial_capital', 1)) * 100
    print(f"   P&L:     {format_currency(pnl)} ({format_pct(pnl_pct)})")

    print(f"\n📈 DAILY PERFORMANCE")
    day_pnl = account.get('day_pnl', 0)
    day_return = account.get('day_return_pct', 0)
    print(f"   Day P&L: {format_currency(day_pnl)} ({format_pct(day_return)})")

    print(f"\n📊 ACTIVITY")
    print(f"   Open Positions: {account.get('open_positions', 0)}")
    print(f"   Entries Today:  {account.get('entries_today', 0)}")
    print(f"   Total Trades:   {account.get('trade_count', 0)}")

    if positions:
        print(f"\n📋 OPEN POSITIONS ({len(positions)})")
        print("-" * 60)
        for ticker, pos in positions.items():
            entry = pos.get('entry_price', 0)
            shares = pos.get('shares', 0)
            stop = pos.get('stop_price', 0)
            stop_type = pos.get('current_stop_type', 'HARD')
            sector = pos.get('sector', 'Unknown')

            print(f"   {ticker:6} | {sector[:12]:12} | {shares:4} shares | "
                  f"Entry: ${entry:.2f} | Stop: ${stop:.2f} ({stop_type})")

    # Last update
    ts = account.get('timestamp')
    if ts:
        print(f"\n🕐 Last Update: {ts}")


def cmd_live(args):
    """Show real-time position values."""
    import yfinance as yf

    positions = load_json_file(POSITIONS_FILE)
    account = load_json_file(ACCOUNT_FILE)

    if not positions:
        print("📭 No open positions")
        return

    print("\n" + "=" * 80)
    print("📈 LIVE POSITIONS (Fetching current prices...)")
    print("=" * 80)
    print(f"{'Ticker':<8} {'Shares':<8} {'Entry':<10} {'Current':<10} "
          f"{'P&L $':<12} {'P&L %':<10} {'Stop':<10} {'Type':<10} {'R'}")
    print("-" * 80)

    total_pnl = 0
    total_value = 0

    for ticker, pos in positions.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m")

            if len(hist) == 0:
                print(f"{ticker:<8} <no data>")
                continue

            current = hist['Close'].iloc[-1]
            entry = pos.get('entry_price', 0)
            shares = pos.get('shares', 0)
            stop = pos.get('stop_price', 0)
            stop_type = pos.get('current_stop_type', 'HARD')
            initial_risk = pos.get('initial_risk', 1)

            position_pnl = (current - entry) * shares
            position_value = current * shares
            pnl_pct = ((current / entry) - 1) * 100
            r_multiple = position_pnl / initial_risk if initial_risk > 0 else 0

            total_pnl += position_pnl
            total_value += position_value

            emoji = "🟢" if position_pnl >= 0 else "🔴"
            print(f"{emoji} {ticker:<5} {shares:<8} ${entry:<9.2f} ${current:<9.2f} "
                  f"${position_pnl:<11,.2f} {pnl_pct:+.2f}%    ${stop:<9.2f} {stop_type:<9} {r_multiple:+.2f}")

        except Exception as e:
            print(f"{ticker:<8} Error: {e}")

    print("-" * 80)
    print(f"{'TOTAL':<8} {'':<8} {'':<10} {'':<10} "
          f"${total_pnl:<11,.2f}")

    if account:
        cash = account.get('cash', 0)
        total_equity = cash + total_value
        print(f"\n💰 Cash: {format_currency(cash)}")
        print(f"📊 Equity: {format_currency(total_equity)}")


def cmd_today(args):
    """Show today's trades."""
    trades = load_trades(limit=200)

    today = datetime.now().strftime('%Y-%m-%d')
    today_trades = [t for t in trades if t.get('timestamp', '').startswith(today)]

    if not today_trades:
        print(f"📭 No trades recorded for {today}")
        return

    print(f"\n" + "=" * 80)
    print(f"📅 TODAY'S TRADES ({today}) - {len(today_trades)} events")
    print("=" * 80)

    entries = [t for t in today_trades if t.get('event') == 'ENTRY']
    exits = [t for t in today_trades if t.get('event') == 'EXIT']

    if entries:
        print(f"\n🚀 ENTRIES ({len(entries)}):")
        print(f"{'Time':<12} {'Ticker':<8} {'Price':<10} {'Shares':<8} {'Sector'}")
        print("-" * 50)
        for t in entries:
            ts = t.get('timestamp', '')[11:19]
            print(f"{ts:<12} {t.get('ticker', ''):<8} "
                  f"${t.get('entry_price', 0):<9.2f} {t.get('shares', 0):<8}")

    if exits:
        print(f"\n🎯 EXITS ({len(exits)}):")
        print(f"{'Time':<12} {'Ticker':<8} {'Price':<10} {'Reason':<15} {'P&L $':<12} {'R'}")
        print("-" * 70)
        total_realized = 0
        for t in exits:
            ts = t.get('timestamp', '')[11:19]
            pnl = t.get('realized_pnl', 0)
            total_realized += pnl if pnl else 0
            emoji = "🟢" if pnl >= 0 else "🔴"
            print(f"{emoji} {ts:<10} {t.get('ticker', ''):<8} "
                  f"${t.get('exit_price', 0):<9.2f} {t.get('exit_reason', ''):<15} "
                  f"${pnl:<11,.2f}")

        print("-" * 70)
        print(f"Total Realized P&L: {format_currency(total_realized)}")


def cmd_history(args):
    """Show trade history."""
    trades = load_trades(limit=args.limit)

    if not trades:
        print("📭 No trade history found")
        return

    print(f"\n" + "=" * 100)
    print(f"📜 TRADE HISTORY (Last {len(trades)} events)")
    print("=" * 100)
    print(f"{'Timestamp':<20} {'Event':<8} {'Ticker':<8} {'Price':<10} "
          f"{'Reason':<15} {'P&L':<12}")
    print("-" * 100)

    for t in trades:
        ts = t.get('timestamp', '')[:19]
        event = t.get('event', '')
        ticker = t.get('ticker', '')
        price = t.get('exit_price' if event == 'EXIT' else 'entry_price', 0)
        reason = t.get('exit_reason', '') or ''
        pnl = t.get('realized_pnl', 0)

        pnl_str = f"${pnl:,.2f}" if pnl else ""
        emoji = "🚀" if event == 'ENTRY' else "🎯" if pnl and pnl >= 0 else "🛑"

        print(f"{ts:<20} {emoji} {event:<6} {ticker:<8} ${price:<9.2f} "
              f"{reason:<15} {pnl_str:<12}")


def cmd_report(args):
    """Generate performance report."""
    trades = load_trades(limit=1000)
    account = load_json_file(ACCOUNT_FILE)

    if not trades:
        print("📭 No trades to report")
        return

    # Calculate statistics
    exits = [t for t in trades if t.get('event') == 'EXIT']
    entries = [t for t in trades if t.get('event') == 'ENTRY']

    if not exits:
        print("📭 No completed trades yet")
        return

    print("\n" + "=" * 60)
    print("📊 PERFORMANCE REPORT")
    print("=" * 60)

    # P&L stats
    pnls = [t.get('realized_pnl', 0) for t in exits]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    avg_trade = sum(pnls) / len(pnls) if pnls else 0
    win_rate = len(winners) / len(pnls) * 100 if pnls else 0

    print(f"\n📈 TRADE STATISTICS")
    print(f"   Total Trades:    {len(exits)}")
    print(f"   Winners:         {len(winners)} ({win_rate:.1f}%)")
    print(f"   Losers:          {len(losers)}")
    print(f"   Total P&L:        {format_currency(total_pnl)}")
    print(f"   Average Trade:   {format_currency(avg_trade)}")

    if winners:
        avg_winner = sum(winners) / len(winners)
        print(f"   Avg Winner:      {format_currency(avg_winner)}")
        print(f"   Largest Win:     {format_currency(max(winners))}")

    if losers:
        avg_loser = sum(losers) / len(losers)
        print(f"   Avg Loser:       {format_currency(avg_loser)}")
        print(f"   Largest Loss:    {format_currency(min(losers))}")

    # R-multiple stats if available
    r_multiples = []
    for t in exits:
        entry = t.get('entry_price', 0)
        exit_p = t.get('exit_price', 0)
        shares = t.get('shares', 0)
        pnl = t.get('realized_pnl', 0)
        if entry and exit_p and shares and pnl:
            # Estimate initial risk
            risk = abs((exit_p - entry) * shares / (pnl / ((exit_p - entry) * shares))) if pnl != 0 else 1
            r_multiples.append(pnl / risk)

    print(f"\n🎯 R-MULTIPLE ANALYSIS")
    print(f"   Based on initial risk per trade")


def cmd_close(args):
    """Manually close a position."""
    if not args.ticker:
        print("❌ Ticker required. Use: python3 scripts/paper_portfolio.py close TICKER")
        return

    import yfinance as yf
    sys.path.insert(0, str(Path(__file__).parent))
    from paper_state import PaperState

    positions = load_json_file(POSITIONS_FILE)

    if not positions or args.ticker not in positions:
        print(f"❌ Position {args.ticker} not found in open positions")
        return

    # Get current price
    try:
        stock = yf.Ticker(args.ticker)
        hist = stock.history(period="1d", interval="5m")
        current_price = hist['Close'].iloc[-1] if len(hist) > 0 else 0
    except Exception:
        print(f"⚠️ Could not fetch price for {args.ticker}")
        if not args.force:
            confirm = input(f"Force close at last known price? (y/n): ")
            if confirm.lower() != 'y':
                return
        current_price = None

    # Initialize state and close
    state = PaperState()
    reason = args.reason or "manual_close"

    pos = state.close_position(args.ticker, current_price, reason)

    if pos:
        print(f"\n✅ CLOSED {args.ticker}")
        print(f"   Exit Price: ${current_price:.2f}" if current_price else "   Exit: Manual")
        print(f"   Reason: {reason}")
        print(f"   Realized P&L: ${pos.realized_pnl:,.2f}" if pos.realized_pnl else "")
    else:
        print(f"❌ Failed to close {args.ticker}")


def main():
    parser = argparse.ArgumentParser(
        description='Paper Trading Portfolio CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/paper_portfolio.py status       # Account overview
  python3 scripts/paper_portfolio.py live           # Live position prices
  python3 scripts/paper_portfolio.py today         # Today's trades
  python3 scripts/paper_portfolio.py history       # Full trade log
  python3 scripts/paper_portfolio.py report        # Performance stats
  python3 scripts/paper_portfolio.py close AAPL    # Emergency close
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # status
    p_status = subparsers.add_parser('status', help='Account status overview')
    p_status.set_defaults(func=cmd_status)

    # live
    p_live = subparsers.add_parser('live', help='Real-time position values')
    p_live.set_defaults(func=cmd_live)

    # today
    p_today = subparsers.add_parser('today', help="Today's trades")
    p_today.set_defaults(func=cmd_today)

    # history
    p_history = subparsers.add_parser('history', help='Trade history')
    p_history.add_argument('--limit', type=int, default=100, help='Number of trades')
    p_history.set_defaults(func=cmd_history)

    # report
    p_report = subparsers.add_parser('report', help='Performance report')
    p_report.set_defaults(func=cmd_report)

    # close
    p_close = subparsers.add_parser('close', help='Manually close position')
    p_close.add_argument('ticker', help='Ticker to close')
    p_close.add_argument('--reason', help='Exit reason')
    p_close.add_argument('--force', action='store_true', help='Skip confirmation')
    p_close.set_defaults(func=cmd_close)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
