#!/usr/bin/env python3
"""CLI tool for paper trading portfolio management and monitoring."""

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Add scripts directory to path for local imports
import sys
sys.path.insert(0, str(Path(__file__).parent))
from trading_exceptions import TradingExceptionHandler

# Data paths - configurable via environment variable for testing
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
POSITIONS_FILE = DATA_DIR / 'paper_positions.json'
DAILY_TRACKER_FILE = DATA_DIR / 'daily_tracker.json'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'

# Constants
DEFAULT_INITIAL_CAPITAL = 100000.0


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
    except Exception as e:
        TradingExceptionHandler.log_exception(
            "load_recent_trades", e,
            severity=TradingExceptionHandler.WARNING,
            file=str(TRADES_FILE)
        )

    return trades[-limit:] if trades else []


def format_currency(value: float) -> str:
    """Format currency with sign."""
    return f"${value:,.2f}"


def format_pct(value: float) -> str:
    """Format percentage with sign."""
    color = "🟢" if value >= 0 else "🔴"
    return f"{color} {value:+.2f}%"


def _calculate_day_stats() -> Dict:
    """Calculate day stats from trade log (source of truth)."""
    today = datetime.now().strftime('%Y-%m-%d')
    trades = load_trades(limit=1000)  # Load enough to cover the day

    day_pnl = 0.0
    entries_today = 0
    total_trades = 0

    for trade in trades:
        total_trades += 1
        ts = trade.get('timestamp', '')

        if trade.get('event') == 'EXIT':
            realized = trade.get('realized_pnl', 0) or 0
            if isinstance(ts, str) and ts.startswith(today):
                day_pnl += realized

        if trade.get('event') == 'ENTRY':
            if isinstance(ts, str) and ts.startswith(today):
                entries_today += 1

    day_return = (day_pnl / DEFAULT_INITIAL_CAPITAL) * 100 if DEFAULT_INITIAL_CAPITAL else 0

    return {
        'day_pnl': day_pnl,
        'day_return': day_return,
        'entries_today': entries_today,
        'total_trades': total_trades
    }


def cmd_status(args):
    """Show current account and market status using Alpaca real-time prices."""
    from alpaca_client import AlpacaClient

    positions = load_json_file(POSITIONS_FILE)

    # Load watchlist for sector lookup
    watchlist_df = None
    try:
        watchlist_df = pd.read_csv(DATA_DIR / 'watchlist.csv')
    except Exception as e:
        TradingExceptionHandler.log_exception(
            "watchlist_load", e,
            severity=TradingExceptionHandler.WARNING,
            file=str(DATA_DIR / 'watchlist.csv')
        )

    # Initialize Alpaca client for real-time pricing
    try:
        alpaca = AlpacaClient(mode='paper')
        price_source = "Alpaca Real-Time"
    except Exception as e:
        TradingExceptionHandler.log_exception(
            "alpaca_init", e,
            severity=TradingExceptionHandler.WARNING,
            message="Failed to initialize Alpaca client for pricing"
        )
        print("❌ Failed to connect to Alpaca. Check API credentials.")
        return

    # Get cash from Alpaca API (live)
    try:
        alpaca_account = alpaca.get_account()
        cash = alpaca_account['cash']
        cash_source = "Alpaca Live"
    except Exception as e:
        # Fallback if API fails
        cash = 0
        cash_source = "Unavailable"
        TradingExceptionHandler.log_exception(
            "cash_fetch", e,
            severity=TradingExceptionHandler.WARNING,
            message="Failed to fetch cash from Alpaca"
        )

    initial_capital = DEFAULT_INITIAL_CAPITAL

    # Calculate account value using Alpaca real-time prices
    account_value = cash  # Start with cash
    position_values = {}

    if positions:
        pos_dict = {}
        if isinstance(positions, list):
            for p in positions:
                ticker = p.get('symbol') or p.get('ticker')
                if ticker:
                    pos_dict[ticker] = p
        else:
            pos_dict = positions

        # Fetch real-time prices from Alpaca
        for ticker, pos in pos_dict.items():
            current_price = None
            price_source_detail = 'POSITION'

            try:
                # Use AlpacaClient.get_latest_price() which uses:
                # 1. Position API current_price (marked to market) when position exists
                # 2. Quotes API (bid/ask midpoint) for non-positions
                current_price = alpaca.get_latest_price(ticker, use_fallback=False)
                if current_price is None:
                    # Fallback to entry price if Alpaca returns None
                    current_price = pos.get('entry_price', 0) or pos.get('avg_entry_price', 0)
                    price_source_detail = 'ENTRY'
            except Exception:
                current_price = pos.get('entry_price', 0) or pos.get('avg_entry_price', 0)
                price_source_detail = 'ENTRY'

            shares = pos.get('shares') or pos.get('qty', 0)
            position_market_value = current_price * shares
            position_values[ticker] = {
                'current_price': current_price,
                'price_source': price_source_detail,
                'market_value': position_market_value,
                'entry_price': pos.get('entry_price') or pos.get('avg_entry_price', 0),
                'shares': shares
            }
            account_value += position_market_value

    print("\n" + "=" * 60)
    print(f"📊 PAPER TRADING ACCOUNT STATUS ({price_source})")
    print("=" * 60)

    print(f"\n💰 ACCOUNT")
    print(f"   Initial Capital:   {format_currency(initial_capital)}")
    print(f"   Account Value:     {format_currency(account_value)}")
    print(f"   Available Cash:    {format_currency(cash)} ({cash_source})")

    pnl = account_value - initial_capital
    pnl_pct = (pnl / initial_capital) * 100 if initial_capital else 0
    print(f"   P&L:               {format_currency(pnl)} ({format_pct(pnl_pct)})")

    print(f"\n📈 DAILY PERFORMANCE")
    # Calculate from trade log instead of stale account file
    day_stats = _calculate_day_stats()
    print(f"   Day P&L: {format_currency(day_stats['day_pnl'])} ({format_pct(day_stats['day_return'])})")

    # Calculate unrealized P&L using Alpaca real-time prices
    unrealized_pnl = 0.0
    if positions and position_values:
        for ticker, pos in position_values.items():
            entry_price = pos['entry_price']
            current_price = pos['current_price']
            shares = pos['shares']
            if entry_price and current_price and shares:
                unrealized_pnl += (current_price - entry_price) * shares

    if unrealized_pnl != 0:
        unrealized_pct = (unrealized_pnl / initial_capital) * 100 if initial_capital else 0
        print(f"   Unrealized P&L: {format_currency(unrealized_pnl)} ({format_pct(unrealized_pct)})")

    print(f"\n📊 ACTIVITY")
    open_count = len(pos_dict) if positions else 0
    print(f"   Open Positions: {open_count}")
    print(f"   Entries Today:  {day_stats['entries_today']}")
    print(f"   Total Trades:   {day_stats['total_trades']}")

    if positions:
        pos_dict = {}
        if isinstance(positions, list):
            for p in positions:
                ticker = p.get('symbol') or p.get('ticker')
                if ticker:
                    pos_dict[ticker] = p
        else:
            pos_dict = positions

        print(f"\n📋 OPEN POSITIONS ({len(pos_dict)}) - Alpaca Prices")
        print("-" * 75)
        print(f"{'Ticker':7} {'Sector':12} {'Shares':7} {'Entry':>10} {'Current':>10} {'P&L $':>12} {'Stop':>10} {'Type'}")
        print("-" * 75)

        for ticker, pos in pos_dict.items():
            # Handle both Alpaca format (avg_entry_price) and internal format (entry_price)
            entry = pos.get('entry_price') or pos.get('avg_entry_price', 0)
            shares = pos.get('shares') or pos.get('qty', 0)
            stop = pos.get('stop_price', 0)
            stop_type = pos.get('current_stop_type', 'HARD')

            # Sector and stop lookup from watchlist if not in position data
            sector = pos.get('sector', 'Unknown')
            if watchlist_df is not None:
                try:
                    row = watchlist_df[watchlist_df['Ticker'] == ticker]
                    if not row.empty:
                        if sector == 'Unknown' and 'Sector' in row.columns:
                            sector = str(row['Sector'].values[0])
                        # Look up stop level from watchlist if missing
                        if stop == 0 and 'Stop_Level' in row.columns:
                            stop_val = row['Stop_Level'].values[0]
                            if pd.notna(stop_val) and stop_val > 0:
                                stop = float(stop_val)
                except Exception as e:
                    TradingExceptionHandler.log_exception(
                        "stop_level_lookup", e,
                        severity=TradingExceptionHandler.WARNING,
                        ticker=ticker
                    )

            # Get current price from Alpaca fetched values
            pos_value = position_values.get(ticker, {})
            current_price = pos_value.get('current_price', entry)
            pos_pnl = (current_price - entry) * shares if current_price and entry else 0

            emoji = "🟢" if pos_pnl >= 0 else "🔴"
            print(f"{emoji} {ticker:5} {sector[:12]:12} {shares:7} "
                  f"${entry:>9.2f} ${current_price:>9.2f} ${pos_pnl:>11,.2f} "
                  f"${stop:>9.2f} {stop_type}")

    # Last update
    print(f"\n🕐 Last Update: {datetime.now().isoformat()}")


def cmd_live(args):
    """Show real-time position values."""
    import yfinance as yf

    positions = load_json_file(POSITIONS_FILE)

    if not positions:
        print("📭 No open positions")
        return

    pos_dict = {}
    if isinstance(positions, list):
        for p in positions:
            ticker = p.get('symbol') or p.get('ticker')
            if ticker:
                pos_dict[ticker] = p
    else:
        pos_dict = positions

    print("\n" + "=" * 80)
    print("📈 LIVE POSITIONS (Fetching current prices...)")
    print("=" * 80)
    print(f"{'Ticker':<8} {'Shares':<8} {'Entry':<10} {'Current':<10} "
          f"{'P&L $':<12} {'P&L %':<10} {'Stop':<10} {'Type':<10} {'R'}")
    print("-" * 80)

    total_pnl = 0
    total_value = 0

    for ticker, pos in pos_dict.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m")

            if len(hist) == 0:
                print(f"{ticker:<8} <no data>")
                continue

            current = hist['Close'].iloc[-1]
            entry = pos.get('entry_price', 0) or pos.get('avg_entry_price', 0)
            shares = pos.get('shares', 0) or pos.get('qty', 0)
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
    print(f"\n💰 Total Position Value: {format_currency(total_value)}")





def cmd_today(args):
    """Show today's trades."""
    trades = load_trades(limit=200)

    # Filter out test entries
    trades = [t for t in trades if not t.get('_meta', {}).get('test_mode', False)]

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

    # Filter out test entries unless --include-test-data
    if not getattr(args, 'include_test_data', False):
        trades = [t for t in trades if not t.get('_meta', {}).get('test_mode', False)]

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

    if not trades:
        print("📭 No trades to report")
        return

    # PHASE 2: Filter out test entries unless --include-test-data flag
    if not getattr(args, 'include_test_data', False):
        original_count = len(trades)
        trades = [t for t in trades if not t.get('_meta', {}).get('test_mode', False)]
        filtered_count = original_count - len(trades)
        if filtered_count > 0:
            print(f"   (Filtered {filtered_count} test entries, use --include-test-data to show)")

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


def cmd_reconcile(args):
    """Reconcile counters with trade log."""
    sys.path.insert(0, str(Path(__file__).parent))
    from paper_state import PaperState

    print("🔄 Reconciling counters with trade log...")
    print()

    # Use default initial capital (no longer stored in account file)
    initial_capital = DEFAULT_INITIAL_CAPITAL
    print(f"   Using initial_capital: ${initial_capital:,.2f}")

    # Initialize state with initial_capital
    state = PaperState(initial_capital=initial_capital)

    # Get the reconciliation stats
    stats = state._reconcile_counters_from_log()

    if 'error' in stats:
        print(f"❌ {stats['error']}")
        return

    print()
    print("=" * 60)
    print("📊 RECONCILIATION RESULTS")
    print("=" * 60)
    print(f"   Total trades in log:     {stats['total_trades']}")
    print(f"   Test trades filtered:    {stats['test_trades']}")
    print(f"   Production trades:       {stats['production_trades']}")
    print(f"   Entries today:           {stats['production_entries_today']}")
    print()
    print(f"✅ Counters updated:")
    print(f"   trade_count:   {state.trade_count}")
    print(f"   entries_today: {state.entries_today}")

    # Save the reconciled state
    state.save_state()
    print()
    print("💾 State saved.")


def main():
    parser = argparse.ArgumentParser(
        description='Paper Trading Portfolio CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/paper_portfolio.py status       # Account overview
  python3 scripts/paper_portfolio.py live         # Live position prices
  python3 scripts/paper_portfolio.py today         # Today's trades
  python3 scripts/paper_portfolio.py history       # Full trade log
  python3 scripts/paper_portfolio.py report        # Performance stats
  python3 scripts/paper_portfolio.py close AAPL  # Emergency close
  python3 scripts/paper_portfolio.py reconcile   # Fix counter discrepancies
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
    p_history.add_argument('--include-test-data', action='store_true',
                          help='Include test entries in history (default: filtered)')
    p_history.set_defaults(func=cmd_history)

    # report
    p_report = subparsers.add_parser('report', help='Performance report')
    p_report.add_argument('--include-test-data', action='store_true',
                         help='Include test entries in report (default: filtered)')
    p_report.set_defaults(func=cmd_report)

    # close
    p_close = subparsers.add_parser('close', help='Manually close position')
    p_close.add_argument('ticker', help='Ticker to close')
    p_close.add_argument('--reason', help='Exit reason')
    p_close.add_argument('--force', action='store_true', help='Skip confirmation')
    p_close.set_defaults(func=cmd_close)

    # reconcile
    p_reconcile = subparsers.add_parser('reconcile', help='Reconcile counters with trade log')
    p_reconcile.set_defaults(func=cmd_reconcile)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
