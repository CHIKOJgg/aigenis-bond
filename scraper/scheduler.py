"""Планировщик APScheduler."""

from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper.client import AigenisClient
from scraper.config import get_settings
from scraper.logging import get_logger
from scraper.pipeline import run_once
from scraper.scheduler_v3 import scheduled_auto_rebalance, scheduled_ml_train
from scraper.scheduler_v4 import scheduled_curve, scheduled_rv, scheduled_stress

logger = get_logger("scraper.scheduler")


async def scheduled_job() -> None:
    settings = get_settings()
    try:
        async with AigenisClient(settings) as client:
            await run_once(client, settings.currencies)
    except Exception as e:  # noqa: BLE001
        logger.exception("scheduled_job_failed", error=str(e))


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")

    scheduler.add_job(
        _safe_run,
        CronTrigger.from_crontab("0 */6 * * *"),
        id="scrape_all_6h",
        name="scrape_all_6h",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_run,
        CronTrigger.from_crontab("0 3 * * *"),
        id="scrape_history_daily",
        name="scrape_history_daily",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_v3,
        CronTrigger.from_crontab("30 3 * * 0"),
        id="ml_train_weekly",
        name="ml_train_weekly",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_rebalance,
        CronTrigger.from_crontab("0 4 * * *"),
        id="auto_rebalance_daily",
        name="auto_rebalance_daily",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_v4_curve,
        CronTrigger.from_crontab("30 4 * * *"),
        id="desk_curve_daily",
        name="desk_curve_daily",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_v4_rv,
        CronTrigger.from_crontab("0 5 * * *"),
        id="desk_rv_daily",
        name="desk_rv_daily",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        _safe_v4_stress,
        CronTrigger.from_crontab("0 5 * * 0"),
        id="desk_stress_weekly",
        name="desk_stress_weekly",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    return scheduler


async def _safe_v4_curve() -> None:
    try:
        await scheduled_curve()
    except Exception as e:  # noqa: BLE001
        logger.exception("desk_curve_failed", error=str(e))


async def _safe_v4_rv() -> None:
    try:
        await scheduled_rv()
    except Exception as e:  # noqa: BLE001
        logger.exception("desk_rv_failed", error=str(e))


async def _safe_v4_stress() -> None:
    try:
        await scheduled_stress()
    except Exception as e:  # noqa: BLE001
        logger.exception("desk_stress_failed", error=str(e))


async def _safe_v3() -> None:
    try:
        await scheduled_ml_train()
    except Exception as e:  # noqa: BLE001
        logger.exception("ml_train_failed", error=str(e))


async def _safe_rebalance() -> None:
    try:
        await scheduled_auto_rebalance()
    except Exception as e:  # noqa: BLE001
        logger.exception("auto_rebalance_failed", error=str(e))


async def _safe_run() -> None:
    try:
        await scheduled_job()
    except Exception as e:  # noqa: BLE001
        logger.exception("scheduler_run_failed", error=str(e))


async def run_forever() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler_started")
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
