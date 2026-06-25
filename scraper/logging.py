from __future__ import annotations

import os
import sys
import uuid

from loguru import logger as _logger

from scraper.config import get_settings

_configured = False


def _serialize_record(record):
    subset = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    if record.get("extra"):
        subset.update(record["extra"])
    if record["exception"]:
        subset["exception"] = str(record["exception"])
    return subset


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    _logger.remove()

    log_format_key = "LOG_FORMAT"
    use_json = (
        os.getenv(log_format_key, "true" if settings.aigenis.log_json else "false").lower()
        == "true"
    )

    if use_json:
        _logger.add(
            sys.stdout,
            level=settings.aigenis.log_level,
            serialize=True,
            backtrace=True,
            diagnose=False,
            enqueue=True,
        )
    else:
        _logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=settings.aigenis.log_level,
            backtrace=True,
            diagnose=False,
            enqueue=True,
        )

    log_path = settings.aigenis.log_file_path()
    _logger.add(
        str(log_path),
        level=settings.aigenis.log_level,
        serialize=use_json,
        rotation=settings.aigenis.log_rotation,
        retention=settings.aigenis.log_retention,
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    _configured = True


def get_logger(name: str | None = None):
    if not _configured:
        configure_logging()
    return _logger.bind(module=name) if name else _logger


def correlation_id() -> str:
    return uuid.uuid4().hex[:12]
