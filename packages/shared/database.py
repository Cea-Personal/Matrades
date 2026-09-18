from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from packages.shared.config import get_settings



settings = get_settings()
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise
