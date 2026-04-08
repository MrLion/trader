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
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError

# Config path
CONFIG_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data/config')
CONFIG_FILE = CONFIG_DIR / 'alpaca_config.json'

# Import rate limiter
sys.path.insert(0, str(Path(__file__).parent))
from rate_limiter import RateLimiter, health_monitor


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
            raise ValueError("Alpaca API keys not found. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars.")

        # Initialize REST clients
        self.trading_client = TradingClient(self.api_key, self.secret_key, paper=(mode == 'paper'))
        self.data_client = StockHistoricalDataClient(self.api_key, self.secret_key)

        # WebSocket stream (initialized on demand)
        self.stream: Optional[StockDataStream] = None
        self.price_cache: Dict[str, Dict] = {}
        self._trade_handlers: List[Callable] = []
        self._order_handlers: List[Callable] = []

        # Health tracking
        self.last_ws_message = None
        self.ws_connected = False
        self.api_error_count = 0

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
            raise
        except Exception as e:
            health_monitor.mark_failure('alpaca')
            self.api_error_count += 1
            raise

    def get_latest_price(self, ticker: str, use_fallback: bool = True) -> Optional[float]:
        """Get latest trade price with rate limiting and fallback.

        Args:
            ticker: Stock symbol
            use_fallback: If True, fallback to yfinance on failure
        """
        # Check WebSocket cache first
        cached = self.get_cached_price(ticker)
        if cached:
            return cached

        if not self.rate_limiter.can_make_request():
            if use_fallback:
                return self._yfinance_fallback_price(ticker)
            return None

        try:
            self.rate_limiter.record_request()
            from alpaca.data.requests import StockTradesRequest

            request = StockTradesRequest(symbol_or_symbols=ticker)
            trades = self.data_client.get_stock_trades(request)

            if ticker in trades.data and len(trades.data[ticker]) > 0:
                price = float(trades.data[ticker][0].price)
                self.rate_limiter.record_success()
                health_monitor.mark_success('alpaca')
                return price

            return None

        except Exception as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')

            if use_fallback:
                return self._yfinance_fallback_price(ticker)
            return None

    def _yfinance_fallback_price(self, ticker: str) -> Optional[float]:
        """Fallback to yfinance for price data."""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m")
            if len(hist) > 0:
                price = float(hist['Close'].iloc[-1])
                health_monitor.mark_success('yfinance')
                return price
        except Exception:
            pass
        return None

    def get_historical_bars(self, ticker: str, days: int = 252,
                           use_fallback: bool = True) -> Optional[pd.DataFrame]:
        """Get historical daily bars with rate limiting and fallback."""
        if not self.rate_limiter.can_make_request():
            if use_fallback:
                return self._yfinance_fallback_bars(ticker, days)
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
                feed=DataFeed.IEX  # Free tier feed
            )

            bars = self.data_client.get_stock_bars(request)

            if ticker not in bars.data:
                if use_fallback:
                    return self._yfinance_fallback_bars(ticker, days)
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

            if use_fallback:
                return self._yfinance_fallback_bars(ticker, days)
            return None

    def _yfinance_fallback_bars(self, ticker: str, days: int = 252) -> Optional[pd.DataFrame]:
        """Fallback to yfinance for historical bars."""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d")
            if len(hist) > 0:
                health_monitor.mark_success('yfinance')
                return hist
        except Exception:
            pass
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
            except Exception:
                pass
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
        print(f"📡 WebSocket stream starting for {len(tickers)} tickers...")

        try:
            # Run the stream - use _run_forever() to avoid event loop conflict
            # This is a known workaround for alpaca-py bug in v0.41.0-0.42.1
            await self.stream._run_forever()
        except asyncio.CancelledError:
            # Normal shutdown
            print("🔄 WebSocket cancelled (normal shutdown)")
        except Exception as e:
            print(f"⚠️ WebSocket error: {e}")
        finally:
            self.ws_connected = False
            self.stream = None

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

    def get_cached_price(self, ticker: str) -> Optional[float]:
        """Get price from WebSocket cache."""
        if ticker in self.price_cache:
            return self.price_cache[ticker]['price']
        return None

    def check_health(self) -> Dict:
        """Check client health."""
        return {
            'ws_connected': self.ws_connected,
            'ws_healthy': self.is_ws_healthy(),
            'api_errors': self.api_error_count,
            'cache_size': len(self.price_cache),
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
