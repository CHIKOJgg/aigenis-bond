"""V4 scheduler hooks: ежедневная кривая, еженедельные стрессы, еженедельный RV."""

from __future__ import annotations

from scraper.commands_v4 import cmd_desk_curve, cmd_desk_rv, cmd_desk_stress
from scraper.logging import get_logger

logger = get_logger("scraper.scheduler.v4")


async def scheduled_curve() -> int:
    logger.info("scheduled_curve_start")
    try:
        rc = await cmd_desk_curve()
        logger.info("scheduled_curve_done", rc=rc)
    except Exception as e:
        logger.exception("scheduled_curve_failed", error=str(e))
    return 0


async def scheduled_rv() -> int:
    logger.info("scheduled_rv_start")
    try:
        rc = await cmd_desk_rv()
        logger.info("scheduled_rv_done", rc=rc)
    except Exception as e:
        logger.exception("scheduled_rv_failed", error=str(e))
    return 0


async def scheduled_stress() -> int:
    logger.info("scheduled_stress_start")
    try:
        rc = await cmd_desk_stress()
        logger.info("scheduled_stress_done", rc=rc)
    except Exception as e:
        logger.exception("scheduled_stress_failed", error=str(e))
    return 0


async def scheduled_alerts() -> int:
    logger.info("scheduled_alerts_start")
    try:
        from notifications.alerts_service import run_alert_checks

        fired = await run_alert_checks()
        logger.info("scheduled_alerts_done", fired=fired)
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("scheduled_alerts_failed", error=str(e))
    return 0
