"""Tests for scraper/db.py: engine, upsert_row branches, health, advisory lock."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import scraper.db as db


def test_log_slow_query_warns_and_skips():
    db._log_slow_query(None, None, "SELECT 1" * 50, None, SimpleNamespace(get_total_execution_time=lambda: 5.0), None)
    db._log_slow_query(None, None, "x", None, SimpleNamespace(get_total_execution_time=lambda: 0), None)
    db._log_slow_query(None, None, "x", None, SimpleNamespace(get_total_execution_time=lambda: 5.0), None)


def test_get_engine_non_sqlite_kwargs(monkeypatch):
    import scraper.db as mod

    original_engine, original_factory = mod._engine, mod._session_factory
    try:
        mod._engine = None
        mod._session_factory = None

        def fake_settings():
            return SimpleNamespace(
                database=SimpleNamespace(
                    url="postgresql+asyncpg://u:p@localhost:5432/db",
                    slow_query_threshold_s=0.1,
                    echo=False,
                    pool_size=11,
                    max_overflow=22,
                    pool_timeout=33.0,
                    pool_recycle=44,
                )
            )

        monkeypatch.setattr("scraper.db.get_settings", fake_settings)
        engine = mod.get_engine()
        assert engine.dialect.name == "postgresql"
        assert engine.pool._pool.maxsize == 11

        async def cleanup():
            await mod.dispose()

        asyncio.run(cleanup())
    finally:
        mod._engine = original_engine
        mod._session_factory = original_factory


@pytest.mark.asyncio
async def test_upsert_row_postgres_branch(monkeypatch):
    from scraper.orm import FxRateORM

    executed = []

    class FakeResult:
        def __init__(self, existing):
            self._existing = existing

        def scalar_one_or_none(self):
            return self._existing

    class FakeSession:
        async def execute(self, stmt):
            executed.append(stmt)

    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    fake_session = FakeSession()
    await db.upsert_row(fake_session, FxRateORM, ["pair"], {"pair": "USD/BYN", "rate": 1})
    assert executed
    assert "ON CONFLICT" in str(executed[0])


@pytest.mark.asyncio
async def test_upsert_row_sqlite_insert_and_update(monkeypatch):
    from scraper.orm import FxRateORM

    async with db.session_scope() as session:
        await db.upsert_row(session, FxRateORM, ["pair"], {"pair": "USD/BYN", "rate": 1})
        await session.flush()
        await db.upsert_row(session, FxRateORM, ["pair"], {"pair": "USD/BYN", "rate": 2})
        await session.flush()

    async with db.session_scope() as session:
        from sqlalchemy import select

        row = (await session.execute(select(FxRateORM))).scalar_one()
        assert row.rate == 2


@pytest.mark.asyncio
async def test_check_db_health_ok():
    result = await db.check_db_health()
    assert result["status"] == "ok"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_check_db_health_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no db")

    monkeypatch.setattr("scraper.db.get_session_factory", boom)
    result = await db.check_db_health()
    assert result["status"] == "error"
    assert "no db" in result["error"]


class _FakeConn:
    def __init__(self, acquired: bool, fail_on_call: int | None = None):
        self._acquired = acquired
        self._fail_on_call = fail_on_call
        self._calls = 0
        self.closed = False

    async def execute(self, *args, **kwargs):
        self._calls += 1
        if self._fail_on_call is not None and self._calls == self._fail_on_call:
            raise RuntimeError("unlock failed")
        return SimpleNamespace(first=lambda: [self._acquired])

    async def close(self):
        self.closed = True


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn
        self.disposed = False

    async def connect(self):
        return self._conn

    async def dispose(self):
        self.disposed = True


@pytest.mark.asyncio
async def test_advisory_lock_acquired_and_released(monkeypatch):
    conn = _FakeConn(True)
    engine = _FakeEngine(conn)
    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", lambda *a, **k: engine)

    lock = db.AdvisoryLock()
    assert await lock.acquire("leader") is True
    assert lock._engine is engine
    await lock.release()
    assert conn.closed
    await lock.dispose()
    assert engine.disposed


@pytest.mark.asyncio
async def test_advisory_lock_not_acquired(monkeypatch):
    conn = _FakeConn(False)
    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", lambda *a, **k: _FakeEngine(conn))

    lock = db.AdvisoryLock()
    assert await lock.acquire("other") is False
    assert conn.closed


@pytest.mark.asyncio
async def test_advisory_lock_acquire_failure(monkeypatch):
    class BrokenEngine:
        async def connect(self):
            raise RuntimeError("pg down")

    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", lambda *a, **k: BrokenEngine())

    lock = db.AdvisoryLock()
    assert await lock.acquire("leader") is False
    assert lock._conn is None


@pytest.mark.asyncio
async def test_advisory_lock_execute_failure_closes_conn(monkeypatch):
    conn = _FakeConn(True, fail_on_call=1)
    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", lambda *a, **k: _FakeEngine(conn))

    lock = db.AdvisoryLock()
    assert await lock.acquire("leader") is False
    assert conn.closed
    assert lock._conn is None


@pytest.mark.asyncio
async def test_advisory_lock_sqlite_local(monkeypatch):
    monkeypatch.setattr("scraper.db._is_postgresql", lambda: False)
    lock = db.AdvisoryLock()
    assert await lock.acquire("local") is True
    await lock.release()


@pytest.mark.asyncio
async def test_advisory_lock_unlock_failure_logged(monkeypatch):
    conn = _FakeConn(True, fail_on_call=2)
    monkeypatch.setattr("scraper.db._is_postgresql", lambda: True)
    monkeypatch.setattr("sqlalchemy.ext.asyncio.create_async_engine", lambda *a, **k: _FakeEngine(conn))

    lock = db.AdvisoryLock()
    assert await lock.acquire("leader") is True
    await lock.release()
    assert conn.closed


def test_is_postgresql_defaults_true_when_unreachable(monkeypatch):
    monkeypatch.setattr("scraper.db.get_engine", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert db._is_postgresql() is True
