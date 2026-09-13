from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from config import CrawlerConfig

logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="web-crawler",
        description="Async Web Crawler & Data Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_parser = subparsers.add_parser("crawl", help="Start a new crawl job")
    crawl_parser.add_argument("urls", nargs="+", help="Seed URLs to crawl")
    crawl_parser.add_argument("--depth", type=int, default=3, help="Max crawl depth (default: 3)")
    crawl_parser.add_argument("--max-pages", type=int, default=1000, help="Max pages to crawl (default: 1000)")
    crawl_parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests (default: 10)")
    crawl_parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    crawl_parser.add_argument("--rate-limit", type=float, default=1.0, help="Requests per second per domain (default: 1.0)")
    crawl_parser.add_argument("--no-robots", action="store_true", help="Ignore robots.txt")
    crawl_parser.add_argument("--db", type=str, default="crawl_data.db", help="SQLite database path")
    crawl_parser.add_argument("--name", type=str, default="crawl", help="Job name")
    crawl_parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    resume_parser = subparsers.add_parser("resume", help="Resume a paused/failed crawl job")
    resume_parser.add_argument("job_id", type=int, help="Job ID to resume")
    resume_parser.add_argument("--concurrency", type=int, default=10)
    resume_parser.add_argument("--rate-limit", type=float, default=1.0)
    resume_parser.add_argument("--db", type=str, default="crawl_data.db")
    resume_parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    status_parser = subparsers.add_parser("status", help="Show crawl job status")
    status_parser.add_argument("--db", type=str, default="crawl_data.db")
    status_parser.add_argument("job_id", nargs="?", type=int, help="Job ID (default: latest)")

    stats_parser = subparsers.add_parser("stats", help="Show crawl statistics")
    stats_parser.add_argument("--db", type=str, default="crawl_data.db")

    return parser.parse_args()


async def cmd_crawl(args: argparse.Namespace) -> None:
    from crawler.engine import CrawlEngine

    config = CrawlerConfig(
        start_urls=args.urls,
        max_concurrency=args.concurrency,
        max_depth=args.depth,
        max_pages=args.max_pages,
        request_timeout=args.timeout,
        rate_limit_per_second=args.rate_limit,
        respect_robots_txt=not args.no_robots,
        db_path=args.db,
        log_level=args.log_level,
    )

    engine = CrawlEngine(config)

    try:
        await engine.crawl(urls=args.urls, job_name=args.name)
    except KeyboardInterrupt:
        engine.stop()
        logger.info("Crawl interrupted by user")

    print(f"\nCrawl complete: {engine.pages_crawled} pages crawled, {engine.pages_failed} failed")


async def cmd_resume(args: argparse.Namespace) -> None:
    from crawler.engine import CrawlEngine

    config = CrawlerConfig(
        max_concurrency=args.concurrency,
        rate_limit_per_second=args.rate_limit,
        db_path=args.db,
        log_level=args.log_level,
    )
    engine = CrawlEngine(config)
    await engine.resume_job(args.job_id)


async def cmd_status(args: argparse.Namespace) -> None:
    from models.job import JobStatus
    from pipeline.storage import Storage

    config = CrawlerConfig(db_path=args.db)
    storage = Storage(config)
    await storage.initialize()

    try:
        if args.job_id:
            job = await storage.get_job(args.job_id)
        else:
            job = await storage.get_latest_job()

        if job is None:
            print("No job found")
            return

        print(f"Job #{job.id}: {job.name}")
        print(f"  Status:        {job.status}")
        print(f"  Pages crawled: {job.pages_crawled}")
        print(f"  Pages failed:  {job.pages_failed}")
        print(f"  Pages skipped: {job.pages_skipped}")
        print(f"  Max depth:     {job.max_depth}")
        print(f"  Max pages:     {job.max_pages}")
        print(f"  Created:       {job.created_at}")
        if job.completed_at:
            print(f"  Completed:     {job.completed_at}")
        if job.error_message:
            print(f"  Error:         {job.error_message}")
    finally:
        await storage.close()


async def cmd_stats(args: argparse.Namespace) -> None:
    from sqlalchemy import func, select

    from models.page import Page, PageStatus
    from pipeline.storage import Storage

    config = CrawlerConfig(db_path=args.db)
    storage = Storage(config)
    await storage.initialize()

    try:
        async with storage._session_factory() as session:
            total = await session.execute(select(func.count(Page.id)))
            total_pages = total.scalar_one()

            crawled = await session.execute(
                select(func.count(Page.id)).where(Page.status == PageStatus.CRAWLED.value)
            )
            crawled_pages = crawled.scalar_one()

            failed = await session.execute(
                select(func.count(Page.id)).where(Page.status == PageStatus.FAILED.value)
            )
            failed_pages = failed.scalar_one()

            words = await session.execute(select(func.sum(Page.word_count)))
            total_words = words.scalar_one() or 0

            avg_time = await session.execute(select(func.avg(Page.response_time)))
            avg_response = avg_time.scalar_one() or 0

        print(f"Total pages:     {total_pages}")
        print(f"  Crawled:       {crawled_pages}")
        print(f"  Failed:        {failed_pages}")
        print(f"Total words:     {total_words:,}")
        print(f"Avg response:    {avg_response:.2f}s")
    finally:
        await storage.close()


def main() -> None:
    if sys.platform != "win32":
        try:
            import uvloop
            uvloop.install()
        except ImportError:
            pass

    args = parse_args()
    setup_logging(getattr(args, "log_level", "INFO"))

    commands = {
        "crawl": cmd_crawl,
        "resume": cmd_resume,
        "status": cmd_status,
        "stats": cmd_stats,
    }

    handler = commands.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
