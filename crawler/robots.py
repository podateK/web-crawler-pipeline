from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


class RobotsChecker:
    def __init__(self, user_agent: str = "*"):
        self._user_agent = user_agent
        self._cache: dict[str, RobotFileParser | None] = {}
        self._lock = asyncio.Lock()

    async def can_fetch(self, url: str, user_agent: str | None = None) -> bool:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        agent = user_agent or self._user_agent

        async with self._lock:
            if base_url not in self._cache:
                await self._load(base_url)

        rp = self._cache.get(base_url)
        if rp is None:
            return True
        return rp.can_fetch(agent, url)

    async def _load(self, base_url: str) -> None:
        robots_url = f"{base_url}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, rp.read)
        except Exception:
            logger.debug("Failed to fetch robots.txt from %s", robots_url)
            rp = None
        self._cache[base_url] = rp

    def get_crawl_delay(self, base_url: str) -> float | None:
        rp = self._cache.get(base_url)
        if rp is None:
            return None
        delay = rp.crawl_delay(self._user_agent)
        return float(delay) if delay else None
