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

        # SPY cache for relative strength calculation (refreshed daily)
        self.spy_cache = {
            'date': None,
            'return_6m': 0.0,
            'price': None
        }

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
            # Load watchlist for sector lookup
            watchlist_sectors = {}
            try:
                df = pd.read_csv(WATCHLIST_PATH)
                if 'Ticker' in df.columns and 'Sector' in df.columns:
                    watchlist_sectors = {
                        row['Ticker']: str(row['Sector']) if pd.notna(row['Sector']) else 'Unknown'
                        for _, row in df.iterrows()
                    }
            except Exception:
                pass

            # Sync positions via order manager
            sync_result = self.order_manager.sync_positions(self.state.positions)

            if sync_result['added']:
                for pos in sync_result['added']:
                    ticker = pos['ticker']
                    print(f"📥 Syncing {ticker} position from Alpaca")

                    # Get sector from watchlist, fallback to 'Unknown'
                    sector = watchlist_sectors.get(ticker, 'Unknown')

                    position = Position(
                        ticker=ticker,
                        status='OPEN',
                        entry_date=datetime.now().isoformat(),
                        entry_price=pos['avg_price'],
                        shares=pos['qty'],
                        stop_price=pos['avg_price'] * 0.95,  # Estimate
                        target_price=pos['avg_price'] * 1.1,
                        initial_risk=0,
                        sector=sector
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

    def _refresh_spy_cache(self) -> bool:
        """Refresh SPY 6-month return cache (called daily).

        Returns:
            True if successful, False otherwise
        """
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Check if already cached for today
        if self.spy_cache['date'] == current_date:
            return True

        try:
            print(f"🔄 Refreshing SPY cache for {current_date}...")

            # Get SPY historical data (6 months + buffer)
            hist = self.alpaca.get_historical_bars('SPY', days=200)
            if hist is None or len(hist) < 100:
                bar_count = len(hist) if hist is not None else 0
                print(f"⚠️ Insufficient SPY data ({bar_count} bars)")
                return False

            current_price = hist['Close'].iloc[-1]
            # Use available data (up to 130 days for 6 months, or whatever we have)
            days_back = min(130, len(hist) - 1)
            price_6m_ago = hist['Close'].iloc[-days_back]  # ~6 months ago or best available
            return_6m = ((current_price / price_6m_ago) - 1) * 100

            self.spy_cache['date'] = current_date
            self.spy_cache['return_6m'] = return_6m
            self.spy_cache['price'] = current_price

            print(f"✅ SPY cache updated: 6M return = {return_6m:+.1f}%")
            return True

        except Exception as e:
            print(f"⚠️ Failed to refresh SPY cache: {e}")
            return False

    def _get_spy_return_6m(self) -> float:
        """Get cached SPY 6-month return (refresh if needed)."""
        if not self._refresh_spy_cache():
            # Return 0 if refresh fails, but log warning
            if self.spy_cache['return_6m'] == 0:
                print("⚠️ SPY cache unavailable, RS calculations will use 0")
        return self.spy_cache['return_6m']

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
            # Stream ended (either normally or with error)
        except Exception as e:
            print(f"⚠️ WebSocket error: {e}")
        finally:
            self.ws_running = False
            print("📡 WebSocket disconnected. Using REST polling for prices.")

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
        # Try WebSocket cache first (if recent)
        if ticker in self.price_cache:
            cache_entry = self.price_cache[ticker]
            age = (datetime.now() - cache_entry.get('timestamp', datetime.now())).total_seconds()
            if age < 60:  # Only use if < 60 seconds old
                return cache_entry['price']

        # Always try REST as primary source for entry decisions
        price = self.alpaca.get_latest_price(ticker, use_fallback=True)
        if price:
            self.price_cache[ticker] = {'price': price, 'timestamp': datetime.now()}
            return price

        # Final fallback: use stale cache if available (better than nothing)
        if ticker in self.price_cache:
            print(f"   ⚠️  {ticker}: Using stale price from cache (REST failed)")
            return self.price_cache[ticker]['price']

        return None

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
        if ticker in self.state.positions:
            return None

        if ticker in self.signaled_tickers:
            return None

        try:
            # Get historical data from Alpaca (uses configured historical_days, default 365)
            hist = self.alpaca.get_historical_bars(ticker)
            if hist is None or len(hist) < 30:
                bar_count = len(hist) if hist is not None else 0
                print(f"   ⏸️  {ticker}: Insufficient historical data ({bar_count} bars)")
                return None

            current = self._get_current_price(ticker)
            if current is None:
                print(f"   ⏸️  {ticker}: Cannot get current price")
                return None

            # Calculate Stage 2 score
            stage2 = calculate_stage2_score(hist)

            # Get pivot and sector from watchlist
            pivot = current
            sector = 'Unknown'
            try:
                df = pd.read_csv(WATCHLIST_PATH)
                row = df[df['Ticker'] == ticker]
                if not row.empty:
                    if 'Pivot_Price' in row.columns:
                        pivot_val = row['Pivot_Price'].values[0]
                        if not pd.isna(pivot_val):
                            pivot = float(pivot_val)
                    if 'Sector' in row.columns:
                        sector_val = row['Sector'].values[0]
                        if not pd.isna(sector_val):
                            sector = str(sector_val)
            except Exception:
                pass

            # Calculate metrics
            ret_6m = 0
            if len(hist) >= 130:
                ret_6m = ((current / hist['Close'].iloc[-130]) - 1) * 100

            # ATR and stop
            try:
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                ranges = pd.concat([high_low, high_close, low_close], axis=1)
                true_range = ranges.max(axis=1)
                atr = true_range.rolling(14).mean().iloc[-1]
            except Exception as e:
                print(f"   ⏸️  {ticker}: ATR calculation error - {e}")
                print(f"      hist columns: {hist.columns.tolist()}, shape: {hist.shape}")
                return None

            stop = self.exits.calculate_initial_stop(ticker, current)
            target = self.exits.calculate_target_price(current, stop)

            dist_to_pivot = ((pivot - current) / current) * 100
            risk_pct = abs((stop - pivot) / pivot) * 100 if pivot > stop else 999

            # Get SPY 6-month return for relative strength calculation
            spy_return_6m = self._get_spy_return_6m()
            rs_6m = ret_6m - spy_return_6m

            # Calculate entry score with RS component
            entry_score = get_entry_score(stage2, risk_pct, dist_to_pivot, ret_6m, rs_6m)

            return {
                'ticker': ticker,
                'current': current,
                'pivot': pivot,
                'dist_to_pivot': dist_to_pivot,
                'stop': stop,
                'target': target,
                'stage2': stage2,
                'entry_score': entry_score,
                'sector': sector
            }

        except Exception as e:
            print(f"   ⏸️  {ticker}: Analysis error - {type(e).__name__}: {e}")
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
            print(f"⏸️  Market condition failed: {market_msg}")
            return

        watchlist = self._load_watchlist_tickers()
        if not watchlist:
            print("⏸️  No tickers in watchlist")
            return

        print(f"\n🔍 Checking {len(watchlist)} tickers for entry signals...")

        checked = 0
        eligible = 0
        rejected_score = 0
        rejected_distance = 0
        logs = []

        for ticker in watchlist:
            checked += 1
            analysis = self._analyze_ticker(ticker)
            if not analysis:
                continue

            # Entry criteria with detailed logging (accumulate for batch output)
            if analysis['entry_score'] < ENTRY_THRESHOLD:
                logs.append(f"   ⏸️  {ticker}: Score {analysis['entry_score']:.0f} < {ENTRY_THRESHOLD} (need Tier 1)")
                rejected_score += 1
                continue

            # Fixed: symmetric distance filter (±1%)
            if not (-MAX_DIST_TO_PIVOT <= analysis['dist_to_pivot'] <= MAX_DIST_TO_PIVOT):
                logs.append(f"   ⏸️  {ticker}: Distance {analysis['dist_to_pivot']:+.1f}% outside ±{MAX_DIST_TO_PIVOT}% (Current ${analysis['current']:.2f}, Pivot ${analysis['pivot']:.2f})")
                rejected_distance += 1
                continue

            eligible += 1
            logs.append(f"   ✅ {ticker}: Score {analysis['entry_score']:.0f}, Distance {analysis['dist_to_pivot']:+.1f}% - EXECUTING")
            print("\n".join(logs))
            logs.clear()
            self._execute_entry(analysis)

        # Print accumulated logs
        if logs:
            print("\n".join(logs))

        if checked > 0:
            print(f"\n📊 Entry Check Summary: Checked {checked} | Eligible {eligible} | Rejected (score) {rejected_score} | Rejected (distance) {rejected_distance}")

    def _execute_entry(self, analysis: Dict):
        """Execute entry via Alpaca."""
        ticker = analysis['ticker']

        # Check if already signaled today
        if ticker in self.signaled_tickers:
            print(f"   ⏸️  {ticker}: Already signaled today")
            return

        # Check if already have pending order
        if self.order_manager.has_pending_order(ticker):
            print(f"   ⏸️  {ticker}: Order already pending")
            return

        entry_price = analysis['current']
        stop_price = analysis['stop']
        target_price = analysis['target']
        sector = analysis['sector']

        # Calculate position size
        equity = self.state.get_equity()
        shares = self.exits.calculate_position_size(equity, entry_price, stop_price)
        position_value = entry_price * shares

        print(f"   📐 {ticker}: Position sizing - Equity ${equity:,.0f}, Entry ${entry_price:.2f}, Stop ${stop_price:.2f}")
        print(f"   📐 {ticker}: Calculated {shares} shares, Position value ${position_value:,.2f}")

        # Validate
        can_enter, reason = self.state.can_enter_position(sector, position_value)
        if not can_enter:
            print(f"   ⏸️  {ticker}: Risk validation failed - {reason}")
            return

        print(f"   🚀 {ticker}: Submitting order for {shares} shares...")

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
        else:
            print(f"   ❌ {ticker}: Order submission failed (check Alpaca API)")

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

        # WebSocket status
        if self.alpaca.is_ws_healthy():
            print(f"📡 WebSocket: Connected ({len(self.price_cache)} tickers cached)")
        else:
            print(f"📡 WebSocket: Disconnected (using REST fallback)")

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
        ws_task = None

        while self.running:
            try:
                # Start/restart WebSocket if not running
                if not ws_task or ws_task.done():
                    if ws_task and ws_task.done():
                        print("\n🔄 WebSocket task ended, restarting...")
                    ws_task = asyncio.create_task(self._start_websocket())
                    await asyncio.sleep(2)

                # Refresh SPY cache (will only fetch if new day or not cached)
                self._refresh_spy_cache()

                self._reset_daily_signals()
                self._print_status()
                self._process_pending_orders()

                if self._is_market_hours():
                    self._check_exits()
                    self._check_entries()
                else:
                    print("   ⏳ Market closed - monitoring only")

                # Countdown on single line
                print("\n⏱️  Next check in 30s...", end='', flush=True)
                for i in range(29, 0, -1):
                    if not self.running:
                        break
                    print(f"\r⏱️  Next check in {i}s... ", end='', flush=True)
                    await asyncio.sleep(1)
                print()  # New line after countdown

            except Exception as e:
                print(f"\n❌ Error in main loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)

        # Cleanup
        print("\n🛑 Stopping WebSocket...")
        await self.alpaca.stop_price_stream()
        if ws_task:
            ws_task.cancel()
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
