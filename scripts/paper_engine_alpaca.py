#!/usr/bin/env python3
"""Alpaca-powered paper trading engine with real-time WebSocket data."""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).parent / 'lib'))
sys.path.insert(0, str(Path(__file__).parent))

from alpaca_client import AlpacaClient
from paper_state import PaperState, Position
from paper_exits import ExitEngine, ExitSignal
from order_manager import OrderManager, OrderStatus
from stage2_utils import calculate_stage2_score, get_entry_score

# Configurable paths
DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'

# Market hours (Eastern Time)
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)

# Entry criteria thresholds
ENTRY_THRESHOLD = 60
MAX_DIST_TO_PIVOT = 1.0
MIN_VOLUME_RATIO = 1.5
MAX_SPY_DECLINE = -0.3


class AlpacaPaperEngine:
    """Paper trading engine using Alpaca for real-time data and execution."""

    def __init__(self, mode: str = 'paper'):
        print("🔌 Initializing Alpaca client...")
        self.alpaca = AlpacaClient(mode=mode)
        self.order_manager = OrderManager(self.alpaca)
        self.state = PaperState(initial_capital=self._get_account_value())
        self.exits = ExitEngine()

        self.running = False
        self.ws_running = False

        # Price cache from WebSocket
        self.price_cache: Dict[str, Dict] = {}
        self.ws_tickers: Set[str] = set()

        # Entry tracking
        self.signaled_tickers: Set[str] = set()
        self.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        # Market data
        self.spy_data = None

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Account sync
        self._sync_with_alpaca()

        print(f"✅ Engine ready - Mode: {mode.upper()}")
        print(f"📋 Pending orders: {self.order_manager.get_pending_count()}")

    def _get_account_value(self) -> float:
        """Get initial account value from Alpaca."""
        try:
            account = self.alpaca.get_account()
            return account['equity']
        except Exception:
            return 100000.0

    def _sync_with_alpaca(self):
        """Sync local state with Alpaca positions."""
        try:
            # Sync positions via order manager
            sync_result = self.order_manager.sync_positions(self.state.positions)

            if sync_result['added']:
                for pos in sync_result['added']:
                    ticker = pos['ticker']
                    print(f"📥 Syncing {ticker} position from Alpaca")
                    position = Position(
                        ticker=ticker,
                        status='OPEN',
                        entry_date=datetime.now().isoformat(),
                        entry_price=pos['avg_price'],
                        shares=pos['qty'],
                        stop_price=pos['avg_price'] * 0.95,  # Estimate
                        target_price=pos['avg_price'] * 1.1,
                        initial_risk=0,
                        sector='Unknown'
                    )
                    self.state.positions[ticker] = position

            if sync_result['removed']:
                for ticker in sync_result['removed']:
                    print(f"📤 Position {ticker} closed externally")
                    if ticker in self.state.positions:
                        del self.state.positions[ticker]

            if sync_result['discrepancies']:
                for disc in sync_result['discrepancies']:
                    print(f"⚠️ Position discrepancy: {disc['ticker']} - "
                          f"Alpaca: {disc['alpaca_qty']}, Local: {disc['local_qty']}")

            # Update cash
            account = self.alpaca.get_account()
            self.state.cash = account['cash']

        except Exception as e:
            print(f"⚠️ Error syncing with Alpaca: {e}")

    def _signal_handler(self, signum, frame):
        """Graceful shutdown."""
        print("\n\n🛑 Shutdown signal received...")
        self.running = False

    def _is_market_hours(self) -> bool:
        """Check if market is open."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        if now.weekday() >= 5:
            return False

        current_time = (now.hour, now.minute)
        return MARKET_OPEN <= current_time < MARKET_CLOSE

    def _is_pre_market(self) -> bool:
        """Check if pre-market hours."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        if now.weekday() >= 5:
            return False

        current_time = (now.hour, now.minute)
        return (4, 0) <= current_time < MARKET_OPEN

    async def _ws_trade_handler(self, trade):
        """Handle WebSocket trade updates."""
        ticker = trade.symbol
        price = float(trade.price)

        self.price_cache[ticker] = {
            'price': price,
            'timestamp': datetime.now(),
            'size': trade.size
        }

        # Check exits for open positions
        if ticker in self.state.positions:
            await self._check_exit_async(ticker, price)

    async def _start_websocket(self):
        """Start WebSocket stream for watchlist tickers."""
        watchlist = self._load_watchlist_tickers()
        if not watchlist:
            print("⚠️ No tickers to stream")
            return

        # Add open positions to stream
        open_tickers = list(self.state.positions.keys())
        all_tickers = list(set(watchlist + open_tickers + ['SPY']))

        print(f"📡 Starting WebSocket stream for {len(all_tickers)} tickers...")

        self.ws_running = True
        self.ws_tickers = set(all_tickers)

        try:
            await self.alpaca.start_price_stream(
                tickers=all_tickers,
                trade_handler=self._ws_trade_handler
            )
        except Exception as e:
            print(f"⚠️ WebSocket error: {e}")
            self.ws_running = False

    def _load_watchlist_tickers(self) -> List[str]:
        """Load watchlist tickers."""
        if not WATCHLIST_PATH.exists():
            return []
        try:
            df = pd.read_csv(WATCHLIST_PATH)
            return df['Ticker'].tolist()
        except Exception:
            return []

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price from cache or REST API."""
        # Try WebSocket cache first
        if ticker in self.price_cache:
            return self.price_cache[ticker]['price']

        # Fallback to REST
        return self.alpaca.get_latest_price(ticker)

    def _check_market_conditions(self) -> tuple:
        """Check SPY market conditions."""
        spy_price = self._get_current_price('SPY')
        if spy_price is None:
            return False, "Cannot fetch SPY"

        # Get yesterday's close from yfinance for comparison
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            hist = spy.history(period="2d")
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                change_pct = ((spy_price / prev_close) - 1) * 100

                if change_pct < MAX_SPY_DECLINE:
                    return False, f"SPY {change_pct:+.2f}%"

                return True, f"SPY {change_pct:+.2f}%"
        except Exception:
            pass

        return True, "SPY OK"

    def _analyze_ticker(self, ticker: str) -> Optional[Dict]:
        """Analyze ticker for entry."""
        if ticker in self.state.positions or ticker in self.signaled_tickers:
            return None

        try:
            # Get historical data from Alpaca
            hist = self.alpaca.get_historical_bars(ticker, days=60)
            if hist is None or len(hist) < 50:
                return None

            current = self._get_current_price(ticker)
            if current is None:
                return None

            # Calculate Stage 2 score
            stage2 = calculate_stage2_score(hist)

            # Get pivot from watchlist
            pivot = current
            try:
                df = pd.read_csv(WATCHLIST_PATH)
                row = df[df['Ticker'] == ticker]
                if not row.empty and 'Pivot_Price' in row.columns:
                    pivot_val = row['Pivot_Price'].values[0]
                    if not pd.isna(pivot_val):
                        pivot = float(pivot_val)
            except Exception:
                pass

            # Calculate metrics
            ret_6m = 0
            if len(hist) >= 130:
                ret_6m = ((current / hist['Close'].iloc[-130]) - 1) * 100

            # ATR and stop
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]

            stop = self.exits.calculate_initial_stop(ticker, current)
            target = self.exits.calculate_target_price(current, stop)

            dist_to_pivot = ((pivot - current) / current) * 100
            risk_pct = abs((stop - pivot) / pivot) * 100 if pivot > stop else 999

            # Approximate entry score
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, 0)

            return {
                'ticker': ticker,
                'current': current,
                'pivot': pivot,
                'dist_to_pivot': dist_to_pivot,
                'stop': stop,
                'target': target,
                'stage2': stage2,
                'entry_score': entry_score,
                'sector': 'Unknown'
            }

        except Exception as e:
            return None

    async def _check_exit_async(self, ticker: str, current_price: float):
        """Check if position should exit (async version)."""
        if ticker not in self.state.positions:
            return

        position = self.state.positions[ticker]
        signal = self.exits.evaluate_exit(position, current_price)

        if signal.should_exit:
            await self._execute_exit(ticker, signal)

    def _check_exits(self):
        """Check all open positions for exits."""
        for ticker in list(self.state.positions.keys()):
            current_price = self._get_current_price(ticker)
            if current_price is None:
                continue

            position = self.state.positions[ticker]
            signal = self.exits.evaluate_exit(position, current_price)

            if signal.should_exit:
                asyncio.create_task(self._execute_exit(ticker, signal))

    def _check_entries(self):
        """Scan for entry opportunities."""
        market_ok, market_msg = self._check_market_conditions()
        if not market_ok:
            return

        watchlist = self._load_watchlist_tickers()
        if not watchlist:
            return

        for ticker in watchlist:
            analysis = self._analyze_ticker(ticker)
            if not analysis:
                continue

            # Entry criteria
            if analysis['entry_score'] < ENTRY_THRESHOLD:
                continue
            if analysis['dist_to_pivot'] > MAX_DIST_TO_PIVOT:
                continue

            self._execute_entry(analysis)

    def _execute_entry(self, analysis: Dict):
        """Execute entry via Alpaca."""
        ticker = analysis['ticker']
        entry_price = analysis['current']
        stop_price = analysis['stop']
        target_price = analysis['target']
        sector = analysis['sector']

        # Check if already have pending order
        if self.order_manager.has_pending_order(ticker):
            return

        # Calculate position size
        equity = self.state.get_equity()
        shares = self.exits.calculate_position_size(equity, entry_price, stop_price)

        position_value = entry_price * shares

        # Validate
        can_enter, reason = self.state.can_enter_position(sector, position_value)
        if not can_enter:
            return

        # Submit order via order manager
        order = self.order_manager.submit_entry(
            ticker=ticker,
            shares=shares,
            stop_price=stop_price
        )

        if order:
            # Record locally (optimistic - will update on fill)
            position = self.state.enter_position(
                ticker=ticker,
                entry_price=entry_price,
                shares=shares,
                stop_price=stop_price,
                target_price=target_price,
                sector=sector
            )

            self.signaled_tickers.add(ticker)

            print(f"\n🚀 AUTO-ENTRY: {ticker} at ${entry_price:.2f} x {shares} shares")
            print(f"   Order ID: {order.id}")
            print(f"   Stop: ${stop_price:.2f} | Target: ${target_price:.2f}")

    async def _execute_exit(self, ticker: str, signal: ExitSignal):
        """Execute exit via Alpaca."""
        if ticker not in self.state.positions:
            return

        position = self.state.positions[ticker]

        # Check if already have pending exit order
        pending = self.order_manager.get_pending_for_ticker(ticker)
        if any(o.side == 'sell' for o in pending):
            return

        # Submit exit via order manager
        order = self.order_manager.submit_exit(
            ticker=ticker,
            shares=position.shares,
            reason=signal.reason
        )

        if order:
            # Record locally (optimistic)
            position = self.state.close_position(
                ticker=ticker,
                exit_price=signal.exit_price,
                reason=signal.reason
            )

            if position:
                pnl_emoji = "🎯" if position.realized_pnl and position.realized_pnl > 0 else "🛑"
                print(f"\n{pnl_emoji} AUTO-EXIT: {ticker} at ${signal.exit_price:.2f}")
                print(f"   Reason: {signal.reason}")
                print(f"   P&L: ${position.realized_pnl:,.2f}")

    def _process_pending_orders(self):
        """Check status of all pending orders."""
        if self.order_manager.get_pending_count() == 0:
            return

        filled = self.order_manager.process_all_pending()
        for order in filled:
            if order.side == 'buy':
                print(f"✅ Entry filled: {order.ticker} "
                      f"@${order.filled_price:.2f} x {order.filled_qty}")
            else:
                print(f"✅ Exit filled: {order.ticker} "
                      f"(${order.reason})")

    def _reset_daily_signals(self):
        """Reset entry signals for new day."""
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_signal_reset != current_date:
            self.signaled_tickers.clear()
            self.last_signal_reset = current_date
            print(f"\n📅 New day: Reset entry signals")

    def _print_status(self):
        """Print current status."""
        print(f"\n{'='*60}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📈 Market: {'OPEN' if self._is_market_hours() else 'CLOSED'}")
        print(f"📡 WebSocket: {'Connected' if self.alpaca.is_ws_healthy() else 'Disconnected'}")

        stats = self.state.get_stats()
        orders = self.order_manager.get_orders_summary()

        print(f"💰 Equity: ${stats['equity']:,.2f} | Cash: ${stats['cash']:,.2f}")
        print(f"📊 Open: {stats['open_positions']} | Day P&L: ${stats['day_pnl']:,.2f}")
        print(f"📋 Pending Orders: {orders['pending']} | Health: {self.alpaca.get_health_summary()}")
        print(f"{'='*60}")

    async def run(self):
        """Main event loop."""
        print("\n" + "="*60)
        print("🚀 ALPACA PAPER TRADING ENGINE STARTED")
        print("="*60)

        self.running = True

        # Start WebSocket in background
        ws_task = asyncio.create_task(self._start_websocket())

        # Wait for WebSocket to connect
        await asyncio.sleep(2)

        while self.running:
            try:
                self._reset_daily_signals()
                self._print_status()

                # Process any pending orders (check fills)
                self._process_pending_orders()

                if self._is_market_hours():
                    # Check exits using cached prices
                    self._check_exits()

                    # Check for entries (REST)
                    self._check_entries()
                else:
                    print("   ⏳ Market closed - monitoring only")

                # Wait before next iteration
                for i in range(30, 0, -1):
                    if not self.running:
                        break
                    print(f"\r⏱️  Next check in {i}s...", end='', flush=True)
                    await asyncio.sleep(1)
                print()

            except Exception as e:
                print(f"\n❌ Error in main loop: {e}")
                await asyncio.sleep(30)

        # Cleanup
        print("\n🛑 Stopping WebSocket...")
        await self.alpaca.stop_price_stream()
        print("✅ Engine stopped gracefully")


def main():
    parser = argparse.ArgumentParser(description='Alpaca Paper Trading Engine')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                        help='Trading mode (default: paper)')
    args = parser.parse_args()

    engine = AlpacaPaperEngine(mode=args.mode)
    asyncio.run(engine.run())


if __name__ == "__main__":
    main()
