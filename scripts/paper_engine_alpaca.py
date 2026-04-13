#!/usr/bin/env python3
"""Alpaca-powered paper trading engine with real-time WebSocket data."""

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import pytz

# Add scripts directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from traderlib.alpaca_client import AlpacaClient
from traderlib.paper_state import PaperState, Position
from traderlib.paper_exits import ExitEngine, ExitSignal
from traderlib.order_manager import OrderManager, OrderStatus
from traderlib import calculate_stage2_score, get_entry_score
from traderlib.risk_config import RiskConfigManager, calculate_position_size_with_constraints
from traderlib.trading_exceptions import TradingExceptionHandler, critical, error, warning

# FINDING-007: Weekend/holiday market hours
from traderlib.market_hours import market_hours, is_market_open, is_trading_day, format_market_status

# Configurable paths - uses environment variable for testing
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'

# Market hours (Eastern Time)
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)


class AlpacaPaperEngine:
    """Paper trading engine using Alpaca for real-time data and execution."""

    def __init__(self, mode: str = 'paper', risk_profile: str = None):
        print("🔌 Initializing Alpaca client...")

        # Load risk configuration first
        self.risk_manager = RiskConfigManager(profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()

        self.alpaca = AlpacaClient(mode=mode)
        self.order_manager = OrderManager(self.alpaca)
        self.state = PaperState(initial_capital=self._get_account_value())

        # Pass risk config to ExitEngine
        self.exits = ExitEngine(risk_config=self.risk_config)

        self.running = False
        self.ws_running = False

        # Price cache from WebSocket
        self.price_cache: Dict[str, Dict] = {}
        self.ws_tickers: Set[str] = set()

        # Entry tracking
        self.signaled_tickers: Set[str] = set()
        self.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        # Cooldown tracking (FLY case study - prevents same-day re-entry after loss)
        # Format: {ticker: exit_timestamp}
        self.last_exit_time: Dict[str, datetime] = {}
        # Track consecutive losses per ticker for exponential backoff
        # Format: {ticker: consecutive_loss_count}
        self.consecutive_losses: Dict[str, int] = {}

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

        # Print risk summary
        self.risk_manager.print_summary()

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
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "watchlist_load", e,
                    severity=TradingExceptionHandler.CRITICAL,
                    file=str(WATCHLIST_PATH)
                )
                watchlist_sectors = {}

            # Sync positions via order manager
            sync_result = self.order_manager.sync_positions(self.state.positions)

            if sync_result['added']:
                for pos in sync_result['added']:
                    ticker = pos['ticker']
                    print(f"📥 Syncing {ticker} position from Alpaca")

                    # Get sector from watchlist, fallback to 'Unknown'
                    sector = watchlist_sectors.get(ticker, 'Unknown')

                    # DANGEROUS FALLBACK FIX: Don't estimate stop_price from Alpaca
                    # Look up stop from watchlist or mark as UNSYNCED
                    stop_price = pos['avg_price'] * 0.95  # Temporary until watchlist lookup
                    target_price = pos['avg_price'] * 1.1

                    # Try to get proper stop from watchlist
                    try:
                        row = watchlist_df[watchlist_df['Ticker'] == ticker]
                        if not row.empty and 'Stop_Level' in row.columns:
                            stop_val = row['Stop_Level'].values[0]
                            if pd.notna(stop_val) and stop_val > 0:
                                stop_price = float(stop_val)
                                # Recalculate target based on actual stop
                                risk = pos['avg_price'] - stop_price
                                target_price = pos['avg_price'] + (2 * risk) if risk > 0 else pos['avg_price'] * 1.05
                                print(f"   🎯 {ticker}: Stop ${stop_price:.2f} from watchlist")
                    except Exception:
                        pass

                    if stop_price == pos['avg_price'] * 0.95:
                        print(f"   ⚠️  {ticker}: No watchlist stop found - marking UNSYNCED")

                    position = Position(
                        ticker=ticker,
                        status='OPEN',
                        entry_date=datetime.now().isoformat(),
                        entry_price=pos['avg_price'],
                        shares=pos['qty'],
                        stop_price=stop_price,
                        target_price=target_price,
                        initial_risk=(pos['avg_price'] - stop_price) * pos['qty'] if stop_price else 0,
                        sector=sector,
                        current_stop_type='UNSYNCED' if stop_price == pos['avg_price'] * 0.95 else 'HARD',
                        initial_stop_price=stop_price  # FINDING-013: Immutable initial stop
                    )
                    self.state.positions[ticker] = position

            if sync_result['removed']:
                for ticker in sync_result['removed']:
                    print(f"📤 Position {ticker} closed externally")
                    if ticker in self.state.positions:
                        # Get current price for proper close recording
                        current_price = self._get_current_price(ticker)
                        if current_price is None:
                            # Fallback to entry price if can't get current
                            current_price = self.state.positions[ticker].entry_price

                        # Properly close position (records exit, P&L, cash, trade log)
                        position = self.state.close_position(
                            ticker=ticker,
                            exit_price=current_price,
                            reason='EXTERNAL_CLOSE'
                        )
                        if position:
                            print(f"   📊 Realized P&L: ${position.realized_pnl:,.2f}")

            if sync_result['discrepancies']:
                for disc in sync_result['discrepancies']:
                    print(f"⚠️ Position discrepancy: {disc['ticker']} - "
                          f"Alpaca: {disc['alpaca_qty']}, Local: {disc['local_qty']}")

            if sync_result['synced']:
                for pos in sync_result['synced']:
                    ticker = pos['ticker']
                    alpaca_entry = float(pos['avg_price'])
                    if ticker in self.state.positions:
                        local_pos = self.state.positions[ticker]
                        if abs(local_pos.entry_price - alpaca_entry) > 0.01:
                            print(f"📝 Syncing entry price for {ticker}: ${local_pos.entry_price:.2f} → ${alpaca_entry:.2f}")
                            local_pos.entry_price = alpaca_entry
                            self.state.save_state()

            # Update cash
            account = self.alpaca.get_account()
            self.state.cash = account['cash']

        except Exception as e:
            TradingExceptionHandler.log_exception(
                "alpaca_sync", e,
                severity=TradingExceptionHandler.ERROR
            )
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
        self.ws_running = False

    def _is_market_hours(self) -> bool:
        """Check if market is open.

        FINDING-007: Uses pandas_market_calendars for accurate market hours
        including holidays and early closes.
        """
        return is_market_open()

    def _is_pre_market(self) -> bool:
        """Check if pre-market hours.

        Note: Pre-market is not checked via market_hours module
        as it focuses on regular trading hours.
        """
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)

        if now.weekday() >= 5:
            return False

        current_time = (now.hour, now.minute)
        return (4, 0) <= current_time < MARKET_OPEN

    def _check_market_hours_for_trading(self) -> tuple:
        """Check if we should attempt trading based on market hours.

        FINDING-007: Returns (should_trade, status_message)
        """
        if not is_trading_day():
            return False, format_market_status()

        if not is_market_open():
            return False, format_market_status()

        return True, "Market open"

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
        except asyncio.CancelledError:
            # Normal shutdown - don't print error
            raise
        except Exception as e:
            # Log error but don't spam - only print if engine is still running
            if self.running:
                print(f"⚠️ WebSocket error: {e}")
        finally:
            self.ws_running = False
            # Only print polling message if engine is still running (not during shutdown)
            if self.running:
                print("📡 WebSocket disconnected. Using REST polling for prices.")

    def _load_watchlist_tickers(self) -> List[str]:
        """Load watchlist tickers."""
        if not WATCHLIST_PATH.exists():
            return []
        try:
            df = pd.read_csv(WATCHLIST_PATH)
            return df['Ticker'].tolist()
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "watchlist_ticker_load", e,
                severity=TradingExceptionHandler.WARNING,
                file=str(WATCHLIST_PATH)
            )
            return []

    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price via AlpacaClient (WebSocket cache + REST fallback).

        Uses AlpacaClient's cache (populated by WebSocket and batch pre-fetch)
        with a generous staleness window when the WebSocket is disconnected.
        Falls back to per-ticker REST only if the batch pre-fetch didn't
        populate this ticker.
        """
        # Check AlpacaClient cache first (fed by WebSocket + batch pre-fetch)
        # When WS is disconnected, allow stale prices up to 5 minutes
        max_age = 300 if not self.alpaca.is_ws_healthy() else None
        cached = self.alpaca.get_cached_price(ticker, max_age_seconds=max_age)
        if cached:
            self.price_cache[ticker] = {'price': cached, 'timestamp': datetime.now()}
            return cached

        # If batch pre-fetch already got this ticker, the cache hit above
        # would have returned it. Only try per-ticker REST for tickers
        # that the batch call didn't cover (e.g. newly added to watchlist).
        # Skip per-ticker REST if circuit breaker is open (avoid cascade).
        if not self.alpaca.rate_limiter.circuit_open:
            price = self.alpaca.get_latest_price(ticker)
            if price:
                self.price_cache[ticker] = {'price': price, 'timestamp': datetime.now()}
                return price

        # Final fallback: use stale engine cache if available (better than nothing)
        if ticker in self.price_cache:
            age = (datetime.now() - self.price_cache[ticker].get('timestamp', datetime.now())).total_seconds()
            if age < 300:  # Accept up to 5 minutes stale
                print(f"   ⚠️  {ticker}: Using stale price from cache ({age:.0f}s old)")
                return self.price_cache[ticker]['price']

        return None

    def _check_cooldown(self, ticker: str) -> tuple[bool, Optional[str]]:
        """Check if ticker is in re-entry cooldown period.

        Args:
            ticker: Ticker symbol to check

        Returns:
            Tuple of (can_enter: bool, reason: Optional[str])
            - can_enter: True if entry is allowed, False if in cooldown
            - reason: Explanation if entry blocked, None if allowed

        See: memory/2026-04-11-fly-reentry-lesson.md - FLY case study
        """
        cooldown_cfg = self.risk_config.cooldown

        # Check if we have exit history for this ticker
        if ticker not in self.last_exit_time:
            return True, None

        last_exit = self.last_exit_time[ticker]
        elapsed_minutes = (datetime.now() - last_exit).total_seconds() / 60

        # Calculate effective cooldown with exponential backoff
        consecutive_count = self.consecutive_losses.get(ticker, 0)
        base_cooldown = cooldown_cfg.reentry_cooldown_minutes
        multiplier = cooldown_cfg.consecutive_loss_multiplier ** consecutive_count
        effective_cooldown = min(
            base_cooldown * multiplier,
            cooldown_cfg.max_cooldown_minutes
        )

        if elapsed_minutes < effective_cooldown:
            remaining = effective_cooldown - elapsed_minutes
            return False, f"Cooldown: {remaining:.0f}min remaining ({consecutive_count} consecutive losses)"

        return True, None

    def _record_position_exit(self, ticker: str, realized_pnl: float):
        """Record position exit for cooldown tracking.

        Args:
            ticker: Ticker symbol that was exited
            realized_pnl: P&L from the trade (positive = profit, negative = loss)
        """
        cooldown_cfg = self.risk_config.cooldown

        # Record exit time
        self.last_exit_time[ticker] = datetime.now()

        # Check if this was a losing trade
        min_loss_pct = cooldown_cfg.min_loss_to_trigger_cooldown_pct
        # Determine if it's a loss based on dollar amount
        is_loss = realized_pnl < 0

        if is_loss:
            # Increment consecutive loss count
            current_count = self.consecutive_losses.get(ticker, 0)
            self.consecutive_losses[ticker] = current_count + 1
            print(f"   ⏱️  {ticker}: Exit recorded (loss ${realized_pnl:.2f}), "
                  f"consecutive losses: {self.consecutive_losses[ticker]}")
        else:
            # Reset consecutive loss count on profit
            if ticker in self.consecutive_losses:
                del self.consecutive_losses[ticker]
                print(f"   ⏱️  {ticker}: Exit recorded (profit ${realized_pnl:.2f}), cooldown reset")

    def _check_market_conditions(self) -> tuple:
        """Check SPY market conditions using configured thresholds."""
        spy_price = self._get_current_price('SPY')
        if spy_price is None:
            return False, "Cannot fetch SPY"

        # Get yesterday's close from Alpaca for comparison
        try:
            hist = self.alpaca.get_historical_bars('SPY', days=5)
            if hist is not None and len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                change_pct = ((spy_price / prev_close) - 1) * 100

                max_decline = self.risk_config.market.max_spy_decline_pct
                if change_pct < max_decline:
                    return False, f"SPY {change_pct:+.2f}% (below {max_decline}%)"

                return True, f"SPY {change_pct:+.2f}%"
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "market_condition_check", e,
                severity=TradingExceptionHandler.ERROR,
                ticker="SPY"
            )

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
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "sector_lookup", e,
                    severity=TradingExceptionHandler.WARNING,
                    ticker=ticker,
                    file=str(WATCHLIST_PATH)
                )

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

            # Use ATR from Alpaca data (already calculated above)
            atr_stop = current - (2 * atr)
            # Get recent low from Alpaca data for support
            recent_low = hist['Low'].tail(10).min()
            stop = max(atr_stop, recent_low)
            # Sanity check: stop should be 3-15% below entry
            if stop > current * 0.97:
                stop = current * 0.97
            elif stop < current * 0.85:
                stop = current * 0.85

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

    async def _check_exits(self):
        """Check all open positions for exits."""
        for ticker in list(self.state.positions.keys()):
            # Run blocking price fetch in thread
            current_price = await asyncio.to_thread(self._get_current_price, ticker)
            if current_price is None:
                continue

            position = self.state.positions[ticker]
            signal = self.exits.evaluate_exit(position, current_price)

            if signal.should_exit:
                asyncio.create_task(self._execute_exit(ticker, signal))

    async def _check_entries(self):
        """Scan for entry opportunities using configured thresholds."""
        watchlist = self._load_watchlist_tickers()
        if not watchlist:
            print("⏸️  No tickers in watchlist")
            return

        # Pre-fetch prices BEFORE market check (SPY needs a price for the gate)
        batch_tickers = list(set(watchlist + ['SPY']))
        batch_prices = await asyncio.to_thread(self.alpaca.get_latest_prices_batch, batch_tickers)
        missing = [t for t, p in batch_prices.items() if p is None]
        if missing:
            print(f"   ℹ️  Batch pre-fetch: {len(batch_tickers) - len(missing)}/{len(batch_tickers)} prices fetched, {len(missing)} unavailable ({', '.join(missing[:5])}{'...' if len(missing) > 5 else ''})")

        market_ok, market_msg = self._check_market_conditions()
        if not market_ok:
            print(f"⏸️  Market condition failed: {market_msg}")
            return

        print(f"\n🔍 Checking {len(watchlist)} tickers for entry signals...")

        # Get thresholds from config
        entry_threshold = self.risk_config.entry.min_entry_score
        max_dist = self.risk_config.entry.max_dist_to_pivot_pct

        checked = 0
        eligible = 0
        rejected_score = 0
        rejected_distance = 0
        rejected_stop = 0
        logs = []

        for ticker in watchlist:
            checked += 1
            analysis = await asyncio.to_thread(self._analyze_ticker, ticker)
            if not analysis:
                continue

            # Entry criteria with detailed logging (accumulate for batch output)
            if analysis['entry_score'] < entry_threshold:
                logs.append(f"   ⏸️  {ticker}: Score {analysis['entry_score']:.0f} < {entry_threshold} (need Tier 1)")
                rejected_score += 1
                continue

            # Symmetric distance filter
            if not (-max_dist <= analysis['dist_to_pivot'] <= max_dist):
                logs.append(f"   ⏸️  {ticker}: Distance {analysis['dist_to_pivot']:+.1f}% outside ±{max_dist}%")
                rejected_distance += 1
                continue

            # Check stop distance is within configured limits
            stop_dist_pct = abs(analysis['stop'] - analysis['current']) / analysis['current'] * 100
            max_stop_pct = self.risk_config.stop_loss.max_stop_distance_pct * 100
            if stop_dist_pct > max_stop_pct:
                logs.append(f"   ⏸️  {ticker}: Stop {stop_dist_pct:.1f}% exceeds max {max_stop_pct:.1f}%")
                rejected_stop += 1
                continue

            eligible += 1
            logs.append(f"   ✅ {ticker}: Score {analysis['entry_score']:.0f}, Distance {analysis['dist_to_pivot']:+.1f}%, Stop {stop_dist_pct:.1f}% - EXECUTING")
            print("\n".join(logs))
            logs.clear()
            self._execute_entry(analysis)

        # Print accumulated logs
        if logs:
            print("\n".join(logs))

        if checked > 0:
            print(f"\n📊 Entry Check Summary: Checked {checked} | Eligible {eligible} | Rejected (score) {rejected_score} | Rejected (dist) {rejected_distance} | Rejected (stop) {rejected_stop}")

    def _execute_entry(self, analysis: Dict):
        """Execute entry via Alpaca."""
        ticker = analysis['ticker']

        # FINDING-007: Check market hours before entering
        can_trade, status_msg = self._check_market_hours_for_trading()
        if not can_trade:
            print(f"   ⏸️  {ticker}: {status_msg}")
            return

        # Check if already signaled today
        if ticker in self.signaled_tickers:
            print(f"   ⏸️  {ticker}: Already signaled today")
            return

        # Check re-entry cooldown (prevents FLY-style immediate re-entry after loss)
        can_enter, cooldown_reason = self._check_cooldown(ticker)
        if not can_enter:
            print(f"   ⏸️  {ticker}: {cooldown_reason}")
            return

        # Check if already have pending order
        if self.order_manager.has_pending_order(ticker):
            print(f"   ⏸️  {ticker}: Order already pending")
            return

        entry_price = analysis['current']
        stop_price = analysis['stop']
        target_price = analysis['target']
        sector = analysis['sector']

        # Calculate position size with dual constraint system
        equity = self.state.get_equity()
        shares = self.exits.calculate_position_size(equity, entry_price, stop_price)

        # Get calculation metadata for logging
        calc_meta = self.exits.get_last_position_calc() or {}
        position_value = shares * entry_price if shares else 0

        # Log detailed position sizing
        print(f"   📐 {ticker}: Position sizing - Equity ${equity:,.0f}")
        print(f"      Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f} | Risk/share: ${calc_meta.get('risk_per_share', entry_price-stop_price):.2f}")
        print(f"      Stop distance: {calc_meta.get('stop_distance_pct', 0):.1f}%")

        if calc_meta.get('constraints_applied'):
            for constraint in calc_meta['constraints_applied']:
                print(f"      🔧 {constraint}")

        if calc_meta.get('rejected'):
            print(f"   ⏸️  {ticker}: Position rejected - {calc_meta.get('rejection_reason', 'unknown')}")
            return

        if shares == 0:
            print(f"   ⏸️  {ticker}: Position size is zero")
            return

        print(f"      Shares: {shares} | Position value: ${position_value:,.2f} ({calc_meta.get('position_pct', 0):.1f}% of equity)")
        print(f"      Account risk: ${calc_meta.get('account_risk_dollars', 0):.2f} ({calc_meta.get('account_risk_pct', 0):.2f}%)")

        # Validate
        can_enter, reason = self.state.can_enter_position(sector, position_value, self.risk_config)
        if not can_enter:
            print(f"   ⏸️  {ticker}: Risk validation failed - {reason}")
            return

        print(f"   🚀 {ticker}: Submitting order for {shares} shares...")

        # Submit order via order manager with entry metadata
        # Position will be created on fill confirmation, not immediately
        order = self.order_manager.submit_entry(
            ticker=ticker,
            shares=shares,
            stop_price=stop_price,
            target_price=target_price,
            sector=sector,
            expected_entry_price=entry_price
        )

        if order:
            # DO NOT create position here - prevents split-brain on crash
            # Position will be created when order fills in _process_pending_orders
            self.signaled_tickers.add(ticker)

            print(f"\n🚀 AUTO-ENTRY: {ticker} at ${entry_price:.2f} x {shares} shares")
            print(f"   Order ID: {order.id}")
            print(f"   Stop: ${stop_price:.2f} | Target: ${target_price:.2f}")
            print(f"   ⏳ Waiting for fill confirmation...")
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

                # Record exit for cooldown tracking (FLY case study)
                realized_pnl = position.realized_pnl or 0.0
                self._record_position_exit(ticker, realized_pnl)

    async def _process_pending_orders(self):
        """Check status of all pending orders."""
        if self.order_manager.get_pending_count() == 0:
            return

        # Run blocking API calls in thread pool
        filled = await asyncio.to_thread(self.order_manager.process_all_pending)
        for order in filled:
            if order.side == 'buy':
                print(f"✅ Entry filled: {order.ticker} "
                      f"@${order.filled_price:.2f} x {order.filled_qty}")

                # SPLIT-BRAIN FIX: Create position ONLY when order is confirmed filled
                # This prevents phantom positions if crash occurs between submit and fill
                if order.ticker not in self.state.positions:
                    # Position doesn't exist yet - create it with fill data
                    actual_fill = order.filled_price or order.expected_entry_price

                    # PARTIAL FILL FIX: Use actual filled_qty, not order.qty
                    # filled_qty accumulates across partial fills
                    if order.filled_qty and order.filled_qty > 0:
                        filled_qty = int(order.filled_qty)
                    else:
                        print(f"   ⚠️  {order.ticker}: No filled_qty recorded - using order qty")
                        filled_qty = order.qty

                    # DANGEROUS FALLBACK FIX: Require explicit stop_price from order
                    # Don't silently default to 5% below fill
                    if not order.stop_price or order.stop_price <= 0:
                        print(f"   ⚠️  {order.ticker}: No stop_price in order - cannot create position")
                        continue  # Skip position creation - missing stop is a critical error

                    stop_price = order.stop_price
                    sector = order.sector or 'Unknown'

                    # Calculate target from actual stop (2R)
                    risk = actual_fill - stop_price
                    target_price = order.target_price or (actual_fill + (2 * risk) if risk > 0 else actual_fill * 1.05)

                    position = self.state.enter_position(
                        ticker=order.ticker,
                        entry_price=actual_fill,
                        shares=filled_qty,
                        stop_price=stop_price,
                        target_price=target_price,
                        sector=sector
                    )
                    print(f"   📝 Created position: ${actual_fill:.2f} x {filled_qty} shares")
                else:
                    # Position already exists (shouldn't happen with new flow, but handle gracefully)
                    actual_fill = order.filled_price
                    if actual_fill:
                        pos = self.state.positions[order.ticker]
                        old_entry = pos.entry_price
                        pos.entry_price = actual_fill
                        # Recalculate target based on new entry price
                        risk = actual_fill - pos.stop_price
                        pos.target_price = actual_fill + (2 * risk) if risk > 0 else actual_fill * 1.05
                        # Recalculate initial_risk
                        pos.initial_risk = risk * pos.shares
                        self.state.save_state()
                        print(f"   📝 Updated entry price: ${old_entry:.2f} → ${actual_fill:.2f}")
            else:
                # Exit orders - position is closed by order_manager or elsewhere
                print(f"✅ Exit filled: {order.ticker} "
                      f"(${order.reason})")

    def _reset_daily_signals(self):
        """Reset entry signals for new day."""
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_signal_reset != current_date:
            self.signaled_tickers.clear()
            self.last_signal_reset = current_date

            # Clear cooldown tracking for fresh start (exits from yesterday don't block today)
            self.last_exit_time.clear()
            self.consecutive_losses.clear()

            print(f"\n📅 New day: Reset entry signals and cooldown tracking")

    async def _print_status(self):
        """Print current status."""
        print(f"\n{'='*60}")
        # DESIGN FIX: Add ET timezone suffix to timestamp
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET")
        # FINDING-007: Use detailed market status including holidays
        print(f"📈 Market: {format_market_status()}")

        # WebSocket status
        if self.alpaca.is_ws_healthy():
            print(f"📡 WebSocket: Connected ({len(self.price_cache)} tickers cached)")
        else:
            print(f"📡 WebSocket: Disconnected (using REST fallback)")

        stats = self.state.get_stats()
        orders = self.order_manager.get_orders_summary()

        # Calculate Account Value and Unrealized PnL
        # Fetch prices asynchronously if not in cache
        account_value = stats['cash']
        unrealized_pnl = 0.0
        for ticker, pos in self.state.positions.items():
            if pos.status == 'OPEN':
                # Try cache first
                current_price = self.price_cache.get(ticker, {}).get('price')
                if current_price is None:
                    current_price = self.alpaca.get_cached_price(ticker)
                # Fetch via REST if not cached (non-blocking)
                if current_price is None:
                    current_price = await asyncio.to_thread(self.alpaca.get_latest_price, ticker)
                if current_price:
                    account_value += current_price * pos.shares
                    unrealized_pnl += (current_price - pos.entry_price) * pos.shares

        print(f"💰 Account Value: ${account_value:,.2f} | Cash: ${stats['cash']:,.2f}", flush=True)
        print(f"📊 Open: {stats['open_positions']} | Day P&L: ${stats['day_pnl']:,.2f} | Unrealized: ${unrealized_pnl:,.2f}", flush=True)

        # Rate limit status
        rl = self.alpaca.rate_limiter.get_status()
        rl_pct = rl['requests_in_window'] / rl['max_requests'] * 100 if rl['max_requests'] > 0 else 0
        circuit = "🔴 OPEN" if rl['circuit_open'] else "🟢 closed"
        print(f"📡 API: {rl['requests_in_window']}/{rl['max_requests']} requests/min ({rl_pct:.0f}%) | Circuit: {circuit}", flush=True)
        print(f"📋 Pending Orders: {orders['pending']}", flush=True)
        # Skip health summary for now - potential deadlock in rate limiter
        print(f"{'='*60}", flush=True)

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
                        delay = self.alpaca.ws_reconnect_delay
                        # Check if task ended with exception
                        if ws_task.exception():
                            exc = ws_task.exception()
                            # Suppress verbose error messages for common WebSocket disconnects
                            if "no close frame" in str(exc) or "ConnectionClosed" in type(exc).__name__:
                                print(f"\n🔄 WebSocket disconnected, restarting in {delay}s...")
                            else:
                                print(f"\n🔄 WebSocket error ({type(exc).__name__}), restarting in {delay}s...")
                        else:
                            print(f"\n🔄 WebSocket task ended, restarting in {delay}s...")
                        await asyncio.sleep(delay)
                    ws_task = asyncio.create_task(self._start_websocket())
                    await asyncio.sleep(2)

                # Refresh SPY cache (will only fetch if new day or not cached)
                self._refresh_spy_cache()

                self._reset_daily_signals()
                await self._print_status()
                await self._process_pending_orders()

                if self._is_market_hours():
                    await self._check_exits()
                    await self._check_entries()
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

        # Cleanup - Cancel task first, then cleanup resources
        print("\n🛑 Stopping WebSocket...")
        if ws_task:
            ws_task.cancel()
            try:
                await asyncio.wait_for(ws_task, timeout=3.0)
            except asyncio.CancelledError:
                print("   ✓ WebSocket task cancelled")
            except asyncio.TimeoutError:
                print("   ⚠ WebSocket task timeout (forcing)")
        # Stop the stream after task is cancelled
        try:
            await asyncio.wait_for(self.alpaca.stop_price_stream(), timeout=2.0)
        except Exception:
            pass  # Ignore cleanup errors
        print("✅ Engine stopped gracefully")


def main():
    parser = argparse.ArgumentParser(description='Alpaca Paper Trading Engine')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                        help='Trading mode (default: paper)')
    parser.add_argument('--risk-profile', type=str, default=None,
                        help='Risk profile from config (conservative, aggressive, tight_stops)')
    parser.add_argument('--risk-summary', action='store_true',
                        help='Print risk configuration and exit')
    args = parser.parse_args()

    # If just printing risk summary
    if args.risk_summary:
        manager = RiskConfigManager(profile=args.risk_profile)
        manager.print_summary()
        return

    engine = AlpacaPaperEngine(mode=args.mode, risk_profile=args.risk_profile)
    asyncio.run(engine.run())


if __name__ == "__main__":
    main()
