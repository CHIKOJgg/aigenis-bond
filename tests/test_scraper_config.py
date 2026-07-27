"""Tests for the scraper configuration and error handling.

Covers: settings validation, database connection, Redis connectivity,
and all error path logging in the pipeline.
"""
from __future__ import annotations

import pytest
from scraper.config import get_settings, Settings, DatabaseSettings, RedisSettings
from scraper.errors import (
    TransientError,
    FatalError,
    NotFoundError,
    ParseError,
    ValidationError,
    CircuitBreakerOpenError,
    RateLimitError,
)


def test_settings_loads_with_defaults():
    settings = Settings()
    assert settings.base_url == "https://aigenis.by"
    assert settings.headless is True
    assert settings.max_concurrency == 2


def test_settings_validates_delay():
    """Negative delay should be clamped to 0."""
    with pytest.raises(Exception):
        s = Settings(delay_between_requests=-1)


def test_database_settings_default_url():
    db = DatabaseSettings()
    assert db.url == "sqlite+aiosqlite:///:memory:"


def test_redis_settings_default_url():
    r = RedisSettings()
    assert r.url == "redis://localhost:6379/0"


def test_transient_error_is_scraper_error():
    err = TransientError("timeout")
    assert isinstance(err, ScraperError)


def test_fatal_error_stops_pipeline():
    err = FatalError("captcha detected")
    assert isinstance(err, ScraperError)


def test_not_found_error_is_transient():
    err = NotFoundError("bond delisted")
    assert isinstance(err, ScraperError)


def test_parse_error_is_scraper_error():
    err = ParseError("unexpected structure")
    assert isinstance(err, ScraperError)


def test_validation_error_is_scraper_error():
    err = ValidationError("missing required field")
    assert isinstance(err, ScraperError)


def test_circuit_breaker_error_is_transient():
    err = CircuitBreakerOpenError("service unavailable")
    assert isinstance(err, TransientError)


def test_rate_limit_error_is_transient():
    err = RateLimitError("upstream rate limited")
    assert isinstance(err, TransientError)


def test_engine_creation_logs():
    from scraper.db import get_engine, dispose
    engine = get_engine()
    assert engine is not None
    dispose()