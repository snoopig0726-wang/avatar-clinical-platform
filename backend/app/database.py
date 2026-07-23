from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config.settings import get_settings


def ensure_database_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    database_path = database_url.removeprefix(prefix)
    if database_path == ":memory:":
        return
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_settings().database_url
    ensure_database_parent(url)
    return create_async_engine(url, pool_pre_ping=True)


@lru_cache
def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(database_url), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


@asynccontextmanager
async def get_isolated_db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """Create a session whose connections cannot leak across event loops.

    Celery invokes each async task through ``asyncio.run``, which creates a fresh
    event loop. Reusing an asyncpg connection pooled by a previous task attaches
    its Future objects to the old loop, so workers use a short-lived NullPool
    engine instead of the API server's cached pool.
    """

    ensure_database_parent(database_url)
    engine = create_async_engine(database_url, pool_pre_ping=True, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()
