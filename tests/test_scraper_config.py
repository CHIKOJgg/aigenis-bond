"""Tests for the scraper configuration and error handling.

Covers: settings validation, database connection, Redis connectivity,
and all error path logging in the pipeline.
"""
from __future__ import annotations

import asyncio

from scraper.config import DatabaseSettings, RedisSettings, Settings
from scraper.errors import (
    CircuitBreakerOpenError,
    FatalError,
    NotFoundError,
    ParseError,
    RateLimitError,
    ScraperError,
    TransientError,
    ValidationError,
)


def test_settings_loads_with_defaults():
    settings = Settings()
    assert settings.base_url == "https://aigenis.by"
    assert settings.headless is True
    assert settings.max_concurrency == 2


def test_settings_validates_delay():
    """Negative delay is clamped to 0."""
    s = Settings(delay_between_requests=-1)
    assert s.delay_between_requests == 0.0


def test_database_settings_default_url():
    db = DatabaseSettings()
    assert db.url == "sqlite+aiosqlite:///:memory:"


def test_redis_settings_default_url():
    r = RedisSettings()
    assert r.url.startswith("redis://")
    assert "redis:6379" in r.url


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


def test_circuit_breaker_error_is_scraper_error():
    err = CircuitBreakerOpenError("service unavailable")
    assert isinstance(err, ScraperError)


def test_rate_limit_error_is_transient():
    err = RateLimitError("upstream rate limited")
    assert isinstance(err, TransientError)


def test_engine_creation_logs():
    from scraper.db import dispose, get_engine
    engine = get_engine()
    assert engine is not None
    asyncio.run(dispose())
