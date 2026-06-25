from __future__ import annotations

from scraper.errors import (
    BrowserNotAvailable,
    CircuitBreakerOpenError,
    ConfigError,
    DatabaseError,
    FatalError,
    HistoryUnavailable,
    NotFoundError,
    ParseError,
    RateLimitError,
    ScraperError,
    TransientError,
    ValidationError,
)


def test_scraper_error_hierarchy():
    assert issubclass(TransientError, ScraperError)
    assert issubclass(FatalError, ScraperError)
    assert issubclass(NotFoundError, ScraperError)
    assert issubclass(ParseError, ScraperError)
    assert issubclass(ValidationError, ScraperError)
    assert issubclass(DatabaseError, ScraperError)
    assert issubclass(CircuitBreakerOpenError, ScraperError)
    assert issubclass(ConfigError, ScraperError)
    assert issubclass(BrowserNotAvailable, TransientError)
    assert issubclass(RateLimitError, TransientError)


def test_scraper_error_context():
    e = ScraperError("test error", context={"key": "value"})
    assert str(e) == "test error"
    assert e.context == {"key": "value"}


def test_scraper_error_cause():
    cause = ValueError("root cause")
    e = ScraperError("wrapped", cause=cause)
    assert e.cause is cause
    assert "wrapped" in str(e)


def test_transient_error():
    e = TransientError("timeout")
    assert isinstance(e, ScraperError)


def test_fatal_error():
    e = FatalError("blocked")
    assert isinstance(e, ScraperError)
    assert not isinstance(e, TransientError)


def test_history_unavailable():
    e = HistoryUnavailable("no history for OP-1")
    assert isinstance(e, ScraperError)
