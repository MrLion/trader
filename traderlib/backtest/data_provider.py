"""Data providers for backtesting.

Provides historical market data with anti-look-ahead slicing.
All data is sliced to <= sim_date to prevent future data leakage.
"""

from datetime import date
from typing import Optional, Protocol, runtime_checkable

import pandas as pd

from traderlib.rate_limiter import RateLimiter
from traderlib.market_hours import MarketHours


class InsufficientDataError(Exception):
    """Raised when a ticker has fewer rows than the minimum required."""
    def __init__(self, ticker: str, rows: int, min_required: int):
        self.ticker = ticker
        self.rows = rows
        self.min_required = min_required
        super().__init__(
            f"{ticker}: {rows} rows available, {min_required} required"
        )


@runtime_checkable
class DataFrameProvider(Protocol):
    """Protocol for data providers used by backtesting strategies."""

    def get_bars(self, ticker: str, as_of: date) -> pd.DataFrame:
        """Return OHLCV data with rows <= as_of.

        Args:
            ticker: Stock symbol
            as_of: Simulation date — only data on or before this date is returned

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            Index is DatetimeIndex

        Raises:
            InsufficientDataError: If fewer than min_lookback rows available
        """
        ...

    def get_trading_days(self, start: date, end: date) -> list[date]:
        """Return trading days between start and end (inclusive)."""
        ...


class AlpacaDataProvider:
    """Fetches historical data from Alpaca for backtesting.

    v1: In-memory only. Data is fetched on each get_bars() call.
    v2 (deferred): Parquet cache with cache_dir parameter.
    """

    def __init__(self, alpaca_client=None, min_lookback: int = 252):
        """Initialize with an Alpaca historical data client.

        Args:
            alpaca_client: StockHistoricalDataClient instance from alpaca-py
            min_lookback: Minimum rows required per ticker (default 252 for 1 year)
        """
        self._client = alpaca_client
        self._min_lookback = min_lookback
        self._cache: dict[str, pd.DataFrame] = {}
        self._rate_limiter = RateLimiter(max_requests=200, window_seconds=60)
        self._prefetched: bool = False
        self._market_hours = MarketHours()
        # Track tickers dropped due to insufficient data
        self.tickers_dropped: list[dict] = []

    def prefetch(self, tickers: list[str], start: date, end: date) -> None:
        """Bulk fetch all ticker data into memory.

        Uses rate limiting to stay within Alpaca's 200 req/min limit.
        Tickers with insufficient data are logged in self.tickers_dropped.

        Args:
            tickers: List of stock symbols to fetch
            start: Start date for historical data
            end: End date for historical data
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        for ticker in tickers:
            try:
                self._rate_limiter.wait_if_needed()
                request = StockBarsRequest(
                    symbol_or_symbols=ticker,
                    timeframe=TimeFrame.Day,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    adjustment='split',
                )
                bars = self._client.get_stock_bars(request)

                if ticker in bars:
                    df = bars[ticker].df
                    if len(df) < self._min_lookback:
                        self.tickers_dropped.append({
                            'ticker': ticker,
                            'reason': 'insufficient_data',
                            'rows': len(df),
                            'min_required': self._min_lookback,
                        })
                        continue
                    self._cache[ticker] = df
                else:
                    self.tickers_dropped.append({
                        'ticker': ticker,
                        'reason': 'no_data',
                        'rows': 0,
                        'min_required': self._min_lookback,
                    })
            except Exception as e:
                self.tickers_dropped.append({
                    'ticker': ticker,
                    'reason': f'error: {type(e).__name__}',
                    'rows': 0,
                    'min_required': self._min_lookback,
                })

        self._prefetched = True

    def get_bars(self, ticker: str, as_of: date) -> pd.DataFrame:
        """Return OHLCV data sliced to <= as_of.

        Args:
            ticker: Stock symbol
            as_of: Simulation date — data beyond this date is excluded

        Returns:
            DataFrame sliced to as_of with standard column names

        Raises:
            InsufficientDataError: If fewer than min_lookback rows after slicing
        """
        if ticker in self._cache:
            df = self._cache[ticker]
        else:
            # Fetch on-demand if not prefetched
            if self._client is not None:
                self.prefetch([ticker], start=date(2020, 1, 1), end=as_of)
                if ticker not in self._cache:
                    raise InsufficientDataError(ticker, 0, self._min_lookback)
                df = self._cache[ticker]
            else:
                raise ValueError(
                    f"No data for {ticker} and no Alpaca client configured"
                )

        # Slice to prevent look-ahead
        as_of_ts = pd.Timestamp(as_of, tz='UTC')
        if df.index.tz is None:
            as_of_ts = pd.Timestamp(as_of)

        sliced = df[df.index <= as_of_ts].copy()

        if len(sliced) < self._min_lookback:
            raise InsufficientDataError(ticker, len(sliced), self._min_lookback)

        return sliced

    def get_trading_days(self, start: date, end: date) -> list[date]:
        """Return trading days between start and end (inclusive)."""
        days = self._market_hours.get_trading_days(
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
        )
        return [d.date() for d in days]

    def get_current_price(self, ticker: str, as_of: date) -> Optional[float]:
        """Get closing price on a specific date.

        Convenience method for strategies that need a single price point.
        """
        try:
            df = self.get_bars(ticker, as_of)
            as_of_ts = pd.Timestamp(as_of, tz='UTC')
            if df.index.tz is None:
                as_of_ts = pd.Timestamp(as_of)
            # Find the row closest to as_of
            mask = df.index <= as_of_ts
            if mask.any():
                return float(df.loc[mask, 'Close'].iloc[-1])
            return None
        except InsufficientDataError:
            return None


class DictDataProvider:
    """In-memory data provider for testing.

    Accepts a dict of {ticker: DataFrame} and slicing logic.
    No network calls, no Alpaca dependency.
    """

    def __init__(self, data: dict[str, pd.DataFrame],
                 trading_days: Optional[list[date]] = None,
                 min_lookback: int = 10):
        """Initialize with pre-built data.

        Args:
            data: Dict mapping ticker symbols to OHLCV DataFrames
            trading_days: Optional list of trading days. If None, inferred from data.
            min_lookback: Minimum rows required (default 10 for tests)
        """
        self._data = data
        self._min_lookback = min_lookback
        self.tickers_dropped: list[dict] = []

        # Build trading days from data if not provided
        if trading_days is not None:
            self._trading_days = trading_days
        else:
            all_dates = set()
            for df in data.values():
                if hasattr(df.index, 'date'):
                    all_dates.update(d.date() if hasattr(d, 'date') else d for d in df.index)
                else:
                    all_dates.update(df.index)
            self._trading_days = sorted(all_dates)

    def get_bars(self, ticker: str, as_of: date) -> pd.DataFrame:
        """Return data sliced to <= as_of."""
        if ticker not in self._data:
            raise InsufficientDataError(ticker, 0, self._min_lookback)

        df = self._data[ticker]
        as_of_ts = pd.Timestamp(as_of)

        sliced = df[df.index <= as_of_ts].copy()

        if len(sliced) < self._min_lookback:
            raise InsufficientDataError(ticker, len(sliced), self._min_lookback)

        return sliced

    def get_trading_days(self, start: date, end: date) -> list[date]:
        """Return trading days within range."""
        return [d for d in self._trading_days if start <= d <= end]

    def get_current_price(self, ticker: str, as_of: date) -> Optional[float]:
        """Get closing price on a specific date."""
        try:
            df = self.get_bars(ticker, as_of)
            as_of_ts = pd.Timestamp(as_of)
            mask = df.index <= as_of_ts
            if mask.any():
                return float(df.loc[mask, 'Close'].iloc[-1])
            return None
        except InsufficientDataError:
            return None