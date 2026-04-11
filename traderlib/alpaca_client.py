#!/usr/bin/env python3
"""Alpaca API client - Hybrid REST + WebSocket for paper trading."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable

import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient

# Load environment variables from .env file (if it exists)
# This allows credentials to be stored in .env instead of environment variables
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')
from websockets.exceptions import ConnectionClosed
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError

# Config path
CONFIG_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/config/secrets')
CONFIG_FILE = CONFIG_DIR / 'alpaca_config.json'

# Import rate limiter
sys.path.insert(0, str(Path(__file__).parent))
from traderlib.rate_limiter import RateLimiter, health_monitor
from traderlib.trading_exceptions import TradingExceptionHandler, APIKeyError


class AlpacaClient:
    """Unified Alpaca REST + WebSocket client for paper trading."""

    def __init__(self, mode: str = 'paper'):
        """Initialize Alpaca clients.

        Args:
            mode: 'paper' or 'live'
        """
        self.mode = mode
        self.api_key = os.getenv('ALPACA_API_KEY') or self._load_config('api_key')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY') or self._load_config('secret_key')

        if not self.api_key or not self.secret_key:
            raise APIKeyError("Alpaca")

        # Historical data configuration (default 365 days for full Stage 2 scoring)
        self.historical_days = self._load_config_int('historical_days', default=365)

        # Initialize REST clients
        self.trading_client = TradingClient(self.api_key, self.secret_key, paper=(mode == 'paper'))
        self.data_client = StockHistoricalDataClient(self.api_key, self.secret_key)

        # WebSocket stream (initialized on demand)
        self.stream: Optional[StockDataStream] = None
        self.price_cache: Dict[str, Dict] = {}

        # FINDING-006: Stale price cache protection
        # Max age in seconds before price is considered stale (30s for WebSocket data)
        self.price_cache_max_age = 30
        self._trade_handlers: List[Callable] = []
        self._order_handlers: List[Callable] = []

        # Health tracking
        self.last_ws_message = None
        self.ws_connected = False
        self.api_error_count = 0
        self.ws_reconnect_delay = 5  # Start with 5 seconds, exponential backoff

        # Rate limiter
        self.rate_limiter = RateLimiter(max_requests=200, window_seconds=60)

    def _load_config(self, key: str) -> Optional[str]:
        """Load config from file."""
        if not CONFIG_FILE.exists():
            return None
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get(self.mode, {}).get(key)
        except Exception:
            return None

    def _load_config_int(self, key: str, default: int) -> int:
        """Load integer config value from file."""
        if not CONFIG_FILE.exists():
            return default
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                val = config.get(key, default)
                return int(val) if val is not None else default
        except Exception:
            return default

    def get_account(self) -> Dict:
        """Get account information with rate limiting."""
        if not self.rate_limiter.can_make_request():
            wait = self.rate_limiter.get_wait_time()
            if wait > 0:
                print(f"⏳ Rate limit: waiting {wait:.1f}s")
                import time
                time.sleep(wait)

        try:
            self.rate_limiter.record_request()
            account = self.trading_client.get_account()
            self.rate_limiter.record_success()
            health_monitor.mark_success('alpaca')
            self.api_error_count = 0
            return {
                'id': account.id,
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'status': account.status,
                'currency': account.currency
            }
        except APIError as e:
            self.rate_limiter.record_error(is_rate_limit=e.status_code == 429)
            health_monitor.mark_failure('alpaca')
            self.api_error_count += 1
            # EH-003: Provide actionable error for auth failures
            if e.status_code in (401, 403):
                raise APIKeyError(
                    "Alpaca",
                    f"Authentication failed ({e.status_code}). Keys may be invalid or expired."
                ) from e
            raise
        except Exception as e:
            health_monitor.mark_failure('alpaca')
            self.api_error_count += 1
            raise

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Get current marked-to-market price.

        Uses position API current_price when position exists (most accurate),
        falls back to quotes API for non-positions.

        Args:
            ticker: Stock symbol

        Returns:
            Current price or None if unavailable
        """
        # Check WebSocket cache first
        cached = self.get_cached_price(ticker)
        if cached:
            return cached

        # 1. If we have a position, use position API's current_price (marked to market)
        position = self.get_position(ticker)
        if position and position.get('current_price'):
            return float(position['current_price'])

        if not self.rate_limiter.can_make_request():
            return None

        try:
            # 2. Use quotes API (bid/ask midpoint) for non-positions
            self.rate_limiter.record_request()
            from alpaca.data.requests import StockLatestQuoteRequest

            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quotes = self.data_client.get_stock_latest_quote(request)

            if ticker in quotes.data:
                quote = quotes.data[ticker]
                # Use bid/ask midpoint for fair value
                if quote.bid_price and quote.ask_price:
                    price = float((quote.bid_price + quote.ask_price) / 2)
                elif quote.bid_price:
                    price = float(quote.bid_price)
                elif quote.ask_price:
                    price = float(quote.ask_price)
                else:
                    return None

                self.rate_limiter.record_success()
                health_monitor.mark_success('alpaca')
                return price

            return None

        except Exception as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            return None

    def get_historical_bars(self, ticker: str, days: int = None) -> Optional[pd.DataFrame]:
        """Get historical daily bars with rate limiting.

        Args:
            ticker: Stock symbol
            days: Number of days to fetch (default: uses configured historical_days)
        """
        if days is None:
            days = self.historical_days

        if not self.rate_limiter.can_make_request():
            return None

        try:
            self.rate_limiter.record_request()
            end = datetime.now()
            start = end - timedelta(days=days)

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                adjustment=Adjustment.ALL
            )

            bars = self.data_client.get_stock_bars(request)

            if ticker not in bars.data:
                return None

            df = pd.DataFrame([{
                'Open': b.open,
                'High': b.high,
                'Low': b.low,
                'Close': b.close,
                'Volume': b.volume,
                'Timestamp': b.timestamp
            } for b in bars.data[ticker]])

            df.set_index('Timestamp', inplace=True)
            self.rate_limiter.record_success()
            health_monitor.mark_success('alpaca')
            return df

        except Exception as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            return None

    def submit_market_order(self, ticker: str, shares: int, side: str,
                           stop_price: Optional[float] = None) -> Optional[Dict]:
        """Submit a market order with rate limiting.

        Args:
            ticker: Stock symbol
            shares: Number of shares
            side: 'buy' or 'sell'
            stop_price: Optional stop loss price
        """
        if not self.rate_limiter.can_make_request():
            wait = self.rate_limiter.get_wait_time()
            print(f"⏳ Rate limited: waiting {wait:.1f}s before order")
            import time
            time.sleep(wait)

        try:
            self.rate_limiter.record_request()
            order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL

            # Build order request
            order_data = {
                'symbol': ticker,
                'qty': shares,
                'side': order_side,
                'time_in_force': TimeInForce.DAY
            }

            # Add stop loss if provided (for entries)
            if stop_price and side == 'buy':
                order_data['stop_loss'] = StopLossRequest(stop_price=stop_price)

            request = MarketOrderRequest(**order_data)
            order = self.trading_client.submit_order(request)

            self.rate_limiter.record_success()
            health_monitor.mark_success('alpaca')

            return {
                'id': str(order.id),
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'type': order.order_type.value,
                'status': order.status.value,
                'stop_price': float(order.stop_price) if order.stop_price else None
            }

        except APIError as e:
            is_rate_limit = e.status_code == 429
            self.rate_limiter.record_error(is_rate_limit=is_rate_limit)
            health_monitor.mark_failure('alpaca')
            # EH-003: Provide actionable error for auth failures
            if e.status_code in (401, 403):
                print(f"\n❌ Order submission failed: Authentication error ({e.status_code})")
                print("   Your API keys may be invalid or expired.")
                print("   Run: python3 scripts/setup_alpaca.py")
                print("   Docs: docs/runbooks/api_credentials.md")
            else:
                print(f"❌ Order submission failed: {e}")
            return None
        except Exception as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            print(f"❌ Order submission failed: {e}")
            return None

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        try:
            order = self.trading_client.get_order_by_id(order_id)
            return {
                'id': str(order.id),
                'symbol': order.symbol,
                'qty': float(order.qty),
                'filled_qty': float(order.filled_qty),
                'side': order.side.value,
                'status': order.status.value,
                'filled_price': float(order.filled_avg_price) if order.filled_avg_price else None
            }
        except Exception:
            return None

    def list_positions(self) -> List[Dict]:
        """Get all open positions."""
        try:
            positions = self.trading_client.get_all_positions()
            return [{
                'symbol': p.symbol,
                'qty': float(p.qty),
                'avg_entry_price': float(p.avg_entry_price),
                'market_value': float(p.market_value),
                'current_price': float(p.current_price),
                'unrealized_pl': float(p.unrealized_pl),
                'unrealized_plpc': float(p.unrealized_plpc),
                'change_today': float(p.change_today)
            } for p in positions]
        except Exception:
            return []

    def get_position(self, ticker: str) -> Optional[Dict]:
        """Get position for specific ticker."""
        try:
            p = self.trading_client.get_open_position(ticker)
            return {
                'symbol': p.symbol,
                'qty': float(p.qty),
                'avg_entry_price': float(p.avg_entry_price),
                'market_value': float(p.market_value),
                'current_price': float(p.current_price),
                'unrealized_pl': float(p.unrealized_pl)
            }
        except Exception:
            return None

    def close_position(self, ticker: str) -> Optional[Dict]:
        """Close position for ticker."""
        try:
            order = self.trading_client.close_position(ticker)
            return {
                'id': str(order.id),
                'symbol': order.symbol,
                'qty': float(order.qty),
                'status': order.status.value
            }
        except Exception as e:
            print(f"❌ Failed to close position {ticker}: {e}")
            return None

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self.trading_client.cancel_orders()
            return True
        except Exception:
            return False

    # WebSocket Methods

    async def start_price_stream(self, tickers: List[str],
                                  trade_handler: Callable,
                                  quote_handler: Optional[Callable] = None):
        """Start WebSocket price stream for tickers.

        Args:
            tickers: List of symbols to subscribe
            trade_handler: Callback for trade updates (price changes)
            quote_handler: Optional callback for quote updates
        """
        if not tickers:
            print("⚠️ No tickers provided for WebSocket stream")
            return

        # Cleanup any existing stream first to prevent orphan coroutines
        if self.stream:
            try:
                await self.stream.stop()
                await asyncio.sleep(0.5)
            except Exception as e:
                TradingExceptionHandler.log_exception(
                    "websocket_cleanup", e,
                    severity=TradingExceptionHandler.WARNING
                )
            self.stream = None
            self.ws_connected = False

        try:
            # Create stream with IEX feed (free tier)
            from alpaca.data.enums import DataFeed
            import ssl
            import certifi

            # Create SSL context with certifi certificates (fixes macOS cert issues)
            ssl_context = ssl.create_default_context(cafile=certifi.where())

            self.stream = StockDataStream(
                self.api_key,
                self.secret_key,
                feed=DataFeed.IEX,
                websocket_params={'ssl': ssl_context}
            )
        except Exception as e:
            print(f"⚠️ Failed to create WebSocket stream: {e}")
            self.ws_connected = False
            return

        # Subscribe to trades
        async def _trade_callback(t):
            try:
                self.price_cache[t.symbol] = {
                    'price': t.price,
                    'timestamp': datetime.now(),
                    'size': getattr(t, 'size', 0)
                }
                self.last_ws_message = datetime.now()
                await trade_handler(t)
            except Exception as e:
                print(f"⚠️ Trade callback error: {e}")

        try:
            self.stream.subscribe_trades(_trade_callback, *tickers)
        except Exception as e:
            print(f"⚠️ Failed to subscribe to trades: {e}")
            self.ws_connected = False
            return

        # Subscribe to quotes if handler provided
        if quote_handler:
            async def _quote_callback(q):
                await quote_handler(q)
            try:
                self.stream.subscribe_quotes(_quote_callback, *tickers)
            except Exception as e:
                print(f"⚠️ Failed to subscribe to quotes: {e}")

        self.ws_connected = True
        # Reset reconnect delay on successful connection
        self.ws_reconnect_delay = 5
        print(f"📡 WebSocket stream starting for {len(tickers)} tickers...")

        try:
            # Run the stream - use _run_forever() to avoid event loop conflict
            # This is a known workaround for alpaca-py bug in v0.41.0-0.42.1
            await self.stream._run_forever()
        except asyncio.CancelledError:
            # Normal shutdown
            print("🔄 WebSocket cancelled (normal shutdown)")
        except ConnectionClosed as e:
            # Common disconnects - don't show error code to reduce noise
            code_str = f" (code: {e.code})" if hasattr(e, 'code') and e.code else ""
            print(f"⚠️ WebSocket disconnected{code_str}, will reconnect...")
        except Exception as e:
            print(f"⚠️ WebSocket error: {e}")
        finally:
            self.ws_connected = False
            self.stream = None
            # Exponential backoff for reconnects (max 60 seconds)
            self.ws_reconnect_delay = min(self.ws_reconnect_delay * 2, 60)

    async def stop_price_stream(self):
        """Stop WebSocket stream."""
        if self.stream:
            try:
                await asyncio.wait_for(self.stream.stop(), timeout=3.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Don't hang on cleanup
            self.ws_connected = False
            self.stream = None

    def is_ws_healthy(self) -> bool:
        """Check if WebSocket connection is healthy."""
        if not self.ws_connected or not self.last_ws_message:
            return False

        # Consider unhealthy if no message in 60 seconds
        elapsed = (datetime.now() - self.last_ws_message).total_seconds()
        return elapsed < 60

    def get_cached_price(self, ticker: str, max_age_seconds: Optional[int] = None) -> Optional[float]:
        """Get price from WebSocket cache with staleness check.

        Args:
            ticker: Stock symbol
            max_age_seconds: Maximum age before rejecting (default: self.price_cache_max_age)

        Returns:
            Price if fresh, None if stale or missing
        """
        if ticker not in self.price_cache:
            return None

        cache_entry = self.price_cache[ticker]
        cache_time = cache_entry.get('timestamp')

        if not cache_time:
            # No timestamp - treat as stale for safety
            return None

        # Check staleness
        max_age = max_age_seconds if max_age_seconds is not None else self.price_cache_max_age
        age_seconds = (datetime.now() - cache_time).total_seconds()

        if age_seconds > max_age:
            # FINDING-006: Stale price - reject to prevent bad trading decisions
            return None

        return cache_entry['price']

    def is_price_fresh(self, ticker: str, max_age_seconds: Optional[int] = None) -> bool:
        """Check if cached price is fresh (not stale).

        Args:
            ticker: Stock symbol
            max_age_seconds: Maximum acceptable age (default: self.price_cache_max_age)

        Returns:
            True if price exists and is fresh, False otherwise
        """
        return self.get_cached_price(ticker, max_age_seconds) is not None

    def get_cache_staleness(self, ticker: str) -> Optional[float]:
        """Get age of cached price in seconds.

        Args:
            ticker: Stock symbol

        Returns:
            Age in seconds, or None if not in cache
        """
        if ticker not in self.price_cache:
            return None

        cache_time = self.price_cache[ticker].get('timestamp')
        if not cache_time:
            return None

        return (datetime.now() - cache_time).total_seconds()

    def check_health(self) -> Dict:
        """Check client health including cache staleness."""
        # FINDING-006: Track stale price cache entries
        fresh_count = 0
        stale_count = 0
        stale_tickers = []

        for ticker, entry in self.price_cache.items():
            cache_time = entry.get('timestamp')
            if cache_time:
                age = (datetime.now() - cache_time).total_seconds()
                if age <= self.price_cache_max_age:
                    fresh_count += 1
                else:
                    stale_count += 1
                    stale_tickers.append(ticker)

        return {
            'ws_connected': self.ws_connected,
            'ws_healthy': self.is_ws_healthy(),
            'api_errors': self.api_error_count,
            'cache_size': len(self.price_cache),
            'cache_fresh': fresh_count,
            'cache_stale': stale_count,
            'stale_tickers': stale_tickers[:10],  # Limit to 10 for readability
            'cache_max_age_seconds': self.price_cache_max_age,
            'rate_limiter': self.rate_limiter.get_status(),
            'health_monitor': health_monitor.get_status()
        }

    def get_health_summary(self) -> str:
        """Get formatted health summary."""
        health = self.check_health()
        rl = health['rate_limiter']
        hm = health['health_monitor']

        lines = [
            f"WebSocket: {'✅' if health['ws_healthy'] else '❌'} ({health['cache_size']} prices cached)",
            f"Rate Limit: {rl['requests_in_window']}/{rl['max_requests']} requests",
            f"Circuit: {'🔴 OPEN' if rl['circuit_open'] else '🟢 CLOSED'}",
            f"Provider: {hm['current']} (alpaca: {'✅' if hm['providers']['alpaca']['healthy'] else '❌'}, "
            f"yfinance: {'✅' if hm['providers']['yfinance']['healthy'] else '❌'})"
        ]
        return " | ".join(lines)


# Test function
if __name__ == "__main__":
    import sys

    print("Testing Alpaca Client...")

    try:
        client = AlpacaClient(mode='paper')

        # Test account
        print("\n📊 Account:")
        account = client.get_account()
        print(f"   Cash: ${account['cash']:,.2f}")
        print(f"   Equity: ${account['equity']:,.2f}")
        print(f"   Status: {account['status']}")

        # Test positions
        print("\n📋 Positions:")
        positions = client.list_positions()
        if positions:
            for p in positions:
                print(f"   {p['symbol']}: {p['qty']} shares @ ${p['avg_entry_price']:.2f}")
        else:
            print("   No open positions")

        # Test price
        print("\n💰 AAPL Price:")
        price = client.get_latest_price('AAPL')
        if price:
            print(f"   ${price:.2f}")
        else:
            print("   Could not fetch")

        print("\n✅ Client initialized successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure ALPACA_API_KEY and ALPACA_SECRET_KEY are set.")
        sys.exit(1)
