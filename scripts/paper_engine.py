#!/usr/bin/env python3
"""Main paper trading engine - daemon with event loop for auto-execution."""

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytz
import yfinance as yf

from traderlib import calculate_stage2_score, get_entry_score

from paper_state import PaperState, Position
from paper_exits import ExitEngine, ExitSignal

# Configurable paths
DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'

# Market hours (Eastern Time)
MARKET_OPEN = (9, 30)   # 9:30 AM ET
MARKET_CLOSE = (16, 0)  # 4:00 PM ET
POLL_INTERVAL = 30      # 30 seconds

# Entry criteria thresholds
ENTRY_THRESHOLD = 60    # QScore >= 60 for Tier 1
MAX_DIST_TO_PIVOT = 1.0  # Within 1% of pivot
MIN_VOLUME_RATIO = 1.5   # 1.5x average volume
MAX_SPY_DECLINE = -0.3   # SPY >= -0.3%


class PaperEngine:
    """Main trading engine with event loop."""

    def __init__(self, initial_capital: float = 100000):
        self.state = PaperState(initial_capital)
        self.exits = ExitEngine()
        self.running = False
        self.last_poll = None
        self.spy_data = None
        self.spy_last_fetch = None

        # Track entry signals to avoid duplicates
        self.signaled_tickers = set()
        self.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        print(f"💰 Initial Capital: ${initial_capital:,.2f}")
        print(f"💵 Cash Available: ${self.state.cash:,.2f}")
        print(f"📊 Open Positions: {len(self.state.positions)}")

    def _signal_handler(self, signum, frame):
        """Graceful shutdown on SIGINT/SIGTERM."""
        print("\n\n🛑 Shutdown signal received, stopping engine...")
        self.running = False

    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours (ET)."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        # Check if weekday
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        current_time = (now.hour, now.minute)
        return MARKET_OPEN <= current_time < MARKET_CLOSE

    def _get_market_status(self) -> str:
        """Get formatted market status."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        current_time = (now.hour, now.minute)

        if now.weekday() >= 5:
            return "CLOSED (Weekend)"
        elif current_time < MARKET_OPEN:
            return f"PRE-MARKET (Opens {MARKET_OPEN[0]}:{MARKET_OPEN[1]:02d} ET)"
        elif current_time >= MARKET_CLOSE:
            return "CLOSED"
        else:
            return f"OPEN ({now.strftime('%H:%M')} ET)"

    def _fetch_spy_data(self) -> Optional[Dict]:
        """Fetch SPY data for market condition check."""
        now = datetime.now()

        # Cache SPY data for 5 minutes
        if self.spy_last_fetch and (now - self.spy_last_fetch).seconds < 300:
            return self.spy_data

        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(period="5d", interval="5m")

            if len(hist) < 2:
                return None

            current = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-1]  # Using last available

            # Get yesterday's close for daily change
            daily_hist = spy.history(period="2d")
            if len(daily_hist) >= 2:
                prev_close = daily_hist['Close'].iloc[-2]

            change_pct = ((current / prev_close) - 1) * 100

            self.spy_data = {
                'price': current,
                'change_pct': change_pct,
                'timestamp': now
            }
            self.spy_last_fetch = now

            return self.spy_data

        except Exception as e:
            print(f"⚠️ Error fetching SPY: {e}")
            return self.spy_data  # Return cached if available

    def _check_market_conditions(self) -> Tuple[bool, str]:
        """Check if market conditions allow entries."""
        spy = self._fetch_spy_data()

        if spy is None:
            return False, "Cannot fetch SPY data"

        if spy['change_pct'] < MAX_SPY_DECLINE:
            return False, f"SPY down {spy['change_pct']:.2f}% (limit: {MAX_SPY_DECLINE}%)"

        return True, f"SPY {spy['change_pct']:+.2f}%"

    def _load_watchlist(self) -> List[Dict]:
        """Load watchlist tickers."""
        if not WATCHLIST_PATH.exists():
            return []

        try:
            df = pd.read_csv(WATCHLIST_PATH)
            return df.to_dict('records')
        except Exception as e:
            print(f"⚠️ Error loading watchlist: {e}")
            return []

    def _analyze_ticker(self, ticker_data: Dict) -> Optional[Dict]:
        """Analyze a single ticker for entry opportunity."""
        ticker = ticker_data.get('Ticker')
        if not ticker:
            return None

        # Skip if already in position
        if ticker in self.state.positions:
            return None

        # Skip if already signaled today
        if ticker in self.signaled_tickers:
            return None

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            info = stock.info

            if len(hist) < 200:
                return None

            current = hist['Close'].iloc[-1]
            volume = hist['Volume'].iloc[-1]

            # Get pivot (from watchlist or calculate)
            pivot = ticker_data.get('Pivot_Price')
            if pd.isna(pivot) or pivot == '':
                pivot = hist['High'].tail(5).max()
            else:
                pivot = float(pivot)

            # Calculate metrics
            ret_6m = (current / hist['Close'].iloc[-130] - 1) * 100

            # Calculate Stage 2 score
            stage2 = calculate_stage2_score(hist)

            # Volume ratio
            avg_volume = hist['Volume'].tail(50).mean()
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

            # Calculate ATR and stop
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            stop = self.exits.calculate_initial_stop(ticker, current)
            target = self.exits.calculate_target_price(current, stop)

            # Distance to pivot
            dist_to_pivot = ((pivot - current) / current) * 100

            # Get SPY for RS
            spy = self._fetch_spy_data()
            rs_6m = 0
            if spy:
                # Approximate RS
                spy_hist = yf.Ticker("SPY").history(period="1y")
                spy_6m = (spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[-130] - 1) * 100
                rs_6m = ret_6m - spy_6m

            # Calculate entry score
            risk_pct = abs((stop - pivot) / pivot) * 100 if pivot > stop else 999
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)

            return {
                'ticker': ticker,
                'current': current,
                'pivot': pivot,
                'dist_to_pivot': dist_to_pivot,
                'stop': stop,
                'target': target,
                'stage2': stage2,
                'volume_ratio': volume_ratio,
                'entry_score': entry_score,
                'atr': atr,
                'sector': info.get('sector', 'Unknown')
            }

        except Exception as e:
            return None

    def _check_entries(self):
        """Scan for entry opportunities."""
        # Check market conditions first
        market_ok, market_msg = self._check_market_conditions()
        if not market_ok:
            return

        # Load watchlist
        watchlist = self._load_watchlist()
        if not watchlist:
            return

        print(f"\n🔍 Scanning {len(watchlist)} tickers for entries...")

        for ticker_data in watchlist:
            analysis = self._analyze_ticker(ticker_data)
            if not analysis:
                continue

            ticker = analysis['ticker']

            # Entry criteria check
            if analysis['entry_score'] < ENTRY_THRESHOLD:
                continue

            if analysis['dist_to_pivot'] > MAX_DIST_TO_PIVOT:
                continue

            if analysis['volume_ratio'] < MIN_VOLUME_RATIO:
                continue

            # All criteria met - execute entry
            self._execute_entry(analysis)

    def _execute_entry(self, analysis: Dict):
        """Execute a paper trade entry."""
        ticker = analysis['ticker']
        entry_price = analysis['current']
        stop_price = analysis['stop']
        target_price = analysis['target']
        sector = analysis['sector']

        # Calculate position size
        equity = self.state.get_equity()
        shares = self.exits.calculate_position_size(
            equity, entry_price, stop_price
        )

        position_value = entry_price * shares

        # Validate entry
        can_enter, reason = self.state.can_enter_position(sector, position_value)
        if not can_enter:
            return

        # Execute
        position = self.state.enter_position(
            ticker=ticker,
            entry_price=entry_price,
            shares=shares,
            stop_price=stop_price,
            target_price=target_price,
            sector=sector
        )

        # Mark as signaled
        self.signaled_tickers.add(ticker)

        # Log entry
        risk_pct = ((entry_price - stop_price) / entry_price) * 100
        print(f"\n🚀 AUTO-ENTRY: {ticker} at ${entry_price:.2f} x {shares} shares")
        print(f"   Stop: ${stop_price:.2f} | Target: ${target_price:.2f} | Risk: {risk_pct:.2f}%")
        print(f"   Sector: {sector} | Score: {analysis['entry_score']}")

    def _check_exits(self):
        """Monitor open positions for exit signals."""
        if not self.state.positions:
            return

        print(f"\n📊 Checking {len(self.state.positions)} open positions...")

        for ticker, position in list(self.state.positions.items()):
            try:
                # Get current price
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d", interval="5m")

                if len(hist) == 0:
                    continue

                current_price = hist['Close'].iloc[-1]

                # Evaluate exit
                signal = self.exits.evaluate_exit(position, current_price)

                if signal.should_exit:
                    self._execute_exit(position, signal)
                else:
                    # Show position status
                    summary = self.exits.get_position_summary(position, current_price)
                    status_emoji = "🟢" if summary['r_multiple'] > 0 else "🔴"
                    print(f"   {status_emoji} {ticker}: ${current_price:.2f} | "
                          f"P&L: ${summary['unrealized_pnl']:,.2f} ({summary['unrealized_pct']:+.2f}%) | "
                          f"{summary['r_multiple']:.2f}R | Stop: {position.current_stop_type}")

            except Exception as e:
                print(f"   ⚠️ Error checking {ticker}: {e}")

    def _execute_exit(self, position: Position, signal: ExitSignal):
        """Execute a paper trade exit."""
        ticker = position.ticker

        result = self.state.close_position(
            ticker=ticker,
            exit_price=signal.exit_price,
            reason=signal.reason
        )

        if result:
            pnl_emoji = "🎯" if result.realized_pnl > 0 else "🛑"
            print(f"\n{pnl_emoji} AUTO-EXIT: {ticker} at ${signal.exit_price:.2f}")
            print(f"   Reason: {signal.reason}")
            print(f"   P&L: ${result.realized_pnl:,.2f} ({signal.r_multiple:.2f}R)")

    def _reset_daily_signals(self):
        """Reset entry signals for new day."""
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_signal_reset != current_date:
            self.signaled_tickers.clear()
            self.last_signal_reset = current_date
            print(f"\n📅 New day: Reset entry signals")

    def _print_status(self):
        """Print current engine status."""
        print(f"\n{'='*60}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📈 Market: {self._get_market_status()}")

        stats = self.state.get_stats()
        print(f"💰 Equity: ${stats['equity']:,.2f} | Cash: ${stats['cash']:,.2f}")
        print(f"📊 Open: {stats['open_positions']} | Day P&L: ${stats['day_pnl']:,.2f} ({stats['day_return_pct']:+.2f}%)")
        print(f"{'='*60}")

    def run_once(self):
        """Single iteration of the trading loop."""
        self._reset_daily_signals()
        self._print_status()

        if self._is_market_hours():
            # Check exits first (risk management priority)
            self._check_exits()

            # Then check for entries
            self._check_entries()
        else:
            print(f"   ⏳ Market closed - monitoring only")

    def run(self):
        """Main event loop."""
        print("\n" + "="*60)
        print("🚀 PAPER TRADING ENGINE STARTED")
        print("="*60)

        self.running = True

        while self.running:
            try:
                self.run_once()

                # Countdown for next poll
                for i in range(POLL_INTERVAL, 0, -1):
                    if not self.running:
                        break
                    print(f"\r⏱️  Next poll in {i}s...", end='', flush=True)
                    time.sleep(1)
                print()

            except Exception as e:
                print(f"\n❌ Error in main loop: {e}")
                time.sleep(POLL_INTERVAL)

        print("\n✅ Engine stopped gracefully")


def main():
    parser = argparse.ArgumentParser(description='Paper Trading Engine')
    parser.add_argument('--capital', type=float, default=100000,
                        help='Initial capital (default: 100000)')
    parser.add_argument('--once', action='store_true',
                        help='Run once and exit (no loop)')
    args = parser.parse_args()

    engine = PaperEngine(initial_capital=args.capital)

    if args.once:
        engine.run_once()
    else:
        engine.run()


if __name__ == "__main__":
    main()
