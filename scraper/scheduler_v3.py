"""V3 scheduler hooks: еженедельное переобучение ML + ежедневный auto-rebalance."""

from __future__ import annotations

from scraper.commands_v3 import cmd_ml_predict, cmd_ml_train, cmd_rebalance_now
from scraper.logging import get_logger

logger = get_logger("scraper.scheduler.v3")


async def scheduled_ml_train() -> int:
    """Раз в неделю: переобучить модели."""
    logger.info("scheduled_ml_train_start")
    try:
        rc = await cmd_ml_train()
        if rc == 0:
            await cmd_ml_predict()
        logger.info("scheduled_ml_train_done", rc=rc)
    except Exception as e:
        logger.exception("scheduled_ml_train_failed", error=str(e))
    return 0


async def scheduled_auto_rebalance() -> int:
    """Раз в день: проверить drift и сформировать план."""
    logger.info("scheduled_auto_rebalance_start")
    try:
        rc = await cmd_rebalance_now()
        logger.info("scheduled_auto_rebalance_done", rc=rc)
    except Exception as e:
        logger.exception("scheduled_auto_rebalance_failed", error=str(e))
    return 0
