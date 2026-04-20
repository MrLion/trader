#!/usr/bin/env python3
"""Universe builder for dynamic stock discovery.

Fetches active US equities from Alpaca, applies prefilter pipeline
(cheap filters first, expensive filters last), and caches results.

MarketSurge-style funnel:
1. Asset metadata filters (FREE) — tradable, exclude OTC/AMEX
2. Price filter (FREE) — from asset.last_price
3. Dollar volume filter (EXPENSIVE) — only for survivors
4. Cache to disk with same-day invalidation
"""

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
import yaml
from alpaca.data.enums import Adjustment

from traderlib.alpaca_client import AlpacaClient
from traderlib.trading_exceptions import TradingExceptionHandler


@dataclass
class UniverseResult:
    """Result from universe building with funnel metrics."""
    tickers: List[str]
    profile: str
    total_assets: int = 0
    after_tradable_filter: int = 0
    after_price_filter: int = 0
    after_dvol_filter: int = 0
    cache_path: Optional[Path] = None
    cache_hit: bool = False
    cache_age_hours: float = 0.0
    funnel_metrics: Dict[str, int] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to DataFrame for export."""
        df = pd.DataFrame({'Ticker': self.tickers})
        df['Profile'] = self.profile
        df['GeneratedDate'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return df


class UniverseBuilder:
    """Build and cache stock universes from Alpaca with prefilter pipeline."""

    CACHE_TTL_HOURS = 4  # Refresh every 4 hours during market hours
    UNIVERSES_DIR = Path(__file__).parent.parent / 'data' / 'universes'

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize universe builder.

        Args:
            config_path: Path to screener_config.yaml (default: config/screener_config.yaml)
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'screener_config.yaml'

        self.config_path = config_path
        self.config = self._load_config()
        self.alpaca = AlpacaClient(mode='paper')  # Data-only mode

        # Ensure cache directory exists
        self.UNIVERSES_DIR.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> dict:
        """Load universe configuration from YAML."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('universes', {})
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "universe_config_load", e,
                severity=TradingExceptionHandler.WARNING
            )
            # Default config
            return {
                'default': 'large_cap',
                'large_cap': {
                    'min_price': 10,
                    'min_dollar_volume': 80000000,
                    'lookback_days': 60,
                    'exclude_exchanges': ['OTC', 'AMEX']
                },
                'high_octane': {
                    'min_price': 2,
                    'min_dollar_volume': 20000000,
                    'lookback_days': 60,
                    'exclude_exchanges': ['OTC', 'AMEX']
                }
            }

    def _get_cache_path(self, profile: str) -> Path:
        """Get cache file path for profile."""
        today = date.today().strftime('%Y-%m-%d')
        return self.UNIVERSES_DIR / f'{profile}_{today}.csv'

    def _load_cached(self, cache_path: Path) -> Optional[UniverseResult]:
        """
        Load cached universe if valid.

        Returns None if cache is expired or invalid.
        """
        if not cache_path.exists():
            return None

        # Check cache age
        cache_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age_hours = (datetime.now() - cache_mtime).total_seconds() / 3600

        # Same-day cache with TTL
        if age_hours > self.CACHE_TTL_HOURS:
            return None

        try:
            df = pd.read_csv(cache_path)
            tickers = df['Ticker'].tolist()

            # Reconstruct funnel metrics from cache header if available
            funnel_metrics = {}
            for col in ['TotalAssets', 'AfterTradable', 'AfterPrice', 'AfterDVol']:
                if col in df.columns:
                    funnel_metrics[col.lower()] = int(df[col].iloc[0]) if len(df) > 0 else 0

            # Populate UniverseResult fields from cached funnel metrics
            return UniverseResult(
                tickers=tickers,
                profile='cached',
                total_assets=funnel_metrics.get('totalassets', 0),
                after_tradable_filter=funnel_metrics.get('aftertradable', 0),
                after_price_filter=funnel_metrics.get('afterprice', 0),
                after_dvol_filter=funnel_metrics.get('afterdvol', 0),
                cache_path=cache_path,
                cache_hit=True,
                cache_age_hours=age_hours,
                funnel_metrics=funnel_metrics
            )
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "universe_cache_load", e,
                severity=TradingExceptionHandler.WARNING
            )
            return None

    def _save_cache(self, result: UniverseResult, cache_path: Path):
        """Save universe to cache using atomic write pattern."""
        df = result.to_dataframe()

        # Add funnel metrics as columns (repeated for each row, but enables easy CSV inspection)
        df['TotalAssets'] = result.total_assets
        df['AfterTradable'] = result.after_tradable_filter
        df['AfterPrice'] = result.after_price_filter
        df['AfterDVol'] = result.after_dvol_filter

        # Atomic write: write to temp file, then rename
        temp_path = cache_path.with_suffix('.tmp')
        try:
            df.to_csv(temp_path, index=False)
            temp_path.replace(cache_path)  # Atomic on Unix
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "universe_cache_save", e,
                severity=TradingExceptionHandler.WARNING
            )
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()

    def _fetch_assets(self) -> List:
        """Fetch all active US equities from Alpaca."""
        try:
            return self.alpaca.get_assets(status='active', asset_class='us_equity')
        except Exception as e:
            TradingExceptionHandler.log_exception(
                "universe_fetch_assets", e,
                severity=TradingExceptionHandler.CRITICAL
            )
            return []

    def _get_current_prices(self, tickers: List[str]) -> Dict[str, float]:
        """Get current prices for a list of tickers with batching and rate limiting."""
        prices = {}
        batch_size = 100  # Safe batch size to avoid 414 errors
        total_batches = (len(tickers) + batch_size - 1) // batch_size

        # Process in batches
        for i, batch_start in enumerate(range(0, len(tickers), batch_size)):
            batch = tickers[batch_start:batch_start + batch_size]
            try:
                batch_prices = self.alpaca.get_latest_prices_batch(batch)
                for k, v in batch_prices.items():
                    if v is not None:
                        prices[k] = v
            except Exception:
                # Fallback for this batch: fetch individually
                for ticker in batch:
                    try:
                        price = self.alpaca.get_latest_price(ticker)
                        if price:
                            prices[ticker] = price
                    except Exception:
                        pass

            # Rate limiting: wait if needed between batches
            # (paid tier: 10000/min handles rapid-fire requests; no artificial delays needed)

        return prices

    def _compute_dollar_volumes(self, tickers: List[str], lookback_days: int) -> Dict[str, float]:
        """Compute average daily dollar volume for multiple tickers.

        Processes in chunks of 500 to avoid URL-length limits on large universes.

        Args:
            tickers: List of ticker symbols
            lookback_days: Number of days to fetch

        Returns:
            Dict mapping ticker to average daily dollar volume
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from datetime import datetime, timedelta

        results = {}
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        chunk_size = 500

        for chunk_start in range(0, len(tickers), chunk_size):
            chunk = tickers[chunk_start:chunk_start + chunk_size]
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=chunk,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=end,
                    adjustment=Adjustment.ALL
                )

                bars_response = self.alpaca.data_client.get_stock_bars(request)
                bars_dict = bars_response.data if hasattr(bars_response, 'data') else bars_response

                for ticker in chunk:
                    if ticker not in bars_dict:
                        continue
                    bars = bars_dict[ticker]
                    if len(bars) < 10:
                        continue
                    dollar_vols = [b.close * b.volume for b in bars]
                    results[ticker] = sum(dollar_vols) / len(dollar_vols)

            except Exception:
                # Fallback: compute individually for failed chunk
                for ticker in chunk:
                    if ticker not in results:
                        dvol = self._compute_dollar_volume_single(ticker, lookback_days)
                        if dvol:
                            results[ticker] = dvol

        return results

    def _compute_dollar_volume_single(self, ticker: str, lookback_days: int) -> Optional[float]:
        """Compute average daily dollar volume for single ticker (fallback)."""
        try:
            bars = self.alpaca.get_historical_bars(ticker, days=lookback_days)
            if bars is None or len(bars) < 10:
                return None

            # Dollar volume = close * volume
            dollar_vol = (bars['Close'] * bars['Volume']).mean()
            return float(dollar_vol)
        except Exception:
            return None

    def build_universe(self, profile: str, force_refresh: bool = False) -> UniverseResult:
        """
        Build universe with prefilter pipeline.

        Args:
            profile: Universe profile name ('large_cap' or 'high_octane')
            force_refresh: If True, bypass cache and rebuild

        Returns:
            UniverseResult with tickers and funnel metrics
        """
        # Get profile config
        profile_config = self.config.get(profile, self.config.get(self.config.get('default', 'large_cap')))
        if not profile_config:
            profile_config = self.config['large_cap']

        min_price = profile_config.get('min_price', 10)
        min_dvol = profile_config.get('min_dollar_volume', 80000000)
        lookback_days = profile_config.get('lookback_days', 60)
        exclude_exchanges = profile_config.get('exclude_exchanges', ['OTC', 'AMEX'])

        # Check cache first
        cache_path = self._get_cache_path(profile)
        if not force_refresh:
            cached = self._load_cached(cache_path)
            if cached:
                cached.profile = profile
                return cached

        # STEP 1: Fetch all assets (FREE)
        print(f"  Fetching assets from Alpaca...")
        all_assets = self._fetch_assets()
        total_assets = len(all_assets)
        print(f"  Fetched {total_assets:,} assets")

        # STEP 2: Cheap filters — tradable, exchange, and ETF exclusion (FREE)
        def is_etf(asset) -> bool:
            """Detect ETFs by name pattern (Alpaca API doesn't distinguish stocks vs ETFs)."""
            if not getattr(asset, 'name', None):
                return False
            name = asset.name.upper()
            # Direct ETF indicators
            if 'ETF' in name or 'EXCHANGE-TRADED FUND' in name:
                return True
            # Trusts from known ETF providers (QQQ, SPDR, etc.)
            if 'TRUST' in name:
                etf_providers = ['SPDR', 'QQQ', 'ISHARES', 'VANGUARD', 'INVESCO', 'PROSHARES']
                if any(x in name for x in etf_providers):
                    return True
            # "Fund" names that are typically ETFs (WisdomTree, PIMCO, RBB Fund, etc.)
            if 'FUND' in name:
                etf_fund_providers = ['WISDOMTREE', 'PIMCO', 'RBB FUND', 'ALPHA ARCHITECT', 'STATE STREET']
                if any(x in name for x in etf_fund_providers):
                    return True
            return False

        # high_octane: require marginable=True to exclude non-institutional penny stocks
        # while still admitting fallen large-caps (e.g. EBAY) which remain marginable
        require_marginable = (profile == 'high_octane')

        filtered = [
            a for a in all_assets
            if getattr(a, 'tradable', False)
            and getattr(a, 'exchange', '') not in exclude_exchanges
            and not is_etf(a)
            and (not require_marginable or getattr(a, 'marginable', False))
        ]
        after_tradable = len(filtered)
        etf_count = sum(1 for a in all_assets if is_etf(a))
        marginable_note = ", marginable only" if require_marginable else ""
        print(f"  Filtered to {after_tradable:,} (tradable, exclude {', '.join(exclude_exchanges)}, {etf_count:,} ETFs{marginable_note})")

        # STEP 3: Get current prices for filtered assets (EXPENSIVE — API calls)
        # Extract tickers from assets
        tickers_to_check = [getattr(a, 'symbol', None) for a in filtered if getattr(a, 'symbol', None)]
        print(f"  Fetching current prices for {len(tickers_to_check)} tickers...")
        current_prices = self._get_current_prices(tickers_to_check)
        print(f"  Received prices for {len(current_prices)} tickers")

        # Filter by price using fetched prices
        filtered_with_price = [
            a for a in filtered
            if current_prices.get(getattr(a, 'symbol', ''), 0) >= min_price
        ]
        after_price = len(filtered_with_price)
        print(f"  Filtered to {after_price:,} (price ≥ ${min_price})")

        # STEP 4: Dollar volume filter (EXPENSIVE — bar fetch for survivors only)
        # Use batch API for much faster processing
        print(f"  Computing liquidity metrics for {after_price:,} stocks ({lookback_days}-day lookback)...")

        # Extract tickers
        tickers_for_dvol = [getattr(a, 'symbol', None) for a in filtered_with_price if getattr(a, 'symbol', None)]

        # Batch compute dollar volumes (single API call for all tickers)
        dollar_volumes = self._compute_dollar_volumes(tickers_for_dvol, lookback_days)

        # Filter by dollar volume (min and optional max)
        max_dvol = profile_config.get('max_dollar_volume')
        if max_dvol:
            validated = [
                t for t, dvol in dollar_volumes.items()
                if dvol and dvol >= min_dvol and dvol <= max_dvol
            ]
            after_dvol = len(validated)
            print(f"  Filtered to {after_dvol:,} (dollar vol ${min_dvol/1e6:.0f}M-${max_dvol/1e6:.0f}M)")
        else:
            validated = [t for t, dvol in dollar_volumes.items() if dvol and dvol >= min_dvol]
            after_dvol = len(validated)
            print(f"  Filtered to {after_dvol:,} (dollar vol ≥ ${min_dvol/1e6:.0f}M)")

        # Build result
        result = UniverseResult(
            tickers=validated,
            profile=profile,
            total_assets=total_assets,
            after_tradable_filter=after_tradable,
            after_price_filter=after_price,
            after_dvol_filter=after_dvol,
            cache_path=cache_path,
            cache_hit=False,
            funnel_metrics={
                'total_assets': total_assets,
                'after_tradable': after_tradable,
                'after_price': after_price,
                'after_dvol': after_dvol
            }
        )

        # Save cache
        self._save_cache(result, cache_path)
        print(f"  Saved to {cache_path}")

        return result

    def get_profile_config(self, profile: str) -> dict:
        """Return the full config dict for a profile (universe + screener params)."""
        default_profile = self.config.get('default', 'large_cap')
        return self.config.get(profile, self.config.get(default_profile, {}))

    def load_universe(self, profile: str = None, force_refresh: bool = False) -> UniverseResult:
        """
        Load or build universe for profile.

        Args:
            profile: Universe profile name (default: from config)
            force_refresh: If True, bypass cache

        Returns:
            UniverseResult with tickers
        """
        if profile is None:
            profile = self.config.get('default', 'large_cap')

        return self.build_universe(profile, force_refresh)
