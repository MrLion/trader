import threading
import time
from pathlib import Path

import pandas as pd
import pytest


class TestThreadSafeRateLimiter:
    """Rate limiter must enforce budget across concurrent threads."""

    def test_enforces_gap_between_two_threads(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        # Bucket of 1 token: first call drains it, second call must wait ~60s
        # But we don't want to wait 60s in tests, so use a high rate
        # Instead, drain the bucket first, then test the next call
        limiter = ThreadSafeRateLimiter(max_per_minute=60)
        timestamps = []

        # Drain the bucket
        for _ in range(60):
            limiter.tokens = max(0.0, limiter.tokens - 1.0)

        def worker():
            limiter.acquire()
            timestamps.append(time.monotonic())

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        start = time.monotonic()
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(timestamps) == 2
        gap = timestamps[1] - timestamps[0]
        # With bucket drained, at least one thread should wait ~1s for token refill
        assert gap >= 0.8, f"Expected ~1s gap at 60/min, got {gap:.3f}s"

    def test_first_call_never_blocks(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        limiter = ThreadSafeRateLimiter(max_per_minute=300)
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1, f"First call blocked for {elapsed:.3f}s"

    def test_respects_max_per_minute_budget(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        limiter = ThreadSafeRateLimiter(max_per_minute=120)  # 2 calls / sec
        timestamps = []

        # Drain the bucket so the 3rd call must wait
        for _ in range(120):
            limiter.tokens = max(0.0, limiter.tokens - 1.0)

        for _ in range(3):
            limiter.acquire()
            timestamps.append(time.monotonic())

        # With bucket drained, 3 calls at 2/sec should take ~1 second total
        total = timestamps[2] - timestamps[0]
        assert total >= 0.8, f"Expected ~1s for 3 calls at 120/min, got {total:.3f}s"

    def test_thread_safety_under_contention(self):
        from traderlib.sector_resolver import ThreadSafeRateLimiter

        limiter = ThreadSafeRateLimiter(max_per_minute=300)
        timestamps = []
        errors = []

        def worker():
            try:
                limiter.acquire()
                timestamps.append(time.monotonic())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during contention: {errors}"
        assert len(timestamps) == 20


class TestSectorResolverWatchlistFallback:
    def test_resolves_from_watchlist(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL") == "Technology"

    def test_watchlist_unknown_ticker(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("UNKNOWN") == "Unknown"

    def test_watchlist_missing_sector_column(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL") == "Unknown"


class TestSectorResolverUniverseFallback:
    def test_resolves_from_universe_csv(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        universe = tmp_path / "large_cap_2026-05-17.csv"
        pd.DataFrame({
            "Ticker": ["AAPL", "MSFT"],
            "Sector": ["Technology", "Technology"],
            "Profile": ["large_cap", "large_cap"],
        }).to_csv(universe, index=False)

        resolver = SectorResolver()
        assert resolver.resolve("AAPL", universe_path=universe) == "Technology"

    def test_watchlist_overrides_universe(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Consumer Discretionary"],
        }).to_csv(watchlist, index=False)

        universe = tmp_path / "universe.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(universe, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        assert resolver.resolve("AAPL", universe_path=universe) == "Consumer Discretionary"

    def test_universe_missing_sector_column(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        universe = tmp_path / "universe.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
        }).to_csv(universe, index=False)

        resolver = SectorResolver()
        assert resolver.resolve("AAPL", universe_path=universe) == "Unknown"


class TestSectorResolverCaching:
    def test_caches_watchlist_results(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL"],
            "Sector": ["Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        # First call
        result1 = resolver.resolve("AAPL")
        # Second call should hit cache
        result2 = resolver.resolve("AAPL")
        assert result1 == "Technology"
        assert result2 == "Technology"
        assert len(resolver._cache) == 1

    def test_cache_persists_across_calls(self, tmp_path: Path):
        from traderlib.sector_resolver import SectorResolver

        watchlist = tmp_path / "watchlist.csv"
        pd.DataFrame({
            "Ticker": ["AAPL", "MSFT"],
            "Sector": ["Technology", "Technology"],
        }).to_csv(watchlist, index=False)

        resolver = SectorResolver(watchlist_path=watchlist)
        resolver.resolve("AAPL")
        resolver.resolve("MSFT")
        assert resolver._cache == {"AAPL": "Technology", "MSFT": "Technology"}


class TestSectorResolverFMPFallback:
    def test_fmp_fallback_without_key_returns_unknown(self):
        from traderlib.sector_resolver import SectorResolver

        resolver = SectorResolver(fmp_api_key=None)
        # No watchlist, no universe, no API key
        assert resolver.resolve("AAPL") == "Unknown"

    def test_prefetch_from_fmp_without_key_returns_all_unknown(self):
        from traderlib.sector_resolver import SectorResolver

        resolver = SectorResolver(fmp_api_key=None)
        result = resolver.prefetch_from_fmp(["AAPL", "MSFT"])
        assert result == {"AAPL": "Unknown", "MSFT": "Unknown"}
