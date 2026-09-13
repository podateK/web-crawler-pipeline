from __future__ import annotations

import asyncio
import time


class DomainRateLimiter:
    def __init__(self, rate: float = 1.0):
        self._rate = rate
        self._min_interval = 1.0 / rate if rate > 0 else 0.0
        self._tokens: dict[str, float] = {}
        self._timestamps: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    def _refill(self, domain: str) -> None:
        now = time.monotonic()
        if domain not in self._timestamps:
            self._tokens[domain] = self._rate - 1.0
            self._timestamps[domain] = now
            return
        elapsed = now - self._timestamps[domain]
        self._tokens[domain] = min(
            self._rate,
            self._tokens[domain] + elapsed * self._rate,
        )
        self._timestamps[domain] = now

    async def acquire(self, domain: str) -> None:
        lock = self._get_lock(domain)
        async with lock:
            while True:
                self._refill(domain)
                if self._tokens[domain] >= 1.0:
                    self._tokens[domain] -= 1.0
                    return
                wait = (1.0 - self._tokens[domain]) / self._rate
                await asyncio.sleep(wait)
