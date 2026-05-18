import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/stable"
_REQUEST_TIMEOUT = 5


class ThreadSafeRateLimiter:
    """Token-bucket rate limiter with threading.Lock protection."""

    def __init__(self, max_per_minute: int = 300):
        self.max_per_minute = max_per_minute
        self.tokens = float(max_per_minute)
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.max_per_minute,
                    self.tokens + elapsed * (self.max_per_minute / 60.0),
                )
                self.last_update = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                sleep_time = (1.0 - self.tokens) * (60.0 / self.max_per_minute)

            time.sleep(sleep_time)


class SectorResolver:
    """Unified sector resolver with 3-tier fallback and in-memory cache."""

    def __init__(
        self,
        fmp_api_key: Optional[str] = None,
        watchlist_path: Optional[Path] = None,
        universe_dir: Optional[Path] = None,
    ):
        load_dotenv(_PROJECT_ROOT / ".env")
        self._cache: Dict[str, str] = {}
        self._fmp_api_key = fmp_api_key or os.environ.get("FMP_API_KEY")
        self._limiter = ThreadSafeRateLimiter(max_per_minute=300)
        self._watchlist_path = watchlist_path or (_PROJECT_ROOT / "data" / "watchlist.csv")
        self._universe_dir = universe_dir or (_PROJECT_ROOT / "data" / "universes")
        # Cached DataFrames to avoid repeated disk I/O
        self._watchlist_df: Optional[pd.DataFrame] = None
        self._watchlist_mtime: Optional[float] = None
        self._universe_df: Optional[pd.DataFrame] = None
        self._universe_mtime: Optional[float] = None
        self._universe_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, ticker: str, universe_path: Optional[Path] = None) -> str:
        """Return sector for ticker using cached 3-tier fallback."""
        ticker = ticker.upper()
        if ticker in self._cache:
            return self._cache[ticker]

        # 1. Watchlist
        sector = self._from_watchlist(ticker)
        if sector != "Unknown":
            self._cache[ticker] = sector
            return sector

        # 2. Universe
        if universe_path is None:
            universe_path = self._latest_universe_path()
        sector = self._from_universe(ticker, universe_path)
        if sector != "Unknown":
            self._cache[ticker] = sector
            return sector

        # 3. FMP fallback
        sector = self._from_fmp(ticker)
        self._cache[ticker] = sector
        return sector

    def resolve_many(
        self, tickers: List[str], universe_path: Optional[Path] = None
    ) -> Dict[str, str]:
        return {t: self.resolve(t, universe_path) for t in tickers}

    def prefetch_from_fmp(self, tickers: List[str]) -> Dict[str, str]:
        """Batch-fetch sectors from FMP and populate cache."""
        if not self._fmp_api_key:
            logger.warning("FMP_API_KEY not set; skipping sector prefetch")
            return {t: "Unknown" for t in tickers}

        from concurrent.futures import ThreadPoolExecutor

        def fetch_one(ticker: str) -> tuple[str, str]:
            self._limiter.acquire()
            import requests

            url = f"{_FMP_BASE}/profile"
            params = {"symbol": ticker, "apikey": self._fmp_api_key}
            try:
                resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    sector = data[0].get("sector", "Unknown")
                    if sector in ("—", "ETF", ""):
                        sector = "Unknown"
                    return ticker, sector
            except Exception as exc:
                logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
            return ticker, "Unknown"

        results: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_one, t) for t in tickers]
            for future in futures:
                t, s = future.result()
                results[t] = s
                self._cache[t] = s
        return results

    # ------------------------------------------------------------------
    # Internal fallback layers
    # ------------------------------------------------------------------

    def _from_watchlist(self, ticker: str) -> str:
        if not self._watchlist_path.exists():
            return "Unknown"
        try:
            mtime = self._watchlist_path.stat().st_mtime
            if self._watchlist_df is None or self._watchlist_mtime != mtime:
                self._watchlist_df = pd.read_csv(self._watchlist_path)
                self._watchlist_mtime = mtime
            df = self._watchlist_df
            if "Sector" not in df.columns:
                return "Unknown"
            row = df[df["Ticker"] == ticker]
            if row.empty:
                return "Unknown"
            val = row["Sector"].values[0]
            return str(val) if pd.notna(val) else "Unknown"
        except Exception:
            return "Unknown"

    def _from_universe(self, ticker: str, path: Optional[Path]) -> str:
        if path is None or not path.exists():
            return "Unknown"
        try:
            mtime = path.stat().st_mtime
            if self._universe_df is None or self._universe_path != path or self._universe_mtime != mtime:
                self._universe_df = pd.read_csv(path)
                self._universe_path = path
                self._universe_mtime = mtime
            df = self._universe_df
            if "Sector" not in df.columns:
                return "Unknown"
            row = df[df["Ticker"] == ticker]
            if row.empty:
                return "Unknown"
            val = row["Sector"].values[0]
            return str(val) if pd.notna(val) else "Unknown"
        except Exception:
            return "Unknown"

    def _from_fmp(self, ticker: str) -> str:
        """Single-ticker FMP fetch (slower than prefetch_from_fmp)."""
        if not self._fmp_api_key:
            return "Unknown"
        self._limiter.acquire()
        import requests

        url = f"{_FMP_BASE}/profile"
        params = {"symbol": ticker, "apikey": self._fmp_api_key}
        try:
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                sector = data[0].get("sector", "Unknown")
                if sector in ("—", "ETF", ""):
                    sector = "Unknown"
                return sector
        except Exception as exc:
            logger.debug("FMP sector fetch failed for %s: %s", ticker, exc)
        return "Unknown"

    def _latest_universe_path(self, profile: Optional[str] = None) -> Optional[Path]:
        """Auto-resolve the most recent universe CSV.

        Args:
            profile: Optional profile name filter (e.g. 'large_cap').
                     If None, searches across all profiles.
        """
        if not self._universe_dir.exists():
            return None
        pattern = (
            f"{profile}_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"
            if profile
            else "*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].csv"
        )
        matches = sorted(self._universe_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
        return matches[-1] if matches else None
