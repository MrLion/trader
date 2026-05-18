import threading
import time


class ThreadSafeRateLimiter:
    """Token-bucket rate limiter with threading.Lock protection."""

    def __init__(self, max_per_minute: int = 300):
        self.max_per_minute = max_per_minute
        self.tokens = float(max_per_minute)
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
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
        self.acquire()
