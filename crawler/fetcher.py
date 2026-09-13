from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import aiohttp

from config import CrawlerConfig
from utils.user_agent import UserAgentRotator

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    status: int
    content: str
    content_type: str
    headers: dict[str, str]
    response_time: float
    final_url: str


class Fetcher:
    def __init__(self, config: CrawlerConfig, user_agent: UserAgentRotator):
        self._config = config
        self._user_agent = user_agent
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(config.max_concurrency)

    async def start(self) -> None:
        if self._session is not None:
            return
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch(self, url: str) -> FetchResult | None:
        if self._session is None:
            await self.start()

        last_error: Exception | None = None
        for attempt in range(self._config.retry_attempts):
            try:
                async with self._semaphore:
                    return await self._do_fetch(url)
            except asyncio.CancelledError:
                raise
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < self._config.retry_attempts - 1:
                    delay = self._config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            except Exception as e:
                last_error = e
                if attempt < self._config.retry_attempts - 1:
                    delay = self._config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        logger.debug("Fetch failed after %d attempts for %s: %s", self._config.retry_attempts, url, last_error)
        return None

    async def _do_fetch(self, url: str) -> FetchResult:
        headers = {"User-Agent": self._user_agent.get()}
        start = time.monotonic()

        async with self._session.get(url, headers=headers, allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text" in content_type or "html" in content_type:
                raw = await resp.read()
                content = raw.decode("utf-8", errors="replace")
            else:
                content = ""

            elapsed = time.monotonic() - start

            return FetchResult(
                url=str(resp.url),
                status=resp.status,
                content=content,
                content_type=content_type,
                headers={k: v for k, v in resp.headers.items()},
                response_time=elapsed,
                final_url=str(resp.url),
            )
