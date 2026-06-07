#!/usr/bin/env python3
"""Alpaca API client - Hybrid REST + WebSocket for paper trading."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable

import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient

# Load .env from project root — this is the canonical credential source
from traderlib.paths import project_root
PROJECT_ROOT = project_root()
load_dotenv(PROJECT_ROOT / '.env')

from websockets.exceptions import ConnectionClosed
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockQuotesRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, StopLossRequest, GetAssetsRequest,
)

# SDK capability guard — fail gracefully on older SDK versions
try:
    from alpaca.trading.requests import StopOrderRequest, LimitOrderRequest
    STOP_ORDER_AVAILABLE = True
    LIMIT_ORDER_AVAILABLE = True
except ImportError:
    STOP_ORDER_AVAILABLE = False
    LIMIT_ORDER_AVAILABLE = False
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError

# Import rate limiter
sys.path.insert(0, str(Path(__file__).parent))
from traderlib.rate_limiter import RateLimiter, health_monitor
from traderlib.trading_exceptions import TradingExceptionHandler, APIKeyError


class AlpacaClient:
    """Unified Alpaca REST + WebSocket client for paper trading."""

    def __init__(self, mode: str = 'paper', data_only: bool = False):
        """Initialize Alpaca clients.

        Args:
            mode: 'paper' or 'live'
            data_only: If True, skip TradingClient creation. Only creates
                       StockHistoricalDataClient for data access. Backtests
                       use this to avoid connecting to any trading sub-account.
        """
        self.mode = mode
        self.data_only = data_only

        # Key loading: mode-specific vars take priority, plain vars are fallback.
        # Paper/data-only:  ALPACA_PAPER_API_KEY  → ALPACA_API_KEY
        # Live:             ALPACA_LIVE_API_KEY   → ALPACA_API_KEY
        _prefix = 'ALPACA_LIVE_' if mode == 'live' else 'ALPACA_PAPER_'
        self.api_key = os.getenv(f'{_prefix}API_KEY') or os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv(f'{_prefix}SECRET_KEY') or os.getenv('ALPACA_SECRET_KEY')

        if not self.api_key or not self.secret_key:
            raise APIKeyError("Alpaca")

        # Historical data configuration (default 365 days for full Stage 2 scoring)
        self.historical_days = int(os.getenv('ALPACA_HISTORICAL_DAYS', '365'))

        # Initialize REST clients
        if data_only:
            self.trading_client = None
        else:
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

        # Rate limiter - load from config (default to paid tier: 10000/min)
        rate_config = self._load_rate_limiter_config()
        self.rate_limiter = RateLimiter(
            max_requests=rate_config.get('max_requests', 10000),
            window_seconds=rate_config.get('window_seconds', 60)
        )

    def _load_rate_limiter_config(self) -> Dict:
        """Load rate limiter configuration from screener_config.yaml."""
        from pathlib import Path

        config_paths = [
            project_root() / 'config' / 'screener_config.yaml',
            Path('config/screener_config.yaml'),
        ]

        import yaml
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        if config and 'rate_limiter' in config:
                            return config['rate_limiter']
                except Exception:
                    pass

        # Default: Paid tier limits (10000/min)
        return {'max_requests': 10000, 'window_seconds': 60}

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

    def get_assets(self, status: str = 'active', asset_class: str = 'us_equity') -> List:
        """
        Get list of assets from Alpaca.

        Args:
            status: Asset status ('active', 'inactive', 'all')
            asset_class: Asset class ('us_equity', etc.)

        Returns:
            List of Asset objects
        """
        if not self.rate_limiter.can_make_request():
            wait = self.rate_limiter.get_wait_time()
            if wait > 0:
                import time
                print(f"⏳ Rate limit: waiting {wait:.1f}s")
                time.sleep(wait)

        try:
            self.rate_limiter.record_request()
            # Use GetAssetsRequest with the get_all_assets method
            from alpaca.trading.enums import AssetStatus, AssetClass
            filter_req = GetAssetsRequest(
                status=AssetStatus(status) if status != 'all' else None,
                asset_class=AssetClass(asset_class)
            )
            assets = self.trading_client.get_all_assets(filter=filter_req)
            self.rate_limiter.record_success()
            health_monitor.mark_success('alpaca')
            self.api_error_count = 0
            return assets
        except APIError as e:
            self.rate_limiter.record_error(is_rate_limit=e.status_code == 429)
            health_monitor.mark_failure('alpaca')
            self.api_error_count += 1
            if e.status_code in (401, 403):
                raise APIKeyError(
                    "Alpaca",
                    f"Authentication failed ({e.status_code}). Keys may be invalid or expired."
                ) from e
            raise
        except Exception as e:
            self.rate_limiter.record_error(is_rate_limit=False)
            health_monitor.mark_failure('alpaca')
            TradingExceptionHandler.log_exception(
                "get_assets", e,
                severity=TradingExceptionHandler.ERROR
            )
            return []

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

            # Handle both dict and object responses (SDK returns dict for single-symbol)
            if hasattr(quotes, 'data'):
                quotes_dict = quotes.data
            elif isinstance(quotes, dict):
                quotes_dict = quotes
            else:
                quotes_dict = {}

            if ticker in quotes_dict:
                quote = quotes_dict[ticker]
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

    def get_latest_prices_batch(self, tickers: list[str]) -> dict[str, Optional[float]]:
        """Fetch current prices for multiple tickers in a single API call.

        Checks WebSocket cache first, then batches remaining tickers into a
        single quotes API call. Uses 1 API call instead of N for non-cached
        tickers.

        Args:
            tickers: List of ticker symbols to fetch prices for.

        Returns:
            Dict mapping ticker to price (or None if unavailable).
        """
        result: dict[str, Optional[float]] = {}
        need_quotes: list[str] = []

        # 1. Check cache for all tickers first
        for ticker in tickers:
            cached = self.get_cached_price(ticker)
            if cached:
                result[ticker] = cached
            else:
                need_quotes.append(ticker)

        if not need_quotes:
            return result

        # 2. Check positions API for tickers in portfolio (single call)
        try:
            all_positions = self.trading_client.get_all_positions()
            position_map = {p.symbol: p for p in all_positions}
        except Exception:
            position_map = {}

        still_need_quotes: list[str] = []
        for ticker in need_quotes:
            if ticker in position_map and position_map[ticker].current_price:
                price = float(position_map[ticker].current_price)
                result[ticker] = price
                self.price_cache[ticker] = {
                    'price': price,
                    'timestamp': datetime.now(),
                }
            else:
                still_need_quotes.append(ticker)

        if not still_need_quotes:
            return result

        # 3. Batch quotes API call for remaining tickers
        if not self.rate_limiter.can_make_request():
            for ticker in still_need_quotes:
                result[ticker] = None
            return result

        try:
            self.rate_limiter.record_request()
            from alpaca.data.requests import StockLatestQuoteRequest

            request = StockLatestQuoteRequest(symbol_or_symbols=still_need_quotes)
            quotes_response = self.data_client.get_stock_latest_quote(request)

            # Alpaca SDK returns Dict[str, Quote] for batch requests
            # (not an object with .data attribute like single-symbol responses)
            if hasattr(quotes_response, 'data'):
                quotes_dict = quotes_response.data
            elif isinstance(quotes_response, dict):
                quotes_dict = quotes_response
            else:
                quotes_dict = {}

            fetched = 0
            for ticker in still_need_quotes:
                if ticker in quotes_dict:
                    quote = quotes_dict[ticker]
                    if quote.bid_price and quote.ask_price:
                        price = float((quote.bid_price + quote.ask_price) / 2)
                    elif quote.bid_price:
                        price = float(quote.bid_price)
                    elif quote.ask_price:
                        price = float(quote.ask_price)
                    else:
                        result[ticker] = None
                        continue

                    result[ticker] = price
                    self.price_cache[ticker] = {
                        'price': price,
                        'timestamp': datetime.now(),
                    }
                    fetched += 1
                else:
                    result[ticker] = None

            if fetched > 0:
                self.rate_limiter.record_success()
                health_monitor.mark_success('alpaca')

        except Exception as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            print(f"   ⚠️  Batch quotes API failed: {e}")
            for ticker in still_need_quotes:
                if ticker not in result:
                    result[ticker] = None

        return result

    def get_bars(self, ticker: str, limit: int = None) -> Optional[pd.DataFrame]:
        """Get historical daily bars with rate limiting.

        Alias for get_historical_bars for backwards compatibility.
        Converts limit (trading bars) to calendar days.

        Args:
            ticker: Stock symbol
            limit: Number of trading bars to fetch (default: uses configured historical_days)

        Returns:
            DataFrame with OHLCV data indexed by Timestamp
        """
        # Convert limit (trading bars) to calendar days
        # ~252 trading days per year, so multiply by 365/252 ≈ 1.45
        if limit:
            days = int(limit * 1.45)  # Convert trading days to calendar days
        else:
            days = self.historical_days
        return self.get_historical_bars(ticker, days=days)

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

    def submit_stop_order(self, ticker: str, shares: int, stop_price: float,
                          side: str = 'buy') -> Optional[Dict]:
        """Submit a stop-entry order (triggers when price >= stop_price).

        Args:
            ticker: Stock symbol
            shares: Number of shares
            stop_price: Stop price (triggers market order when reached)
            side: 'buy' or 'sell'

        Returns:
            Order dict or None if submission failed
        """
        if not STOP_ORDER_AVAILABLE:
            print("⚠️  StopOrderRequest not available in Alpaca SDK. Update alpaca-py.")
            return None

        if not self.rate_limiter.can_make_request():
            wait = self.rate_limiter.get_wait_time()
            print(f"⏳ Rate limited: waiting {wait:.1f}s before order")
            import time
            time.sleep(wait)

        try:
            self.rate_limiter.record_request()
            order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL

            request = StopOrderRequest(
                symbol=ticker,
                qty=shares,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                stop_price=stop_price
            )
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
            if e.status_code in (401, 403):
                print(f"\n❌ Stop order failed: Authentication error ({e.status_code})")
                print("   Your API keys may be invalid or expired.")
                print("   Run: python3 scripts/setup_alpaca.py")
            else:
                print(f"❌ Stop order failed: {e}")
            return None
        except (ConnectionError, TimeoutError) as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            TradingExceptionHandler.log_exception(
                "submit_stop_order", e,
                severity=TradingExceptionHandler.ERROR,
                ticker=ticker
            )
            return None

    def submit_limit_order(self, ticker: str, shares: int, limit_price: float,
                           side: str = 'buy',
                           stop_price: Optional[float] = None) -> Optional[Dict]:
        """Submit a limit order.

        Args:
            ticker: Stock symbol
            shares: Number of shares
            limit_price: Maximum/minimum price for fill
            side: 'buy' or 'sell'
            stop_price: Optional stop loss price (for entries)

        Returns:
            Order dict or None if submission failed
        """
        if not LIMIT_ORDER_AVAILABLE:
            print("⚠️  LimitOrderRequest not available in Alpaca SDK. Update alpaca-py.")
            return None

        if not self.rate_limiter.can_make_request():
            wait = self.rate_limiter.get_wait_time()
            print(f"⏳ Rate limited: waiting {wait:.1f}s before order")
            import time
            time.sleep(wait)

        try:
            self.rate_limiter.record_request()
            order_side = OrderSide.BUY if side == 'buy' else OrderSide.SELL

            order_data = {
                'symbol': ticker,
                'qty': shares,
                'side': order_side,
                'time_in_force': TimeInForce.DAY,
                'limit_price': limit_price
            }

            if stop_price and side == 'buy':
                order_data['stop_loss'] = StopLossRequest(stop_price=stop_price)

            request = LimitOrderRequest(**order_data)
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
                'limit_price': float(order.limit_price) if order.limit_price else None
            }

        except APIError as e:
            is_rate_limit = e.status_code == 429
            self.rate_limiter.record_error(is_rate_limit=is_rate_limit)
            health_monitor.mark_failure('alpaca')
            if e.status_code in (401, 403):
                print(f"\n❌ Limit order failed: Authentication error ({e.status_code})")
                print("   Your API keys may be invalid or expired.")
                print("   Run: python3 scripts/setup_alpaca.py")
            else:
                print(f"❌ Limit order failed: {e}")
            return None
        except (ConnectionError, TimeoutError) as e:
            self.rate_limiter.record_error()
            health_monitor.mark_failure('alpaca')
            TradingExceptionHandler.log_exception(
                "submit_limit_order", e,
                severity=TradingExceptionHandler.ERROR,
                ticker=ticker
            )
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
        except (ConnectionError, TimeoutError) as e:
            TradingExceptionHandler.log_exception(
                "get_order", e,
                severity=TradingExceptionHandler.WARNING,
                order_id=order_id
            )
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order by ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            self.trading_client.cancel_order_by_id(order_id)
            return True
        except (ConnectionError, TimeoutError) as e:
            TradingExceptionHandler.log_exception(
                "cancel_order", e,
                severity=TradingExceptionHandler.WARNING,
                order_id=order_id
            )
            return False

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
                websocket_params={
                    'ssl': ssl_context,
                    'ping_interval': 30,  # Send keepalive pings every 30s (default 20s)
                    'ping_timeout': 60,    # Wait 60s for pong (default 20s) — prevents code 1011 disconnects
                }
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
        self.last_ws_message = datetime.now()  # Consider healthy immediately on connect
        # Reset reconnect delay on successful connection
        self.ws_reconnect_delay = 5
        print(f"📡 WebSocket stream starting for {len(tickers)} tickers...")

        stream_task = None
        watchdog_task = None
        try:
            # Run the stream with a health watchdog.
            # The SDK's _run_forever() has an internal reconnection loop with zero
            # delay, which causes a rapid TimeoutError cascade on disconnect.
            # The watchdog force-stops the stream if no messages arrive for 90s,
            # breaking the SDK's infinite loop and allowing our exponential backoff.
            stream_task = asyncio.create_task(self.stream._run_forever())
            watchdog_task = asyncio.create_task(
                self._ws_health_watchdog(stream_task)
            )

            done, pending = await asyncio.wait(
                [stream_task, watchdog_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If watchdog finished first, WS was unhealthy — stop the stream
            if watchdog_task in done:
                await self.stop_price_stream()

            # Propagate any exception from the stream task
            if stream_task.done() and stream_task.exception():
                raise stream_task.exception()
        except asyncio.CancelledError:
            # Normal shutdown
            print("🔄 WebSocket cancelled (normal shutdown)")
        except ConnectionClosed as e:
            # Common disconnects - don't show error code to reduce noise
            code_str = f" (code: {e.code})" if hasattr(e, 'code') and e.code else ""
            print(f"⚠️ WebSocket disconnected{code_str}, will reconnect...")
        except Exception as e:
            error_str = str(e).lower()
            # Check for rate limit or connection limit errors
            if "connection limit exceeded" in error_str or "429" in error_str:
                print(f"⚠️ Alpaca connection limit hit - forcing extended backoff")
                # Force a much longer backoff (5 minutes) to let limits reset
                self.ws_reconnect_delay = 300
            else:
                print(f"⚠️ WebSocket error: {e}")
        finally:
            # Cancel any still-running tasks
            for task in [watchdog_task, stream_task]:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
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

    async def _ws_health_watchdog(self, stream_task: asyncio.Task):
        """Force-stop the stream if no messages received for 90s.

        The Alpaca SDK's _run_forever() has an internal reconnection loop with
        zero delay between attempts, causing a rapid TimeoutError cascade on
        disconnect. This watchdog detects when the connection has been unhealthy
        for too long and force-stops the stream (via stop_ws()), breaking the
        SDK's infinite loop and allowing our exponential backoff to work.
        """
        unhealthy_since = None
        while not stream_task.done():
            await asyncio.sleep(5)
            if not self.is_ws_healthy():
                if unhealthy_since is None:
                    unhealthy_since = datetime.now()
                elif (datetime.now() - unhealthy_since).total_seconds() > 90:
                    print("⚠️ WebSocket unhealthy for 90s, force-stopping for reconnect...")
                    try:
                        await self.stream.stop_ws()
                    except Exception:
                        pass
                    return  # Exit triggers stream_task completion in start_price_stream
            else:
                unhealthy_since = None

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
