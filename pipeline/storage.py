from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import CrawlerConfig
from models.job import Job, JobStatus
from models.page import Base, Page, PageStatus


class Storage:
    def __init__(self, config: CrawlerConfig) -> None:
        self._config = config
        self._engine = create_async_engine(config.database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    async def upsert_page(self, page_data: dict) -> Page:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Page).where(Page.url == page_data["url"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                for key, value in page_data.items():
                    if value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(existing)
                return existing

            page = Page(**page_data)
            session.add(page)
            await session.commit()
            await session.refresh(page)
            return page

    async def get_page(self, url: str) -> Page | None:
        async with self._session_factory() as session:
            result = await session.execute(select(Page).where(Page.url == url))
            return result.scalar_one_or_none()

    async def get_pages_by_status(self, status: PageStatus, limit: int = 100) -> Sequence[Page]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Page)
                .where(Page.status == status.value)
                .limit(limit)
            )
            return result.scalars().all()

    async def get_page_count(self) -> int:
        async with self._session_factory() as session:
            result = await session.execute(select(func.count(Page.id)))
            return result.scalar_one()

    async def update_page_status(self, url: str, status: PageStatus, **kwargs) -> None:
        async with self._session_factory() as session:
            values: dict = {"status": status.value, "updated_at": datetime.now(timezone.utc)}
            values.update(kwargs)
            await session.execute(
                update(Page).where(Page.url == url).values(**values)
            )
            await session.commit()

    async def create_job(
        self, name: str, seed_urls: list[str], max_depth: int, max_pages: int
    ) -> Job:
        async with self._session_factory() as session:
            job = Job(
                name=name,
                status=JobStatus.PENDING.value,
                seed_urls=json.dumps(seed_urls),
                max_depth=max_depth,
                max_pages=max_pages,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def update_job(self, job_id: int, **kwargs) -> None:
        async with self._session_factory() as session:
            kwargs["updated_at"] = datetime.now(timezone.utc)
            await session.execute(
                update(Job).where(Job.id == job_id).values(**kwargs)
            )
            await session.commit()

    async def get_job(self, job_id: int) -> Job | None:
        async with self._session_factory() as session:
            result = await session.execute(select(Job).where(Job.id == job_id))
            return result.scalar_one_or_none()

    async def get_latest_job(self) -> Job | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Job).order_by(Job.id.desc()).limit(1)
            )
            return result.scalar_one_or_none()
