import threading
import time

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
