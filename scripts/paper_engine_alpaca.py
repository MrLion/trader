#!/usr/bin/env python3
"""Alpaca-powered paper trading engine with real-time WebSocket data."""

import argparse
import asyncio
import json
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import pytz

# Add repo root to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# TUI Dashboard (optional — falls back to plain text)
try:
    from traderlib.dashboard import Dashboard
except ImportError:
    Dashboard = None

from traderlib.alpaca_client import AlpacaClient
from traderlib.earnings_calendar import EarningsCalendar
from traderlib.paper_state import PaperState, Position
from traderlib.paper_exits import ExitEngine, ExitSignal, ExitAction, ExitActionType
from traderlib.order_manager import OrderManager, OrderStatus
from traderlib import calculate_stage2_score, get_entry_score, get_stage2_details
from traderlib.paths import data_dir, project_root
from traderlib.risk_config import RiskConfigManager, calculate_position_size_with_constraints
from traderlib.trading_exceptions import TradingExceptionHandler, critical, error, warning
from traderlib.backtest.data_provider import DataFrameProvider
from traderlib.ticker_analyzer import TickerAnalyzer, TickerAnalysis
from traderlib.sector_resolver import SectorResolver

# FINDING-007: Weekend/holiday market hours
from traderlib.market_hours import market_hours, is_market_open, is_trading_day, next_market_open, format_market_status

# Configurable paths - resolved via traderlib.paths so PAPER_TRADING_DATA_DIR is honored
DATA_DIR = data_dir()
WATCHLIST_PATH = DATA_DIR / 'watchlist.csv'

# Market hours (Eastern Time)
MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)


# Paper engine data provider adapter
class AlpacaDataProviderAdapter:
    """Adapter to make AlpacaClient compatible with DataFrameProvider protocol."""

    def __init__(self, alpaca: AlpacaClient):
        self.alpaca = alpaca

    def get_bars(self, ticker: str, as_of, min_rows: int = 30):
        """Get historical bars."""
        return self.alpaca.get_bars(ticker, limit=min_rows)

    def get_current_price(self, ticker: str, as_of=None):
        """Get current price (from latest bar or quote)."""
        return self.alpaca.get_current_price(ticker)


class AlpacaPaperEngine:
    """Paper trading engine using Alpaca for real-time data and execution."""

    def __init__(self, mode: str = 'paper', risk_profile: str = None, dashboard=None):
        print("🔌 Initializing Alpaca client...")

        # Mode-specific data directory for state isolation
        # Use module-level DATA_DIR so test patches on paper_engine_alpaca.DATA_DIR take effect
        root_data_dir = DATA_DIR
        self.mode = mode
        self.mode_data_dir = root_data_dir / mode
        self.mode_data_dir.mkdir(parents=True, exist_ok=True)

        # Run one-time migration from old flat layout to mode-specific directories
        self._migrate_old_layout()

        # Mode-specific risk config path
        config_path = project_root() / 'config' / mode / 'risk_config.yaml'
        self.risk_manager = RiskConfigManager(config_path=config_path, profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()

        self.alpaca = AlpacaClient(mode=mode)
        self.order_manager = OrderManager(self.alpaca, data_dir=self.mode_data_dir)
        self.state = PaperState(initial_capital=self._get_account_value(), 
                                data_dir=self.mode_data_dir, mode=mode)
        self.analyzer = TickerAnalyzer(self.alpaca, self.risk_config, WATCHLIST_PATH)

        # Pass risk config to ExitEngine
        self.exits = ExitEngine(risk_config=self.risk_config)

        # Earnings calendar — gates entries and forces exits before earnings events
        self.earnings_calendar = EarningsCalendar()

        self.data_provider = AlpacaDataProviderAdapter(self.alpaca)

        self.running = False
        self.ws_running = False
        self.shutdown_requested = False  # Set True on Ctrl+C for graceful shutdown

        # Price cache from WebSocket
        self.price_cache: Dict[str, Dict] = {}
        self.ws_tickers: Set[str] = set()

        # Alpaca historical bars for exit engine (replaces yfinance fallback)
        self._alpaca_bar_cache: Dict[str, pd.DataFrame] = {}

        # Entry tracking
        self.signaled_tickers: Set[str] = set()
        self.last_signal_reset = datetime.now().strftime('%Y-%m-%d')

        # Cooldown tracking (FLY case study - prevents same-day re-entry after loss)
        # Format: {ticker: exit_timestamp}
        self.last_exit_time: Dict[str, datetime] = {}
        # Track consecutive losses per ticker for exponential backoff
        # Format: {ticker: consecutive_loss_count}
        self.consecutive_losses: Dict[str, int] = {}

        # Rebuild cooldown state from trade log after restart
        self._rebuild_cooldown_state()

        # Market data
        self.spy_data = None

        # Setup signal handlers (save old ones for cleanup)
        self._old_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self._old_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)

        # Account sync
        self._sync_with_alpaca()

        # Use passed-in dashboard or create a new one
        self.dashboard = dashboard
        if self.dashboard is None:
            try:
                self.dashboard = Dashboard() if Dashboard else None
            except Exception:
                self.dashboard = None

        print(f"✅ Engine ready - Mode: {mode.upper()}")
        print(f"📋 Pending orders: {self.order_manager.get_pending_count()}")

        # Print risk summary
        self.risk_manager.print_summary()

    def _migrate_old_layout(self) -> None:
        """Migrate old flat data files into mode-specific subdirectory (one-time)."""
        if self.mode != 'paper':
            return
        old_dir = self.mode_data_dir.parent  # data/
        old_files = [
            ('paper_positions.json', 'positions.json'),
            ('paper_trades.jsonl', 'trades.jsonl'),
            ('alpaca_orders.json', 'orders.json'),
        ]
        migrated = False
        for old_name, new_name in old_files:
            old_path = old_dir / old_name
            new_path = self.mode_data_dir / new_name
            if old_path.exists() and not new_path.exists():
                try:
                    import shutil
                    shutil.move(str(old_path), str(new_path))
                    print(f"📦 Migrated {old_name} -> {self.mode_data_dir.name}/{new_name}")
                    migrated = True
                except Exception as e:
                    print(f"⚠️  Migration failed for {old_name}: {e}")
        if migrated:
            # Also migrate daily_tracker if it exists at root level
            old_tracker = old_dir / 'daily_tracker.json'
            new_tracker = self.mode_data_dir / 'daily_tracker.json'
            if old_tracker.exists() and not new_tracker.exists():
                try:
                    import shutil
                    shutil.move(str(old_tracker), str(new_tracker))
                    print(f"📦 Migrated daily_tracker.json -> {self.mode_data_dir.name}/")
                except Exception as e:
                    print(f"⚠️  Migration failed for daily_tracker.json: {e}")

    def _get_account_value(self) -> float:
        """Get initial account value from Alpaca."""
        try:
            account = self.alpaca.get_account()
            return account['equity']
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "account_value_fetch", e,
                severity=TradingExceptionHandler.WARNING,
            )
            print(f"❌ Alpaca account fetch failed: {e}")
            print("   ⚠️  Paper engine MUST start with real account value.")
            raise RuntimeError(
                f"Cannot start engine: Alpaca account fetch failed ({e}). "
                "Check API credentials and network."
            ) from e

    def _sync_with_alpaca(self):
        """Sync local state with Alpaca positions."""
        try:
            # Load watchlist for Stop_Level / Pivot_Price lookup
            watchlist_df = None
            try:
                watchlist_df = pd.read_csv(WATCHLIST_PATH)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "watchlist_load", e,
                    severity=TradingExceptionHandler.CRITICAL,
                    file=str(WATCHLIST_PATH)
                )

            # Sector resolver for unified sector lookup
            sector_resolver = SectorResolver()

            # Sync positions via order manager
            sync_result = self.order_manager.sync_positions(self.state.positions)

            if sync_result['added']:
                for pos in sync_result['added']:
                    ticker = pos['ticker']

                    # Shared field resolution for both merge and create paths
                    # Get sector via unified resolver (watchlist -> universe -> FMP)
                    sector = sector_resolver.resolve(ticker)

                    # DANGEROUS FALLBACK FIX: Don't estimate stop_price from Alpaca
                    # Look up stop from watchlist or mark as UNSYNCED
                    stop_price = pos['avg_price'] * 0.95  # Temporary until watchlist lookup
                    target_price = pos['avg_price'] * 1.1

                    r_mult = 2.0  # Default risk multiple before watchlist lookup

                    # Try to get proper stop from watchlist
                    try:
                        if watchlist_df is not None:
                            row = watchlist_df[watchlist_df['Ticker'] == ticker]
                            if not row.empty and 'Stop_Level' in row.columns:
                                stop_val = row['Stop_Level'].values[0]
                                if pd.notna(stop_val) and stop_val > 0:
                                    stop_price = float(stop_val)
                                    # Recalculate target based on actual stop
                                    risk = pos['avg_price'] - stop_price
                                    r_mult = self.risk_config.profit_target.min_r_multiple if self.risk_config else 2.0
                                    target_price = pos['avg_price'] + (r_mult * risk) if risk > 0 else pos['avg_price'] * 1.05
                                    print(f"   🎯 {ticker}: Stop ${stop_price:.2f} from watchlist")
                    except Exception as e:
                        TradingExceptionHandler.log_exception(
                            "watchlist_stop_lookup", e,
                            severity=TradingExceptionHandler.WARNING,
                            ticker=ticker, file=str(WATCHLIST_PATH)
                        )

                    if stop_price == pos['avg_price'] * 0.95:
                        print(f"   ⚠️  {ticker}: No watchlist stop found - marking UNSYNCED")

                    new_stop_type = 'UNSYNCED' if stop_price == pos['avg_price'] * 0.95 else 'HARD'

                    # Defensive: ticker may have been added locally since sync_positions ran,
                    # or load_state may have recovered it from trade log. Merge if exists.
                    if ticker in self.state.positions:
                        # MERGE path: update existing position
                        existing = self.state.positions[ticker]
                        old_shares = existing.shares
                        old_stop = existing.stop_price
                        existing.shares = pos['qty']
                        existing.entry_price = pos['avg_price']
                        existing.stop_price = stop_price
                        existing.target_price = target_price
                        existing.current_stop_type = new_stop_type
                        existing.sector = sector
                        if existing.stop_price and existing.stop_price > 0:
                            existing.initial_risk = (existing.entry_price - existing.stop_price) * existing.shares
                        # Preserve entry_min_r when target was recalculated from a watchlist-derived stop
                        if new_stop_type != 'UNSYNCED':
                            existing.entry_min_r = r_mult
                        self.state.save_state()
                        print(
                            f"   🔄 {ticker}: Sync merge — shares {old_shares}→{pos['qty']}, "
                            f"stop ${old_stop:.2f}→${stop_price:.2f}"
                        )
                        try:
                            TradingExceptionHandler.log_exception(
                                "sync_merge",
                                Exception("Sync merge"),
                                severity=TradingExceptionHandler.INFO,
                                ticker=ticker,
                                old_shares=old_shares,
                                new_shares=pos['qty'],
                                old_stop=old_stop,
                                new_stop=stop_price,
                                initial_stop=existing.initial_stop_price,
                                entry_date=existing.entry_date,
                            )
                        except Exception:
                            pass
                        continue

                    # CREATE path: new position
                    print(f"📥 Syncing {ticker} position from Alpaca (new)")
                    try:
                        TradingExceptionHandler.log_exception(
                            "sync_new",
                            Exception("Sync new"),
                            severity=TradingExceptionHandler.WARNING,
                            ticker=ticker,
                            data_source="Alpaca",
                            initial_stop=stop_price,
                            entry_date=datetime.now().isoformat(),
                        )
                    except Exception:
                        pass
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
                        current_stop_type=new_stop_type,
                        initial_stop_price=stop_price,  # FINDING-013: Immutable initial stop
                        entry_min_r=r_mult,
                    )
                    self.state.positions[ticker] = position
                    self.state.save_state()

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
                        # Re-resolve sector if still Unknown (positions from before sector enrichment)
                        if getattr(local_pos, 'sector', 'Unknown') == 'Unknown':
                            resolved = sector_resolver.resolve(ticker)
                            if resolved != 'Unknown':
                                local_pos.sector = resolved
                                print(f"   🏷️  {ticker}: sector resolved → {resolved}")
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

    def _cleanup(self):
        """Restore original signal handlers so main() can use its own."""
        signal.signal(signal.SIGINT, self._old_sigint)
        signal.signal(signal.SIGTERM, self._old_sigterm)

    def _signal_handler(self, signum, frame):
        """Graceful shutdown. Force-exits on second Ctrl+C."""
        if not self.running:
            # Second Ctrl+C — force exit
            print("\n⚡ Force exit")
            import os
            os._exit(1)
        # Restore normal terminal screen immediately so the shutdown message is visible
        if hasattr(self, 'dashboard') and self.dashboard:
            self.dashboard.stop_now()
        print("\n\n🛑 Shutdown signal received. Stopping gracefully...")
        print("   (Press Ctrl+C again to force exit)")
        self.shutdown_requested = True  # Signal to main() not to restart
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
        # NEW: Guard - don't start WebSocket when market closed
        if not is_market_open():
            return False

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

    def _get_historical_for_exits(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch historical daily bars from Alpaca for exit engine EMA calculations.

        Cached per ticker for the session lifetime — daily bars don't change
        intraday, so one fetch per ticker is enough. Replaces the yfinance
        fallback in ExitEngine._get_ema_values.
        """
        if ticker in self._alpaca_bar_cache:
            return self._alpaca_bar_cache[ticker]

        ema_long = self.risk_config.profit_target.ema_long_period if self.risk_config else 21
        try:
            df = self.alpaca.get_bars(ticker, limit=ema_long + 40)
            if df is not None and len(df) >= ema_long:
                self._alpaca_bar_cache[ticker] = df
                return df
        except Exception:
            pass
        return None

    def _get_current_prices_map(self) -> Dict[str, float]:
        """Extract ticker->price map from price cache for equity calculations."""
        return {
            ticker: data['price']
            for ticker, data in self.price_cache.items()
            if data.get('price')
        }

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



    def _handle_scale_out_fill(self, order, fill_price: float):
        """Handle a scale-out (partial exit) order fill.

        Shares were already reduced and scale_out_history recorded when the
        order was submitted. Here we just update cash, log the event, and keep
        the position open — NOT close_position() which would delete it entirely.

        Args:
            order: The filled Order object (order.qty = shares sold).
            fill_price: Actual fill price from Alpaca.
        """
        position = self.state.positions[order.ticker]
        shares_sold = order.qty
        realized_pnl = (fill_price - position.entry_price) * shares_sold
        self.state.cash += fill_price * shares_sold

        # Log scale-out fill to trades.jsonl with the actual shares sold
        trade_record = {
            'event': 'EXIT',
            'timestamp': datetime.now().isoformat(),
            'ticker': order.ticker,
            'entry_price': position.entry_price,
            'exit_price': fill_price,
            'shares': shares_sold,
            'realized_pnl': realized_pnl,
            'exit_reason': order.reason,
            'stop_type': position.current_stop_type,
            'initial_stop_price': position.initial_stop_price or 0.0,
            'initial_risk': getattr(position, 'initial_risk', 0.0),
            '_meta': {
                'test_mode': False,
                'data_dir': str(self.state.data_dir),
                'source': 'paper_engine',
                'partial_exit': True,
                'remaining_shares': position.shares,
            }
        }
        with open(self.state.trades_file, 'a') as f:
            f.write(json.dumps(trade_record) + '\n')

        if self.dashboard:
            self.dashboard.log_event({
                "type": "EXIT",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "ticker": order.ticker,
                "detail": f"Scale-out {shares_sold} @ ${fill_price:.2f}",
                "pnl": realized_pnl,
            })

        print(f"   📤 Scale-out filled: {order.ticker} {shares_sold} shares "
              f"@ ${fill_price:.2f} ({order.reason})")
        print(f"   📤 {position.shares} shares remain | P&L: ${realized_pnl:+.2f}")

    def _get_active_cooldowns(self) -> Dict[str, float]:
        """Return active cooldowns for dashboard display.

        Returns:
            Dict mapping ticker -> remaining minutes.
        """
        active = {}
        cooldown_cfg = self.risk_config.cooldown
        for ticker, last_exit in self.last_exit_time.items():
            elapsed_minutes = (datetime.now() - last_exit).total_seconds() / 60
            consecutive_count = self.consecutive_losses.get(ticker, 0)
            base_cooldown = cooldown_cfg.reentry_cooldown_minutes
            multiplier = cooldown_cfg.consecutive_loss_multiplier ** consecutive_count
            effective_cooldown = min(
                base_cooldown * multiplier,
                cooldown_cfg.max_cooldown_minutes
            )
            remaining = effective_cooldown - elapsed_minutes
            if remaining > 0:
                active[ticker] = remaining
        return active

    def _get_today_trade_stats(self) -> Dict[str, Any]:
        """Return today's closed trade statistics from trade log.

        Returns:
            Dict with wins, losses, total_pnl, avg_r.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        wins = 0
        losses = 0
        total_pnl = 0.0
        total_r = 0.0

        if not self.state.trades_file.exists():
            return {"wins": 0, "losses": 0, "total_pnl": 0.0, "avg_r": 0.0}

        try:
            with open(self.state.trades_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trade = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if self.state._is_test_trade(trade):
                        continue
                    if trade.get("event") != "EXIT":
                        continue

                    ts = trade.get("timestamp", "")
                    if not ts.startswith(today):
                        continue

                    pnl = trade.get("realized_pnl", 0.0)
                    total_pnl += pnl
                    if pnl >= 0:
                        wins += 1
                    else:
                        losses += 1

                    # Use actual initial risk from trade log if available
                    risk = trade.get("initial_risk", 0.0) or trade.get("initial_risk_amount", 0.0)
                    if risk > 0:
                        total_r += pnl / risk
                    else:
                        # Fallback: estimate from entry/stop distance
                        entry = trade.get("entry_price", 0)
                        stop = trade.get("initial_stop_price") or trade.get("stop_price") or 0
                        shares = trade.get("shares", 0)
                        risk = (entry - stop) * shares if entry > stop > 0 and shares > 0 else 0
                        if risk > 0:
                            total_r += pnl / risk
        except Exception:
            pass

        total = wins + losses
        return {
            "wins": wins,
            "losses": losses,
            "total_pnl": total_pnl,
            "avg_r": total_r / total if total > 0 else 0.0,
        }

    def _rebuild_cooldown_state(self):
        """Rebuild cooldown state from trade log after engine restart.

        Reads paper_trades.jsonl to reconstruct last_exit_time and
        consecutive_losses dicts. Mirrors the _reconcile_counters_from_log
        pattern in PaperState.
        """
        cutoff = datetime.now() - timedelta(
            minutes=self.risk_config.cooldown.max_cooldown_minutes)

        if not self.state.trades_file.exists():
            return

        # Collect EXIT events within cooldown window, grouped by ticker
        ticker_exits = {}  # ticker -> [(timestamp, pnl), ...]

        try:
            with open(self.state.trades_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trade = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines

                    if self.state._is_test_trade(trade):
                        continue
                    if trade.get('event') != 'EXIT':
                        continue

                    ts_str = trade.get('timestamp', '')
                    try:
                        ts = datetime.fromisoformat(ts_str)
                    except (ValueError, TypeError):
                        continue

                    if ts < cutoff:
                        continue  # Outside window

                    ticker = trade.get('ticker', '')
                    if not ticker:
                        continue

                    pnl = trade.get('realized_pnl')
                    ticker_exits.setdefault(ticker, []).append((ts, pnl))
        except Exception as e:
            print(f"⚠️  Could not read trade log for cooldown rebuild: {e}")
            return

        # For each ticker, find latest exit time and count consecutive losses
        rebuilt = 0
        for ticker, exits in ticker_exits.items():
            # Sort most recent first
            exits.sort(key=lambda x: x[0], reverse=True)

            # Latest exit time
            self.last_exit_time[ticker] = exits[0][0]

            # Count consecutive losses from most recent exit backwards
            consecutive = 0
            for _, pnl in exits:
                if pnl is not None and pnl < 0:
                    consecutive += 1
                else:
                    break  # Profit or break-even breaks the streak

            if consecutive > 0:
                self.consecutive_losses[ticker] = consecutive

            rebuilt += 1

        if rebuilt:
            print(f"   ⏱️  Rebuilt cooldown state for {rebuilt} ticker(s)")

    async def _check_exit_async(self, ticker: str, current_price: float):
        """Check if position should exit (async version)."""
        if ticker not in self.state.positions:
            return

        position = self.state.positions[ticker]
        historical_data = self._get_historical_for_exits(ticker)
        signal = self.exits.evaluate_exit(position, current_price, historical_data=historical_data)

        # Handle scale_out before stop update
        scale_out_info = signal.metadata.get('scale_out') if signal.metadata else None
        if scale_out_info:
            shares_to_sell = scale_out_info['shares_to_sell']
            if shares_to_sell > 0 and shares_to_sell < position.shares:
                order = self.order_manager.submit_exit(
                    ticker=ticker,
                    shares=shares_to_sell,
                    reason=signal.reason
                )
                if order:
                    position.shares -= shares_to_sell
                    position.record_scale_out(scale_out_info['trigger_r'])
                    self.state.save_state()
                    print(f"   📤 {ticker}: Scale-out {shares_to_sell} shares "
                          f"at {scale_out_info['trigger_r']}R "
                          f"({scale_out_info['scale_fraction']*100:.0f}%)")

        # Apply stop update if returned (no mutation inside evaluate_exit)
        if signal.new_stop is not None:
            position.stop_price = signal.new_stop
            position.current_stop_type = signal.new_stop_type
            self.state.update_stop(ticker, signal.new_stop, signal.new_stop_type)

        if signal.should_exit:
            await self._execute_exit(ticker, signal)

    async def _check_exits(self):
        """Check all open positions for exits.

        Priority order:
        1. Earnings exits — always fire regardless of strategy.
        2. Legacy ExitEngine path.
        """
        if not self.running:
            return

        from datetime import date as _date
        today = _date.today()

        # ── 1. Earnings exits (highest priority) ──────────────────────────
        for ticker in list(self.state.positions.keys()):
            if self.earnings_calendar.should_force_exit(ticker, today):
                current_price = await asyncio.to_thread(self._get_current_price, ticker)
                exit_price = current_price or self.state.positions[ticker].entry_price
                earnings_signal = ExitSignal(
                    should_exit=True,
                    reason='EARNINGS_EXIT',
                    exit_price=exit_price,
                    r_multiple=0.0,
                )
                print(f"   📅 {ticker}: Exiting before earnings — EARNINGS_EXIT")
                await self._execute_exit(ticker, earnings_signal)

        # ── 2. Legacy ExitEngine path ──────────────────────────────────────
        for ticker in list(self.state.positions.keys()):
            if ticker not in self.state.positions:
                continue  # already exited above

            current_price = await asyncio.to_thread(self._get_current_price, ticker)
            if current_price is None:
                continue

            position = self.state.positions[ticker]
            historical_data = self._get_historical_for_exits(ticker)
            signal = self.exits.evaluate_exit(position, current_price, historical_data=historical_data)

            # Handle scale_out before stop update
            scale_out_info = signal.metadata.get('scale_out') if signal.metadata else None
            if scale_out_info:
                shares_to_sell = scale_out_info['shares_to_sell']
                if shares_to_sell > 0 and shares_to_sell < position.shares:
                    order = self.order_manager.submit_exit(
                        ticker=ticker,
                        shares=shares_to_sell,
                        reason=signal.reason
                    )
                    if order:
                        position.shares -= shares_to_sell
                        position.record_scale_out(scale_out_info['trigger_r'])
                        self.state.save_state()

            # Apply stop update if returned (no mutation inside evaluate_exit)
            if signal.new_stop is not None:
                position.stop_price = signal.new_stop
                position.current_stop_type = signal.new_stop_type
                self.state.update_stop(ticker, signal.new_stop, signal.new_stop_type)

            if signal.should_exit:
                asyncio.create_task(self._execute_exit(ticker, signal))

    async def _check_entries(self):
        """Scan for entry opportunities using configured thresholds."""
        if not self.running:
            return

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

        market_ok, market_msg, _ = self.analyzer.check_market_conditions()
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

        from datetime import date as _date
        today = _date.today()

        for ticker in watchlist:
            if not self.running:
                break
            checked += 1

            # Engine-specific entry gates
            if ticker in self.state.positions:
                continue
            if ticker in self.signaled_tickers:
                continue
            if self.earnings_calendar.is_earnings_blackout(ticker, today):
                print(f"   📅 {ticker}: Skipping — earnings today")
                continue

            result = await asyncio.to_thread(self.analyzer.analyze, ticker)
            if not result:
                continue
            analysis = result.to_dict()

            # Entry criteria with detailed logging (accumulate for batch output)
            if analysis['entry_score'] < entry_threshold:
                logs.append(f"   ⏸️  {ticker}: Score {analysis['entry_score']:.0f} < {entry_threshold} (need Tier 1)")
                rejected_score += 1
                continue

            # Symmetric distance filter — skip when no pivot is set (dist_to_pivot is None)
            _dist = analysis['dist_to_pivot']
            if _dist is not None and not (-max_dist <= _dist <= max_dist):
                logs.append(f"   ⏸️  {ticker}: Distance {_dist:+.1f}% outside ±{max_dist}%")
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
            _dist_str = f"{_dist:+.1f}%" if _dist is not None else "—(no pivot)"
            logs.append(f"   ✅ {ticker}: Score {analysis['entry_score']:.0f}, Distance {_dist_str}, Stop {stop_dist_pct:.1f}% - EXECUTING")
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

        # Calculate position size with triple constraint system (risk, position cap, cash)
        prices = self._get_current_prices_map()
        equity = self.state.get_equity(prices)
        shares = self.exits.calculate_position_size(
            equity, entry_price, stop_price,
            available_cash=self.state.cash
        )

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
        can_enter, reason = self.state.can_enter_position(
            sector, position_value, self.risk_config, current_prices=prices)
        if not can_enter:
            print(f"   ⏸️  {ticker}: Risk validation failed - {reason}")
            return

        print(f"   🚀 {ticker}: Submitting order for {shares} shares...")

        # Submit order via order manager with entry metadata
        # Position will be created on fill confirmation, not immediately
        try:
            order = self.order_manager.submit_entry(
                ticker=ticker,
                shares=shares,
                stop_price=stop_price,
                target_price=target_price,
                sector=sector,
                expected_entry_price=entry_price
            )
        except (TimeoutError, ConnectionError) as e:
            print(f"   ⚠️ {ticker}: Order submission failed due to connectivity issue — {e}")
            return

        if order:
            # DO NOT create position here - prevents split-brain on crash
            # Position will be created when order fills in _process_pending_orders
            self.signaled_tickers.add(ticker)

            entry_msg = f"AUTO-ENTRY: {ticker} at ${entry_price:.2f} x {shares} shares"
            print(f"\n🚀 {entry_msg}")
            if self.dashboard:
                self.dashboard.log_event({
                    "type": "ENTRY",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "ticker": ticker,
                    "detail": f"${entry_price:.2f} x{shares}",
                })
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
            # DO NOT optimistically close here — wait for Alpaca fill
            # confirmation in _process_pending_orders(). This prevents
            # ghost exits where the trade is logged locally but Alpaca
            # never fills it (e.g. order rejected, partial fill, crash).
            print(f"\n⏳ EXIT SUBMITTED: {ticker} at ${signal.exit_price:.2f}")
            print(f"   Reason: {signal.reason}")
            print(f"   Waiting for Alpaca fill confirmation...")

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

                    # Calculate target from actual stop (R multiple from config)
                    risk = actual_fill - stop_price
                    r_mult = self.risk_config.profit_target.min_r_multiple if self.risk_config else 2.0; target_price = order.target_price or (actual_fill + (r_mult * risk) if risk > 0 else actual_fill * 1.05)

                    position = self.state.enter_position(
                        ticker=order.ticker,
                        entry_price=actual_fill,
                        shares=filled_qty,
                        stop_price=stop_price,
                        target_price=target_price,
                        sector=sector,
                        entry_min_r=r_mult,
                    )
                    print(f"   📝 Created position: ${actual_fill:.2f} x {filled_qty} shares")
                else:
                    # Position already exists (shouldn't happen with new flow, but handle gracefully)
                    actual_fill = order.filled_price
                    if actual_fill:
                        pos = self.state.positions[order.ticker]
                        old_entry = pos.entry_price
                        pos.entry_price = actual_fill
                        # Recalculate target based on new entry price (R from config)
                        risk = actual_fill - pos.stop_price
                        r_mult = self.risk_config.profit_target.min_r_multiple if self.risk_config else 2.0; pos.target_price = actual_fill + (r_mult * risk) if risk > 0 else actual_fill * 1.05
                        pos.entry_min_r = r_mult
                        # Recalculate initial_risk
                        pos.initial_risk = risk * pos.shares
                        self.state.save_state()
                        print(f"   📝 Updated entry price: ${old_entry:.2f} → ${actual_fill:.2f}")
            else:
                # Exit orders - close position ONLY when Alpaca confirms fill
                print(f"✅ Exit filled: {order.ticker} "
                      f"(${order.reason})")

                if order.ticker in self.state.positions:
                    fill_price = order.filled_price or self.state.positions[order.ticker].entry_price

                    # Scale-out: partial exit, keep remaining position open
                    if order.reason and order.reason.startswith("SCALE_OUT_"):
                        self._handle_scale_out_fill(order, fill_price)
                    else:
                        position = self.state.close_position(
                            ticker=order.ticker,
                            exit_price=fill_price,
                            reason=order.reason
                        )
                        if position:
                            pnl_emoji = "🎯" if position.realized_pnl and position.realized_pnl > 0 else "🛑"
                            print(f"\n{pnl_emoji} EXIT CONFIRMED: {order.ticker}")
                            print(f"   Fill Price: ${fill_price:.2f}")
                            print(f"   Reason: {order.reason}")
                            print(f"   P&L: ${position.realized_pnl:,.2f}")

                            if self.dashboard:
                                self.dashboard.log_event({
                                    "type": "EXIT",
                                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                                    "ticker": order.ticker,
                                    "detail": f"${fill_price:.2f}",
                                    "pnl": position.realized_pnl,
                                })

                            # Record exit for cooldown tracking (FLY case study)
                            realized_pnl = position.realized_pnl or 0.0
                            self._record_position_exit(order.ticker, realized_pnl)

    def _reset_daily_signals(self):
        """Reset entry signals for new day."""
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.last_signal_reset != current_date:
            self.signaled_tickers.clear()
            self.last_signal_reset = current_date

            # Remove expired cooldown entries (keep active cooldowns that span overnight)
            cutoff = datetime.now()
            expired_tickers = [
                ticker for ticker, exit_time in self.last_exit_time.items()
                if exit_time < cutoff - timedelta(
                    minutes=self.risk_config.cooldown.max_cooldown_minutes)
            ]
            for ticker in expired_tickers:
                self.last_exit_time.pop(ticker, None)
                self.consecutive_losses.pop(ticker, None)

            print(f"\n📅 New day: Reset entry signals and cooldown tracking")

    async def _print_status(self):
        """Print current status — dashboard mode or fallback."""
        prices = self._get_current_prices_map()
        stats = self.state.get_stats(prices)
        account_value = stats.get("cash", 0.0)
        unrealized_pnl = 0.0
        positions_data = {}

        for ticker, pos in self.state.positions.items():
            if pos.status == "OPEN":
                current_price = self.price_cache.get(ticker, {}).get("price")
                if current_price is None:
                    current_price = await asyncio.to_thread(self._get_current_price, ticker)
                if current_price:
                    account_value += current_price * pos.shares
                    upnl = (current_price - pos.entry_price) * pos.shares
                    unrealized_pnl += upnl
                phase = getattr(pos, "exit_phase", "phase1")
                positions_data[ticker] = {
                    "entry_price": pos.entry_price,
                    "current_price": current_price or pos.entry_price,
                    "stop_price": pos.stop_price,
                    "shares": pos.shares,
                    "current_stop_type": pos.current_stop_type,
                    "exit_phase": phase,
                    "sector": getattr(pos, "sector", "Unknown"),
                    "initial_stop_price": getattr(pos, "initial_stop_price", 0.0),
                }

        et = pytz.timezone("US/Eastern")
        now = datetime.now(et)
        market_close_seconds = None
        if now.weekday() < 5:
            close_time = now.replace(hour=16, minute=0, second=0)
            if now < close_time:
                market_close_seconds = int((close_time - now).total_seconds())

        # Fetch VIX for dashboard header (same source as fallback path)
        vix_current = None
        try:
            import yfinance as yf
            vix_hist = yf.Ticker("^VIX").history(period="2d", auto_adjust=False)
            if not vix_hist.empty:
                vix_current = float(vix_hist['Close'].iloc[-1])
        except Exception:
            pass

        rl = self.alpaca.rate_limiter.get_status()
        # Compute dashboard extras
        active_cooldowns = self._get_active_cooldowns()
        today_stats = self._get_today_trade_stats()

        # Compute market regime for dashboard
        regime = "UNKNOWN"
        try:
            spy_hist = self.alpaca.get_historical_bars("SPY")
            if spy_hist is not None and len(spy_hist) >= 50:
                spy_current = float(spy_hist["Close"].iloc[-1])
                spy_50ma = float(spy_hist["Close"].tail(50).mean())
                spy_200ma = float(spy_hist["Close"].tail(200).mean()) if len(spy_hist) >= 200 else spy_50ma
                if spy_current > spy_50ma > spy_200ma and (vix_current or 0) < 20:
                    regime = "BULL"
                elif spy_current > spy_50ma and (vix_current or 0) < 25:
                    regime = "BULL"
                elif spy_current < spy_50ma and (vix_current or 0) > 25:
                    regime = "BEAR"
                else:
                    regime = "NEUTRAL"
        except Exception:
            pass

        state_data = {
            "mode": self.mode,
            "equity": account_value,
            "cash": stats.get("cash", 0.0),
            "day_pnl": stats.get("day_pnl", 0.0),
            "unrealized_pnl": unrealized_pnl,
            "open_positions": len(self.state.positions),
            "pending_orders": self.order_manager.get_pending_count(),
            "positions": positions_data,
            "market_status": "OPEN" if is_market_open() else "CLOSED",
            "vix": vix_current,
            "ws_connected": self.alpaca.is_ws_healthy(),
            "api_requests": rl.get("requests_in_window", 0),
            "api_max": rl.get("max_requests", 10000),
            "next_scan_seconds": 30,
            "market_close_seconds": market_close_seconds,
            "cooldowns": active_cooldowns,
            "today_stats": today_stats,
            "regime": regime,
        }

        self._last_state_data = state_data
        if self.dashboard and self.dashboard.enabled:
            self.dashboard.update(state_data)
        else:
            self._print_status_fallback(state_data)

    def _print_status_fallback(self, state):
        """Plain-text status when dashboard is unavailable."""
        print(f"\n{'='*60}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET")
        print(f"📈 Market: {format_market_status()}")

        # VIX Regime Status
        try:
            import yfinance as yf
            vix_hist = yf.Ticker("^VIX").history(period="2d", auto_adjust=False)
            if not vix_hist.empty:
                vix_current = float(vix_hist['Close'].iloc[-1])
                if vix_current < 20:
                    vix_regime = "🟢 LOW"
                elif vix_current < 30:
                    vix_regime = "🟡 ELEVATED"
                elif vix_current < 40:
                    vix_regime = "🟠 HIGH"
                else:
                    vix_regime = "🔴 EXTREME"
                print(f"📊 VIX: {vix_current:.2f} {vix_regime}")
            else:
                print(f"📊 VIX: unavailable")
        except Exception:
            print(f"📊 VIX: unavailable")

        # Earnings Gate Status
        if self.earnings_calendar._api_key:
            cached_tickers = len(self.earnings_calendar._cache)
            print(f"🚦 Earnings Gate: ON ({cached_tickers} tickers cached)")
        else:
            print(f"🚦 Earnings Gate: OFF (FMP_API_KEY not set)")

        # WebSocket status
        if self.alpaca.is_ws_healthy():
            print(f"📡 WebSocket: Connected ({len(self.price_cache)} tickers cached)")
        else:
            print(f"📡 WebSocket: Disconnected (using REST fallback)")

        print(f"💰 Account Value: ${state['equity']:,.2f} | Cash: ${state['cash']:,.2f}", flush=True)
        print(f"📊 Open: {state['open_positions']} | Day P&L: ${state['day_pnl']:,.2f} | Unrealized: ${state['unrealized_pnl']:,.2f}", flush=True)

        # Individual position lines
        for ticker, pos in state['positions'].items():
            current_price = pos['current_price']
            upnl = (current_price - pos['entry_price']) * pos['shares']
            phase = pos.get('exit_phase', 'phase1')
            phase_badge = '①' if phase == 'phase1' else '②'
            print(
                f"   {ticker:<6} {phase_badge} "
                f"${current_price:.2f} | stop ${pos['stop_price']:.2f} "
                f"({pos['current_stop_type']}) | upnl ${upnl:+,.0f}",
                flush=True
            )

        # Rate limit status
        rl = self.alpaca.rate_limiter.get_status()
        rl_pct = rl['requests_in_window'] / rl['max_requests'] * 100 if rl['max_requests'] > 0 else 0
        circuit = "🔴 OPEN" if rl['circuit_open'] else "🟢 closed"
        print(f"📡 API: {rl['requests_in_window']}/{rl['max_requests']} requests/min ({rl_pct:.0f}%) | Circuit: {circuit}", flush=True)
        print(f"📋 Pending Orders: {state['pending_orders']}", flush=True)
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
                # NEW: Check if market closed - shut down gracefully
                if not is_market_open():
                    print("\n🛑 Market closed. Shutting down gracefully.")
                    self.running = False
                    break

                # Start/restart WebSocket only if market is open
                if is_market_open() and (not ws_task or ws_task.done()):
                    if ws_task and ws_task.done():
                        delay = self.alpaca.ws_reconnect_delay
                        # Check if task ended with exception
                        if ws_task.exception():
                            exc = ws_task.exception()
                            exc_str = str(exc).lower()
                            # Check for rate limit / connection limit errors
                            if "connection limit" in exc_str or "429" in exc_str:
                                print(f"\n⏳ Alpaca connection limit hit - backing off for {delay}s...")
                            # Suppress verbose error messages for common WebSocket disconnects
                            elif "no close frame" in str(exc) or "ConnectionClosed" in type(exc).__name__:
                                print(f"\n🔄 WebSocket disconnected, restarting in {delay}s...")
                            else:
                                print(f"\n🔄 WebSocket error ({type(exc).__name__}), restarting in {delay}s...")
                        else:
                            print(f"\n🔄 WebSocket task ended, restarting in {delay}s...")
                        await asyncio.sleep(delay)
                    ws_task = asyncio.create_task(self._start_websocket())
                    await asyncio.sleep(2)

                self._reset_daily_signals()
                await self._process_pending_orders()

                if self._is_market_hours():
                    await self._check_exits()
                    await self._check_entries()
                else:
                    # This should not happen now (we exit when market closes)
                    # Keeping as fallback for edge cases
                    print("   ⏳ Outside market hours - waiting")

                await self._print_status()

                # Countdown on single line (skip if shutting down)
                if not self.running:
                    break
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

        # Cleanup - Stop the stream first to signal the SDK's internal loop
        # to exit (sets _should_run = False), then cancel the task as a safety net.
        # Python 3.14+ prints noisy tracebacks from asyncio.shield()'d futures
        # inside the websockets library during cancellation. Suppress the event
        # loop's exception handler during cleanup to avoid scaring the user.
        print("\n🛑 Stopping WebSocket...")
        loop = asyncio.get_running_loop()
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda ctx: None)
        try:
            # 1. Signal the SDK to stop — this breaks _run_forever()'s internal loop
            try:
                await asyncio.wait_for(self.alpaca.stop_price_stream(), timeout=2.0)
            except Exception:
                pass
            # 2. Cancel the task as a safety net
            if ws_task and not ws_task.done():
                ws_task.cancel()
                try:
                    await asyncio.wait_for(ws_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
        finally:
            loop.set_exception_handler(old_handler)
        # Restore signal handlers so main() wait loop isn't hijacked
        # Stop dashboard to exit alternate screen before restoring handlers
        if self.dashboard:
            self.dashboard.stop()
        self._cleanup()
        print("✅ Engine stopped gracefully")
        # Preserve final state for post-market dashboard
        final_state = getattr(self, '_last_state_data', {})
        final_state['shutdown_requested'] = self.shutdown_requested
        return final_state




def _load_post_market_state(mode: str = "paper"):
    """Load saved positions and fetch closing prices for post-market summary.

    Args:
        mode: 'paper' or 'live' — reads from data/{mode}/positions.json
    """
    import json
    from pathlib import Path
    # Resolve data dir via traderlib.paths (honors PAPER_TRADING_DATA_DIR)
    positions_file = data_dir() / mode / 'positions.json'
    if not positions_file.exists():
        return None
    try:
        with open(positions_file, 'r') as f:
            positions = json.load(f)
    except Exception:
        return None
    if not positions:
        return None
    # Fetch closing prices via yfinance
    import yfinance as yf
    tickers = list(positions.keys())
    prices = {}
    try:
        data = yf.download(tickers, period='1d', progress=False, threads=True) if len(tickers) > 1 else yf.Ticker(tickers[0]).history(period='1d')
        if len(tickers) == 1:
            prices[tickers[0]] = float(data['Close'].iloc[-1]) if not data.empty else None
        else:
            for t in tickers:
                try:
                    prices[t] = float(data['Close'][t].iloc[-1])
                except Exception:
                    prices[t] = None
    except Exception:
        prices = {}
    # Build positions_data
    positions_data = {}
    total_unreal = 0.0
    total_value = 0.0
    for ticker, pos in positions.items():
        entry = float(pos.get('entry_price', 0))
        shares = int(pos.get('shares', 0))
        stop = float(pos.get('stop_price', 0))
        current = prices.get(ticker) or entry  # fallback to entry price
        unreal = (current - entry) * shares
        total_unreal += unreal
        total_value += current * shares
        positions_data[ticker] = {
            'entry_price': entry,
            'current_price': current,
            'stop_price': stop,
            'initial_stop_price': float(pos.get('initial_stop_price', 0)),
            'shares': shares,
            'current_stop_type': pos.get('current_stop_type', 'HARD'),
            'sector': pos.get('sector', 'Unknown'),
        }
    return {
        'equity': total_value,  # approximate, cash not persisted
        'cash': 0.0,
        'day_pnl': 0.0,
        'unrealized_pnl': total_unreal,
        'open_positions': len(positions),
        'pending_orders': 0,
        'positions': positions_data,
        'market_status': 'POST',
        'vix': None,
        'ws_connected': False,
        'api_requests': None,
        'api_max': None,
        'next_scan_seconds': 0,
        'market_close_seconds': None,
    }


def main():
    parser = argparse.ArgumentParser(description='Alpaca Paper Trading Engine')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                        help='Trading mode (default: paper)')
    parser.add_argument('--risk-profile', type=str, default=None,
                        help='Risk profile from config (conservative, aggressive, tight_stops)')
    parser.add_argument('--risk-summary', action='store_true',
                        help='Print risk configuration and exit')
    args = parser.parse_args()

    # If just printing risk summary, skip dashboard — Live screen captures print output
    if args.risk_summary:
        manager = RiskConfigManager(profile=args.risk_profile)
        manager.print_summary()
        return

    # Create dashboard early so it shows during market-closed waits
    try:
        dashboard = Dashboard() if Dashboard else None
    except Exception:
        dashboard = None

    # Main loop: wait for market open → run → repeat
    print("🔄 Auto-restart mode enabled. Press Ctrl+C to stop permanently.\n")

    while True:
        try:
            # Wait for market to open if closed
            if not is_market_open():
                next_open = next_market_open()
                if not next_open:
                    print("⏳ Market closed. Unable to determine next open time. Retrying in 60s...")
                    import time
                    time.sleep(60)
                    continue

                # Calculate wait time
                now = datetime.now(pytz.timezone('America/New_York'))
                wait_seconds = (next_open - now).total_seconds()

                if wait_seconds > 0:
                    print(f"⏳ Market closed. Opens {next_open.strftime('%A at %H:%M')} ET.")
                    print(f"   Waiting {int(wait_seconds // 60)} minutes... (Ctrl+C to stop)")

                    # Show dashboard while waiting
                    if dashboard and dashboard.enabled:
                        post_state = _load_post_market_state(args.mode)
                        if post_state:
                            post_state['next_scan_seconds'] = int(wait_seconds)
                            dashboard.update(post_state)
                        else:
                            dashboard.update({
                                "equity": 0.0,
                                "cash": 0.0,
                                "day_pnl": 0.0,
                                "unrealized_pnl": 0.0,
                                "open_positions": 0,
                                "pending_orders": 0,
                                "positions": {},
                                "market_status": "CLOSED",
                                "vix": None,
                                "ws_connected": False,
                                "api_requests": None,
                                "api_max": None,
                                "next_scan_seconds": int(wait_seconds),
                                "market_close_seconds": None,
                            })

                    # Sleep in 10-second chunks to allow interrupt
                    try:
                        while wait_seconds > 0:
                            sleep_chunk = min(10, wait_seconds)
                            import time
                            time.sleep(sleep_chunk)
                            wait_seconds -= sleep_chunk
                            if is_market_open():
                                break
                    except KeyboardInterrupt:
                        print("\n🛑 Stopped by user.")
                        if dashboard:
                            dashboard.stop()
                        return

                    print("   Market is now open. Starting engine...\n")

            # Run the engine (blocks until market closes or user stops)
            engine = AlpacaPaperEngine(mode=args.mode, risk_profile=args.risk_profile, dashboard=dashboard)
            result = asyncio.run(engine.run())
            # Engine stopped — restore default signal handling for wait loop
            engine._cleanup()

            # Check if user requested shutdown
            if result and result.get('shutdown_requested'):
                print("\n👋 Goodbye!")
                break

            # Engine stopped (market closed) — engine called dashboard.stop()
            # which permanently disabled it. Create a fresh dashboard for
            # post-market viewing and the next day's engine startup.
            if dashboard:
                dashboard.stop_now()
            try:
                dashboard = Dashboard() if Dashboard else None
            except Exception:
                dashboard = None

            final_state = result or {}
            if dashboard and dashboard.enabled and not final_state.get('shutdown_requested'):
                # Preserve final state for post-market viewing
                post_state = dict(final_state)
                post_state['market_status'] = 'POST'
                post_state['next_scan_seconds'] = 0
                if 'market_close_seconds' in post_state:
                    post_state['market_close_seconds'] = None
                dashboard.update(post_state)
                print("\n📊 Post-market summary displayed. Press Ctrl+C to exit.")
            print("\n⏳ Market closed. Will restart at next open...\n")
            import time
            time.sleep(30)  # Brief pause before checking again

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("   Restarting in 60 seconds... (Ctrl+C to stop)")
            try:
                import time
                time.sleep(60)
            except KeyboardInterrupt:
                print("\n🛑 Stopped by user.")
                break
    if dashboard:
        dashboard.stop()


if __name__ == "__main__":
    main()
