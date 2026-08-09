from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper.config import get_settings
from scraper.db import PIPELINE_LOCK
from scraper.logging import correlation_id, get_logger

logger = get_logger("scraper.scheduler")


async def scheduled_stocks_job() -> None:
    """Scheduled job for MOEX stock scraping (independent of bond pipeline)."""
    from scraper.pipeline import run_once_moex_stocks

    cfg = getattr(get_settings(), "stock", None)
    if cfg is not None and not cfg.enabled:
        logger.info("scheduled_stocks_job_disabled")
        return
    cid = correlation_id()
    logger.info("scheduled_stocks_job_start", correlation_id=cid)
    try:
        await run_once_moex_stocks()
        logger.info("scheduled_stocks_job_done", correlation_id=cid)
    except Exception:
        logger.exception("scheduled_stocks_job_failed", correlation_id=cid)


async def scheduled_history_job() -> str:
    """Daily history-only refresh (03:00), complementing the full 6-hour run.

    Previously this cron slot re-ran the entire listing+details+history
    pipeline — a full duplicate of ``scrape_all_6h``. Now it only refreshes
    price/YTM candles (30 days) and the coupon calendar for the top-N bonds per
    currency, so charts are fresh by market open without duplicating the scrape.

    Returns a PIPELINE_LOCK outcome so the scheduler wrapper can record it.
    """
    if PIPELINE_LOCK._local.locked():
        logger.info("scheduled_history_job_skipped_already_running")
        return "skipped"
    acquired = await PIPELINE_LOCK.acquire("history")
    if not acquired:
        logger.info("scheduled_history_job_skipped_leader_is_another_instance")
        return "skipped"
    try:
        settings = get_settings()
        cid = correlation_id()
        logger.info("scheduled_history_job_start", correlation_id=cid)
        try:
            source = (os.getenv("DATA_SOURCE") or "aigenis").strip().lower()
            cap = int(os.getenv("MOEX_HISTORY_SAMPLE", "200"))
            days = int(os.getenv("MOEX_HISTORY_DAYS", "30"))
            from sqlalchemy import select

            if source in ("moex", "both"):
                from scraper import repositories
                from scraper.db import session_scope
                from scraper.moex import MoexClient
                from scraper.orm import BondORM
                from scraper.pipeline import _build_coupon_schedule

                async with MoexClient(settings) as client:
                    cur_list = [c.upper() for c in settings.aigenis.currencies]
                    if "RUB" not in cur_list:
                        cur_list = ["RUB", *cur_list]
                    for cur in cur_list:
                        async with session_scope() as session:
                            ids = (
                                (
                                    await session.execute(
                                        select(BondORM.internal_id)
                                        .where(BondORM.currency == cur)
                                        .order_by(BondORM.yield_to_maturity.desc())
                                        .limit(cap)
                                    )
                                )
                                .scalars()
                                .all()
                            )
                        for iid in ids:
                            try:
                                hist = await client.fetch_history(iid, _days=days)
                                if hist:
                                    async with session_scope() as session:
                                        await repositories.history.upsert_history_batch(
                                            session, hist
                                        )
                                coupons = await client.fetch_coupons(iid)
                                if coupons:
                                    schedule = _build_coupon_schedule(coupons)
                                    async with session_scope() as session:
                                        orm = (
                                            await session.execute(
                                                select(BondORM).where(BondORM.internal_id == iid)
                                            )
                                        ).scalar_one_or_none()
                                        if orm is not None:
                                            orm.coupon_schedule = schedule
                            except Exception:
                                logger.warning(
                                    "history_refresh_bond_failed",
                                    internal_id=iid,
                                    correlation_id=cid,
                                )
            if source in ("aigenis", "both"):
                from scraper.client import AigenisClient
                from scraper.db import session_scope
                from scraper.orm import BondORM
                from scraper.pipeline import backfill_history

                async with AigenisClient(settings.aigenis) as client:
                    async with session_scope() as session:
                        ids = (
                            (
                                await session.execute(
                                    select(BondORM.internal_id).where(BondORM.status == "active")
                                )
                            )
                            .scalars()
                            .all()
                        )
                    ok, err = await backfill_history(
                        client,
                        list(ids),
                        days=settings.aigenis.history_backfill_days,
                    )
                    logger.info(
                        "history_refresh_done",
                        rows=ok,
                        err=err,
                        correlation_id=cid,
                    )
        except Exception:
            logger.exception("scheduled_history_job_failed", correlation_id=cid)
        else:
            logger.info("scheduled_history_job_done", correlation_id=cid)
    finally:
        await PIPELINE_LOCK.release()
    return "ok"


async def scheduled_job() -> str:
    if PIPELINE_LOCK._local.locked():
        logger.info("scheduled_job_skipped_already_running")
        return "skipped"
    acquired = await PIPELINE_LOCK.acquire("pipeline")
    if not acquired:
        logger.info("scheduled_job_skipped_leader_is_another_instance")
        return "skipped"
    try:
        settings = get_settings()
        cid = correlation_id()
        logger.info("scheduled_job_start", correlation_id=cid)
        try:
            source = (os.getenv("DATA_SOURCE") or "aigenis").strip().lower()
            if source in ("moex", "both"):
                from scraper.moex import MoexClient
                from scraper.pipeline import run_once_moex

                async with MoexClient(settings) as client:
                    await run_once_moex(client, settings.aigenis.currencies)
            if source in ("aigenis", "both"):
                from scraper.client import AigenisClient
                from scraper.pipeline import run_once

                async with AigenisClient(settings.aigenis) as client:
                    await run_once(client, settings.aigenis.currencies)
            # Refresh the public sitemap cache (no-op unless SEO_PUBLIC_BASE_URL
            # is configured) so new bond pages are discoverable by crawlers.
            try:
                from api.seo import regenerate_sitemap

                await regenerate_sitemap()
            except Exception:
                logger.exception("seo_sitemap_regenerate_failed", correlation_id=cid)
            logger.info("scheduled_job_done", correlation_id=cid)
        except Exception:
            logger.exception("scheduled_job_failed", correlation_id=cid)
    finally:
        await PIPELINE_LOCK.release()
    return "ok"


def _exc_summary() -> str:
    """Single-line error summary for the job_runs table."""
    import sys

    exc = sys.exc_info()[1]
    if exc is None:
        return ""
    text = str(exc) or exc.__class__.__name__
    return text.replace("\n", " ").strip()[:512]


def _wrap(name: str, fn: Callable[[], Awaitable[Any]]) -> Callable[[], Awaitable[str | None]]:
    async def wrapper() -> str | None:
        from datetime import UTC, datetime

        from scraper.job_runs import finish_job_run, start_job_run

        cid = correlation_id()
        started_at = datetime.now(UTC)
        run_id = await start_job_run(name)
        logger.info(f"{name}_start", correlation_id=cid)
        try:
            outcome = str(await fn())
            if outcome in ("skipped",):
                logger.info(f"{name}_skipped", correlation_id=cid)
                await finish_job_run(run_id, "skipped", started_at=started_at)
                return outcome
            logger.info(f"{name}_done", correlation_id=cid)
            await finish_job_run(run_id, "ok", started_at=started_at)
            return outcome
        except Exception:
            logger.exception(f"{name}_failed", correlation_id=cid)
            await finish_job_run(run_id, "failed", started_at=started_at, error=_exc_summary())
            return None

    wrapper.__name__ = name
    return wrapper


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")

    jobs: list[tuple[str, str, Callable[[], Awaitable[Any]], int]] = [
        ("scrape_all_6h", "0 */6 * * *", scheduled_job, 900),
        # History-only refresh — NOT a duplicate full pipeline.
        ("scrape_history_daily", "0 3 * * *", scheduled_history_job, 1800),
    ]

    try:
        from scraper.scheduler_v3 import scheduled_auto_rebalance, scheduled_ml_train

        jobs.append(("ml_train_weekly", "30 3 * * 0", scheduled_ml_train, 3600))
        jobs.append(("auto_rebalance_daily", "0 4 * * *", scheduled_auto_rebalance, 1800))
    except ImportError:
        logger.warning("scheduler_v3_not_available")

    try:
        from scraper.fx import fetch_and_save_metal_prices, fetch_and_save_rates

        jobs.append(("fx_fetch_daily", "0 7 * * *", fetch_and_save_rates, 1800))
        jobs.append(("fx_metals_daily", "30 7 * * *", fetch_and_save_metal_prices, 1800))
    except ImportError:
        logger.warning("fx_module_not_available")

    try:
        from api.notifications.reminders import notify_expiring_trials

        jobs.append(("reminders_daily", "0 9 * * *", notify_expiring_trials, 1800))
    except ImportError:
        logger.warning("reminders_module_not_available")

    # Stock scraping runs every `stock.refresh_cadence_min` minutes during
    # market hours (only when the stock data source is enabled).
    stock_cfg = getattr(get_settings(), "stock", None)
    if stock_cfg is None or stock_cfg.enabled:
        cadence = stock_cfg.refresh_cadence_min if stock_cfg is not None else 30
        cron = f"*/{max(cadence, 1)} 10-18 * * 1-5"
        jobs.append(("moex_stocks_30m", cron, scheduled_stocks_job, 600))
    else:
        logger.info("moex_stocks_job_disabled_by_config")

    try:
        from scraper.scheduler_v4 import (
            scheduled_alerts,
            scheduled_curve,
            scheduled_rv,
            scheduled_stress,
        )

        jobs.append(("desk_curve_daily", "30 4 * * *", scheduled_curve, 1800))
        jobs.append(("desk_rv_daily", "0 5 * * *", scheduled_rv, 1800))
        jobs.append(("desk_stress_weekly", "0 5 * * 0", scheduled_stress, 3600))
        jobs.append(("alerts_check_daily", "0 8 * * *", scheduled_alerts, 1800))
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
    from functools import partial

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, partial(_shutdown, sig))

    try:
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler_interrupted")
    finally:
        logger.info("scheduler_shutting_down")
        scheduler.shutdown(wait=True, timeout=120)
        from scraper.db import dispose as db_dispose

        await db_dispose()
        logger.info("scheduler_shutdown_complete")
