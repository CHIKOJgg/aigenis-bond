"""Job run history helpers (plan 11.3).

Thin wrapper over :class:`scraper.orm.jobs.JobRunORM` used by the scheduler:
``start_job_run`` opens a row with status ``running``, ``finish_job_run``
marks it ``ok`` / ``skipped`` / ``failed`` / ``timeout`` and records wall-clock
duration. Failures are summarized to a single line; tracebacks stay in logs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select

from scraper.db import session_scope
from scraper.logging import correlation_id, get_logger
from scraper.orm.jobs import JobRunORM

logger = get_logger("scraper.job_runs")


async def start_job_run(job_name: str) -> int | None:
    """Open a run row; returns its id (None when history writes fail)."""
    try:
        async with session_scope() as session:
            run = JobRunORM(job_name=job_name, status="running")
            session.add(run)
            await session.flush()
            return run.id
    except Exception:
        logger.exception("job_run_start_failed", job_name=job_name)
        return None


async def finish_job_run(
    run_id: int | None,
    status: str,
    *,
    started_at: datetime | None = None,
    error: str | None = None,
) -> None:
    """Close a run row; best-effort, never raises into the job body."""
    if run_id is None:
        return
    try:
        async with session_scope() as session:
            run = (
                await session.execute(select(JobRunORM).where(JobRunORM.id == run_id))
            ).scalar_one_or_none()
            if run is None:
                return
            run.status = status
            run.finished_at = datetime.now(UTC)
            if started_at is not None:
                run.duration_ms = max(0, int((run.finished_at - started_at).total_seconds() * 1000))
            run.error = error
    except Exception:
        logger.exception("job_run_finish_failed", job_name=None, status=status)


async def _wrap_with_history(
    job_name: str, fn: Callable[[], Awaitable[None]]
) -> Callable[[], Awaitable[None]]:
    """Wrap a scheduler job with job_runs bookkeeping (skipped status too)."""

    async def wrapper() -> None:
        started = datetime.now(UTC)
        run_id = await start_job_run(job_name)
        cid = correlation_id()
        logger.info(f"{job_name}_start", correlation_id=cid)
        try:
            await fn()
            logger.info(f"{job_name}_done", correlation_id=cid)
            await finish_job_run(run_id, "ok", started_at=started)
        except Exception:
            logger.exception(f"{job_name}_failed", correlation_id=cid)
            await finish_job_run(
                run_id,
                "failed",
                started_at=started,
                error=str_exc_last_line(),
            )

    return wrapper


def str_exc_last_line(exc: BaseException) -> str:
    """Single-line error summary (message only, no traceback)."""
    text = str(exc) or exc.__class__.__name__
    return text.replace("\n", " ").strip()[:512]
