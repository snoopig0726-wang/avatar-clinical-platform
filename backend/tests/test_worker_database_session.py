from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.database import get_isolated_db_session


def test_isolated_worker_sessions_are_safe_across_asyncio_run_calls(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}"
    observed_pools: list[type[object]] = []

    async def query_once() -> None:
        async with get_isolated_db_session(database_url) as session:
            observed_pools.append(type(session.bind.sync_engine.pool))
            assert await session.scalar(text("SELECT 1")) == 1

    asyncio.run(query_once())
    asyncio.run(query_once())

    assert observed_pools == [NullPool, NullPool]
