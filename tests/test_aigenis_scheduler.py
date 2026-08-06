"""Phase 11 tests: scheduler leadership (11.2), job run history (11.3) and
failure handling (11.4).

The in-memory SQLite engine (see conftest) degrades AdvisoryLock to a local
asyncio lock, so leadership is exercised in-process. asyncio.Lock is created
inside each test (not a fixture) because pytest-asyncio runs every test on a
fresh event loop and locks are loop-bound.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest


@pytest.fixture(autouse=True)
def _clean_job_runs() -> Iterator[None]:
    """Drop any leftover job_runs rows from previous tests (shared engine)."""
    from sqlalchemy import delete

    from scraper.db import get_engine
    from scraper.orm.jobs import JobRunORM

    async def _clean() -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(delete(JobRunORM))

    import asyncio

    asyncio.run(_clean())
    yield


# ──────────────────────────────────────────────
# Scheduler leadership (11.2)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_advisory_lock_sqlite_is_local() -> None:
    """SQLite path acquires immediately and stays held until release."""
    from scraper.db import AdvisoryLock

    lock = AdvisoryLock()
    assert await lock.acquire("pipeline") is True
    assert lock._local.locked() is True
    await lock.release()
    assert lock._local.locked() is False


@pytest.mark.asyncio
async def test_advisory_lock_acquire_release_roundtrip() -> None:
    from scraper.db import AdvisoryLock

    lock = AdvisoryLock()
    assert await lock.acquire("history") is True
    await lock.release()
    assert lock._local.locked() is False


@pytest.mark.asyncio
async def test_advisory_lock_key_is_int64() -> None:
    """Lock keys must fit PG int8 (< 2**63)."""
    from scraper.db import AdvisoryLock

    key = AdvisoryLock._key_for("pipeline")
    assert isinstance(key, int)
    assert -(2**63) <= key < 2**63


# ──────────────────────────────────────────────
# Job run history (11.3)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_run_ok_recorded() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.job_runs import finish_job_run, start_job_run
    from scraper.orm.jobs import JobRunORM

    started = datetime.now(UTC)
    run_id = await start_job_run("test_ok_job")
    assert run_id is not None
    await finish_job_run(run_id, "ok", started_at=started)

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert len(runs) == 1
    assert runs[0].job_name == "test_ok_job"
    assert runs[0].status == "ok"
    assert runs[0].duration_ms is not None and runs[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_job_run_failed_records_error() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.job_runs import finish_job_run, start_job_run
    from scraper.orm.jobs import JobRunORM

    started = datetime.now(UTC)
    run_id = await start_job_run("boom_job")
    await finish_job_run(run_id, "failed", started_at=started, error="intake timeout")

    async with session_scope() as session:
        run = (await session.execute(select(JobRunORM))).scalars().one()
    assert run.status == "failed"
    assert run.error == "intake timeout"


@pytest.mark.asyncio
async def test_job_run_skipped_recorded() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.job_runs import finish_job_run, start_job_run
    from scraper.orm.jobs import JobRunORM

    started = datetime.now(UTC)
    run_id = await start_job_run("who_cares")
    await finish_job_run(run_id, "skipped", started_at=started)

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "skipped"


@pytest.mark.asyncio
async def test_job_run_finish_unknown_id_is_noop() -> None:
    from scraper.job_runs import finish_job_run

    await finish_job_run(424242, "ok")  # must not raise


@pytest.mark.asyncio
async def test_job_run_history_survives_multiple_runs() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.job_runs import finish_job_run, start_job_run
    from scraper.orm.jobs import JobRunORM

    started = datetime.now(UTC)
    await finish_job_run(await start_job_run("a"), "ok", started_at=started)
    await finish_job_run(await start_job_run("a"), "failed", started_at=started)
    await finish_job_run(await start_job_run("a"), "skipped", started_at=started)

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert [r.status for r in runs] == ["ok", "failed", "skipped"]


# ──────────────────────────────────────────────
# Scheduler outcomes (11.2 / 11.4)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scheduler_wraps_skipped_outcome() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.orm.jobs import JobRunORM
    from scraper.scheduler import _wrap

    async def _skipped() -> str:
        return "skipped"

    wrapped = _wrap("fake_cron", _skipped)
    assert await wrapped() == "skipped"

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "skipped"


@pytest.mark.asyncio
async def test_scheduler_wraps_ok_outcome() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.orm.jobs import JobRunORM
    from scraper.scheduler import _wrap

    async def _good() -> str:
        return "ok"

    wrapped = _wrap("good_cron", _good)
    assert await wrapped() == "ok"

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert runs[0].job_name == "good_cron"


@pytest.mark.asyncio
async def test_scheduler_wraps_failure_outcome() -> None:
    from sqlalchemy import select

    from scraper.db import session_scope
    from scraper.orm.jobs import JobRunORM
    from scraper.scheduler import _wrap

    async def _explodes() -> str:
        raise RuntimeError("feed malformed")

    wrapped = _wrap("boom_cron", _explodes)
    assert await wrapped() is None

    async with session_scope() as session:
        runs = (await session.execute(select(JobRunORM))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error is not None
    assert "feed malformed" in runs[0].error


@pytest.mark.asyncio
async def test_scheduler_builds_all_jobs() -> None:
    from scraper.scheduler import build_scheduler

    scheduler = build_scheduler()
    ids = [j.id for j in scheduler.get_jobs()]
    assert "scrape_all_6h" in ids
    assert "scrape_history_daily" in ids
    assert "moex_stocks_30m" in ids
    assert len(ids) >= 4
