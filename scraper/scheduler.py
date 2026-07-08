from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper.client import AigenisClient
from scraper.config import get_settings
from scraper.logging import correlation_id, get_logger
from scraper.pipeline import run_once

logger = get_logger("scraper.scheduler")


async def scheduled_job() -> None:
    settings = get_settings()
    cid = correlation_id()
    logger.info("scheduled_job_start", correlation_id=cid)
    try:
        async with AigenisClient(settings.aigenis) as client:
            await run_once(client, settings.aigenis.currencies)
        logger.info("scheduled_job_done", correlation_id=cid)
    except Exception:
        logger.exception("scheduled_job_failed", correlation_id=cid)


def _wrap(name: str, fn: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    async def wrapper() -> None:
        cid = correlation_id()
        logger.info(f"{name}_start", correlation_id=cid)
        try:
            await fn()
            logger.info(f"{name}_done", correlation_id=cid)
        except Exception:
            logger.exception(f"{name}_failed", correlation_id=cid)

    wrapper.__name__ = name
    return wrapper


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")

    jobs = [
        ("scrape_all_6h", "0 */6 * * *", scheduled_job, 900),
        ("scrape_history_daily", "0 3 * * *", scheduled_job, 1800),
    ]

    try:
        from scraper.scheduler_v3 import scheduled_auto_rebalance, scheduled_ml_train

        jobs.append(("ml_train_weekly", "30 3 * * 0", scheduled_ml_train, 3600))
        jobs.append(("auto_rebalance_daily", "0 4 * * *", scheduled_auto_rebalance, 1800))
    except ImportError:
        logger.warning("scheduler_v3_not_available")

    try:
        from scraper.fx import fetch_and_save_rates, fetch_and_save_metal_prices

        jobs.append(("fx_fetch_daily", "0 7 * * *", fetch_and_save_rates, 1800))
        jobs.append(("fx_metals_daily", "30 7 * * *", fetch_and_save_metal_prices, 1800))
    except ImportError:
        logger.warning("fx_module_not_available")

    try:
        from scraper.scheduler_v4 import scheduled_curve, scheduled_rv, scheduled_stress

        jobs.append(("desk_curve_daily", "30 4 * * *", scheduled_curve, 1800))
        jobs.append(("desk_rv_daily", "0 5 * * *", scheduled_rv, 1800))
        jobs.append(("desk_stress_weekly", "0 5 * * 0", scheduled_stress, 3600))
    except ImportError:
        logger.warning("scheduler_v4_not_available")

    for job_id, cron, fn, grace in jobs:
        scheduler.add_job(
            _wrap(job_id, fn),
            CronTrigger.from_crontab(cron),
            id=job_id,
            name=job_id,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=grace,
            replace_existing=True,
        )

    return scheduler


async def run_forever() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler_started", jobs=[j.id for j in scheduler.get_jobs()])

    stop_event = asyncio.Event()

    def _shutdown(sig: int) -> None:
        logger.info("shutdown_signal_received", signal=sig)
        stop_event.set()

    from contextlib import suppress

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda s=sig: _shutdown(s))

    try:
        await stop_event.wait()
    finally:
        logger.info("scheduler_shutting_down")
        scheduler.shutdown(wait=False)
        from scraper.db import dispose as db_dispose

        await db_dispose()
        logger.info("scheduler_shutdown_complete")
