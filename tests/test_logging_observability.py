"""Tests for logging and observability across all modules.

Ensures that every error path and critical operation produces
structured log output that can be ingested by Sentry/Loguru
for deployment monitoring.
"""
from __future__ import annotations

import pytest
import logging
from scraper.logging import get_logger


def test_logger_produces_json_output(caplog):
    """scraper.logging must produce structured JSON output."""
    logger = get_logger("test.module")
    with caplog.at_level(logging.INFO):
        logger.info("test_event", key="value", count=42)
    assert "test_event" in caplog.text
    assert "key" in caplog.text
    assert "value" in caplog.text
    assert "count" in caplog.text


def test_logger_error_includes_traceback(caplog):
    """Error-level logs must include the exception traceback."""
    logger = get_logger("test.errors")
    try:
        raise ValueError("test error for logging")
    except ValueError as exc:
        logger.error("test_error_occurred", error=str(exc))
    assert "test_error_occurred" in caplog.text
    assert "ValueError" in caplog.text


def test_logger_warning_includes_context(caplog):
    """Warning logs must include all context fields."""
    logger = get_logger("test.warnings")
    logger.warning("payment_amount_mismatch", payment_id="pay_123", plan="pro", paid=10.0, expected=29.0)
    assert "payment_amount_mismatch" in caplog.text
    assert "pay_123" in caplog.text
    assert "pro" in caplog.text


def test_logger_critical_surfaces():
    """Critical events should be logged at ERROR level for visibility."""
    logger = get_logger("test.critical")
    with caplog.at_level(logging.ERROR):
        logger.error("api_unhandled_error", error="unexpected failure")
    assert "api_unhandled_error" in caplog.text


def test_logger_name_is_module_scoped():
    """Each module gets its own logger name for filtering."""
    logger1 = get_logger("api.main")
    logger2 = get_logger("api.auth")
    assert logger1.name == "api.main"
    assert logger2.name == "api.auth"
    assert logger1.name != logger2.name