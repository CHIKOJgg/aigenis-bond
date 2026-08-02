"""Tests for logging and observability across all modules.

Ensures that every error path and critical operation produces
structured log output that can be ingested by Sentry/Loguru
for deployment monitoring.

``get_logger`` returns a loguru Logger, so these tests capture output with a
temporary loguru sink (pytest's ``caplog`` only sees the stdlib logging module).
"""
from __future__ import annotations

import io
import json

from loguru import logger as _l

from scraper.logging import get_logger


def _capture_json() -> tuple[io.StringIO, int]:
    stream = io.StringIO()
    get_logger("test.init")  # ensure logging is configured first
    sink_id = _l.add(stream, serialize=True, enqueue=False)
    return stream, sink_id


def _records(stream: io.StringIO) -> list[dict]:
    return [json.loads(line)["record"] for line in stream.getvalue().splitlines() if line.strip()]


def test_logger_produces_json_output():
    """scraper.logging must produce structured JSON output."""
    stream, sink_id = _capture_json()
    try:
        get_logger("test.module").info("test_event", key="value", count=42)
    finally:
        _l.remove(sink_id)
    (record,) = _records(stream)
    assert record["message"] == "test_event"
    assert record["extra"]["key"] == "value"
    assert record["extra"]["count"] == 42


def test_logger_error_includes_traceback():
    """Error-level logs must include the exception traceback."""
    stream, sink_id = _capture_json()
    try:
        logger = get_logger("test.errors")
        try:
            raise ValueError("test error for logging")
        except ValueError:
            logger.exception("test_error_occurred")
    finally:
        _l.remove(sink_id)
    (record,) = _records(stream)
    assert record["message"] == "test_error_occurred"
    assert record["level"]["name"] == "ERROR"
    assert record["exception"]["type"] == "ValueError"


def test_logger_warning_includes_context():
    """Warning logs must include all context fields."""
    stream, sink_id = _capture_json()
    try:
        get_logger("test.warnings").warning(
            "payment_amount_mismatch", payment_id="pay_123", plan="pro", paid=10.0, expected=29.0
        )
    finally:
        _l.remove(sink_id)
    (record,) = _records(stream)
    assert record["message"] == "payment_amount_mismatch"
    assert record["extra"]["payment_id"] == "pay_123"
    assert record["extra"]["plan"] == "pro"
    assert record["extra"]["paid"] == 10.0


def test_logger_critical_surfaces():
    """Critical events should be logged at ERROR level for visibility."""
    stream, sink_id = _capture_json()
    try:
        get_logger("test.critical").error("api_unhandled_error", error="unexpected failure")
    finally:
        _l.remove(sink_id)
    (record,) = _records(stream)
    assert record["message"] == "api_unhandled_error"
    assert record["extra"]["error"] == "unexpected failure"
    assert record["level"]["name"] == "ERROR"


def test_logger_name_is_module_scoped():
    """Each module gets its own logger name for filtering."""
    stream, sink_id = _capture_json()
    try:
        get_logger("api.main").info("m1")
        get_logger("api.auth").info("m2")
    finally:
        _l.remove(sink_id)
    records = _records(stream)
    modules = [r["extra"]["module"] for r in records]
    assert modules == ["api.main", "api.auth"]
    assert modules[0] != modules[1]
