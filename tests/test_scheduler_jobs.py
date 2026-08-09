"""Tests for scraper/scheduler: scheduled jobs, build_scheduler, run_forever."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from scraper.db import session_scope


class FakeClient:
    """Async context manager mimicking MoexClient / AigenisClient surfaces."""

    def __init__(self, history=None, coupons=None, raise_history=False) -> None:
        self._history = history or []
        self._coupons = coupons or []
        self._raise = raise_history

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def fetch_history(self, internal_id, _days=30):
        if self._raise:
            raise RuntimeError("history boom")
        return self._history

    async def fetch_coupons(self, internal_id):
        return self._coupons


async def _add_bond(session, internal_id: str, currency: str) -> None:
    from decimal import Decimal

    from scraper.orm import BondORM

    session.add(
        BondORM(
            internal_id=internal_id,
            name=f"Bond {internal_id}",
            currency=currency,
            market="bcse",
            status="active",
            yield_to_maturity=Decimal("8.0"),
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_scheduled_stocks_job_success_and_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from scraper import pipeline
    from scraper.scheduler import scheduled_stocks_job

    async def ok():
        return None

    async def boom():
        raise RuntimeError("stocks down")

    monkeypatch.setattr(pipeline, "run_once_moex_stocks", ok)
    await scheduled_stocks_job()

    monkeypatch.setattr(pipeline, "run_once_moex_stocks", boom)
    await scheduled_stocks_job()


@pytest.mark.asyncio
async def test_scheduled_stocks_job_disabled(monkeypatch):
    from scraper import pipeline
    from scraper.scheduler import scheduled_stocks_job

    def fake_settings():
        return SimpleNamespace(stock=SimpleNamespace(enabled=False))

    monkeypatch.setattr("scraper.scheduler.get_settings", fake_settings)
    monkeypatch.setattr(pipeline, "run_once_moex_stocks", lambda: (_ for _ in ()).throw(AssertionError))
    await scheduled_stocks_job()


@pytest.mark.asyncio
async def test_scheduled_history_job_skipped_variants(monkeypatch):
    from scraper.db import PIPELINE_LOCK
    from scraper.scheduler import scheduled_history_job

    assert await PIPELINE_LOCK.acquire("history") is True
    try:
        assert await scheduled_history_job() == "skipped"
    finally:
        await PIPELINE_LOCK.release()

    async def not_acquired(name: str) -> bool:
        return False

    monkeypatch.setattr(PIPELINE_LOCK, "acquire", not_acquired)
    assert await scheduled_history_job() == "skipped"


@pytest.mark.asyncio
async def test_scheduled_history_job_moex_source(monkeypatch):
    from scraper import repositories
    from scraper.moex import MoexClient
    from scraper.pipeline import _build_coupon_schedule
    from scraper.scheduler import scheduled_history_job
    from scraper.models import BondHistory

    monkeypatch.setenv("DATA_SOURCE", "moex")
    monkeypatch.setenv("MOEX_HISTORY_SAMPLE", "5")
    monkeypatch.setenv("MOEX_HISTORY_DAYS", "10")
    monkeypatch.setattr(MoexClient, "fetch_history", FakeClient().fetch_history)
    monkeypatch.setattr(
        MoexClient,
        "fetch_coupons",
        FakeClient(coupons=[{"date": date(2026, 6, 29), "coupon": __import__("decimal").Decimal("38.57")}]).fetch_coupons,
    )

    async with session_scope() as session:
        await _add_bond(session, "SH-M1", "RUB")
        await _add_bond(session, "SH-M2", "USD")
    assert await scheduled_history_job() == "ok"

    async with session_scope() as session:
        from scraper.orm import BondORM

        orm = (
            await session.execute(
                __import__("sqlalchemy").select(BondORM).where(BondORM.internal_id == "SH-M2")
            )
        ).scalar_one_or_none()
    assert orm is not None
    assert orm.coupon_schedule is not None


@pytest.mark.asyncio
async def test_scheduled_history_job_moex_failure_path(monkeypatch):
    from scraper.moex import MoexClient
    from scraper.scheduler import scheduled_history_job

    monkeypatch.setenv("DATA_SOURCE", "moex")
    monkeypatch.setattr(MoexClient, "fetch_history", FakeClient(raise_history=True).fetch_history)
    monkeypatch.setattr(MoexClient, "fetch_coupons", FakeClient().fetch_coupons)

    async with session_scope() as session:
        await _add_bond(session, "SH-F1", "RUB")
    assert await scheduled_history_job() == "ok"


@pytest.mark.asyncio
async def test_scheduled_history_job_aigenis_source(monkeypatch):
    from unittest.mock import AsyncMock

    from scraper.client import AigenisClient
    from scraper.pipeline import backfill_history
    from scraper.scheduler import scheduled_history_job

    monkeypatch.setenv("DATA_SOURCE", "aigenis")
    monkeypatch.setattr(AigenisClient, "__aenter__", FakeClient().__aenter__)
    monkeypatch.setattr(AigenisClient, "__aexit__", FakeClient().__aexit__)
    monkeypatch.setattr(backfill_history, "__call__", AsyncMock(return_value=(5, 1)))

    async with session_scope() as session:
        await _add_bond(session, "SH-A1", "USD")
    assert await scheduled_history_job() == "ok"


@pytest.mark.asyncio
async def test_scheduled_history_job_both_sources(monkeypatch):
    from unittest.mock import AsyncMock

    from scraper.client import AigenisClient
    from scraper.moex import MoexClient
    from scraper.pipeline import backfill_history
    from scraper.scheduler import scheduled_history_job

    monkeypatch.setenv("DATA_SOURCE", "both")
    monkeypatch.setattr(MoexClient, "fetch_history", FakeClient().fetch_history)
    monkeypatch.setattr(MoexClient, "fetch_coupons", FakeClient().fetch_coupons)
    monkeypatch.setattr(AigenisClient, "__aenter__", FakeClient().__aenter__)
    monkeypatch.setattr(AigenisClient, "__aexit__", FakeClient().__aexit__)
    monkeypatch.setattr(backfill_history, "__call__", AsyncMock(return_value=(0, 0)))

    async with session_scope() as session:
        await _add_bond(session, "SH-B1", "BYN")
    assert await scheduled_history_job() == "ok"


@pytest.mark.asyncio
async def test_scheduled_job_sources_and_sitemap_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from scraper.client import AigenisClient
    from scraper.moex import MoexClient
    from scraper.pipeline import run_once, run_once_moex
    from scraper.scheduler import scheduled_job

    monkeypatch.setenv("DATA_SOURCE", "both")
    monkeypatch.setattr(MoexClient, "__aenter__", FakeClient().__aenter__)
    monkeypatch.setattr(MoexClient, "__aexit__", FakeClient().__aexit__)
    monkeypatch.setattr(AigenisClient, "__aenter__", FakeClient().__aenter__)
    monkeypatch.setattr(AigenisClient, "__aexit__", FakeClient().__aexit__)
    monkeypatch.setattr(run_once_moex, "__call__", AsyncMock())
    monkeypatch.setattr(run_once, "__call__", AsyncMock())

    def boom():
        raise RuntimeError("sitemap down")

    monkeypatch.setattr("api.seo.regenerate_sitemap", boom)
    assert await scheduled_job() == "ok"


@pytest.mark.asyncio
async def test_scheduled_job_failure_logs_and_returns_ok(monkeypatch):
    from unittest.mock import AsyncMock

    from scraper.moex import MoexClient
    from scraper.pipeline import run_once_moex
    from scraper.scheduler import scheduled_job

    monkeypatch.setenv("DATA_SOURCE", "moex")
    monkeypatch.setattr(MoexClient, "__aenter__", FakeClient().__aenter__)
    monkeypatch.setattr(MoexClient, "__aexit__", FakeClient().__aexit__)

    async def boom():
        raise RuntimeError("pipeline down")

    monkeypatch.setattr(run_once_moex, "__call__", boom)
    assert await scheduled_job() == "ok"


def test_exc_summary_with_and_without_exception():
    from scraper.scheduler import _exc_summary

    assert _exc_summary() == ""
    try:
        raise ValueError("multi\nline boom")
    except ValueError:
        summary = _exc_summary()
        assert summary == "multi line boom"


def test_build_scheduler_with_optional_imports_missing(monkeypatch):
    import sys

    from scraper.scheduler import build_scheduler

    for mod in (
        "scraper.scheduler_v3",
        "scraper.scheduler_v4",
        "scraper.fx",
        "api.notifications.reminders",
    ):
        monkeypatch.setitem(sys.modules, mod, None)

    scheduler = build_scheduler()
    ids = [j.id for j in scheduler.get_jobs()]
    assert "scrape_all_6h" in ids
    assert "scrape_history_daily" in ids


def test_build_scheduler_stock_disabled(monkeypatch):
    import sys

    from scraper.scheduler import build_scheduler

    for mod in ("scraper.scheduler_v3", "scraper.scheduler_v4", "scraper.fx", "api.notifications.reminders"):
        monkeypatch.setitem(sys.modules, mod, None)

    def fake_settings():
        return SimpleNamespace(stock=SimpleNamespace(enabled=False))

    monkeypatch.setattr("scraper.scheduler.get_settings", fake_settings)
    scheduler = build_scheduler()
    ids = [j.id for j in scheduler.get_jobs()]
    assert "moex_stocks_30m" not in ids


@pytest.mark.asyncio
async def test_run_forever_shutdown_flow(monkeypatch):
    import asyncio
    import signal

    class FakeEvent:
        def __init__(self) -> None:
            self._set = False

        def set(self) -> None:
            self._set = True

        async def wait(self):
            raise KeyboardInterrupt

    class FakeScheduler:
        def __init__(self) -> None:
            self._started = False
            self._shutdown = False

        def start(self) -> None:
            self._started = True

        def get_jobs(self):
            return [SimpleNamespace(id="job1")]

        def shutdown(self, **kw):
            self._shutdown = True

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr("scraper.scheduler.build_scheduler", lambda: fake_scheduler)
    monkeypatch.setattr("scraper.scheduler.asyncio.Event", FakeEvent)

    async def fake_dispose() -> None:
        return None

    monkeypatch.setattr("scraper.db.dispose", fake_dispose)
    await __import__("scraper.scheduler", fromlist=["run_forever"]).run_forever()
    assert fake_scheduler._started and fake_scheduler._shutdown
