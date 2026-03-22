"""
Token-bucket rate limiter per domain.
Usage:
    limiter = RateLimiter(rate=0.33)   # 1 req / 3s
    await limiter.acquire()
    response = await client.get(url)
"""
import asyncio
import random
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """
    Async token-bucket rate limiter.
    rate: max requests per second (e.g., 0.33 = 1 req every 3s)
    jitter: fraction of wait time to randomize (0.2 = ±20%)
    """
    rate: float = 0.33
    jitter: float = 0.20
    _last_request_at: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            min_interval = 1.0 / self.rate
            elapsed = now - self._last_request_at
            sleep_time = min_interval - elapsed

            if sleep_time > 0:
                # Add jitter: randomize ±jitter%
                jitter_amount = sleep_time * self.jitter
                sleep_time += random.uniform(-jitter_amount, jitter_amount)
                sleep_time = max(sleep_time, 0)
                await asyncio.sleep(sleep_time)

            self._last_request_at = time.monotonic()


# Per-domain singletons
_limiters: dict[str, RateLimiter] = {}


def get_limiter(domain: str, rate: float = 0.33) -> RateLimiter:
    """Get or create a rate limiter for a domain."""
    if domain not in _limiters:
        _limiters[domain] = RateLimiter(rate=rate)
    return _limiters[domain]
