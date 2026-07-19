from __future__ import annotations

import io
import os
import sys
import uuid

from loguru import logger as _logger

from scraper.config import get_settings

_configured = False


class _Utf8Stream(io.TextIOBase):
    """Wrap a binary stdout/stderr so loguru always emits UTF-8.

    On platforms whose console codec is not UTF-8 (e.g. Windows cp1251), writing
    Cyrillic log messages to ``sys.stdout`` raises ``UnicodeEncodeError`` inside
    loguru's background writer thread and can crash the process. Routing through
    the underlying binary buffer with an explicit UTF-8 encoding avoids that.
    """

    def __init__(self, binary_stream: io.RawIOBase | io.BufferedIOBase) -> None:
        self._buffer = binary_stream

    def write(self, message: str) -> int:
        import contextlib

        with contextlib.suppress(ValueError, OSError):
            # Underlying stream already closed (e.g. subprocess stderr pipe) —
            # never let logging crash the application.
            self._buffer.write(message.encode("utf-8", errors="replace"))
            self._buffer.flush()
        return len(message)

    def flush(self) -> None:
        import contextlib

        with contextlib.suppress(ValueError, OSError):
            self._buffer.flush()


def _stdout_sink():
    stream = getattr(sys.stdout, "buffer", None)
    if stream is not None:
        return _Utf8Stream(stream)
    return sys.stdout


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
            _stdout_sink(),
            level=settings.aigenis.log_level,
            serialize=True,
            backtrace=True,
            diagnose=False,
            enqueue=True,
        )
    else:
        _logger.add(
            _stdout_sink(),
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
