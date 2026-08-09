"""Tests for scraper/job_runs.py and scraper/observability.py."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from scraper import job_runs, observability
from scraper.db import session_scope
from scraper.orm.jobs import JobRunORM
from sqlalchemy import select


@pytest.mark.asyncio
async def test_start_and_finish_job_run_roundtrip():
    run_id = await job_runs.start_job_run("test-job")
    assert run_id is not None

    await job_runs.finish_job_run(
        run_id,
        "ok",
        started_at=datetime.now(UTC) - timedelta(seconds=2),
    )

    async with session_scope() as session:
        row = (await session.execute(select(JobRunORM).where(JobRunORM.id == run_id))).scalar_one()
        assert row.status == "ok"
        assert row.finished_at is not None
        assert row.duration_ms is not None and row.duration_ms >= 1500


@pytest.mark.asyncio
async def test_finish_job_run_none_id_is_noop():
    await job_runs.finish_job_run(None, "ok")


@pytest.mark.asyncio
async def test_finish_job_run_missing_row_is_noop():
    await job_runs.finish_job_run(99999999, "ok")


@pytest.mark.asyncio
async def test_start_job_run_failure_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("scraper.job_runs.session_scope", boom)
    assert await job_runs.start_job_run("x") is None


@pytest.mark.asyncio
async def test_finish_job_run_failure_is_best_effort(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("scraper.job_runs.session_scope", boom)
    await job_runs.finish_job_run(1, "ok")


def test_str_exc_last_line():
    assert job_runs.str_exc_last_line(RuntimeError("simple")) == "simple"
    assert job_runs.str_exc_last_line(RuntimeError("multi\nline\nerror")) == "multi line error"
    assert job_runs.str_exc_last_line(RuntimeError("")) == "RuntimeError"
    assert job_runs.str_exc_last_line(RuntimeError("x" * 600)) == "x" * 512


@pytest.mark.asyncio
async def test_wrap_with_history_ok():
    ran = []

    async def fn():
        ran.append(1)

    wrapper = await job_runs._wrap_with_history("wrapped-ok", fn)
    assert await wrapper() is None
    assert ran == [1]

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(JobRunORM).where(JobRunORM.job_name == "wrapped-ok")
            )
        ).scalars().all()
        assert rows
        assert all(r.status == "ok" for r in rows)
        assert all(r.error is None for r in rows)


@pytest.mark.asyncio
async def test_wrap_with_history_failed():
    async def fn():
        raise ValueError("boom failed")

    wrapper = await job_runs._wrap_with_history("wrapped-fail", fn)
    await wrapper()

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(JobRunORM).where(JobRunORM.job_name == "wrapped-fail")
            )
        ).scalars().all()
        assert rows
        assert all(r.status == "failed" for r in rows)
        assert all(r.error == "boom failed" for r in rows)


# ──────────────────────────────────────────────
# scraper/observability
# ──────────────────────────────────────────────


def test_init_sentry_disabled_in_dev(monkeypatch):
    assert observability.init_sentry(None, environment="development") is False


def test_init_sentry_disabled_prod_warns(caplog):
    with caplog.at_level("WARNING"):
        assert observability.init_sentry(None, environment="production") is False
    assert "SENTRY_DSN" in caplog.text


def test_init_sentry_enabled(monkeypatch):
    sentry = MagicMock()
    sentry.init = MagicMock()
    monkeypatch.setattr("sentry_sdk.init", sentry.init)
    result = observability.init_sentry("https://dsn@sentry.example/1", release="1.2.3")
    assert result is True
    sentry.init.assert_called_once()
    kwargs = sentry.init.call_args.kwargs
    assert kwargs["dsn"] == "https://dsn@sentry.example/1"
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "1.2.3"


def test_init_sentry_missing_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations", None)
    assert observability.init_sentry("https://dsn") is False
