from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SLOW_QUERY_THRESHOLD_S = float(os.getenv("SLOW_QUERY_THRESHOLD_S", "0.1"))


def _log_slow_query(conn, cursor, statement, parameters, context, executemany):
    """Log queries that exceed the threshold."""
    total = getattr(context, "get_total_execution_time", lambda: 0)()
    if total and total >= SLOW_QUERY_THRESHOLD_S:
        from loguru import logger

        logger.warning(
            "slow_query",
            duration_s=round(total, 3),
            statement=statement[:200],
        )

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        dsn = _build_dsn()
        is_sqlite = dsn.startswith("sqlite")
        is_memory = ":memory:" in dsn or "mode=memory" in dsn
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if not is_sqlite:
            kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "10"))
            kwargs["max_overflow"] = int(os.getenv("DB_POOL_OVERFLOW", "20"))
            kwargs["pool_timeout"] = float(os.getenv("DB_POOL_TIMEOUT", "30.0"))
        if is_sqlite and is_memory:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(dsn, **kwargs)
        event.listen(_engine.sync_engine, "after_cursor_execute", _log_slow_query)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def session_scope(**kwargs: Any) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory(**kwargs) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
