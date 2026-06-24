from __future__ import annotations

import sys

from loguru import logger

from scraper.config import get_settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=True,
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )

    logger.add(
        str(settings.log_file_path()),
        level=settings.log_level,
        serialize=True,
        rotation="100 MB",
        retention="14 days",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    _configured = True


def get_logger(name: str | None = None):
    if not _configured:
        configure_logging()
    return logger.bind(module=name) if name else logger
