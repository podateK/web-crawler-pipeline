from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from config import CrawlerConfig
from crawler.fetcher import Fetcher, FetchResult
from crawler.parser import HTMLParser
from crawler.robots import RobotsChecker
from models.job import JobStatus
from models.page import PageStatus
from pipeline.analyzer import ContentAnalyzer
from pipeline.extractor import DataExtractor
from pipeline.storage import Storage
from pipeline.transformer import ContentTransformer
from utils.rate_limiter import DomainRateLimiter
from utils.url_utils import (
    URLBloomFilter,
    extract_domain,
    has_denied_extension,
    is_valid_url,
)
from utils.user_agent import UserAgentRotator

logger = logging.getLogger(__name__)


class CrawlEngine:
    def __init__(self, config: CrawlerConfig) -> None:
        self._config = config
        self._user_agent = UserAgentRotator()
        self._fetcher = Fetcher(config, self._user_agent)
        self._parser = HTMLParser()
        self._robots = RobotsChecker()
        self._extractor = DataExtractor()
        self._transformer = ContentTransformer()
        self._storage = Storage(config)
        self._analyzer = ContentAnalyzer()
        self._rate_limiter = DomainRateLimiter(config.rate_limit_per_second)
        self._visited = URLBloomFilter(config.bloom_filter_size, 0.001)
        self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._running = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._pages_crawled = 0
        self._pages_failed = 0
        self._pages_skipped = 0
        self._job_id: int | None = None
        self._start_time: float = 0.0

    @property
    def pages_crawled(self) -> int:
        return self._pages_crawled

    @property
    def pages_failed(self) -> int:
        return self._pages_failed

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time if self._start_time else 0.0

    async def crawl(self, urls: list[str], job_name: str = "crawl") -> None:
        await self._storage.initialize()
        seed_urls = [u for u in urls if is_valid_url(u)]
        if not seed_urls:
            logger.error("No valid seed URLs provided")
            return

        job = await self._storage.create_job(
            name=job_name,
            seed_urls=seed_urls,
            max_depth=self._config.max_depth,
            max_pages=self._config.max_pages,
        )
        self._job_id = job.id
        await self._storage.update_job(job.id, status=JobStatus.RUNNING.value)

        for url in seed_urls:
            self._visited.add(url)
            await self._queue.put((url, 0))

        logger.info(
            "Starting crawl: %d seeds, depth=%d, max=%d, concurrency=%d",
            len(seed_urls),
            self._config.max_depth,
            self._config.max_pages,
            self._config.max_concurrency,
        )

        try:
            self._running = True
            self._start_time = time.monotonic()

            workers = [
                asyncio.create_task(self._worker(), name=f"crawler-{i}")
                for i in range(self._config.max_concurrency)
            ]

            await self._queue.join()

            self._running = False

            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            await self._storage.update_job(
                job.id,
                status=JobStatus.COMPLETED.value,
                pages_crawled=self._pages_crawled,
                pages_failed=self._pages_failed,
                pages_skipped=self._pages_skipped,
                completed_at=datetime.now(timezone.utc),
            )

            logger.info(
                "Crawl completed: %d crawled, %d failed, %d skipped in %.1fs",
                self._pages_crawled,
                self._pages_failed,
                self._pages_skipped,
                self.elapsed,
            )
        finally:
            await self._fetcher.close()
            await self._storage.close()

    async def _worker(self) -> None:
        while self._running:
            try:
                url, depth = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._pause_event.wait()

                if self._pages_crawled >= self._config.max_pages:
                    self._pages_skipped += 1
                    continue

                if depth > self._config.max_depth:
                    self._pages_skipped += 1
                    continue

                if has_denied_extension(url):
                    self._pages_skipped += 1
                    continue

                if self._config.respect_robots_txt:
                    can_fetch = await self._robots.can_fetch(url, self._user_agent.get())
                    if not can_fetch:
                        logger.debug("Blocked by robots.txt: %s", url)
                        self._pages_skipped += 1
                        continue

                domain = extract_domain(url)
                await self._rate_limiter.acquire(domain)

                result = await self._fetcher.fetch(url)
                if result is None or result.status != 200:
                    self._pages_failed += 1
                    error_msg = f"HTTP {result.status}" if result else "fetch failed"
                    await self._storage.update_page_status(
                        url,
                        PageStatus.FAILED,
                        error_message=error_msg,
                        status_code=result.status if result else None,
                    )
                    continue

                await self._process_page(url, domain, depth, result)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error processing %s: %s", url, e)
                self._pages_failed += 1
            finally:
                self._queue.task_done()

    async def _process_page(
        self, url: str, domain: str, depth: int, result: FetchResult
    ) -> None:
        parsed = self._parser.parse(url, result.content)
        extracted = self._extractor.extract(result.content, url)
        content_hash = self._transformer.compute_hash(parsed.text)

        self._analyzer.analyze(
            url=url,
            text=parsed.text,
            html=result.content,
            title=parsed.title,
            links=parsed.links,
        )

        page_data = {
            "url": url,
            "domain": domain,
            "status": PageStatus.CRAWLED.value,
            "depth": depth,
            "title": parsed.title,
            "description": parsed.description,
            "content_hash": content_hash,
            "word_count": parsed.word_count,
            "link_count": len(parsed.links),
            "response_time": result.response_time,
            "status_code": result.status,
            "content_type": result.content_type,
            "fetched_at": datetime.now(timezone.utc),
            "extracted_tables": DataExtractor.to_json(extracted) if extracted.tables else None,
            "extracted_lists": json.dumps(extracted.lists, ensure_ascii=False) if extracted.lists else None,
            "extracted_metadata": json.dumps(extracted.metadata, ensure_ascii=False) if extracted.metadata else None,
        }

        await self._storage.upsert_page(page_data)
        self._pages_crawled += 1

        if depth < self._config.max_depth:
            for link in parsed.links:
                if self._visited.add(link):
                    await self._queue.put((link, depth + 1))

        logger.debug(
            "Crawled [%d]: %s (%d words, %.2fs)",
            result.status,
            url,
            parsed.word_count,
            result.response_time,
        )

    def pause(self) -> None:
        self._paused = True
        self._pause_event.clear()
        logger.info("Crawl paused")

    def resume(self) -> None:
        self._paused = False
        self._pause_event.set()
        logger.info("Crawl resumed")

    def stop(self) -> None:
        self._running = False
        self._paused = False
        self._pause_event.set()
        self._drain_queue()
        logger.info("Crawl stopped")

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def resume_job(self, job_id: int) -> None:
        await self._storage.initialize()
        job = await self._storage.get_job(job_id)
        if job is None:
            logger.error("Job %d not found", job_id)
            return

        if job.status not in (JobStatus.PAUSED.value, JobStatus.FAILED.value):
            logger.error("Cannot resume job %d (status: %s)", job_id, job.status)
            return

        seed_urls = json.loads(job.seed_urls)
        await self._storage.update_job(job_id, status=JobStatus.RUNNING.value)

        self._job_id = job_id

        for url in seed_urls:
            self._visited.add(url)
            await self._queue.put((url, 0))

        try:
            self._running = True
            self._start_time = time.monotonic()

            workers = [
                asyncio.create_task(self._worker(), name=f"crawler-{i}")
                for i in range(self._config.max_concurrency)
            ]

            await self._queue.join()

            self._running = False

            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            await self._storage.update_job(
                job_id,
                status=JobStatus.COMPLETED.value,
                pages_crawled=self._pages_crawled,
                pages_failed=self._pages_failed,
                completed_at=datetime.now(timezone.utc),
            )

            logger.info("Job %d resumed and completed", job_id)
        finally:
            await self._fetcher.close()
            await self._storage.close()
