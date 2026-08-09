from __future__ import annotations

import asyncio
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

from scraper.config import get_settings
from scraper.logging import get_logger

logger = get_logger("scraper.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _log_slow_query(_conn, _cursor, statement, _parameters, context, _executemany):
    threshold = get_settings().database.slow_query_threshold_s
    total = getattr(context, "get_total_execution_time", lambda: 0)()
    if total and total >= threshold:
        logger.warning("slow_query", duration_s=round(total, 3), statement=statement[:200])


def _build_dsn() -> str:
    return get_settings().database.url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_settings = get_settings().database
        dsn = _build_dsn()
        is_sqlite = dsn.startswith("sqlite")
        is_memory = ":memory:" in dsn or "mode=memory" in dsn
        kwargs: dict[str, Any] = {
            "future": True,
            "pool_pre_ping": True,
            "echo": db_settings.echo,
        }
        if not is_sqlite:
            kwargs["pool_size"] = db_settings.pool_size
            kwargs["max_overflow"] = db_settings.max_overflow
            kwargs["pool_timeout"] = db_settings.pool_timeout
            kwargs["pool_recycle"] = db_settings.pool_recycle
        if is_sqlite and is_memory:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(dsn, **kwargs)
        event.listen(_engine.sync_engine, "after_cursor_execute", _log_slow_query)
        logger.info(
            "engine_created",
            dsn_type="sqlite" if is_sqlite else "postgresql",
            pool_size=kwargs.get("pool_size"),
            max_overflow=kwargs.get("max_overflow"),
        )
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


def _is_postgresql() -> bool:
    """Best-effort detection of the active dialect.

    Used by :func:`upsert_row` to pick a dialect-appropriate upsert strategy.
    Defaults to Postgres when the engine isn't reachable yet (production).
    """
    try:
        from scraper.db import get_engine

        return get_engine().dialect.name == "postgresql"
    except Exception:  # pragma: no cover - defensive fallback
        return True


async def upsert_row(
    session: AsyncSession,
    model: Any,
    index_elements: list[str],
    values: dict[str, Any],
    set_columns: list[str] | None = None,
) -> None:
    """Insert a row, or update it on conflict — dialect-agnostic.

    On PostgreSQL this compiles to ``INSERT ... ON CONFLICT``. On SQLite (and
    any other dialect) it falls back to a SELECT-then-UPDATE/INSERT so the same
    repository code is testable against the project's in-memory SQLite suite.
    """
    if set_columns is None:
        set_columns = [c for c in values if c not in index_elements]

    if _is_postgresql():
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        excluded = pg_insert(model).excluded
        set_ = {c: getattr(excluded, c) for c in set_columns}
        stmt = (
            pg_insert(model)
            .values(**values)
            .on_conflict_do_update(index_elements=index_elements, set_=set_)
        )
        await session.execute(stmt)
        return

    from sqlalchemy import select

    conditions = [getattr(model, col) == values[col] for col in index_elements]
    existing = (await session.execute(select(model).where(*conditions))).scalar_one_or_none()
    if existing is not None:
        for col, val in values.items():
            setattr(existing, col, val)
    else:
        instance = model()
        for col, val in values.items():
            setattr(instance, col, val)
        session.add(instance)


async def check_db_health() -> dict[str, Any]:
    """Check database connectivity and return status."""
    from sqlalchemy import text as sa_text

    result: dict[str, Any] = {"status": "ok", "error": None}
    try:
        async with session_scope() as session:
            await session.execute(sa_text("SELECT 1"))
            result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error("db_health_check_failed", error=str(e))
    return result


async def dispose() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("engine_disposed")
    _engine = None
    _session_factory = None


# ──────────────────────────────────────────────
# Scheduler leadership lock (plan item 11.2)
# ──────────────────────────────────────────────


class AdvisoryLock:
    """PostgreSQL advisory lock for cross-instance scheduler leadership.

    ``pg_try_advisory_lock`` is acquired per database connection. We hold a
    dedicated connection on a NullPool engine (not the pooled session engine)
    so the lock is released on process exit and never lingers after a crash,
    and so returning the connection to a pool can't silently keep the lock
    alive on a reused socket.

    Non-PostgreSQL dialects (tests/sqlite) degrade to a local asyncio lock —
    scheduler tests run in-process, single replica.
    """

    _KEY = 0x414947_454E_4953  # "AIGENIS" as int64

    def __init__(self) -> None:
        self._local = asyncio.Lock()
        self._conn: Any = None
        self._name: str | None = None
        self._engine: Any = None

    @classmethod
    def _key_for(cls, name: str) -> int:
        # Stable 63-bit key from the lock name (advisory locks take int4/int8).
        return cls._KEY ^ (abs(hash(name)) % 0x7FFF_FFFF)

    async def acquire(self, name: str) -> bool:
        """Try to acquire the lock; returns True if this instance is leader."""
        await self._local.acquire()
        self._name = name
        if not _is_postgresql():
            # sqlite/in-memory: single-process tests — local lock is enough.
            return True
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.pool import NullPool

            if self._engine is None:
                self._engine = create_async_engine(
                    get_settings().database.url,
                    poolclass=NullPool,
                )
            self._conn = await self._engine.connect()
            row = await self._conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": self._key_for(name)},
            )
            acquired = bool(row.first()[0])
            if not acquired:
                await self._conn.close()
                self._conn = None
                self._local.release()
            return acquired
        except Exception:
            logger.exception("advisory_lock_acquire_failed")
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
            self._local.release()
            return False

    async def release(self) -> None:
        if self._conn is not None:
            try:
                from sqlalchemy import text

                await self._conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": self._key_for(self._name or "")},
                )
            except Exception:  # pragma: no cover — best-effort cleanup
                logger.warning("advisory_lock_unlock_failed")
            await self._conn.close()
            self._conn = None
        self._local.release()

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


# Module-level singleton shared by every scheduled job in this process.
PIPELINE_LOCK = AdvisoryLock()
